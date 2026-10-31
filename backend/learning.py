"""Explicit desktop snapshot for the portable learning core. No AI calls."""
from fastapi import APIRouter
from backend.storage import database
from backend.schemas import Question
from backend.knowledge import get_report
from backend.concepts import concept_record
from backend.portable_catalog import initialize,track
import json

router=APIRouter(prefix='/api/learning',tags=['Portable learning'])

@router.get('/snapshot')
def snapshot():
    with database() as c:
        c.execute('BEGIN IMMEDIATE')
        initialize(c)
        inactive={r[0] for r in c.execute("SELECT question_id FROM study_publications WHERE status!='active'")}
        questions=[];concepts={}
        for row in c.execute('SELECT payload FROM questions'):
            q=Question.model_validate_json(row[0])
            a=get_report(c,'question',q.id)
            variant=c.execute('SELECT concept_id,revision FROM question_variants WHERE question_id=?',(q.id,)).fetchone()
            cid=variant['concept_id'] if variant else q.concept_id or 'legacy:'+q.id
            # Portable packages include source metadata, never filesystem paths.
            source={k:v for k,v in q.source.model_dump().items() if k in ['title','section','source_id','chunk_id','quote','sample']}
            questions.append({**q.model_dump(),'choices':list(q.answer.values()) if q.kind=='matching' else q.choices,'source':source,'concept_id':cid,
                'assessment':a,'eligible':a.get('status')=='deterministic_source_verified' and a.get('tier')!='B','deleted':q.id in inactive})
            if cid not in concepts:
                record=concept_record(cid,c) if variant else {}
                concepts[cid]={k:record[k] for k in ['concept_id','course','week','topic','title','explanation_zh','core_mechanism','difficulty','tags','english_terms','learning_objectives','assessment','revision'] if k in record}
                concepts[cid]['sources']=[{k:s.get(k) for k in ['source_id','chunk_id','locator','quote']} for s in record.get('sources',[])]
                if record.get('assessment',{}).get('tier')=='B':
                    # Earlier draft translations remain in SQLite for audit, but
                    # portable concept summaries use current supported facts.
                    from backend.study_bank import AtomicClaim,source_frame
                    supported=[dict(r) for r in c.execute("SELECT * FROM study_claims WHERE concept_id=? AND status='supported' ORDER BY created_at,id",(cid,))]
                    facts=[AtomicClaim.model_validate_json(r['payload']) for r in supported]
                    if facts:
                        concepts[cid]['explanation_zh']=source_frame(facts[0])
                        concepts[cid]['core_mechanism']='\n'.join(f.statement_en for f in facts[:2])
                        concepts[cid]['learning_objectives']=[f.category+': '+f.statement_en for f in facts]
                        refs=[]
                        for r,f in zip(supported,facts):
                            origin=c.execute('SELECT chunks FROM local_sources WHERE id=?',(r['source_id'],)).fetchone()
                            chunk=next(ch for ch in json.loads(origin[0]) if ch['id']==r['chunk_id'])
                            refs.append({'source_id':r['source_id'],'chunk_id':r['chunk_id'],'locator':chunk['locator'],'quote':f.evidence})
                        concepts[cid]['sources']=refs
                    else:
                        concepts[cid].update(deleted=True,explanation_zh='此概念目前沒有通過來源檢查的主張，僅保留歷史記錄。',core_mechanism='',learning_objectives=[],sources=[])
                if not record:concepts[cid]={'concept_id':cid,'title':q.topic,'course':q.course,'week':q.week,'topic':q.topic}
                concepts[cid]=track(c,'concept',cid,{**concepts[cid],'deleted':bool(record.get('deleted',False) or concepts[cid].get('deleted',False))})
            if concepts[cid].get('deleted'):
                questions[-1]['deleted']=True
            questions[-1]=track(c,'question',q.id,questions[-1])
        seen={q['id'] for q in questions}
        for old in c.execute("SELECT id,payload FROM portable_catalog WHERE entity='question'").fetchall():
            if old['id'] not in seen:
                value=json.loads(old['payload']);value['deleted']=True
                questions.append(track(c,'question',old['id'],value))
        for old in c.execute("SELECT id,payload FROM portable_catalog WHERE entity='concept'").fetchall():
            if old['id'] not in concepts:concepts[old['id']]=json.loads(old['payload'])
        events=[]
        for e in c.execute('SELECT * FROM concept_review_events WHERE attempt_id IS NULL OR attempt_id NOT IN (SELECT attempt_id FROM acceptance_attempts)'):
            events.append({'id':e['event_id'],'concept_id':e['concept_id'],'question_id':e['question_id'],'at':e['reviewed_at'],
                'rating':'incorrect' if e['observation']=='incorrect' else 'partial' if e['observation']=='ungraded' else 'observed',
                'eligible':False,'mode':e['answer_mode'],'latency_ms':e['response_latency_ms'],'hint':bool(e['hint_used'])})
        return {'schema':1,'questions':questions,'concepts':list(concepts.values()),'events':events}

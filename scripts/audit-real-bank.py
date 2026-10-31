"""Read actual SQLite and real Ollama cache; save honest acceptance evidence."""
import json
import sqlite3
from pathlib import Path
from collections import Counter
from backend.storage import database
from backend.study_bank import coverage,validate_question,AtomicClaim,Verdict
from backend.schemas import Question

out=Path('data/acceptance/meaningful-bank')
job=json.loads((out/'completed-bank.json').read_text(encoding='utf-8-sig'))
sid=job['params']['source_ids'][0]
baseline=sqlite3.connect(out/'before.sqlite3')
with database() as db:
 preservation={}
 for table in ['questions','attempts','concepts']:
  rows=baseline.execute('SELECT * FROM '+table).fetchall()
  existing=set(tuple(r) for r in db.execute('SELECT * FROM '+table))
  preservation[table]={'baseline':len(rows),'unchanged':sum(tuple(r) in existing for r in rows)}
  assert preservation[table]['unchanged']==len(rows),preservation
 sources={r['id']:json.loads(r['chunks']) for r in db.execute('SELECT id,chunks FROM local_sources')}
 qs=[dict(r) for r in db.execute("SELECT * FROM study_publications WHERE status='active'")]
 stages=dict(Counter(r[0] for r in db.execute('SELECT stage FROM study_stages')))
 checks=[]
 for r in qs:
  q=Question.model_validate_json(r['payload'])
  cr=db.execute('SELECT * FROM study_claims WHERE id=?',(r['claim_id'],)).fetchone()
  claim=AtomicClaim.model_validate_json(cr['payload'])
  chunk=next(c for c in sources[cr['source_id']] if c['id']==cr['chunk_id'])
  assessment=json.loads(db.execute("SELECT payload FROM authoring_checks WHERE entity_type='question' AND entity_id=?",(q.id,)).fetchone()[0])
  assert not validate_question(q,claim,chunk['text'],Verdict.model_validate(assessment['verdict']))
  changes=[('bad_causality',{'explanation_zh':'Resistance is determined by pressure difference.'}),
    ('unsupported_distractor',{'choices':[q.answer,'unpublished invented molecule',next(c for c in q.choices if c!=q.answer)]})] if q.kind=='multiple_choice' else []
  for label,change in changes:
   rejected=validate_question(q.model_copy(update=change),claim,chunk['text'],Verdict.model_validate(assessment['verdict']))
   assert rejected
   checks.append({'real_question_id':q.id,'adversary':label,'blocked_by':rejected})
 result=coverage([sid],[],job['output'].get('processed',[]),job['output'].get('unprocessed',[]),job['output'].get('quarantine',[]),[r['question_id'] for r in qs])
 result.update(baseline_preservation=preservation,real_cached_stages=stages,adversarial_real_questions=checks,
   materials_extracted=db.execute('SELECT COUNT(*) FROM local_sources').fetchone()[0],
   active_course_questions=db.execute("SELECT COUNT(*) FROM questions WHERE json_extract(payload,'$.source.sample')=0 AND id NOT IN (SELECT question_id FROM study_publications WHERE status!='active')").fetchone()[0],
   all_concepts=db.execute('SELECT COUNT(*) FROM concepts').fetchone()[0],
   provisional_not_medically_verified=True)
 (out/'final-source-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:result[k] for k in ['atomic_claims','supported_claims','meaningful_concepts','represented_concepts','concepts_with_distinct_variants','questions_per_mode','baseline_preservation','materials_extracted','active_course_questions']}))

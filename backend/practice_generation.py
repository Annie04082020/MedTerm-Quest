"""Finite, replayable source templates; never a medical reasoning authority."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import json
import re
import unicodedata
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.knowledge import compact, digest, extract_claims, report, save_report
from backend.schemas import Question, Source
from backend.storage import database

router = APIRouter(prefix='/api/knowledge', tags=['Source practice batches'])
POLICY = 'practice-v1'
# A single literal attribution, not a medical definition inferred by a model.
DEFINITION = re.compile(r'(?<![A-Za-z])(?P<term>[A-Z][a-z]+(?: [a-z]+){0,3}) is (?P<definition>(?:the |a |an |plasma )[^.!?;\n]{8,350})[.]')
RISK = re.compile(r'\b(?:patient|diagnos\w*|treat\w*|dose|caus\w*|determin\w*|not|never|except|increase\w*|decrease\w*|due to)\b', re.I)
RATIO = re.compile(r'(?<![A-Za-z0-9])(?P<lhs>[A-Za-z]+)\s*=\s*(?P<num>∆?[A-Za-z]+)\s*/\s*(?P<den>∆?[A-Za-z]+)(?![ \t]*[A-Za-z0-9+*/^=\-])')
ANAPHORA = re.compile(r'^(?:The|A|An|It|This|That|These|Those)\b')


def normalized(text):
    return re.sub(r'[^a-z0-9∆]+', '', unicodedata.normalize('NFKC', text).casefold())


def math_text(text):
    return unicodedata.normalize('NFKC', text).replace('Δ', '∆').replace('∕', '/')


def new_claim(source, chunk, quote, kind, **fields):
    cid = 'claim-' + digest(source['id'] + ':' + chunk['id'] + ':' + quote)[:32]
    return {'claim_id':cid,'source_id':source['id'],'chunk_id':chunk['id'],'locator':chunk['locator'],
            'source_hash':digest(chunk['text']),'text':quote,'evidence':quote,'support':'direct_extraction',
            'structured_kind':kind,'assessment':report('deterministic_source_verified',[
                {'method':'deterministic','code':'literal_'+kind,'passed':True}]),**fields}


def structured_claims(source):
    """Extend the existing registry with individually reconstructible structures."""
    chunks = source['chunks']
    extract_claims(source, chunks)
    accepted, skipped = [], []
    for chunk in chunks:
        text = compact(chunk['text'])
        # A header before a definition is not included in the evidence. Preserve
        # the full quoted sentence while splitting an explicitly attached unit.
        for m in DEFINITION.finditer(text):
            term, definition = m['term'], m['definition']
            if RISK.search(m[0]) or ANAPHORA.search(term):
                continue
            definition = re.split(r',? and (?:it )?is measured in ',definition)[0]
            accepted.append(new_claim(source,chunk,m[0],'definition',term=term,definition=definition,unit=None))
            unit_match=re.search(r'(?:it )?is measured in ([A-Za-z/]+)',m[0])
            if unit_match:
                accepted[-1]['unit']=unit_match[1]
        # Character map lets formula normalization find the *original* quotation.
        converted, positions = '', []
        for index,ch in enumerate(chunk['text']):
            piece=math_text(ch);converted+=piece;positions.extend([index]*len(piece))
        for m in RATIO.finditer(converted):
            quote=chunk['text'][positions[m.start()]:positions[m.end()-1]+1]
            parts=[m[x] for x in ('lhs','num','den')]
            if len(set(parts))!=3:
                skipped.append({'locator':chunk['locator'],'reason':'formula_variables_not_distinct','evidence':quote})
                continue
            accepted.append(new_claim(source,chunk,quote,'ratio',lhs=parts[0],numerator=parts[1],denominator=parts[2],
                                      formula='='.join([parts[0],parts[1]+'/'+parts[2]])))
    unique={}
    for c in accepted:
        if c['claim_id'] in unique:
            skipped.append({'claim_id':c['claim_id'],'locator':c['locator'],'reason':'duplicate_structure'})
        unique[c['claim_id']]=c
    accepted=list(unique.values())
    # Different literal definitions for the same term are ambiguous even if both
    # occur in the lecture. Conservatively hold both; no semantic synonym guess.
    groups=defaultdict(set)
    for c in accepted:
        if c['structured_kind']=='definition':groups[normalized(c['term'])].add(normalized(c['definition']))
    conflicts={term for term,definitions in groups.items() if len(definitions)>1}
    expressions=defaultdict(set)
    for chunk in chunks:
        for m in re.finditer(r'([A-Za-z]+)\s*=\s*(∆?[A-Za-z]+(?:\s*[-+*/]\s*∆?[A-Za-z]+)+)',math_text(chunk['text'])):
            expressions[m[1]].add(re.sub(r'\s+','',m[2]))
    seen={}
    for c in accepted:
        key=(c['structured_kind'],normalized(c.get('term',c.get('formula',''))))
        if c['structured_kind']=='ratio' and len(expressions[c['lhs']])>1:
            c['assessment']=report('needs_expert_review',[{'method':'deterministic','code':'incompatible_formula_structures','passed':False}])
            skipped.append({'claim_id':c['claim_id'],'locator':c['locator'],'reason':'incompatible_formula_structures'})
        elif key[1] in conflicts:
            c['assessment']=report('needs_expert_review',[{'method':'heuristic','code':'conflicting_definitions','passed':False}])
            skipped.append({'claim_id':c['claim_id'],'locator':c['locator'],'reason':'conflicting_definitions'})
        elif key in seen:
            skipped.append({'claim_id':c['claim_id'],'locator':c['locator'],'reason':'duplicate_structure','same_as':seen[key]})
        else:seen[key]=c['claim_id']
    with database() as conn:
        stamp=datetime.now(timezone.utc).isoformat()
        for c in accepted:
            conn.execute('INSERT OR REPLACE INTO knowledge_claims VALUES (?,?,?,?,?,?,?)',
                (c['claim_id'],source['id'],c['chunk_id'],c['locator'],c['source_hash'],json.dumps(c,ensure_ascii=False),stamp))
        all_claims=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM knowledge_claims WHERE source_id=?',(source['id'],))]
    eligible=[c for c in accepted if c['assessment']['status']=='deterministic_source_verified' and seen.get((c['structured_kind'],normalized(c.get('term',c.get('formula','')))))==c['claim_id']]
    accepted_ids={c['claim_id'] for c in eligible}
    for c in all_claims:
        if c['claim_id'] not in accepted_ids and not any(s.get('claim_id')==c['claim_id'] for s in skipped):
            skipped.append({'claim_id':c['claim_id'],'locator':c['locator'],'reason':'outside_supported_atomic_grammar'})
    return eligible, all_claims, skipped


def definition_pool(claim, claims):
    """Unique literal attributions, plus conservative overlap filtering."""
    pool=[claim]
    for other in claims:
        if other['claim_id']==claim['claim_id']:continue
        if any(ambiguous_pair(other,c) for c in pool):continue
        pool.append(other)
        if len(pool)==4:break
    return pool


def ambiguous_pair(a,b):
    for field in ('term','definition'):
        x,y=normalized(a[field]),normalized(b[field])
        if not x or not y or x in y or y in x:return True
    # Semantic similarity is not provable from text overlap. Conservative filter;
    # questions ask exact lecture attribution, never exclusive biological truth.
    x,y=set(a['definition'].lower().split()),set(b['definition'].lower().split())
    return len(x&y)/max(1,len(x|y))>.65


def ratio_value(numerator, denominator):
    n,d=Fraction(numerator),Fraction(denominator)
    if n<=0 or d<=0:raise ValueError('ratio domain requires positive nonzero quantities')
    return n/d


def grade_numeric(answer, proof):
    """Bounded numeric parsing, never eval; no ungrounded unit conversions."""
    if proof.get('template')!='ratio_calculation' or not isinstance(answer,str):return None
    m=re.fullmatch(r'\s*([+-]?\d{1,16}(?:\.\d{1,12})?(?:/\d{1,16})?)\s*(milliliter/minute)?\s*',answer)
    if not m:return 'incorrect'
    try:correct=Fraction(m[1])==Fraction(proof['result'])
    except (ValueError,ZeroDivisionError):correct=False
    return 'correct' if correct else 'incorrect'


def validate_claim(claim,source):
    chunk=next((c for c in source['chunks'] if c['id']==claim['chunk_id']),None)
    if not chunk or digest(chunk['text'])!=claim['source_hash'] or compact(claim['evidence']) not in compact(chunk['text']):
        raise ValueError('stale_or_invalid_evidence')
    if claim['structured_kind']=='definition':
        match=DEFINITION.fullmatch(compact(claim['evidence']))
        if not match or RISK.search(match[0]) or ANAPHORA.search(match['term']) or match['term']!=claim['term']:
            raise ValueError('definition_not_reconstructible')
        definition=re.split(r',? and (?:it )?is measured in ',match['definition'])[0]
        if definition!=claim['definition']:raise ValueError('definition_not_reconstructible')
        unit=re.search(r'(?:it )?is measured in ([A-Za-z/]+)',match[0])
        if claim.get('unit')!=(unit[1] if unit else None):raise ValueError('unit_not_reconstructible')
    else:
        match=RATIO.fullmatch(math_text(claim['evidence']).strip())
        if not match or any(match[k]!=claim[v] for k,v in [('lhs','lhs'),('num','numerator'),('den','denominator')]):
            raise ValueError('formula_not_reconstructible')


def concept_id(claim):
    if claim['structured_kind']=='definition':
        # Same full-sentence claims retain the concept ID from extractive-v1.
        return 'concept-extractive-'+digest(claim['claim_id']+'extractive-v1')[:24]
    return 'concept-ratio-'+digest(claim['scope']+claim['formula'])[:24]


def base_question(source,claim,identity,kind,aspect,prompt,zh,answer,explanation,**extras):
    return Question(id='practice-'+digest(POLICY+identity)[:24],week=source['week'],topic=source['topic'],
        course=source.get('course','Human Anatomy and Physiology'),kind=kind,difficulty='Foundation',
        concept_id=claim['concept_id'],variant_aspect=aspect,prompt=prompt,prompt_zh=zh,answer=answer,
        explanation_zh=explanation,terms=[claim.get('term',claim.get('formula',''))],
        source=Source(title=source['title'],section=claim['locator'],sample=False,source_id=source['id'],
                      chunk_id=claim['chunk_id'],quote=claim['evidence']),**extras)


def candidates(source,claims,skipped):
    definitions=[c for c in claims if c['structured_kind']=='definition']
    results=[]
    for c in claims:
        c['scope']=json.dumps([source.get('course'),source['week'],source['topic']],ensure_ascii=False)
        c['concept_id']=concept_id(c)
    # Definition MCQs use exact lecture attribution in both directions.
    for c in definitions:
        pool=definition_pool(c,definitions)
        if len(pool)<3:
            skipped.append({'claim_id':c['claim_id'],'reason':'insufficient_unambiguous_distractors'});continue
        for reverse in (False,True):
            field='definition' if reverse else 'term'
            prompt=('Which description is explicitly paired with '+c['term']+' in this lecture?' if reverse else
                    'Which term is explicitly paired with this lecture description: "'+c['definition']+'"?')
            zh=('依講義，'+c['term']+' 對應哪個原文描述？' if reverse else '依講義的明確配對，選出此原文描述對應的英文術語。')
            explanation='講義 '+c['locator']+' 原文：「'+c['evidence']+'」本題只辨識原文配對，不主張其他術語在所有情況下皆不適用。'
            q=base_question(source,c,c['concept_id']+('reverse-mcq' if reverse else 'term-mcq'),'multiple_choice',
                            'comparison' if reverse else 'terminology',prompt,zh,c[field],explanation,
                            choices=sorted([p[field] for p in pool],key=digest))
            results.append((q,pool,{'template':'definition_reverse_mcq' if reverse else 'definition_mcq','target':c['claim_id']}))
    # One matching set per page, not one superficially permuted copy per term.
    by_chunk=defaultdict(list)
    for c in definitions:by_chunk[c['chunk_id']].append(c)
    for group in by_chunk.values():
        pool=definition_pool(group[0],group)
        if len(pool)<2:continue
        anchor=dict(pool[0]);anchor['concept_id']='concept-terms-'+digest(source['id']+':'+':'.join(sorted(c['claim_id'] for c in pool)))[:24]
        anchor['members']=[c['concept_id'] for c in pool]
        for reverse in (False,True):
            answer={str(i+1):c['definition' if reverse else 'term'] for i,c in enumerate(pool)}
            pairs=[{'id':str(i+1),'definition':c['term' if reverse else 'definition']} for i,c in enumerate(pool)]
            explanation='依講義 '+anchor['locator']+' 的原文明確配對：'+'；'.join(c['evidence'] for c in pool)
            q=base_question(source,anchor,anchor['concept_id']+str(reverse),'matching','terminology' if reverse else 'definition',
                'Match lecture terms to their exact descriptions.' if reverse else 'Match lecture descriptions to their exact terms.',
                '將術語配回講義原文描述。' if reverse else '將講義原文描述配回英文術語。',answer,explanation,pairs=pairs)
            results.append((q,[anchor]+pool,{'template':'matching_reverse' if reverse else 'matching','target':anchor['claim_id']}))
    for c in [c for c in claims if c['structured_kind']=='ratio']:
        lhs,n,d=c['lhs'],c['numerator'],c['denominator']
        # This asserts only algebra on stated positive variables, never clinical
        # causality or what physiologically determines resistance.
        explanation=f'依 {c["locator"]} 的 {c["formula"]}，在 {n}>0、{d}>0 且 {n} 固定時，{d} 加倍，{lhs} 的新／舊值為 1/2。這是指定條件的代數推導，非臨床因果結論。'
        q=base_question(source,c,c['concept_id']+'direction','multiple_choice','mechanism',
            f'Using {c["formula"]}, assume {n}>0 and {d}>0. Hold {n} fixed and double {d}. What is new {lhs} / old {lhs}?',
            f'依公式，在正值且 {n} 固定時，{d} 加倍，{lhs} 變成原來的幾倍？','1/2',explanation,choices=['2','1/2','1','4'])
        results.append((q,[c],{'template':'ratio_direction','scale_n':1,'scale_d':2,'result':'1/2'}))
        q=base_question(source,c,c['concept_id']+'correction','true_false','application',
            f'Using {c["formula"]} with positive variables: if {d} is fixed and {n} doubles, {lhs} stays unchanged.',
            f'正值條件下，固定 {d} 並將 {n} 加倍，{lhs} 保持不變。判斷並訂正。',
            f'False: {lhs} doubles',f'依 {c["locator"]} 的 {c["formula"]}，新／舊值 = 2/1 = 2；因此 {lhs} 加倍。這是公式練習，未加入醫學機制。',
            accepted_answers=[f'False: {lhs} doubles',f'False: {lhs} 加倍','False: 加倍','False: 變成兩倍'])
        results.append((q,[c],{'template':'ratio_correction','scale_n':2,'scale_d':1,'result':'2'}))
        # Numeric exercises require units explicitly present in the same lecture
        # chunk. Resistance's unit is derived dimensionally, not invented data.
        same=[x for x in definitions if x['chunk_id']==c['chunk_id']]
        units={x['term']:x.get('unit') for x in same}
        if c['formula']=='F=∆P/R' and units.get('Pressure')=='mmHg' and units.get('Flow')=='milliliter/minute':
            explanation=f'依 {c["locator"]} 的 F=∆P/R，代入本題假設值 12/3=4 milliliter/minute。R 的單位由 mmHg ÷ (milliliter/minute) 配平；12 與 3 是練習給定值，非講義實測數據。'
            q=base_question(source,c,c['concept_id']+'calculation','short_answer','quantitative',
                'Practice inputs (not measured lecture data): ∆P=12 mmHg, R=3 mmHg/(milliliter/minute). Using F=∆P/R, enter F in milliliter/minute.',
                '使用題目假設值與講義公式，算出 F；請填數值或附上指定單位。','4',explanation,
                accepted_answers=['4 milliliter/minute'],rubric=['F=12/3=4 milliliter/minute'])
            results.append((q,[c]+same,{'template':'ratio_calculation','n':12,'d':3,'result':'4','units':units}))
        else:skipped.append({'claim_id':c['claim_id'],'reason':'numeric_exercise_requires_explicit_supported_units'})
    # Round-robin modes so a small limit isn't consumed by only MCQs.
    grouped=defaultdict(list)
    for candidate in results:grouped[candidate[0].kind].append(candidate)
    grouped['multiple_choice'].sort(key=lambda item:0 if item[2]['template'].startswith('ratio') else 1)
    ordered=[]
    while any(grouped.values()):
        for kind in ('matching','multiple_choice','short_answer','true_false'):
            if grouped[kind]:ordered.append(grouped[kind].pop(0))
    return ordered


def validate_candidate(candidate,source):
    """Reconstruct all teaching fields, including distractors and explanations."""
    q,claims,proof=candidate
    for c in claims:validate_claim(c,source)
    # Rebuild from trusted structures, not caller-supplied proof results.
    originals=[dict(c) for c in claims if not c.get('members')]
    if q.kind=='multiple_choice':
        if len({normalized(s) for s in q.choices})!=len(q.choices) or q.choices.count(q.answer)!=1:raise ValueError('ambiguous_choices')
    template=proof['template']
    if template.startswith('definition') or template.startswith('matching'):
        if any(ambiguous_pair(a,b) for i,a in enumerate(originals) for b in originals[i+1:]):raise ValueError('ambiguous_attribution_pool')
    if template.startswith('ratio'):
        if template=='ratio_calculation':
            if proof.get('units')!={'Pressure':'mmHg','Flow':'milliliter/minute','Resistance':None}:
                raise ValueError('unsupported_units')
            # Dimensions: R = pressure/flow. For F=pressure/R, the
            # pressure dimension cancels and volume/time remains.
            pressure=(1,0,0);flow=(0,1,-1)
            resistance=tuple(p-f for p,f in zip(pressure,flow))
            if tuple(p-r for p,r in zip(pressure,resistance))!=flow:raise ValueError('unit_dimension_mismatch')
            expected=ratio_value(proof['n'],proof['d'])
        else:expected=ratio_value(proof['scale_n'],proof['scale_d'])
        if Fraction(proof['result'])!=expected:raise ValueError('incorrect_ratio_result')
    # Closed template equality catches wrong answers, polarity, altered units,
    # signs, explanations, and injected unsupported medical prose.
    rebuilt=candidates(source,originals,[])
    expected=next((item for item in rebuilt if item[0].id==q.id),None)
    if expected is None or expected[0].model_dump()!=q.model_dump() or expected[2]!=proof:raise ValueError('closed_template_mismatch')
    from backend.local_processing import validate_activity
    validate_activity(q.model_dump())


def ensure_concept(conn,q,claims):
    stamp=datetime.now(timezone.utc).isoformat();anchor=claims[0]
    title=' / '.join(dict.fromkeys(c['term'] for c in claims if c.get('term'))) if anchor.get('members') else anchor.get('term',anchor.get('formula','Source terms'))
    conn.execute('''INSERT OR IGNORE INTO concepts(concept_id,course,week,topic,title,explanation_zh,core_mechanism,difficulty,status,created_at,updated_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(q.concept_id,q.course,q.week,q.topic,title,
      q.explanation_zh,'只依原文結構及指定條件推導，非獨立醫學驗證。','Foundation','approved',stamp,stamp))
    conn.execute('INSERT OR IGNORE INTO concept_progress(concept_id) VALUES (?)',(q.concept_id,))
    for c in claims:
        conn.execute('INSERT OR IGNORE INTO concept_sources VALUES (?,?,?,?,?,?)',(q.concept_id,c['source_id'],c['chunk_id'],c['locator'],c['evidence'],json.dumps({'title':q.source.title},ensure_ascii=False)))
        conn.execute('INSERT OR IGNORE INTO concept_terms VALUES (?,?)',(q.concept_id,c.get('term',c.get('formula','Source terms'))))
    if anchor.get('members'):
        for c in claims[1:]:
            ensure_concept(conn,q.model_copy(update={'concept_id':c['concept_id'],'explanation_zh':'講義原文：「'+c['evidence']+'」'}),[c])
            conn.execute('INSERT OR IGNORE INTO practice_concept_members VALUES (?,?)',(q.concept_id,c['concept_id']))


class BatchRequest(BaseModel):
    source_id:str=Field(min_length=1,max_length=100)
    max_questions:int=Field(default=16,ge=1,le=60)
    use_ollama:bool=False
    model:str=Field(default='qwen3:4b',max_length=200)
    device:Literal['auto','cpu']='auto'
    allow_cpu:bool=True
    allow_smaller:bool=False


class ExtractionHints(BaseModel):
    evidence:list[str]=Field(max_length=12)


@router.get('/batches')
def batches(source_id:str):
    from backend.local_processing import public_job
    with database() as conn:
        rows=conn.execute("SELECT * FROM local_jobs WHERE kind='practice_batch' ORDER BY created_at DESC LIMIT 100").fetchall()
        return [public_job(r) for r in rows if json.loads(r['params']).get('source_id')==source_id][:5]


@router.post('/batch',status_code=202)
def enqueue_batch(payload:BatchRequest):
    from backend.local_processing import source_record,create_job
    source_record(payload.source_id)
    if payload.use_ollama:
        from backend.ollama_local import OllamaLocal,LocalAIError
        try:OllamaLocal().check_model(payload.model)
        except LocalAIError as exc:raise HTTPException(503,str(exc)) from exc
    return create_job('practice_batch',payload.model_dump())


def process_batch(engine,job_id,params):
    from backend.local_processing import source_record,update_job
    from backend.concepts import register_variant
    source=source_record(params['source_id']);engine.check_cancel(job_id)
    update_job(job_id,stage='擷取整份講義的原子結構',progress=5)
    claims,all_claims,skipped=structured_claims(source)
    hints=[]
    if params.get('use_ollama'):
        # Small batches; model suggestions are evidence pointers only. They do
        # not enlarge the accepted grammar or supply publishable medical prose.
        relevant={c['chunk_id'] for c in claims}
        for chunk in [c for c in source['chunks'] if c['id'] in relevant][:4]:
            engine.check_cancel(job_id)
            content,model=engine.llm(job_id,params,'Extract at most 4 short verbatim definition or ratio-formula quotations. No interpretation. JSON only. /no_think\nSOURCE='+json.dumps(chunk['text'],ensure_ascii=False),ExtractionHints)
            hints.extend({'evidence':e,'locator':chunk['locator'],'quote_valid':compact(e) in compact(chunk['text']),
                          'matched_verified_claim':any(compact(e)==compact(c['evidence']) for c in claims)} for e in content.evidence)
    skipped_families=[]
    pending=candidates(source,claims,skipped_families)
    published=[];duplicates=[];blocked=[];modes=Counter()
    for i,candidate in enumerate(pending):
        engine.check_cancel(job_id)
        q,evidence,proof=candidate
        try:
            validate_candidate(candidate,source)
            with database() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if conn.execute('SELECT 1 FROM questions WHERE id=?',(q.id,)).fetchone():
                    duplicates.append(q.id);continue
                if len(published)>=params['max_questions']:
                    blocked.append({'question_id':q.id,'reason':'configured_limit'});continue
                # Verify source snapshots again under the write lock.
                fresh=source_record(source['id'])
                for c in evidence:validate_claim(c,fresh)
                ensure_concept(conn,q,evidence)
                conn.execute('INSERT INTO questions VALUES (?,?)',(q.id,q.model_dump_json()))
                register_variant(conn,q)
                for cid in {q.concept_id,*evidence[0].get('members',[])}:
                    conn.execute('INSERT OR IGNORE INTO question_concept_members VALUES (?,?)',(q.id,cid))
                conn.execute('INSERT INTO knowledge_question_links VALUES (?,?,?)',(q.id,evidence[0]['claim_id'],POLICY))
                assessment=report('deterministic_source_verified',[
                    {'method':'deterministic','code':code,'passed':True} for code in
                    ['source_hash_and_quotes','reconstructed_closed_template','single_literal_answer','ratio_domain_and_units' if proof['template'].startswith('ratio') else 'distinct_literal_attributions']],
                    [{'field':field,'claim_id':c['claim_id'],'source_id':c['source_id'],'chunk_id':c['chunk_id'],'locator':c['locator'],'evidence':c['evidence']}
                     for c in evidence for field in ['answer','explanation_zh','choices' if q.kind=='multiple_choice' else 'prompt']])
                assessment['construction_proof']=proof
                save_report(conn,'question',q.id,assessment);save_report(conn,'concept',q.concept_id,assessment)
            published.append(q.id);modes[q.kind]+=1
        except (ValueError,HTTPException) as exc:
            blocked.append({'question_id':q.id,'reason':str(exc)})
        update_job(job_id,stage=f'驗證並發布 {i+1}/{len(pending)}',progress=10+int(85*(i+1)/max(1,len(pending))))
    return {'source_id':source['id'],'policy':POLICY,'source_claims_extracted':len(all_claims),'accepted_claims':len(claims),
            'rejected_or_unsupported_claims':len(all_claims)-len(claims),
            'skipped_claims':skipped,'skipped_question_families':skipped_families,
            'questions_per_mode':dict(modes),'auto_published':published,'duplicates_prevented':duplicates,
            'blocked_questions':blocked,'ollama_hints':hints,'medically_verified':False,
            'message':f'已自動發布 {len(published)} 題；來源檢查不代表獨立醫學驗證。'}

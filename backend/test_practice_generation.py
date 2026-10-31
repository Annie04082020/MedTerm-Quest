import copy
import json
import time
from fractions import Fraction

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.practice_generation import structured_claims,candidates,validate_candidate,ratio_value
from backend.storage import database

TEXT='''Pressure is the force exerted by the blood and is measured in mmHg (millimeters of mercury).
Flow is the volume moved per unit time, and it is measured in milliliter/minute.
Resistance is the measure of the friction that impedes flow.
F = ∆P/R
If you increase the resistance, you decrease flow if pressure stays the same.'''


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/'practice.sqlite3'))
    with TestClient(app) as c:yield c


def source(text=TEXT,extra=True):
    chunks=[{'id':'c1','locator':'Page 16','text':text}]
    if extra:chunks.append({'id':'c2','locator':'00:04:00–00:04:10','text':'Compliance = ∆Volume / ∆Pressure'})
    source={'id':'lecture','title':'Circulation','week':4,'topic':'Circulation','course':'A&P','filename':'lecture.pdf','chunks':chunks}
    with database() as conn:
        conn.execute('INSERT INTO local_sources(id,title,week,topic,filename,chunks,created_at,course) VALUES (?,?,?,?,?,?,?,?)',
                     ('lecture','Circulation',4,'Circulation','lecture.pdf',json.dumps(chunks),'now','A&P'))
    return source


def wait(client,jid):
    for _ in range(500):
        job=client.get('/api/local/jobs/'+jid).json()
        if job['status'] in ('completed','failed','cancelled'):break
        time.sleep(.025)
    assert job['status']=='completed',job
    return job['output']


def test_batch_mixes_modes_stable_concepts_evidence_and_idempotent_progress(client,monkeypatch):
    from backend.ollama_local import OllamaLocal
    def no_llm(*args,**kwargs):pytest.fail('Default deterministic batches must not call Ollama')
    monkeypatch.setattr(OllamaLocal,'generate',no_llm)
    source()
    response=client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':30})
    assert response.status_code==202
    result=wait(client,response.json()['id'])
    assert result['accepted_claims']==5
    assert result['source_claims_extracted']==result['accepted_claims']+result['rejected_or_unsupported_claims']
    assert any(x['reason']=='numeric_exercise_requires_explicit_supported_units' for x in result['skipped_question_families'])
    assert not any(x['reason']=='numeric_exercise_requires_explicit_supported_units' for x in result['skipped_claims'])
    assert result['questions_per_mode']=={'matching':2,'multiple_choice':8,'short_answer':1,'true_false':2}
    assert not result['blocked_questions'],result
    assert not result['medically_verified']
    with database() as conn:
        rows=[json.loads(r[0]) for r in conn.execute("SELECT payload FROM questions WHERE id LIKE 'practice-%'")]
    formula=[q for q in rows if q['source']['quote'].startswith('F =')]
    assert len({q['concept_id'] for q in formula})==1
    assert {q['kind'] for q in formula}=={'multiple_choice','true_false','short_answer'}
    q=next(q for q in formula if q['kind']=='short_answer')
    assert client.post('/api/attempts',json={'question_id':q['id'],'answer':'4'}).json()['status']=='correct'
    again=wait(client,client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':30}).json()['id'])
    assert not again['auto_published'] and len(again['duplicates_prevented'])==13
    assert client.get('/api/progress').json()['attempts']==1
    assert client.get('/api/knowledge/batches?source_id=lecture').json()[0]['output']['duplicates_prevented']
    public=next(x for x in client.get('/api/questions').json() if x['id']==q['id'])
    assert all(b['evidence'] and b['chunk_id'] and b['locator'] for b in public['assessment']['bindings'])
    matching=next(x for x in client.get('/api/questions').json() if x['kind']=='matching' and x['id'].startswith('practice-'))
    term_mcq=next(x for x in rows if x['kind']=='multiple_choice' and x['answer']=='Pressure')
    assert term_mcq['concept_id'] in matching['related_concept_ids']


def test_limit_continuation_does_not_duplicate_or_erase_progress(client):
    source()
    first=wait(client,client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':4}).json()['id'])
    assert len(first['auto_published'])==4
    assert first['blocked_questions'] and all(x['reason']=='configured_limit' for x in first['blocked_questions'])
    second=wait(client,client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':4}).json()['id'])
    assert len(second['auto_published'])==4
    assert not set(first['auto_published'])&set(second['auto_published'])
    assert len(second['duplicates_prevented'])==4


def test_closed_templates_reject_tampered_answers_units_signs_explanations_and_distractors(client):
    s=source();claims,_,skips=structured_claims(s);items=candidates(s,claims,skips)
    for item in items:validate_candidate(item,s)
    mcq=next(x for x in items if x[2]['template']=='ratio_direction')
    for change in [{'answer':'2'},{'choices':['1/2','1/2','2','4']},{'explanation_zh':'阻力由壓力差決定。'},
                   {'prompt':mcq[0].prompt.replace('∆P/R','∆P*R')}]:
        candidate=copy.deepcopy(mcq);candidate=(candidate[0].model_copy(update=change),candidate[1],candidate[2])
        with pytest.raises(ValueError):validate_candidate(candidate,s)
    numeric=copy.deepcopy(next(x for x in items if x[2]['template']=='ratio_calculation'))
    numeric[2]['units']['Flow']='L/min'
    with pytest.raises(ValueError,match='unit_not_reconstructible|unsupported_units'):validate_candidate(numeric,s)
    forged=copy.deepcopy(mcq);forged[2].update(scale_n=3,scale_d=1,result='3')
    with pytest.raises(ValueError,match='closed_template_mismatch'):validate_candidate(forged,s)


def test_conflicts_aliases_and_unsupported_clinical_content_are_skipped(client):
    text=TEXT+'\nFlow is the volume moved per second.\nThe exception to this is the pulmonary arteries.\nResistance is determined by pressure difference.'
    s=source(text);claims,all_claims,skips=structured_claims(s)
    assert not any(c.get('term') in ('Flow','The exception to this') for c in claims)
    assert any(s['reason']=='conflicting_definitions' for s in skips)
    assert any(s['reason']=='outside_supported_atomic_grammar' for s in skips)
    pool=[c for c in claims if c['structured_kind']=='definition']
    if pool:
        from backend.practice_generation import ambiguous_pair
        assert ambiguous_pair(pool[0],{**pool[0],'term':'Blood '+pool[0]['term']})
    for q,_,_ in candidates(s,claims,skips):
        assert 'determined by pressure difference' not in q.explanation_zh


def test_formula_conflicts_zero_negative_domain_and_changed_sources_are_rejected(client):
    s=source(TEXT+'\nF = ∆P*R');claims,_,skips=structured_claims(s)
    assert not any(c.get('lhs')=='F' for c in claims)
    assert any(s['reason']=='incompatible_formula_structures' for s in skips)
    assert ratio_value(1,2)==Fraction(1,2)
    for n,d in [(0,2),(2,0),(-1,2),(1,-2)]:
        with pytest.raises(ValueError):ratio_value(n,d)
    items=candidates(s,claims,skips)
    assert items
    changed=copy.deepcopy(s);changed['chunks'][0]['text']+=' modified'
    with pytest.raises(ValueError,match='stale_or_invalid_evidence'):validate_candidate(items[0],changed)


def test_invalid_request_and_same_source_duplicate_formula(client):
    s=source(TEXT+'\nF = ∆P/R')
    claims,_,skips=structured_claims(s)
    assert len([c for c in claims if c.get('lhs')=='F'])==1
    assert any(s['reason']=='duplicate_structure' for s in skips)
    assert client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':0}).status_code==422
    assert client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':61}).status_code==422


def test_ollama_evidence_hints_cannot_expand_publication_grammar(client,monkeypatch):
    from backend.local_processing import ProcessingQueue
    from backend.ollama_local import OllamaLocal
    s=source()
    monkeypatch.setattr(OllamaLocal,'check_model',lambda *a,**k:{'name':'qwen3:4b'})
    def hint(self,jid,params,prompt,schema):
        return schema.model_validate({'evidence':['Resistance is determined by pressure difference.','F = ∆P/R']}),'test-local'
    monkeypatch.setattr(ProcessingQueue,'llm',hint)
    result=wait(client,client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':30,'use_ollama':True}).json()['id'])
    assert result['ollama_hints']
    assert any(not h['quote_valid'] for h in result['ollama_hints'])
    assert all(not h['matched_verified_claim'] for h in result['ollama_hints'] if 'determined' in h['evidence'])
    with database() as conn:
        assert all('determined by' not in json.loads(r[0])['explanation_zh'] for r in conn.execute("SELECT payload FROM questions WHERE id LIKE 'practice-%'"))


@pytest.mark.parametrize('formula',['F = ∆P/R²','F = ∆P/R^2','F = ∆P/R*X','F = ∆P/R + X','F = -∆P/R'])
def test_unsupported_expression_cannot_be_truncated_into_a_ratio(client,formula):
    s=source(formula,extra=False)
    claims,_,skips=structured_claims(s)
    assert not any(c['structured_kind']=='ratio' for c in claims)
    assert not candidates(s,claims,skips)


def test_ratio_directions_hold_for_multiple_positive_rational_inputs():
    for n in [Fraction(1,7),Fraction(1),Fraction(12),Fraction(1000)]:
        for d in [Fraction(1,3),Fraction(2),Fraction(31)]:
            original=n/d
            assert (n/(2*d))/original==Fraction(1,2)
            assert ((2*n)/d)/original==2
            assert ratio_value(n,d)==original


@pytest.mark.parametrize('answer,expected',[('4.0','correct'),('8/2','correct'),('4 milliliter/minute','correct'),
    ('-4','incorrect'),('4 L/min','incorrect'),('4/0','incorrect'),('4+0','incorrect')])
def test_numeric_grading_accepts_equivalence_without_wrong_units_or_eval(client,answer,expected):
    source()
    output=wait(client,client.post('/api/knowledge/batch',json={'source_id':'lecture','max_questions':4}).json()['id'])
    with database() as conn:
        q=next(json.loads(r[0]) for r in conn.execute("SELECT payload FROM questions WHERE id LIKE 'practice-%'") if json.loads(r[0])['kind']=='short_answer')
    response=client.post('/api/attempts',json={'question_id':q['id'],'answer':answer})
    assert response.status_code==200 and response.json()['status']==expected

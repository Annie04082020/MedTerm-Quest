"""Source policy tests use isolated data; they are not real-model acceptance."""
import json
import time

from fastapi.testclient import TestClient
import pytest

from backend.main import app
from backend.knowledge import check_statements, extract_claims, VERSION
from backend.storage import database


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH', str(tmp_path / 'knowledge.sqlite3'))
    with TestClient(app) as client:
        yield client


def source(text='Resistance is the measure of the friction that impedes flow.'):
    with database() as conn:
        conn.execute('INSERT INTO local_sources(id,title,week,topic,filename,chunks,created_at,course) VALUES (?,?,?,?,?,?,?,?)',
                     ('s1','Lecture',4,'Circulation','lecture.pdf',json.dumps([{'id':'c1','locator':'Page 16','text':text}]),'now','A&P'))
    return {'id':'s1','title':'Lecture','week':4,'topic':'Circulation','filename':'lecture.pdf','course':'A&P',
            'chunks':[{'id':'c1','locator':'Page 16','text':text}]}


def test_resistance_determinant_is_rejected_despite_real_quote_and_json():
    quote='Resistance is the measure of the friction that impedes flow.'
    for claim in ['Resistance is determined by pressure difference.', '阻力的大小由壓力差決定。']:
        result=check_statements({'explanation':claim},quote,quote+' F = ∆P/R')
        assert result['status']=='rejected' and not result['medically_verified']
        assert any(c['code']=='unsupported_resistance_determinant' for c in result['checks'])
        assert result['checks'][0]['passed']  # Quote inclusion alone did not suffice.


def test_numeric_units_formula_and_direction_checks_do_not_claim_entailment():
    evidence='Flow is measured in milliliter/minute. If you increase the resistance, you decrease flow. F = ∆P/R'
    result=check_statements({'explanation':'Flow is 12 L/min. F = ∆P*R'}, evidence,evidence)
    assert result['status']=='needs_expert_review'
    assert {c['code'] for c in result['checks']} >= {'numbers_absent_from_evidence','unit_not_exactly_supported','literal_formula_match','semantic_entailment_not_established'}
    assert not next(c for c in result['checks'] if c['code']=='literal_formula_match')['passed']
    reversed_direction=check_statements({'explanation':'Increase resistance will increase flow.'},evidence,evidence)
    assert reversed_direction['status']=='rejected'
    assert not result['medically_verified']


def test_direct_definition_practice_needs_no_ollama_or_medical_approval_and_preserves_progress(client,monkeypatch):
    from backend.ollama_local import OllamaLocal
    def forbidden(*args,**kwargs):
        pytest.fail('Extractive practice must not call an LLM')
    monkeypatch.setattr(OllamaLocal,'generate',forbidden)
    s=source();claims=extract_claims(s,s['chunks'])
    assert len(claims)==1 and claims[0]['term']=='Resistance'
    cid=claims[0]['claim_id']
    response=client.post('/api/knowledge/claims/'+cid+'/practice')
    assert response.status_code==200,response.text
    result=response.json();qid=result['question_id']
    assert result['assessment']['status']=='deterministic_source_verified'
    assert not result['assessment']['medically_verified']
    assert {b['field'] for b in result['assessment']['bindings']} >= {'answer','explanation_zh','prompt','terms'}
    assert client.post('/api/attempts',json={'question_id':qid,'answer':'Resistance'}).json()['status']=='correct'
    assert client.post('/api/attempts',json={'question_id':qid,'answer':'Pressure difference'}).json()['status']=='incorrect'
    assert client.post('/api/knowledge/claims/'+cid+'/practice').json()['question_id']==qid
    with database() as conn:
        assert conn.execute('SELECT COUNT(*) FROM questions WHERE id=?',(qid,)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM attempts WHERE question_id=?',(qid,)).fetchone()[0]==2
    q=next(q for q in client.get('/api/questions').json() if q['id']==qid)
    assert q['source']['section']=='Page 16' and q['assessment']['status']=='deterministic_source_verified'
    assert client.get('/api/knowledge/sources/s1/chunks/c1/view').status_code==200


def test_definitions_with_conflicting_units_or_values_are_held(client):
    s=source('Flow is the volume moved per minute. Flow is the volume moved per second.')
    claims=extract_claims(s,s['chunks'])
    assert all(c['assessment']['status']=='needs_expert_review' for c in claims)
    assert client.post('/api/knowledge/claims/'+claims[0]['claim_id']+'/practice').status_code==409


def test_causal_excerpts_and_unchecked_interpretations_cannot_auto_publish(client):
    s=source('Resistance is determined by pressure difference.')
    claim=extract_claims(s,s['chunks'])[0]
    assert claim['term'] is None
    assert client.post('/api/knowledge/claims/'+claim['claim_id']+'/practice').status_code==409
    assert len(client.get('/api/questions').json())==16


def test_changed_source_and_forged_client_flags_cannot_bypass_checks(client):
    s=source();claim=extract_claims(s,s['chunks'])[0]
    with database() as conn:
        chunks=[{**s['chunks'][0],'text':'Resistance is a different definition in a changed snapshot.'}]
        conn.execute('UPDATE local_sources SET chunks=? WHERE id=?',(json.dumps(chunks),'s1'))
    assert client.post('/api/knowledge/claims/'+claim['claim_id']+'/practice',json={'verified':True}).status_code==409


def test_learner_review_flags_cannot_publish_unsupported_model_explanation(client):
    s=source()
    from backend.schemas import Question,Source
    q=Question(id='bad',week=4,topic='Circulation',kind='multiple_choice',prompt='What determines resistance?',prompt_zh='何者決定阻力？',
               difficulty='Foundation',source=Source(title='Lecture',section='Page 16',sample=False,source_id='s1',chunk_id='c1',quote=s['chunks'][0]['text']),
               terms=['Resistance'],explanation_zh='阻力大小由壓力差決定。',answer='Pressure difference',choices=['Pressure difference','Flow'])
    with database() as conn:
        conn.execute('INSERT INTO local_drafts(id,source_id,payload,evidence,uncertain,model,cache_key,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     ('bad','s1',q.model_dump_json(),s['chunks'][0]['text'],0,'local','bad','now'))
    response=client.post('/api/local/drafts/bad/publish',json={'question':q.model_dump(),'reviewed':True,'acknowledge_uncertainty':True})
    assert response.status_code==409
    assert response.json()['detail']['assessment']['status']=='rejected'
    feedback=client.post('/api/knowledge/drafts/bad/feedback',json={'readable':True,'useful':True,'source_relevant':True})
    assert feedback.json()=={'saved':True,'published':False,'medically_verified':False}
    with database() as conn:
        assert conn.execute("SELECT status FROM local_drafts WHERE id='bad'").fetchone()[0]=='pending'
    assert len(client.get('/api/questions').json())==16


def test_sequential_extraction_job_and_source_html_escaping(client):
    source('Resistance is the measure of friction. <script>alert(1)</script>')
    response=client.post('/api/knowledge/extract',json={'source_id':'s1'})
    assert response.status_code==202
    for _ in range(120):
        job=client.get('/api/local/jobs/'+response.json()['id']).json()
        if job['status'] in ('completed','failed'):break
        time.sleep(.03)
    assert job['status']=='completed',job
    assert client.get('/api/knowledge/claims?source_id=s1').json()
    html=client.get('/api/knowledge/sources/s1/chunks/c1/view').text
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert client.get('/api/knowledge/sources/s1/chunks/missing/view').status_code==404

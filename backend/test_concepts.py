import json
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
import pytest

from backend.main import app,initialize
from backend.concepts import initialize_concepts
from backend import local_processing as local
from backend.ollama_local import OllamaLocal
from backend.storage import database
from backend.test_local_processing import GENERATED,fake_request

SOURCE='Arteries carry blood away from the heart.'
CONCEPT={'title':'Arterial blood-flow direction','explanation_zh':'動脈依血流方向定義，將血液帶離心臟。',
 'english_terms':[{'english':'artery','synonyms':['arteries','動脈']}],
 'core_mechanism':'動脈將血液從心臟輸送到其他位置；定義依血流方向。',
 'learning_objectives':['Distinguish arterial flow direction from oxygen content.'],
 'difficulty':'Foundation','tags':['cardiovascular'],'evidence':SOURCE,'uncertain':True}


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/'test.sqlite3'))
    monkeypatch.setattr(local,'IMPORTS',tmp_path/'imports')
    monkeypatch.setattr(OllamaLocal,'request',fake_request)
    with TestClient(app) as client:
        yield client


def wait(client,jid,expected='completed'):
    end=time.monotonic()+10
    while time.monotonic()<end:
        job=client.get('/api/local/jobs/'+jid).json()
        if job['status'] in ('completed','failed','cancelled'):
            assert job['status']==expected,job
            return job
        time.sleep(.03)
    pytest.fail('Concept job timeout')


def source(client):
    response=client.post('/api/local/imports?filename=lesson.txt&week=4&topic=Blood',content=SOURCE.encode())
    return wait(client,response.json()['id'])['output']['source_id']


def concept_draft(client,monkeypatch,source_id):
    def generate(self,model,prompt,schema,cpu=False):return schema.model_validate(CONCEPT)
    monkeypatch.setattr(OllamaLocal,'generate',generate)
    response=client.post('/api/concepts/generate',json={'source_id':source_id})
    assert response.status_code==202,response.text
    wait(client,response.json()['id'])
    return client.get('/api/concepts/drafts').json()[0]


def approve(client,draft):
    response=client.post('/api/concepts/drafts/'+draft['id']+'/approve',json={'reviewed':True,'acknowledge_uncertainty':True,'content':draft['payload']})
    assert response.status_code==200,response.text
    return response.json()['concept_id']


def publish_variant(client,monkeypatch,sid,cid,aspect):
    def generate(self,model,prompt,schema,cpu=False):
        content=GENERATED if aspect=='definition' else {**GENERATED,'prompt':'A vessel takes blood from the heart toward tissues. Which category fits this scenario?', 'prompt_zh':'情境：某血管將血液由心臟送往組織，應歸為哪一類？'}
        return schema.model_validate(content)
    monkeypatch.setattr(OllamaLocal,'generate',generate)
    response=client.post('/api/local/generate',json={'source_id':sid,'concept_id':cid,'variant_aspect':aspect,'count':1})
    assert response.status_code==202,response.text
    wait(client,response.json()['id'])
    draft=next(d for d in client.get('/api/local/drafts').json() if d['payload']['variant_aspect']==aspect)
    # Seed a pre-policy published variant to exercise preservation and relational
    # invariants. The learner-facing publish endpoint now correctly holds this
    # free-form model output, even with both old review flags set.
    response=client.post('/api/local/drafts/'+draft['id']+'/publish',json={'question':draft['payload'],'reviewed':True,'acknowledge_uncertainty':True})
    assert response.status_code==409,response.text
    from backend.schemas import Question
    from backend.concepts import register_variant
    q=Question.model_validate(draft['payload'])
    with database() as conn:
        conn.execute('INSERT INTO questions VALUES (?,?)',(q.id,q.model_dump_json()))
        register_variant(conn,q)
        conn.execute("UPDATE local_drafts SET status='approved' WHERE id=?",(draft['id'],))
    return q.id


def test_populated_database_migration_is_idempotent_and_preserves_exact_original_rows(tmp_path,monkeypatch):
    path=tmp_path/'legacy.sqlite3';monkeypatch.setenv('MEDTERM_DB_PATH',str(path))
    initialize()
    with sqlite3.connect(path) as c:
        c.execute('INSERT INTO attempts(question_id,answer,status,created_at) VALUES (?,?,?,?)',('w1-01','"Medial"','correct','2026-10-01T00:00:00+00:00'))
        old_q=c.execute('SELECT * FROM questions ORDER BY id').fetchall();old_a=c.execute('SELECT * FROM attempts').fetchall()
    initialize_concepts();initialize_concepts()
    with database() as c:
        assert [tuple(r) for r in c.execute('SELECT * FROM questions ORDER BY id')]==old_q
        assert [tuple(r) for r in c.execute('SELECT * FROM attempts')]==old_a
        assert c.execute('SELECT COUNT(*) FROM concepts').fetchone()[0]==16
        assert c.execute('SELECT COUNT(*) FROM question_variants').fetchone()[0]==16
        assert c.execute('SELECT COUNT(*) FROM concept_review_events').fetchone()[0]==1
        event=dict(c.execute('SELECT * FROM concept_review_events').fetchone())
        assert event['observation']=='legacy_correct' and event['hint_used'] is None
        assert event['eligible_retention']==0
        assert c.execute("SELECT COUNT(*) FROM concept_progress WHERE state!='unassessed' OR next_due_at IS NOT NULL").fetchone()[0]==0


def test_new_attempt_observations_are_separate_from_mastery_and_preserve_latency(client):
    result=client.post('/api/attempts',json={'question_id':'w1-01','answer':'Medial','hint_used':False,'response_latency_ms':2400})
    assert result.json()['status']=='correct'
    q=client.get('/api/questions').json()[0]
    concept=client.get('/api/concepts/'+q['concept_id']).json()
    assert concept['progress']['state']=='unassessed' and concept['progress']['next_due_at'] is None
    assert concept['question_accuracy'][0]['correct']==1
    with database() as c:
        event=dict(c.execute('SELECT * FROM concept_review_events').fetchone())
        assert event['response_latency_ms']==2400 and event['hint_used']==0
        assert event['observation']=='unassisted_correct' and event['eligible_retention']==0


def test_self_assessment_updates_same_event_instead_of_duplicating_review(client):
    attempt=client.post('/api/attempts',json={'question_id':'w1-05','answer':'my own wording','response_latency_ms':3000,'hint_used':False}).json()
    client.patch(f"/api/attempts/{attempt['attempt_id']}/review",json={'correct':True})
    with database() as c:
        assert c.execute('SELECT COUNT(*) FROM concept_review_events').fetchone()[0]==1
        event=dict(c.execute('SELECT * FROM concept_review_events').fetchone())
        assert event['observation']=='self_assessed_correct' and event['response_latency_ms']==3000
        assert event['eligible_retention']==0


def test_source_grounded_concept_requires_review_and_normalizes_terms(client,monkeypatch):
    sid=source(client);draft=concept_draft(client,monkeypatch,sid)
    assert client.get('/api/concepts?status=approved').json()==[]
    endpoint='/api/concepts/drafts/'+draft['id']+'/approve'
    assert client.post(endpoint,json={'content':draft['payload'],'reviewed':False}).status_code==422
    assert client.post(endpoint,json={'content':draft['payload'],'reviewed':True}).status_code==422
    cid=approve(client,draft)
    concept=client.get('/api/concepts/'+cid).json()
    assert concept['english_terms'][0]['english']=='artery'
    assert set(concept['english_terms'][0]['synonyms'])=={'arteries','動脈'}
    assert concept['sources'][0]['quote']==SOURCE and concept['sources'][0]['source_id']==sid
    assert concept['status']=='approved' and concept['variants']==[]
    assert client.post(endpoint,json={'content':draft['payload'],'reviewed':True,'acknowledge_uncertainty':True}).status_code==409


def test_invalid_concept_quote_never_enters_approved_bank(client,monkeypatch):
    sid=source(client)
    def generate(self,model,prompt,schema,cpu=False):return schema.model_validate({**CONCEPT,'evidence':'A quotation that is not in this lecture.'})
    monkeypatch.setattr(OllamaLocal,'generate',generate)
    jid=client.post('/api/concepts/generate',json={'source_id':sid}).json()['id']
    wait(client,jid,'failed')
    assert client.get('/api/concepts/drafts').json()==[]


def test_variants_share_parent_but_repeated_aspect_is_rejected(client,monkeypatch):
    sid=source(client);cid=approve(client,concept_draft(client,monkeypatch,sid))
    first=publish_variant(client,monkeypatch,sid,cid,'definition')
    second=publish_variant(client,monkeypatch,sid,cid,'application')
    assert first!=second
    variants=client.get('/api/concepts/'+cid).json()['variants']
    assert {v['aspect'] for v in variants}=={'definition','application'}
    repeated=client.post('/api/local/generate',json={'source_id':sid,'concept_id':cid,'variant_aspect':'definition','count':1})
    assert repeated.status_code==409
    public={q['id']:q for q in client.get('/api/questions').json()}
    assert public[first]['concept_id']==cid==public[second]['concept_id']


def test_variant_approval_conflict_rolls_back_question_insert(client,monkeypatch):
    sid=source(client);cid=approve(client,concept_draft(client,monkeypatch,sid))
    publish_variant(client,monkeypatch,sid,cid,'definition')
    # An older pending draft must still be rejected if another variant won approval.
    from backend.schemas import Question
    with database() as c:
        row=c.execute('SELECT * FROM local_drafts LIMIT 1').fetchone()
        q=Question.model_validate_json(row['payload']);q.id='racing-question'
        c.execute('INSERT INTO local_drafts(id,source_id,payload,evidence,uncertain,model,cache_key,created_at) VALUES (?,?,?,?,?,?,?,?)',('race',sid,q.model_dump_json(),SOURCE,0,'test','race','2026-10-30'))
    response=client.post('/api/local/drafts/race/publish',json={'question':q.model_dump(),'reviewed':True})
    assert response.status_code==409
    with database() as c:
        assert c.execute("SELECT 1 FROM questions WHERE id='racing-question'").fetchone() is None
        assert c.execute("SELECT status FROM local_drafts WHERE id='race'").fetchone()[0]=='pending'


def test_legacy_concepts_cannot_be_used_as_reviewed_parents(client):
    sid=source(client)
    legacy=client.get('/api/concepts?status=legacy').json()[0]
    result=client.post('/api/local/generate',json={'source_id':sid,'concept_id':legacy['concept_id'],'count':1,'variant_aspect':'definition'})
    assert result.status_code==409


def test_review_event_ids_are_installation_scoped(tmp_path,monkeypatch):
    ids=[]
    for name in ('desktop','android-future'):
        monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/(name+'.sqlite3')))
        with TestClient(app) as client:
            client.post('/api/attempts',json={'question_id':'w1-01','answer':'Medial'})
            with database() as c:ids.append(c.execute('SELECT event_id FROM concept_review_events').fetchone()[0])
    assert ids[0]!=ids[1]


def test_relabeling_identical_question_as_new_aspect_does_not_publish(client,monkeypatch):
    sid=source(client);cid=approve(client,concept_draft(client,monkeypatch,sid))
    publish_variant(client,monkeypatch,sid,cid,'definition')
    def duplicate(self,model,prompt,schema,cpu=False):return schema.model_validate(GENERATED)
    monkeypatch.setattr(OllamaLocal,'generate',duplicate)
    result=client.post('/api/local/generate',json={'source_id':sid,'concept_id':cid,'variant_aspect':'application','count':1})
    wait(client,result.json()['id'])
    draft=next(d for d in client.get('/api/local/drafts').json() if d['payload']['variant_aspect']=='application')
    result=client.post('/api/local/drafts/'+draft['id']+'/publish',json={'question':draft['payload'],'reviewed':True,'acknowledge_uncertainty':True})
    assert result.status_code==409
    assert len(client.get('/api/concepts/'+cid).json()['variants'])==1

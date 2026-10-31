import json
from fastapi.testclient import TestClient
from backend.main import app
from backend.storage import database

def test_portable_snapshot_contains_answers_stable_concepts_and_no_filesystem_paths(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/'learning.sqlite3'))
    with TestClient(app) as client:
        snapshot=client.get('/api/learning/snapshot').json()
        assert snapshot['schema']==1 and len(snapshot['questions'])==16
        concepts={c['concept_id'] for c in snapshot['concepts']}
        assert all(q['concept_id'] in concepts and q['answer'] for q in snapshot['questions'])
        assert {q['kind'] for q in snapshot['questions']}=={'crossword','matching','multiple_choice','short_answer','true_false','clinical'}
        assert all('relative_path' not in q['source'] for q in snapshot['questions'])
        q=snapshot['questions'][0]
        with database() as c:c.execute('INSERT INTO study_publications VALUES (?,?,?,?,?,?,?)',(q['id'],'claim','B','withdrawn',json.dumps(q),'reported','now'))
        updated={q['id']:q for q in client.get('/api/learning/snapshot').json()['questions']}
        assert updated[q['id']]['deleted'] and updated[q['id']]['revision']==q['revision']+1
        assert {x['id']:x for x in client.get('/api/learning/snapshot').json()['questions']}[q['id']]['revision']==q['revision']+1
        other=snapshot['questions'][1]
        with database() as c:c.execute('UPDATE concepts SET deleted=1 WHERE concept_id=?',(other['concept_id'],))
        retired={x['id']:x for x in client.get('/api/learning/snapshot').json()['questions']}[other['id']]
        assert retired['deleted']
        assert {x['id']:x for x in client.get('/api/learning/snapshot').json()['questions']}[other['id']]['revision']==retired['revision']


def test_acceptance_attempts_are_retained_but_do_not_count_as_learner_progress(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/'learning.sqlite3'))
    with TestClient(app) as client:
        q=client.get('/api/learning/snapshot').json()['questions'][0]
        saved=client.post('/api/attempts',json={'question_id':q['id'],'answer':q['answer']}).json()
        assert client.get('/api/progress').json()['attempts']==1
        with database() as c:c.execute('INSERT INTO acceptance_attempts VALUES (?,?)',(saved['attempt_id'],'test'))
        progress=client.get('/api/progress').json();assert progress['attempts']==0 and progress['excluded_acceptance_attempts']==1
        assert next(x for x in client.get('/api/questions').json() if x['id']==q['id'])['last_status'] is None
        assert client.get('/api/learning/snapshot').json()['events']==[]
        with database() as c:assert c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]==1

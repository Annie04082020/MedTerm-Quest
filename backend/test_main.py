import pytest
from fastapi.testclient import TestClient

from backend.main import app, initialize


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH', str(tmp_path / 'test.sqlite3'))
    with TestClient(app) as client:
        yield client


def submit(client, question_id, answer):
    return client.post('/api/attempts', json={'question_id': question_id, 'answer': answer})


def test_backend_root_guides_user_without_build(client, tmp_path, monkeypatch):
    monkeypatch.setattr('backend.main.FRONTEND_DIST', tmp_path)
    response = client.get('/')
    assert response.status_code == 200
    assert 'npm run build' in response.text and 'http://127.0.0.1:5173' in response.text
    assert client.get('/favicon.ico').status_code == 200
    assert client.get('/favicon.svg').headers['content-type'] == 'image/svg+xml'


def test_backend_root_serves_built_frontend(client, tmp_path, monkeypatch):
    monkeypatch.setattr('backend.main.FRONTEND_DIST', tmp_path)
    (tmp_path / 'index.html').write_text('<html><title>Built frontend</title></html>', encoding='utf-8')
    response = client.get('/')
    assert response.status_code == 200 and 'Built frontend' in response.text
    assert 'text/html' in response.headers['content-type']
    assert client.get('/api/health').json()['status'] == 'ok'


def test_seeded_bank_is_valid_and_answers_are_private(client):
    bank = client.get('/api/questions').json()
    assert len(bank) == 16
    assert len({q['kind'] for q in bank}) == 6
    for q in bank:
        assert 'answer' not in q and 'accepted_answers' not in q and 'explanation_zh' not in q
        assert q['source']['section'] and q['terms']
        assert all('term' not in pair for pair in q['pairs'])
    assert client.get('/api/health').json()['ai_enabled'] is False
    assert len(client.get('/api/questions?week=1').json()) == 6
    assert len(client.get('/api/questions?kind=clinical').json()) == 3


@pytest.mark.parametrize(('qid', 'answer'), [
    ('w1-01', 'Medial'),
    ('w1-02', {'1': 'heart', '2': 'hemo', '3': 'tachy'}),
    ('w1-03', {'a': 'cardi/o', 'b': 'neur/o', 'c': 'oste/o'}),
    ('w1-04', 'False: 遠離'),
    ('w1-05', '前側'),
    ('w2-05', '蒸發帶走熱量'),
    ('w3-04', 'CO = HR × SV'),
    ('w3-05', '6.3 L/min'),
])
def test_every_activity_and_both_languages(client, qid, answer):
    response = submit(client, qid, answer)
    assert response.status_code == 200
    assert response.json()['status'] == 'correct'
    assert response.json()['explanation_zh']
    assert client.get('/api/progress').json()['accuracy'] == 100


def test_mistake_review_and_latest_answer(client):
    assert submit(client, 'w1-01', 'Lateral').json()['status'] == 'incorrect'
    progress = client.get('/api/progress').json()
    assert progress['accuracy'] == 0 and progress['review_count'] == 1
    assert client.get('/api/questions?review=true').json()[0]['id'] == 'w1-01'
    submit(client, 'w1-01', 'Medial')
    progress = client.get('/api/progress').json()
    assert progress['accuracy'] == 50 and progress['mastered'] == 1 and progress['review_count'] == 0
    assert client.get('/api/questions?review=true').json() == []


def test_unrecognized_answers_need_explicit_self_assessment(client):
    response = submit(client, 'w2-05', 'Sweat absorbs thermal energy as it vaporizes.').json()
    assert response['status'] == 'needs_review'
    assert client.get('/api/progress').json()['accuracy'] is None
    assert client.get('/api/progress').json()['review_count'] == 1
    attempt_id = response['attempt_id']
    assert client.patch(f'/api/attempts/{attempt_id}/review', json={'correct': True}).json()['status'] == 'correct'
    progress = client.get('/api/progress').json()
    assert progress['accuracy'] == 100 and progress['self_assessed'] == 1
    assert client.patch(f'/api/attempts/{attempt_id}/review', json={'correct': False}).status_code == 409


@pytest.mark.parametrize(('qid', 'answer'), [
    ('w3-04', 'CO = HR + SV'), ('w3-05', '63 L/min'),
    ('w2-05', 'Evaporation does not remove heat from the body'), ('w1-05', 'anteror'),
])
def test_no_false_claims_about_math_negation_or_spelling(client, qid, answer):
    assert submit(client, qid, answer).json()['status'] == 'needs_review'


def test_validation_and_missing_records(client):
    assert submit(client, 'missing', 'anything').status_code == 404
    assert submit(client, 'w1-01', '').status_code == 422
    assert submit(client, 'w1-01', 'not an option').status_code == 422
    assert submit(client, 'w1-02', {'1': 'HEART'}).status_code == 422
    assert submit(client, 'w1-01', {'a': 'Medial'}).status_code == 422
    assert submit(client, 'w1-05', 'a' * 20001).status_code == 422
    assert client.get('/api/questions?kind=unknown').status_code == 422
    assert client.patch('/api/attempts/999/review', json={'correct': True}).status_code == 404


def test_progress_survives_reinitialization_and_answers_are_stored(client):
    submit(client, 'w1-05', '前側')
    initialize()
    assert client.get('/api/progress').json()['attempts'] == 1
    assert client.get('/api/progress').json()['mastered'] == 1


def test_reinitialization_does_not_overwrite_existing_question_payload(client):
    from backend.storage import database
    import json
    with database() as conn:
        payload=json.loads(conn.execute("SELECT payload FROM questions WHERE id='w1-01'").fetchone()[0])
        payload['prompt']='User-reviewed question text retained across restart'
        payload['revision']=7
        original=json.dumps(payload,ensure_ascii=False)
        conn.execute("UPDATE questions SET payload=? WHERE id='w1-01'",(original,))
    initialize()
    with database() as conn:
        assert conn.execute("SELECT payload FROM questions WHERE id='w1-01'").fetchone()[0]==original

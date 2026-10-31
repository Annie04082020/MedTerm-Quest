"""Local games, SQLite progress, and optional queued local AI processing."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import unicodedata

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT / 'dist'
from backend.schemas import KINDS, Question
from backend.storage import database

def initialize():
    questions = [Question.model_validate(q) for q in json.loads((ROOT / 'backend' / 'sample_questions.json').read_text(encoding='utf-8'))]
    if len({q.id for q in questions}) != len(questions):
        raise ValueError('Duplicate sample question IDs')
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS questions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, question_id TEXT NOT NULL REFERENCES questions(id),
          answer TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, self_assessed INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS attempts_question ON attempts(question_id, id);
        CREATE TABLE IF NOT EXISTS acceptance_attempts(attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id),note TEXT NOT NULL);
        ''')
        # Sample seeding must never rewrite an existing user's question on restart.
        conn.executemany('INSERT INTO questions(id,payload) VALUES (?,?) ON CONFLICT(id) DO NOTHING',
                         [(q.id, q.model_dump_json()) for q in questions])

@asynccontextmanager
async def lifespan(app):
    initialize()
    from backend.local_processing import initialize_local, ProcessingQueue
    initialize_local()
    from backend.material_library import initialize_library
    initialize_library()
    from backend.concepts import initialize_concepts
    initialize_concepts()
    from backend.material_classification import initialize_classifications
    initialize_classifications()
    from backend.knowledge import initialize_knowledge
    initialize_knowledge()
    from backend.study_bank import initialize_study_bank
    initialize_study_bank()
    processing = ProcessingQueue()
    app.state.processing_queue = processing
    processing.start()
    try:
        yield
    finally:
        processing.close()

app = FastAPI(title='MedTerm Quest · local API', lifespan=lifespan)
app.mount('/assets', StaticFiles(directory=str(FRONTEND_DIST / 'assets'), check_dir=False), name='frontend-assets')

@app.get('/', include_in_schema=False)
def frontend():
    index = FRONTEND_DIST / 'index.html'
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse('''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>MedTerm Quest · 啟動介面</title>
    <body style="font-family:system-ui;max-width:640px;margin:60px auto;padding:24px;line-height:1.8;background:#f7f8f4;color:#293e36">
    <h1>MedTerm Quest</h1><p>後端已啟動。請選擇以下一種方式開啟學習介面：</p>
    <ol><li>開發模式：另開終端機執行 <code>npm run dev</code>，再開啟
    <a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a>。</li>
    <li>單一伺服器：在專案根目錄執行 <code>npm run build</code>，完成後重新整理此頁即可。</li></ol>
    <p>第一次使用請先執行 <code>npm install</code> 安裝前端套件。</p></body></html>''')

@app.get('/favicon.svg', include_in_schema=False)
@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return FileResponse(ROOT / 'public' / 'favicon.svg', media_type='image/svg+xml')

def get_question(conn, question_id):
    hidden=conn.execute("SELECT 1 FROM study_publications WHERE question_id=? AND status!='active'",(question_id,)).fetchone()
    if hidden:raise HTTPException(410,'此題已撤下；作答歷史仍保留。請更新題庫。')
    row = conn.execute('SELECT payload FROM questions WHERE id=?', (question_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Question not found')
    return Question.model_validate_json(row['payload'])

def normalized(value):
    text = unicodedata.normalize('NFKC', value).casefold().strip()
    # Preserve decimal points, negation, and mathematical operators: 6.3 != 63,
    # HR * SV != HR + SV. Only spacing and terminal sentence marks are cosmetic.
    return re.sub(r'\s+', '', text).rstrip('。.!！?？')

def grade(q, answer):
    if isinstance(q.answer, dict):
        if not isinstance(answer, dict):
            raise HTTPException(422, 'Expected an answer mapping')
        if set(answer) != set(q.answer) or any(not value.strip() for value in answer.values()):
            raise HTTPException(422, 'Complete every item before checking')
        return 'correct' if all(normalized(answer[k]) == normalized(v) for k, v in q.answer.items()) else 'incorrect'
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(422, 'Please enter an answer')
    if q.kind == 'multiple_choice' and answer not in q.choices:
        raise HTTPException(422, 'Choose one of the available answers')
    if normalized(answer) in {normalized(a) for a in [q.answer, *q.accepted_answers]}:
        return 'correct'
    # Normal play remains deterministic. Semantic advice requires a separate opt-in job.
    return 'needs_review' if q.kind in ('short_answer', 'clinical', 'true_false') else 'incorrect'

class Submission(BaseModel):
    question_id: str = Field(max_length=100)
    answer: str | dict[str, str]
    response_latency_ms: int | None = Field(default=None,ge=0,le=86400000)
    hint_used: bool | None = None

    @model_validator(mode='after')
    def bounded_answer(self):
        if len(json.dumps(self.answer)) > 20000:
            raise ValueError('Answer too long')
        return self

class SelfAssessment(BaseModel):
    correct: bool

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'offline', 'phase': 4, 'ai_enabled': False, 'optional_provider': 'ollama-local', 'ai_requires_explicit_request': True,'android_packaged':False}

@app.get('/api/questions')
def questions(week: int | None = None, kind: KINDS | None = None, review: bool = False):
    with database() as conn:
        bank = [Question.model_validate_json(r['payload']) for r in conn.execute('SELECT payload FROM questions ORDER BY id')]
        latest = {r['question_id']: r['status'] for r in conn.execute('SELECT question_id,status FROM attempts WHERE id IN (SELECT MAX(id) FROM attempts WHERE id NOT IN (SELECT attempt_id FROM acceptance_attempts) GROUP BY question_id)')}
        parents = {r['question_id']:dict(r) for r in conn.execute('SELECT question_id,concept_id,aspect FROM question_variants')}
        from backend.knowledge import get_report
        assessments = {q.id: get_report(conn, 'question', q.id) for q in bank}
        related = {}
        inactive={r[0] for r in conn.execute("SELECT question_id FROM study_publications WHERE status!='active'")}
        for row in conn.execute('SELECT question_id,concept_id FROM question_concept_members'):
            related.setdefault(row['question_id'],[]).append(row['concept_id'])
    result = []
    for q in bank:
        if q.id in inactive:continue
        if (week and q.week != week) or (kind and q.kind != kind) or (review and latest.get(q.id) not in ('incorrect', 'needs_review')):
            continue
        public = q.model_dump(exclude={'answer', 'accepted_answers', 'explanation_zh'})
        public['last_status'] = latest.get(q.id)
        public['assessment'] = assessments[q.id]
        if assessments[q.id].get('tier')=='B':
            from backend.study_bank import traditional
            public['prompt_zh']=traditional(public['prompt_zh'])
        public['related_concept_ids'] = related.get(q.id,[])
        if q.id in parents:
            public['concept_id'] = parents[q.id]['concept_id']
            public['variant_aspect'] = parents[q.id]['aspect']
        if q.kind == 'matching':
            public['pairs'] = [{'id': p['id'], 'definition': p['definition']} for p in q.pairs]
            public['choices'] = list(q.answer.values())
            random.Random(q.id).shuffle(public['choices'])
        result.append(public)
    return result

@app.post('/api/attempts')
def submit(payload: Submission):
    with database() as conn:
        q = get_question(conn, payload.question_id)
        status = grade(q, payload.answer)
        from backend.knowledge import get_report
        from backend.practice_generation import grade_numeric
        proof=get_report(conn,'question',q.id).get('construction_proof',{})
        numeric=grade_numeric(payload.answer,proof)
        if numeric is not None:status=numeric
        if status == 'needs_review' and conn.execute('SELECT 1 FROM knowledge_question_links WHERE question_id=?',(q.id,)).fetchone():
            # Closed extractive cloze asks for one original term, not conceptual
            # self-assessment by a novice. Other short answers keep old behavior.
            status = 'incorrect'
        cursor = conn.execute('INSERT INTO attempts(question_id,answer,status,created_at) VALUES (?,?,?,?)',
                              (q.id, json.dumps(payload.answer, ensure_ascii=False), status, datetime.now(timezone.utc).isoformat()))
        from backend.concepts import record_attempt
        record_attempt(conn,dict(conn.execute('SELECT * FROM attempts WHERE id=?',(cursor.lastrowid,)).fetchone()),latency=payload.response_latency_ms,hint_used=payload.hint_used)
        explanation=q.explanation_zh
        if get_report(conn,'question',q.id).get('tier')=='B':
            from backend.study_bank import traditional
            explanation=traditional(explanation)
        return {'attempt_id': cursor.lastrowid, 'status': status, 'answer': q.answer,
                'explanation_zh': explanation, 'source': q.source.model_dump(),
                'feedback': 'Accepted answer recognized.' if status == 'correct' else 'Compare your reasoning with the explanation and assess your answer.' if status == 'needs_review' else 'Review the explanation, then try again in your review queue.'}

@app.patch('/api/attempts/{attempt_id}/review')
def assess(attempt_id: int, payload: SelfAssessment):
    with database() as conn:
        row = conn.execute('SELECT status FROM attempts WHERE id=?', (attempt_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Attempt not found')
        if row['status'] != 'needs_review':
            raise HTTPException(409, 'Only ungraded answers can be self-assessed')
        status = 'correct' if payload.correct else 'incorrect'
        conn.execute('UPDATE attempts SET status=?,self_assessed=1 WHERE id=?', (status, attempt_id))
        from backend.concepts import record_attempt
        record_attempt(conn,dict(conn.execute('SELECT * FROM attempts WHERE id=?',(attempt_id,)).fetchone()))
        return {'status': status, 'self_assessed': True}

@app.get('/api/progress')
def progress():
    with database() as conn:
        bank = [Question.model_validate_json(r['payload']) for r in conn.execute('SELECT payload FROM questions')]
        rows = conn.execute('SELECT * FROM attempts WHERE id NOT IN (SELECT attempt_id FROM acceptance_attempts) ORDER BY id').fetchall()
        excluded=conn.execute('SELECT COUNT(*) FROM acceptance_attempts').fetchone()[0]
        provisional={r[0] for r in conn.execute('SELECT question_id FROM study_publications')}
        inactive={r[0] for r in conn.execute("SELECT question_id FROM study_publications WHERE status!='active'")}
        bank=[q for q in bank if q.id not in inactive]
    latest = {r['question_id']: r['status'] for r in rows}
    graded = [r for r in rows if r['status'] != 'needs_review']
    correct = sum(r['status'] == 'correct' for r in graded)
    return {'total_questions': len(bank), 'attempts': len(rows), 'excluded_acceptance_attempts':excluded,'graded_attempts': len(graded),
            'correct': correct, 'accuracy': round(100 * correct / len(graded)) if graded else None,
            'mastered': sum(s == 'correct' and qid not in provisional for qid,s in latest.items()),
            'review_count': sum(latest.get(q.id) in ('incorrect','needs_review') for q in bank),
            'self_assessed': sum(r['self_assessed'] for r in rows),
            'weeks': [{'week': w, 'total': sum(q.week == w for q in bank),
                       'mastered': sum(q.week == w and latest.get(q.id) == 'correct' and q.id not in provisional for q in bank)} for w in sorted({q.week for q in bank})],
            'recent': [{'id': r['id'], 'question_id': r['question_id'], 'status': r['status'], 'created_at': r['created_at'], 'self_assessed': bool(r['self_assessed'])} for r in rows[-8:][::-1]]}

from backend.local_processing import router as local_router
app.include_router(local_router)
from backend.material_library import router as materials_router
app.include_router(materials_router)
from backend.concepts import router as concepts_router
app.include_router(concepts_router)
from backend.material_classification import router as classification_router
app.include_router(classification_router)
from backend.knowledge import router as knowledge_router
app.include_router(knowledge_router)
from backend.practice_generation import router as practice_router
app.include_router(practice_router)
from backend.study_bank import router as study_bank_router
app.include_router(study_bank_router)
from backend.learning import router as learning_router
app.include_router(learning_router)

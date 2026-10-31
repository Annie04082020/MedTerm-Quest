"""Conservative source checks. No status in this module certifies medical truth."""
import hashlib
from html import escape
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.storage import database

router = APIRouter(prefix='/api/knowledge', tags=['Source-grounded authoring'])
VERSION = 'extractive-v1'
Status = Literal['deterministic_source_verified', 'provisional_source_grounded', 'needs_expert_review', 'rejected']
LABELS = {
    'deterministic_source_verified': '已通過確定性來源檢查（非醫學驗證）',
    'provisional_source_grounded': '暫具來源依據，未經獨立醫學驗證',
    'needs_expert_review': '需要專業審查',
    'rejected': '已拒絕',
}


def initialize_knowledge():
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS knowledge_claims(
          claim_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,chunk_id TEXT NOT NULL,
          locator TEXT NOT NULL,source_hash TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS claims_source ON knowledge_claims(source_id,chunk_id);
        CREATE TABLE IF NOT EXISTS authoring_checks(
          entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,payload TEXT NOT NULL,
          PRIMARY KEY(entity_type,entity_id));
        CREATE TABLE IF NOT EXISTS knowledge_question_links(
          question_id TEXT PRIMARY KEY,claim_id TEXT NOT NULL,template_version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS learner_content_feedback(
          draft_id TEXT PRIMARY KEY,readable INTEGER NOT NULL,useful INTEGER NOT NULL,
          source_relevant INTEGER NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS practice_concept_members(
          group_concept_id TEXT NOT NULL,member_concept_id TEXT NOT NULL,
          PRIMARY KEY(group_concept_id,member_concept_id));
        CREATE TABLE IF NOT EXISTS question_concept_members(
          question_id TEXT NOT NULL,concept_id TEXT NOT NULL,
          PRIMARY KEY(question_id,concept_id));
        ''')


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def compact(text):
    # Only layout whitespace is cosmetic. Units, signs and formula symbols matter.
    return ' '.join(text.split())


def report(status, checks, bindings=None):
    return {'status': status, 'label': LABELS[status], 'medically_verified': False,
            'validator_version': VERSION, 'checks': checks, 'bindings': bindings or [],
            'limitations': '只驗證教材對應與受限模板；不代表教材本身或模型的醫學結論正確。'}


def save_report(conn, kind, identity, assessment):
    conn.execute('INSERT OR REPLACE INTO authoring_checks VALUES (?,?,?)',
                 (kind, identity, json.dumps(assessment, ensure_ascii=False)))


def get_report(conn, kind, identity):
    row = conn.execute('SELECT payload FROM authoring_checks WHERE entity_type=? AND entity_id=?', (kind, identity)).fetchone()
    return json.loads(row[0]) if row else report('provisional_source_grounded', [
        {'method': 'deterministic', 'code': 'legacy_unassessed', 'passed': False,
         'detail': '舊資料保留；尚未經新來源檢查。'}])


# Intentionally small grammar: an entire declarative definition, never a general
# entailment algorithm. Non-matching text remains visible but cannot auto-publish.
DEFINITION = re.compile(r'(?P<term>[A-Z][A-Za-z -]{1,49}?) is (?P<definition>(?:the |a |an )[^.!?]{8,450})[.]')
RISK = re.compile(r'\b(?:patient|disease|diagnos\w*|treat\w*|dose|caus\w*|determin\w*|increase\w*|decrease\w*|not|never|except)\b', re.I)


def sentences(text):
    normalized = compact(text)
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])', normalized) if s.strip()]


def extract_claims(source, chunks):
    """Persist individual source sentences before concept or question authoring."""
    records = []
    for chunk in chunks:
        for text in sentences(chunk['text']):
            match = DEFINITION.fullmatch(text)
            direct = bool(match and not RISK.search(text) and ' and ' not in text)
            cid = 'claim-' + digest(source['id'] + ':' + chunk['id'] + ':' + text)[:32]
            claim = {'claim_id': cid, 'source_id': source['id'], 'chunk_id': chunk['id'],
                     'locator': chunk['locator'], 'text': text, 'evidence': text,
                     'source_hash': digest(chunk['text']),
                     'support': 'direct_extraction' if direct else 'uninterpreted_source_excerpt',
                     'term': match['term'] if direct else None,
                     'definition': match['definition'] if direct else None,
                     'assessment': report('deterministic_source_verified' if direct else 'provisional_source_grounded', [
                         {'method': 'deterministic', 'code': 'exact_source_sentence', 'passed': text in compact(chunk['text'])},
                         {'method': 'deterministic', 'code': 'restricted_definition_grammar', 'passed': direct}])}
            records.append(claim)
    # Conflicting exact definitions, including units/numbers, are held for expert
    # review. This conservative lexical check can overflag equivalent definitions.
    with database() as conn:
        prior = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM knowledge_claims')]
        combined = {c['claim_id']: c for c in prior + records}
        for claim in combined.values():
            conflicts = [c['claim_id'] for c in combined.values() if claim.get('term') and (c.get('term') or '').casefold() == claim['term'].casefold()
                         and c['source_id'] == claim['source_id'] and c.get('definition') != claim['definition']]
            if conflicts:
                claim['assessment'] = report('needs_expert_review', [
                    {'method': 'heuristic', 'code': 'conflicting_definitions', 'passed': False, 'conflicts': conflicts}])
            if claim['claim_id'] in {c['claim_id'] for c in records} or conflicts:
                conn.execute('INSERT OR REPLACE INTO knowledge_claims VALUES (?,?,?,?,?,?,?)',
                             (claim['claim_id'], claim['source_id'], claim['chunk_id'], claim['locator'], claim['source_hash'],
                              json.dumps(claim, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        return [combined[c['claim_id']] for c in records]


def check_statements(fields, evidence, source_text, uncertain=False, clinical=False):
    """Red flags are heuristic; quote/numeric inclusion is deterministic, not entailment."""
    checks = [{'method': 'deterministic', 'code': 'quote_in_source', 'passed': compact(evidence) in compact(source_text) and bool(evidence.strip())}]
    status = 'needs_expert_review'
    if not checks[0]['passed']:
        status = 'rejected'
    def formulas(value):
        value = unicodedata.normalize('NFKC', value).replace('Δ', '∆')
        return re.findall(r'[A-Za-z]+\s*=\s*[∆A-Za-z]+\s*[/×*+-]\s*[A-Za-z]+', value)
    source_formulas = {re.sub(r'\s+', '', f) for f in formulas(source_text)}
    bindings = []
    for field, text in fields.items():
        text = str(text)
        bindings.append({'field': field, 'candidate_text': text, 'evidence': evidence,
                         'support': 'model_interpretation', 'entailed': False})
        # Regression: a valid R=deltaP/F relation does not make deltaP the
        # determinant of R. Do not rewrite equations to invent causal direction.
        bad_resistance = re.search(r'resistance.{0,65}(?:determined by|depends (?:only |solely )?on|caused by).{0,35}pressure', text, re.I | re.S)
        bad_resistance_zh = re.search(r'阻力.{0,35}(?:由壓力差決定|取決於壓力差|因壓力差而|壓力差決定)', text)
        if bad_resistance or bad_resistance_zh:
            bindings[-1]['support'] = 'unsupported_extrapolation'
            checks.append({'method': 'heuristic', 'code': 'unsupported_resistance_determinant', 'field': field, 'passed': False,
                           'detail': '流量公式不支持「壓力差決定阻力」的因果主張；禁止自動發布。'})
            status = 'rejected'
        numbers = re.findall(r'(?<![\w])\d+(?:\.\d+)?', text)
        missing = [n for n in numbers if not re.search(r'(?<![\w.])' + re.escape(n) + r'(?![\w.])', evidence)]
        if missing:
            checks.append({'method': 'deterministic', 'code': 'numbers_absent_from_evidence', 'field': field, 'passed': False, 'values': missing})
        units = re.findall(r'\b(?:mmHg|mL/min|ml/min|milliliter/minute|L/min|kg|mg|mmol/L)\b', text)
        if any(u not in evidence for u in units):
            checks.append({'method': 'deterministic', 'code': 'unit_not_exactly_supported', 'field': field, 'passed': False})
        for formula in formulas(text):
            checks.append({'method': 'deterministic', 'code': 'literal_formula_match', 'field': field,
                           'formula': formula, 'passed': re.sub(r'\s+', '', formula) in source_formulas,
                           'detail': '僅比對公式字面；不推斷因果或驗證代數等價。'})
        if re.search(r'increase.{0,20}resistance.{0,60}increase.{0,15}flow|阻力增加.{0,20}流量增加', text, re.I):
            checks.append({'method': 'heuristic', 'code': 'possible_reversed_flow_direction', 'field': field, 'passed': False})
            status = 'rejected'
        if re.search(r'[=∝]|(?:increase|decrease|causes?|because|導致|增加|減少|成反比|成正比)', text, re.I):
            checks.append({'method': 'heuristic', 'code': 'formula_or_causal_claim_requires_review', 'field': field, 'passed': False})
        checks.append({'method': 'deterministic', 'code': 'semantic_entailment_not_established', 'field': field, 'passed': False,
                       'detail': '引用存在不表示此欄位的意思已獲證明。'})
    if uncertain or clinical:
        checks.append({'method': 'deterministic', 'code': 'uncertain_or_clinical_hold', 'passed': False})
    return report(status, checks, bindings)


def assess_question(conn, q, evidence, uncertain=False):
    row = conn.execute('SELECT chunks FROM local_sources WHERE id=?', (q.source.source_id,)).fetchone()
    chunk = next((c for c in json.loads(row[0]) if c['id'] == q.source.chunk_id), None) if row else None
    return check_statements({'prompt': q.prompt, 'prompt_zh': q.prompt_zh, 'answer': q.answer,
                             'explanation_zh': q.explanation_zh, 'terms': q.terms,
                             'choices': q.choices, 'rubric': q.rubric, 'pairs': q.pairs, 'entries': q.entries},
                            evidence, chunk['text'] if chunk else '', uncertain, q.kind == 'clinical')


def render_question(claim, source, material_id=None):
    """No generated medical prose, synonyms, distractors, numbers or causality."""
    from backend.schemas import Question, Source
    term = claim['term']
    return Question(id='extractive-' + digest(claim['claim_id'] + VERSION)[:24],
                    course=source.get('course', 'Human Anatomy and Physiology'), week=source['week'], topic=source['topic'],
                    kind='short_answer', difficulty='Foundation',
                    prompt='Complete the source definition with the exact English term: ____ is ' + claim['definition'] + '.',
                    prompt_zh='請依講義原文填入英文術語；本題只練習辨識定義。',
                    answer=term, terms=[term], accepted_answers=[],
                    explanation_zh='講義原文：「' + claim['text'] + '」本題答案為 ' + term + '；僅依原文辨識術語，未延伸臨床推論。',
                    rubric=['填入原文術語：' + term],
                    source=Source(title=source['title'], section=claim['locator'], sample=False,
                                  source_id=source['id'], chunk_id=claim['chunk_id'], quote=claim['evidence'],
                                  material_id=material_id, relative_path=source['filename'] if material_id else None))


class ExtractRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    start_chunk: int = Field(default=0, ge=0, le=9999)
    count: int = Field(default=1, ge=1, le=8)


class Feedback(BaseModel):
    readable: bool
    useful: bool
    source_relevant: bool


@router.post('/drafts/{draft_id}/feedback')
def feedback(draft_id: str, payload: Feedback):
    with database() as conn:
        if not conn.execute('SELECT 1 FROM local_drafts WHERE id=?',(draft_id,)).fetchone():
            raise HTTPException(404, '找不到草稿。')
        conn.execute('INSERT OR REPLACE INTO learner_content_feedback VALUES (?,?,?,?,?)',
                     (draft_id,int(payload.readable),int(payload.useful),int(payload.source_relevant),datetime.now(timezone.utc).isoformat()))
    return {'saved': True, 'published': False, 'medically_verified': False}


@router.post('/extract', status_code=202)
def enqueue_extract(payload: ExtractRequest):
    from backend.local_processing import create_job, source_record
    source = source_record(payload.source_id)
    if payload.start_chunk >= len(source['chunks']):
        raise HTTPException(422, '來源片段不存在。')
    return create_job('claims_extract', payload.model_dump())


def process_extraction(engine, job_id, params):
    from backend.local_processing import source_record, update_job
    source = source_record(params['source_id'])
    engine.check_cancel(job_id)
    update_job(job_id, stage='擷取原子來源陳述；不進行醫學推論', progress=20)
    claims = extract_claims(source, source['chunks'][params['start_chunk']:params['start_chunk'] + params['count']])
    return {'claim_ids': [c['claim_id'] for c in claims], 'direct_definitions': sum(c['assessment']['status'] == 'deterministic_source_verified' for c in claims),
            'message': '來源陳述已保存；只有嚴格定義模板可自動發布，其餘保留供專業審查。'}


@router.get('/claims')
def list_claims(source_id: str):
    with database() as conn:
        return [json.loads(r[0]) for r in conn.execute('SELECT payload FROM knowledge_claims WHERE source_id=? ORDER BY locator,claim_id', (source_id,))]


@router.get('/sources/{source_id}/chunks/{chunk_id}')
def view_chunk(source_id: str, chunk_id: str):
    from backend.local_processing import source_record
    source = source_record(source_id)
    chunk = next((c for c in source['chunks'] if c['id'] == chunk_id), None)
    if not chunk:
        raise HTTPException(404, '找不到來源片段。')
    return {'title': source['title'], **chunk}


@router.get('/sources/{source_id}/chunks/{chunk_id}/view', response_class=HTMLResponse)
def readable_chunk(source_id: str, chunk_id: str):
    chunk = view_chunk(source_id, chunk_id)
    return '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>教材來源</title><body style="max-width:900px;margin:2rem auto;padding:1rem;font-family:system-ui"><h1>' + escape(chunk['title']) + '</h1><h2>' + escape(chunk['locator']) + '</h2><p>這是本機擷取快照，保留原教材頁碼或時間戳。</p><pre style="white-space:pre-wrap;line-height:1.8">' + escape(chunk['text']) + '</pre></body></html>'


@router.post('/claims/{claim_id}/practice')
def publish_extractive(claim_id: str):
    """An explicit practice action enables automatic publication, without medical approval."""
    from backend.local_processing import source_record, validate_activity
    from backend.concepts import register_variant
    with database() as conn:
        row = conn.execute('SELECT payload FROM knowledge_claims WHERE claim_id=?', (claim_id,)).fetchone()
    if not row:
        raise HTTPException(404, '找不到知識陳述。')
    claim = json.loads(row[0])
    source = source_record(claim['source_id'])
    chunk = next((c for c in source['chunks'] if c['id'] == claim['chunk_id']), None)
    if not chunk or digest(chunk['text']) != claim['source_hash']:
        raise HTTPException(409, '來源快照已變更，請重新擷取。')
    # Re-extract and check conflicts at time of publication, never trust client flags.
    fresh = extract_claims(source, [chunk])
    claim = next(c for c in fresh if c['claim_id'] == claim_id)
    if claim['assessment']['status'] != 'deterministic_source_verified' or not claim.get('term'):
        raise HTTPException(409, '此陳述無法通過嚴格定義檢查；不會自動發布。')
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        # Re-read the stored assessment inside the publication transaction.
        current = json.loads(conn.execute('SELECT payload FROM knowledge_claims WHERE claim_id=?', (claim_id,)).fetchone()[0])
        if current['assessment']['status'] != 'deterministic_source_verified':
            raise HTTPException(409, '陳述有衝突，已停止發布。')
        link = conn.execute('SELECT reference_id FROM material_source_links WHERE source_id=?', (source['id'],)).fetchone()
        q = validate_activity(render_question(claim, source, link[0] if link else None).model_dump())
        assessment = report('deterministic_source_verified', [
            {'method': 'deterministic', 'code': code, 'passed': True} for code in
            ['current_source_hash', 'exact_definition', 'answer_equals_source_subject', 'unchanged_units_numbers_formula', 'closed_question_template', 'explanation_is_source_quote']],
            [{'field': f, 'claim_id': claim_id, 'evidence': claim['evidence']} for f in ['prompt', 'answer', 'explanation_zh', 'terms', 'rubric']])
        # A deterministic, source-only concept; no LLM medical translation or
        # inferred mechanism is inserted. IDs are stable across repeated practice.
        cid = 'concept-extractive-' + digest(claim_id + VERSION)[:24]
        q = q.model_copy(update={'concept_id': cid, 'variant_aspect': 'definition'})
        stamp = datetime.now(timezone.utc).isoformat()
        conn.execute('''INSERT OR IGNORE INTO concepts
          (concept_id,course,week,topic,title,explanation_zh,core_mechanism,difficulty,status,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                     (cid,q.course,q.week,q.topic,claim['term'],q.explanation_zh,'原文定義辨識；未推導額外生理機制。','Foundation','approved',stamp,stamp))
        conn.execute('INSERT OR IGNORE INTO concept_terms VALUES (?,?)',(cid,claim['term']))
        conn.execute('INSERT OR IGNORE INTO concept_objectives VALUES (?,?,?)',(cid,0,'辨識講義原文術語：'+claim['term']))
        conn.execute('INSERT OR IGNORE INTO concept_sources VALUES (?,?,?,?,?,?)',
                     (cid,source['id'],claim['chunk_id'],claim['locator'],claim['evidence'],json.dumps({'title':source['title'],'filename':source['filename']},ensure_ascii=False)))
        conn.execute('INSERT OR IGNORE INTO concept_progress(concept_id) VALUES (?)',(cid,))
        save_report(conn,'concept',cid,assessment)
        conn.execute('INSERT OR IGNORE INTO questions VALUES (?,?)', (q.id, q.model_dump_json()))
        conn.execute('INSERT OR IGNORE INTO knowledge_question_links VALUES (?,?,?)', (q.id, claim_id, VERSION))
        if not conn.execute('SELECT 1 FROM question_variants WHERE question_id=?',(q.id,)).fetchone():
            register_variant(conn, q)
        save_report(conn, 'question', q.id, assessment)
    return {'question_id': q.id, 'assessment': assessment}

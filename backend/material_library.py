"""Read-only external library. File access is always scoped to the configured root."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.storage import ROOT, database

router = APIRouter(prefix='/api/materials', tags=['External material library'])
SUPPORTED = {'.mp4', '.pdf', '.md', '.txt', '.srt', '.vtt'}
DEFAULT_COURSE = 'Human Anatomy and Physiology'


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize_library():
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS material_files (
          id TEXT PRIMARY KEY, root_key TEXT NOT NULL, relative_path TEXT NOT NULL,
          filename TEXT NOT NULL, file_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
          modified_at TEXT NOT NULL, modified_ns INTEGER NOT NULL, content_hash TEXT,
          status TEXT NOT NULL DEFAULT 'discovered', course TEXT NOT NULL,
          week INTEGER, topic TEXT NOT NULL DEFAULT '', source_id TEXT,
          processed_hash TEXT, error TEXT, last_seen TEXT NOT NULL,
          UNIQUE(root_key,relative_path));
        CREATE INDEX IF NOT EXISTS material_hash ON material_files(root_key,content_hash);
        CREATE TABLE IF NOT EXISTS material_extract_cache (
          content_hash TEXT NOT NULL, method TEXT NOT NULL, chunks TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(content_hash,method));
        CREATE TABLE IF NOT EXISTS material_source_links (
          source_id TEXT PRIMARY KEY, material_id TEXT NOT NULL, reference_id TEXT NOT NULL,
          input_hash TEXT NOT NULL, reference_hash TEXT NOT NULL,
          course TEXT NOT NULL, week INTEGER NOT NULL, topic TEXT NOT NULL,
          created_at TEXT NOT NULL);
        ''')
        # Additive migration: old source records and progress remain valid.
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(local_sources)')}
        if columns and 'course' not in columns:
            conn.execute("ALTER TABLE local_sources ADD COLUMN course TEXT NOT NULL DEFAULT 'Human Anatomy and Physiology'")


def materials_root():
    raw = os.environ.get('COURSE_MATERIALS_DIR', '').strip()
    if not raw:
        raise HTTPException(503, '請在 backend/.env 設定 COURSE_MATERIALS_DIR，再重新啟動後端。')
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise HTTPException(503, 'COURSE_MATERIALS_DIR 必須是絕對路徑。')
    try:
        root = path.resolve(strict=True)
        if not root.is_dir():
            raise OSError('Not a directory')
    except OSError as exc:
        raise HTTPException(503, '教材目錄不存在或無法讀取，請檢查 backend/.env。') from exc
    return root


def root_key(root):
    return hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def resolve_relative(root, relative):
    """Do not follow symlinks/junctions, even when their target would be in root."""
    rel = PurePosixPath(relative)
    if not relative or '\\' in relative or ':' in relative or rel.is_absolute() or any(part in ('..', '.') for part in rel.parts):
        raise HTTPException(403, '不允許的教材路徑。')
    path = root
    try:
        for part in rel.parts:
            path = path / part
            if is_link(path):
                raise HTTPException(403, '教材庫不讀取符號連結或 junction。')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not stat.S_ISREG(resolved.stat().st_mode):
            raise HTTPException(403, '教材路徑超出設定範圍或不是一般檔案。')
        if resolved.suffix.lower() not in SUPPORTED:
            raise HTTPException(403, '不允許的教材類型。')
        return resolved
    except FileNotFoundError as exc:
        raise HTTPException(404, '原始教材已不存在，請重新掃描。') from exc
    except OSError as exc:
        raise HTTPException(403, '無法安全讀取此教材。') from exc


def opened_path(handle):
    """Verify the actual opened handle, closing the resolve/open race on Windows."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        function = ctypes.windll.kernel32.GetFinalPathNameByHandleW
        function.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        function.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = function(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise HTTPException(403, '無法驗證原始檔案位置。')
        value = buffer.value
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
        return Path(value).resolve()
    proc = Path('/proc/self/fd') / str(handle.fileno())
    if proc.exists():
        return proc.resolve()
    return None


@contextmanager
def safe_open(root, relative):
    path = resolve_relative(root, relative)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise HTTPException(403, '原始教材不是一般檔案。')
        actual = opened_path(handle)
        if actual is not None and (not actual.is_relative_to(root) or actual != path):
            raise HTTPException(403, '原始教材位置已變更，拒絕讀取。')
        yield handle
        # Check again after reading, including parent-directory replacements.
        actual = opened_path(handle)
        if actual is not None and not actual.is_relative_to(root):
            raise HTTPException(403, '原始教材已移出設定範圍。')


def hash_file(root, relative, check_cancel=lambda:None, output=None):
    with safe_open(root, relative) as handle:
        before = os.fstat(handle.fileno())
        digest = hashlib.sha256()
        while block := handle.read(1024 * 1024):
            check_cancel()
            digest.update(block)
            if output is not None:
                output.write(block)
        after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('檔案在讀取時變更，請待儲存完成後重新掃描。')
        return digest.hexdigest(), after


def material_record(material_id, root=None):
    root = root or materials_root()
    with database() as conn:
        row = conn.execute('SELECT * FROM material_files WHERE id=? AND root_key=?', (material_id, root_key(root))).fetchone()
    if not row:
        raise HTTPException(404, '此教材不在目前設定的目錄清單中。')
    return dict(row)


def discover(root, check_cancel, warnings):
    files = []
    stack = [root]
    while stack:
        directory = stack.pop()
        check_cancel()
        try:
            # Revalidate each directory before walking it. Never recurse through links.
            if directory != root:
                current = root
                for part in directory.relative_to(root).parts:
                    current = current / part
                    if is_link(current):
                        raise OSError('Linked directory skipped')
            with os.scandir(directory) as entries:
                for entry in entries:
                    check_cancel()
                    path = Path(entry.path)
                    if is_link(path):
                        warnings.append(f'略過連結：{path.relative_to(root).as_posix()}')
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in SUPPORTED:
                        files.append(path.relative_to(root).as_posix())
        except OSError as exc:
            # Incomplete scans must not mark unreadable subtrees as missing.
            raise ValueError(f'無法完整掃描目錄 {directory.relative_to(root)}，未標記任何舊檔案為遺失：{exc}') from exc
    return sorted(files, key=str.casefold)


def scan_library(engine, job_id, params):
    from backend.local_processing import update_job
    root = materials_root()
    key = root_key(root)
    if key != params['root_key']:
        raise ValueError('教材目錄設定已變更，請重新掃描。')
    check = lambda:engine.check_cancel(job_id)
    warnings = []
    update_job(job_id, stage='尋找教材（唯讀，不解析或轉錄）', progress=1)
    files = discover(root, check, warnings)
    token = uuid4().hex
    counts = {'discovered':0, 'changed':0, 'unchanged':0, 'errors':0, 'total':len(files)}
    for i, relative in enumerate(files):
        check()
        update_job(job_id, stage=f'計算 SHA-256 {i+1}/{len(files)} · {relative}', progress=min(98, int(98*i/max(1,len(files)))))
        with database() as conn:
            previous = conn.execute('SELECT * FROM material_files WHERE root_key=? AND relative_path=?', (key, relative)).fetchone()
        try:
            digest, info = hash_file(root, relative, check)
            changed = bool(previous and previous['content_hash'] != digest)
            status = 'changed' if changed else previous['status'] if previous else 'discovered'
            if status in ('missing','error'):
                status = 'extracted' if previous and previous['source_id'] and previous['processed_hash'] == digest else 'discovered'
            counts['changed' if changed else 'unchanged' if previous else 'discovered'] += 1
            modified = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()
            with database() as conn:
                conn.execute('''INSERT INTO material_files
                  (id,root_key,relative_path,filename,file_type,size_bytes,modified_at,modified_ns,content_hash,status,course,last_seen)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(root_key,relative_path) DO UPDATE SET
                  size_bytes=excluded.size_bytes,modified_at=excluded.modified_at,modified_ns=excluded.modified_ns,
                  content_hash=excluded.content_hash,status=excluded.status,error=NULL,last_seen=excluded.last_seen,
                  source_id=CASE WHEN material_files.content_hash=excluded.content_hash THEN material_files.source_id ELSE NULL END''',
                  (previous['id'] if previous else uuid4().hex,key,relative,Path(relative).name,Path(relative).suffix[1:].lower(),info.st_size,modified,info.st_mtime_ns,digest,status,DEFAULT_COURSE,token))
        except HTTPException as exc:
            counts['errors'] += 1
            warnings.append(f'{relative}: {exc.detail}')
            record_scan_error(root,key,relative,previous,token,str(exc.detail))
        except (OSError,ValueError) as exc:
            counts['errors'] += 1
            warnings.append(f'{relative}: 無法讀取 ({exc.__class__.__name__})')
            record_scan_error(root,key,relative,previous,token,str(exc)[:500])
        update_job(job_id, output={**counts, 'warnings':warnings[:50]})
    check()
    with database() as conn:
        conn.execute("UPDATE material_files SET status='missing',error='上次掃描未找到原始檔案' WHERE root_key=? AND last_seen!=?", (key,token))
        # A video is stale when its chosen transcript/notes change, even when the
        # video bytes are unchanged. Old source snapshots/questions remain intact.
        conn.execute('''UPDATE material_files SET status='changed',source_id=NULL,error='配對字幕／筆記已變更或遺失，請重新擷取'
          WHERE root_key=? AND status NOT IN ('missing','error') AND source_id IN (
            SELECT link.source_id FROM material_source_links link JOIN material_files ref ON ref.id=link.reference_id
            WHERE ref.content_hash!=link.reference_hash OR ref.status IN ('missing','error'))''',(key,))
        counts['missing'] = conn.execute("SELECT COUNT(*) FROM material_files WHERE root_key=? AND status='missing'", (key,)).fetchone()[0]
    return {**counts, 'warnings':warnings[:50], 'message':'掃描完成；沒有自動解析、轉錄或產題。'}


def record_scan_error(root,key,relative,previous,token,error):
    """Keep unreadable discoveries visible, without exposing or reading other paths."""
    try:
        info = (root / relative).lstat()
        size, modified, modified_ns = info.st_size, datetime.fromtimestamp(info.st_mtime,timezone.utc).isoformat(), info.st_mtime_ns
    except OSError:
        size, modified, modified_ns = 0, now(), 0
    with database() as conn:
        conn.execute('''INSERT INTO material_files
          (id,root_key,relative_path,filename,file_type,size_bytes,modified_at,modified_ns,status,course,error,last_seen)
          VALUES (?,?,?,?,?,?,?,?,'error',?,?,?) ON CONFLICT(root_key,relative_path) DO UPDATE SET
          status='error',error=excluded.error,last_seen=excluded.last_seen''',
          (previous['id'] if previous else uuid4().hex,key,relative,Path(relative).name,Path(relative).suffix[1:].lower(),size,modified,modified_ns,DEFAULT_COURSE,error,token))


def matching_stem(filename):
    stem = Path(filename).stem.casefold()
    stem = re.sub(r'(?:[ ._-]+(?:transcript|transcription|study[ _-]*notes|notes|subtitle[s]?|captions?|en|zh(?:-tw)?|逐字稿|字幕|筆記))+$', '', stem)
    return re.sub(r'[\W_]+', '', stem)


def companions_for(material, records):
    if material['file_type'] != 'mp4':
        return []
    stem = matching_stem(material['filename'])
    return [row for row in records if row['id'] != material['id'] and row['status'] not in ('missing','error')
            and row['file_type'] in ('srt','vtt','txt','md','pdf') and (matching_stem(row['filename']) == stem
            or (material['week'] is not None and material['topic'].strip() and
                (row['course'],row['week'],row['topic'].casefold()) == (material['course'],material['week'],material['topic'].casefold())))]


def public_material(row, records):
    duplicates = sorted([r for r in records if r['id'] != row['id'] and r['content_hash'] and r['content_hash'] == row['content_hash'] and r['status'] != 'missing'], key=lambda r:r['relative_path'])
    stage='ready_for_generation' if row['status']=='extracted' and row['source_id'] else 'classified' if row['week'] is not None and row['topic'].strip() else 'discovered'
    return {**{k:row[k] for k in ('id','relative_path','filename','file_type','size_bytes','modified_at','content_hash','status','course','week','topic','source_id','error')},'pipeline_stage':stage,
            'duplicate_count':len(duplicates), 'duplicate_paths':[r['relative_path'] for r in duplicates[:5]],
            'companions':[{k:r[k] for k in ('id','filename','relative_path','file_type')} for r in companions_for(row, records)]}


@router.get('')
def list_materials(q: str = '', file_type: str = '', status: str = '', offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=200)):
    try:
        root = materials_root()
    except HTTPException as exc:
        return {'configured':False,'root':os.environ.get('COURSE_MATERIALS_DIR',''),'error':str(exc.detail),'items':[],'total':0,'offset':offset,'limit':limit,'summary':{}}
    with database() as conn:
        records = [dict(r) for r in conn.execute('SELECT * FROM material_files WHERE root_key=? ORDER BY relative_path COLLATE NOCASE',(root_key(root),))]
    filtered = [r for r in records if q.casefold() in f"{r['relative_path']} {r['course']} {r['topic']}".casefold() and (not file_type or r['file_type']==file_type) and (not status or r['status']==status)]
    summary = {s:sum(r['status']==s for r in records) for s in ('discovered','classified','changed','extracted','missing','error')}
    return {'configured':True,'root':str(root),'error':None,'items':[public_material(r,records) for r in filtered[offset:offset+limit]],'total':len(filtered),'offset':offset,'limit':limit,'summary':summary}


@router.post('/scan', status_code=202)
def enqueue_scan():
    from backend.local_processing import create_job
    root = materials_root()
    with database() as conn:
        active = conn.execute("SELECT id FROM local_jobs WHERE kind='library_scan' AND status IN ('queued','running') AND json_extract(params,'$.root_key')=?", (root_key(root),)).fetchone()
    if active:
        return {'id':active['id'],'status':'queued','existing':True}
    return create_job('library_scan',{'root_key':root_key(root)})


class Association(BaseModel):
    model_config = ConfigDict(extra='forbid')
    course: str = Field(min_length=1,max_length=150)
    week: int | None = Field(default=None,ge=1,le=100)
    topic: str = Field(default='',max_length=150)


@router.patch('/{material_id}/association')
def associate(material_id: str, payload: Association):
    record = material_record(material_id)
    if not payload.course.strip():
        raise HTTPException(422,'課程名稱不可空白。')
    course, topic = payload.course.strip(),payload.topic.strip()
    changed = (record['course'],record['week'],record['topic']) != (course,payload.week,topic)
    with database() as conn:
        conn.execute('''UPDATE material_files SET course=?,week=?,topic=?,source_id=CASE WHEN ? THEN NULL ELSE source_id END,
          status=CASE WHEN ? AND status='extracted' THEN 'changed' ELSE status END WHERE id=?''', (course,payload.week,topic,changed,changed,material_id))
    return {'id':material_id,'course':course,'week':payload.week,'topic':topic}


def require_association(record):
    if record['week'] is None or not record['topic'].strip():
        raise HTTPException(422,'請先手動指定課程週次與主題，再處理教材。')
    if record['status'] == 'missing' or not record['content_hash']:
        raise HTTPException(409,'原始檔案遺失或無法讀取，請重新掃描。')


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    companion_id: str | None = None


def select_reference(record, companion_id=None):
    root = materials_root()
    if record['file_type'] != 'mp4':
        if companion_id:
            raise HTTPException(422,'非影片教材不需要配對來源。')
        return record
    with database() as conn:
        candidates = companions_for(record,[dict(r) for r in conn.execute('SELECT * FROM material_files WHERE root_key=?',(root_key(root),))])
    if companion_id:
        selected = next((r for r in candidates if r['id']==companion_id),None)
        if not selected:
            raise HTTPException(422,'所選字幕／筆記不是此影片在目前目錄中的配對候選。')
        return selected
    if not candidates:
        raise HTTPException(422,'未找到配對字幕或筆記。請自行提供檔案並重新掃描，或明確按下影片轉錄。')
    transcripts = [r for r in candidates if r['file_type'] in ('srt','vtt','txt')]
    preferred = transcripts or candidates
    same_folder = [r for r in preferred if Path(r['relative_path']).parent == Path(record['relative_path']).parent]
    preferred = same_folder or preferred
    priority = {'srt':0,'vtt':1,'txt':2,'md':3,'pdf':4}
    preferred.sort(key=lambda r:(priority[r['file_type']],r['relative_path']))
    best = preferred[0]
    if sum(priority[r['file_type']]==priority[best['file_type']] for r in preferred)>1:
        raise HTTPException(409,'有多個配對字幕或筆記，請先在下拉選單選擇正確檔案。')
    return best


def processing_params(record, reference):
    return {'root_key':record['root_key'],'material_id':record['id'],'reference_id':reference['id'],
            'expected_hash':record['content_hash'],'reference_hash':reference['content_hash'],
            'course':record['course'],'week':record['week'],'topic':record['topic'],'filename':record['filename']}


@router.post('/{material_id}/extract', status_code=202)
def enqueue_extraction(material_id: str, payload: ExtractionRequest):
    from backend.local_processing import create_job
    record = material_record(material_id)
    require_association(record)
    reference = select_reference(record,payload.companion_id)
    resolve_relative(materials_root(),reference['relative_path'])
    return create_job('library_extract',processing_params(record,reference))


class TranscriptionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm: bool = False
    ignore_existing: bool = False
    device: Literal['auto','cpu'] = 'auto'
    allow_cpu: bool = True


@router.post('/{material_id}/transcribe', status_code=202)
def enqueue_transcription(material_id: str, payload: TranscriptionRequest):
    from backend.local_processing import create_job
    record = material_record(material_id)
    require_association(record)
    if record['file_type'] != 'mp4' or not payload.confirm:
        raise HTTPException(422,'只有明確觸發的 MP4 工作才可轉錄。')
    with database() as conn:
        related = companions_for(record,[dict(r) for r in conn.execute('SELECT * FROM material_files WHERE root_key=?',(record['root_key'],))])
    if related and not payload.ignore_existing:
        raise HTTPException(409,'已有配對字幕或筆記，請優先使用。若確實需要重新轉錄，請明確勾選忽略既有配對。')
    resolve_relative(materials_root(),record['relative_path'])
    return create_job('library_transcribe',{**processing_params(record,record),'device':payload.device,'allow_cpu':payload.allow_cpu})


@contextmanager
def verified_snapshot(root, record, expected_hash, check_cancel):
    """Copy only to managed temporary data, never write to the original directory."""
    destination = ROOT / 'data' / 'processing'
    destination.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='material-',dir=destination) as directory:
        snapshot = Path(directory) / ('source.'+record['file_type'])
        with snapshot.open('wb') as output:
            digest,_ = hash_file(root,record['relative_path'],check_cancel,output)
        if digest != expected_hash:
            with database() as conn:
                conn.execute("UPDATE material_files SET status='changed',source_id=NULL,error='檔案在掃描後已變更，請重新掃描' WHERE id=?",(record['id'],))
            raise ValueError('原始教材在掃描後已變更，沒有使用舊雜湊解析；請重新掃描。')
        yield snapshot


def process_material(engine, job_id, kind, params):
    from backend.local_processing import update_job
    from backend.source_import import parse_source
    root = materials_root()
    if root_key(root) != params['root_key']:
        raise ValueError('教材目錄設定已變更，請重新掃描並建立新工作。')
    record = material_record(params['material_id'],root)
    reference = material_record(params['reference_id'],root)
    require_association(record)
    if (record['content_hash'],record['course'],record['week'],record['topic']) != (params['expected_hash'],params['course'],params['week'],params['topic']) or reference['content_hash'] != params['reference_hash']:
        raise ValueError('教材版本或課程關聯已變更，請重新建立工作。')
    parse_type = 'text' if reference['file_type'] in ('md','txt') else reference['file_type']
    method = 'transcribe:small:v1' if kind=='library_transcribe' else 'parse:'+parse_type+':v1'
    check = lambda:engine.check_cancel(job_id)
    update_job(job_id,stage='驗證原始教材並建立唯讀處理快照',progress=3)
    try:
        if record['id'] != reference['id']:
            original = resolve_relative(root,record['relative_path']).stat()
            if (original.st_size,original.st_mtime_ns) != (record['size_bytes'],record['modified_ns']):
                raise ValueError('影片在掃描後已變更，請重新掃描。')
        # Even a cache hit revalidates current file bytes before it can be associated.
        with verified_snapshot(root,reference,params['reference_hash'],check) as snapshot:
            with database() as conn:
                cached = conn.execute('SELECT chunks FROM material_extract_cache WHERE content_hash=? AND method=?',(params['reference_hash'],method)).fetchone()
            if cached:
                chunks = json.loads(cached['chunks'])
                update_job(job_id,stage='使用相同內容雜湊的擷取快取',progress=85)
            else:
                update_job(job_id,stage='轉錄影片（使用者明確要求）' if kind=='library_transcribe' else '在本機擷取 PDF／文字，保留原始位置',progress=12)
                chunks = engine.transcribe(job_id,snapshot,params) if kind=='library_transcribe' else parse_source(snapshot)
                if not chunks or len(chunks)>10000:
                    raise ValueError('沒有可用文字或超過 10000 個片段，請分批處理。')
                with database() as conn:
                    conn.execute('INSERT OR IGNORE INTO material_extract_cache VALUES (?,?,?,?)',(params['reference_hash'],method,json.dumps(chunks,ensure_ascii=False),now()))
        check()
        # Association may have been edited while a long transcription was running.
        source_id = hashlib.sha256(json.dumps([record['id'],reference['id'],params['expected_hash'],params['reference_hash'],record['course'],record['week'],record['topic'],method],ensure_ascii=False).encode()).hexdigest()[:32]
        for i,chunk in enumerate(chunks):
            chunk['id'] = f'{source_id}-{i+1}'
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT * FROM material_files WHERE id=?',(record['id'],)).fetchone()
            if (current['course'],current['week'],current['topic'],current['content_hash']) != (record['course'],record['week'],record['topic'],params['expected_hash']):
                raise ValueError('處理期間教材關聯已變更；擷取快取保留，請重新建立工作。')
            conn.execute('INSERT OR IGNORE INTO local_sources(id,title,week,topic,filename,chunks,created_at,course) VALUES (?,?,?,?,?,?,?,?)',
                         (source_id,reference['filename'],record['week'],record['topic'],reference['relative_path'],json.dumps(chunks,ensure_ascii=False),now(),record['course']))
            conn.execute('INSERT OR IGNORE INTO material_source_links VALUES (?,?,?,?,?,?,?,?,?)',
                         (source_id,record['id'],reference['id'],params['expected_hash'],params['reference_hash'],record['course'],record['week'],record['topic'],now()))
            conn.execute("UPDATE material_files SET status='extracted',source_id=?,processed_hash=?,error=NULL WHERE id=?",(source_id,params['expected_hash'],record['id']))
        return {'material_id':record['id'],'source_id':source_id,'reference':reference['relative_path'],'chunks':len(chunks),'cached':bool(cached),'message':'文字已保存，可送往 Local AI studio；未自動產題。'}
    except Exception as exc:
        # Do not turn a changed/missing marker into a generic processing error.
        with database() as conn:
            conn.execute("UPDATE material_files SET status=CASE WHEN status IN ('changed','missing') THEN status ELSE 'error' END,error=? WHERE id=?",(str(exc)[:1200],record['id']))
        raise


@router.get('/{material_id}/content')
def extracted_content(material_id: str):
    record = material_record(material_id)
    if not record['source_id'] or record['status'] != 'extracted':
        raise HTTPException(409,'此教材尚無目前版本的擷取文字，請先處理。')
    with database() as conn:
        row = conn.execute('SELECT title,chunks FROM local_sources WHERE id=?',(record['source_id'],)).fetchone()
    if not row:
        raise HTTPException(404,'找不到擷取結果。')
    return {'source_id':record['source_id'],'title':row['title'],'chunks':json.loads(row['chunks'])}

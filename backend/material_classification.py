"""Deterministic classification proposals; applying them always requires review."""
import json
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.material_library import materials_root,root_key,material_record,resolve_relative,verified_snapshot,now
from backend.storage import database

router=APIRouter(prefix='/api/materials/classifications',tags=['Material classification'])


def initialize_classifications():
    with database() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS material_classifications(
          material_id TEXT PRIMARY KEY,content_hash TEXT NOT NULL,payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',created_at TEXT NOT NULL)''')


def filename_proposal(filename):
    stem=Path(filename).stem
    match=re.search(r'\b(?:handout|lecture|week|w)[ _-]*(\d{1,2})(?:[._-](\d{1,2}))?(?!\d)',stem,re.I)
    week=int(match[1]) if match and 1<=int(match[1])<=30 else None
    code=(match[1]+'-'+match[2]) if match and week and match[2] else None
    topic=stem[match.end():] if match else stem
    topic=re.split(r'\s*[·—]\s*',topic)[0]
    topic=re.sub(r'\.(?:pdf|mp4)$','',topic,flags=re.I)
    topic=re.sub(r'(?:[_ -]+(?:notes|transcript|字幕|筆記))$','',topic,flags=re.I)
    topic=re.sub(r'[_]+',' ',topic).strip(' -_.')
    reasons=['Explicit filename week/lecture hint; requires confirmation.'] if week else ['No reliable week hint; leave unassigned.']
    if match and not week:reasons.append('Week hint outside conservative 1–30 range; not accepted automatically.')
    return {'week':week,'topic':topic[:150],'confidence':.85 if week else .3,'reasons':reasons,'lecture_code':code}


def suggest_classifications(engine,job_id,params):
    from backend.local_processing import update_job
    root=materials_root()
    if root_key(root)!=params['root_key']:raise ValueError('教材目錄已變更，請重建分類工作。')
    with database() as conn:
        rows=[dict(r) for r in conn.execute("SELECT * FROM material_files WHERE root_key=? AND status NOT IN ('missing','error') AND content_hash IS NOT NULL ORDER BY relative_path",(root_key(root),))]
    proposals=[];warnings=[]
    for i,row in enumerate(rows):
        engine.check_cancel(job_id)
        update_job(job_id,stage=f'分類建議 {i+1}/{len(rows)} · {row["filename"]}',progress=int(90*i/max(1,len(rows))))
        p=filename_proposal(row['filename']);metadata={}
        if row['file_type']=='pdf':
            try:
                import pymupdf
                with verified_snapshot(root,row,row['content_hash'],lambda:engine.check_cancel(job_id)) as path:
                    with pymupdf.open(path) as doc:
                        if not doc.needs_pass:
                            metadata['pdf_title']=(doc.metadata.get('title') or '')[:300]
                            metadata['first_heading']=next((s.strip() for s in doc[0].get_text().splitlines() if 4<=len(s.strip())<=150),'') if len(doc) else ''
                title=metadata.get('pdf_title','')
                if title and title.casefold() not in ('powerpoint presentation','untitled','presentation'):
                    title_p=filename_proposal(title)
                    if title_p['week'] and p['week'] and title_p['week']!=p['week']:
                        p['reasons'].append('PDF title and filename disagree about week; review required.');p['confidence']=.4
                    elif title_p['week'] and not p['week']:
                        p['week']=title_p['week'];p['confidence']=.7;p['reasons'].append('Explicit PDF title week hint.')
                    if not p['topic']:p['topic']=title_p['topic']
                if not p['topic']:p['topic']=metadata.get('first_heading','')[:150]
            except ImportError:
                warnings.append(row['filename']+': PyMuPDF unavailable; filename suggestions only.')
            except (OSError,ValueError,HTTPException) as exc:
                warnings.append(row['filename']+': '+str(exc)[:200])
        p.update(material_id=row['id'],content_hash=row['content_hash'],filename=row['filename'],relative_path=row['relative_path'],course=row['course'],metadata=metadata,related_ids=[])
        if row['week'] is not None:
            p['week']=row['week'];p['topic']=row['topic'] or p['topic'];p['reasons'].append('Existing manual association retained.')
        proposals.append(p)
    for p in proposals:
        topic_key=re.sub(r'[^a-z0-9\u3400-\u9fff]','',p['topic'].casefold())
        related=[r for r in proposals if r['material_id']!=p['material_id'] and
                 ((p['lecture_code'] and r['lecture_code']==p['lecture_code']) or (topic_key and re.sub(r'[^a-z0-9\u3400-\u9fff]','',r['topic'].casefold())==topic_key))]
        p['related_ids']=[r['material_id'] for r in related]
        weeks={r['week'] for r in related if r['week'] is not None}
        if p['week'] is None and len(weeks)==1:
            p['week']=next(iter(weeks));p['confidence']=.6;p['reasons'].append('Unique related-material week hint; verify manually.')
    engine.check_cancel(job_id)
    with database() as conn:
        for p in proposals:
            current=conn.execute('SELECT content_hash FROM material_files WHERE id=?',(p['material_id'],)).fetchone()
            if not current or current['content_hash']!=p['content_hash']:continue
            conn.execute('''INSERT INTO material_classifications(material_id,content_hash,payload,created_at) VALUES (?,?,?,?)
              ON CONFLICT(material_id) DO UPDATE SET content_hash=excluded.content_hash,payload=excluded.payload,
              status=CASE WHEN material_classifications.content_hash=excluded.content_hash AND material_classifications.status='confirmed' THEN 'confirmed' ELSE 'pending' END,created_at=excluded.created_at''',
              (p['material_id'],p['content_hash'],json.dumps(p,ensure_ascii=False),now()))
    return {'proposals':len(proposals),'warnings':warnings[:30],'message':'建議尚未套用。請檢查週次及主題後批次確認。'}


@router.get('')
def suggestions():
    try:root=materials_root()
    except HTTPException:return []
    with database() as conn:
        return [{**json.loads(r['payload']),'status':r['status']} for r in conn.execute('''SELECT p.* FROM material_classifications p
          JOIN material_files m ON m.id=p.material_id WHERE m.root_key=? AND m.content_hash=p.content_hash
          AND m.status NOT IN ('missing','error') ORDER BY m.relative_path LIMIT 200''',(root_key(root),))]


@router.post('/suggest',status_code=202)
def enqueue_suggestions():
    from backend.local_processing import create_job
    root=materials_root()
    return create_job('library_classify',{'root_key':root_key(root)})


class ConfirmItem(BaseModel):
    material_id:str=Field(max_length=100)
    content_hash:str=Field(min_length=64,max_length=64)
    course:str=Field(min_length=1,max_length=150)
    week:int=Field(ge=1,le=100)
    topic:str=Field(min_length=1,max_length=150)


class BatchConfirmation(BaseModel):
    items:list[ConfirmItem]=Field(min_length=1,max_length=100)
    extract_text:bool=False


@router.post('/confirm')
def confirm_batch(payload:BatchConfirmation):
    from backend.material_library import processing_params
    root=materials_root();key=root_key(root)
    if len({i.material_id for i in payload.items})!=len(payload.items):raise HTTPException(422,'教材不可重複選取。')
    job_ids=[];skipped=[]
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        records=[]
        for item in payload.items:
            row=conn.execute('SELECT * FROM material_files WHERE id=? AND root_key=?',(item.material_id,key)).fetchone()
            proposal=conn.execute('SELECT content_hash FROM material_classifications WHERE material_id=?',(item.material_id,)).fetchone()
            if not row or not proposal or row['status'] in ('missing','error') or row['content_hash']!=item.content_hash or proposal['content_hash']!=item.content_hash:
                raise HTTPException(409,'教材或建議版本已變更；整批未套用，請重新掃描／取得建議。')
            info=resolve_relative(root,row['relative_path']).stat()
            if (info.st_size,info.st_mtime_ns)!=(row['size_bytes'],row['modified_ns']):raise HTTPException(409,'原始教材已變更；整批未套用，請重新掃描。')
            if not item.course.strip() or not item.topic.strip():raise HTTPException(422,'課程與主題不可空白。')
            records.append((item,dict(row)))
        text_jobs=sum(r['file_type']!='mp4' for _,r in records) if payload.extract_text else 0
        pending=conn.execute("SELECT COUNT(*) FROM local_jobs WHERE status IN ('queued','running')").fetchone()[0]
        if pending+text_jobs>20:raise HTTPException(429,'確認後將超過 20 件處理工作；請減少批次或取消自動擷取。')
        for item,row in records:
            changed=(row['course'],row['week'],row['topic'])!=(item.course.strip(),item.week,item.topic.strip())
            conn.execute('''UPDATE material_files SET course=?,week=?,topic=?,
              source_id=CASE WHEN ? THEN NULL ELSE source_id END,
              status=CASE WHEN ? AND status='extracted' THEN 'changed' WHEN status IN ('discovered','classified') THEN 'classified' ELSE status END WHERE id=?''',
              (item.course.strip(),item.week,item.topic.strip(),changed,changed,item.material_id))
            proposal=json.loads(conn.execute('SELECT payload FROM material_classifications WHERE material_id=?',(item.material_id,)).fetchone()[0])
            proposal.update(course=item.course.strip(),week=item.week,topic=item.topic.strip(),confirmed_at=now())
            conn.execute("UPDATE material_classifications SET status='confirmed',payload=? WHERE material_id=?",(json.dumps(proposal,ensure_ascii=False),item.material_id))
            if payload.extract_text:
                if row['file_type']=='mp4':skipped.append(item.material_id);continue
                row.update(course=item.course.strip(),week=item.week,topic=item.topic.strip())
                jid=uuid4().hex;job_ids.append(jid)
                conn.execute('INSERT INTO local_jobs(id,kind,params,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                  (jid,'library_extract',json.dumps(processing_params(row,row),ensure_ascii=False),'queued','分類確認後等待文字擷取',now(),now()))
    return {'confirmed':len(payload.items),'job_ids':job_ids,'videos_not_transcribed':skipped}

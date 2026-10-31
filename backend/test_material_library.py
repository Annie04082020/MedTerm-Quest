import hashlib
import json
import os
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from backend.main import app, initialize
from backend import material_library as library
from backend import local_processing as local
from backend.storage import database
from backend.test_local_processing import fake_request
from backend.ollama_local import OllamaLocal


@pytest.fixture
def course(tmp_path,monkeypatch):
    root = tmp_path/'external-materials'
    root.mkdir()
    (root/'videos').mkdir()
    (root/'notes').mkdir()
    (root/'videos'/'lecture.mp4').write_bytes(b'test video; never decoded during scans')
    (root/'notes'/'lecture.srt').write_text('1\n00:00:01,000 --> 00:00:04,500\nArteries carry blood away from the heart.\n',encoding='utf-8')
    (root/'notes'/'lecture_notes.md').write_text('# Study notes\nArteries carry blood away from the heart.\n',encoding='utf-8')
    (root/'Week99_unreliable.txt').write_text('Arteries carry blood away from the heart.',encoding='utf-8')
    (root/'duplicate.txt').write_bytes((root/'Week99_unreliable.txt').read_bytes())
    (root/'ignore.zip').write_bytes(b'not supported')
    monkeypatch.setenv('COURSE_MATERIALS_DIR',str(root))
    monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/'app.sqlite3'))
    monkeypatch.setattr(local,'IMPORTS',tmp_path/'managed-imports')
    monkeypatch.setattr(OllamaLocal,'request',fake_request)
    with TestClient(app) as client:
        yield client,root


def wait(client,job_id,status='completed'):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        result=client.get('/api/local/jobs/'+job_id)
        assert result.status_code==200
        job=result.json()
        if job['status'] in ('completed','failed','cancelled'):
            assert job['status']==status,job
            return job
        time.sleep(.03)
    pytest.fail('Library queue timed out')


def scan(client):
    response=client.post('/api/materials/scan')
    assert response.status_code==202,response.text
    return wait(client,response.json()['id'])


def items(client):
    return client.get('/api/materials?limit=200').json()['items']


def named(client,name):
    return next(item for item in items(client) if item['filename']==name)


def associate(client,material_id,week=4,topic='Blood vessels',course='HAP'):
    response=client.patch(f'/api/materials/{material_id}/association',json={'course':course,'week':week,'topic':topic})
    assert response.status_code==200,response.text


def extract(client,material_id,body=None,status='completed'):
    response=client.post(f'/api/materials/{material_id}/extract',json=body or {})
    assert response.status_code==202,response.text
    return wait(client,response.json()['id'],status)


def test_scan_is_read_only_recursive_hashed_and_never_processes_ai(course,monkeypatch):
    client,root=course
    originals={p.relative_to(root):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    def forbidden(*args,**kwargs):raise AssertionError('Scanning must not parse, transcribe, or call AI')
    monkeypatch.setattr(local.ProcessingQueue,'transcribe',forbidden)
    monkeypatch.setattr(OllamaLocal,'request',forbidden)
    monkeypatch.setattr('backend.source_import.parse_source',forbidden)
    result=scan(client)
    assert result['output']['total']==5
    indexed=items(client)
    assert len(indexed)==5
    assert all(m['week'] is None and m['status']=='discovered' for m in indexed)
    text=named(client,'Week99_unreliable.txt')
    assert text['week'] is None
    assert text['content_hash']==hashlib.sha256((root/'Week99_unreliable.txt').read_bytes()).hexdigest()
    assert text['duplicate_count']==1
    assert all(m['modified_at'] and m['size_bytes']>0 and m['course'] for m in indexed)
    assert {p.relative_to(root):(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}==originals
    assert client.get('/api/local/sources').json()==[]


def test_manual_association_and_markdown_extraction_feed_existing_ai_pipeline(course):
    client,_=course
    scan(client)
    material=named(client,'lecture_notes.md')
    assert client.post(f"/api/materials/{material['id']}/extract",json={}).status_code==422
    associate(client,material['id'])
    result=extract(client,material['id'])
    content=client.get(f"/api/materials/{material['id']}/content").json()
    assert content['source_id']==result['output']['source_id']
    assert content['chunks'][0]['segments'][1]['line']==2
    source=client.get('/api/local/sources/'+content['source_id']).json()
    assert source['course']=='HAP' and source['week']==4 and source['topic']=='Blood vessels'
    generation=client.post('/api/local/generate',json={'source_id':source['id'],'count':1})
    wait(client,generation.json()['id'])
    draft=client.get('/api/local/drafts').json()[0]
    assert draft['payload']['course']=='HAP'
    assert draft['payload']['source']['material_id']==material['id']
    assert draft['payload']['source']['relative_path']=='notes/lecture_notes.md'
    assert len(client.get('/api/questions').json())==16


def test_mp4_prefers_existing_timestamped_transcript_and_never_transcribes(course,monkeypatch):
    client,_=course
    scan(client)
    video=named(client,'lecture.mp4')
    assert {c['file_type'] for c in video['companions']}=={'srt','md'}
    associate(client,video['id'])
    def forbidden(*args,**kwargs):raise AssertionError('Existing transcript should bypass transcription')
    monkeypatch.setattr(local.ProcessingQueue,'transcribe',forbidden)
    result=extract(client,video['id'])
    assert result['output']['reference']=='notes/lecture.srt'
    content=client.get(f"/api/materials/{video['id']}/content").json()
    assert content['chunks'][0]['start']==1 and content['chunks'][0]['end']==4.5
    assert content['title']=='lecture.srt'
    assert client.post(f"/api/materials/{video['id']}/transcribe",json={'confirm':True}).status_code==409


def test_video_transcription_requires_explicit_action_and_override(course,monkeypatch):
    client,root=course
    scan(client)
    video=named(client,'lecture.mp4')
    associate(client,video['id'])
    assert client.post(f"/api/materials/{video['id']}/transcribe",json={}).status_code==422
    called=[]
    def transcribe(self,job_id,path,params):
        assert path.is_relative_to(library.ROOT/'data'/'processing')
        assert path.read_bytes()==(root/'videos'/'lecture.mp4').read_bytes()
        called.append(path)
        return [{'text':'Local transcript','locator':'1s → 3s','start':1,'end':3}]
    monkeypatch.setattr(local.ProcessingQueue,'transcribe',transcribe)
    result=client.post(f"/api/materials/{video['id']}/transcribe",json={'confirm':True,'ignore_existing':True})
    wait(client,result.json()['id'])
    assert len(called)==1 and not called[0].exists()


def test_changed_same_size_same_mtime_content_is_detected_and_old_sources_preserved(course):
    client,root=course
    scan(client)
    material=named(client,'Week99_unreliable.txt')
    associate(client,material['id'])
    source_id=extract(client,material['id'])['output']['source_id']
    target=root/'Week99_unreliable.txt'
    info=target.stat()
    target.write_text('X'*info.st_size,encoding='utf-8')
    os.utime(target,ns=(info.st_atime_ns,info.st_mtime_ns))
    scan(client)
    changed=named(client,target.name)
    assert changed['status']=='changed' and changed['source_id'] is None
    assert changed['content_hash']!=material['content_hash']
    assert client.get('/api/local/sources/'+source_id).status_code==200
    new_id=extract(client,material['id'])['output']['source_id']
    assert new_id!=source_id


def test_changed_companion_invalidates_video_extraction(course):
    client,root=course
    scan(client)
    video=named(client,'lecture.mp4')
    associate(client,video['id'])
    old=extract(client,video['id'])['output']['source_id']
    target=root/'notes'/'lecture.srt'
    target.write_text(target.read_text(encoding='utf-8').replace('Arteries','Veins'),encoding='utf-8')
    scan(client)
    updated=named(client,'lecture.mp4')
    assert updated['status']=='changed' and updated['source_id'] is None
    assert '配對' in updated['error']
    assert client.get('/api/local/sources/'+old).status_code==200


def test_duplicate_text_content_reuses_cache_but_keeps_distinct_provenance(course,monkeypatch):
    client,_=course
    scan(client)
    a=named(client,'Week99_unreliable.txt');b=named(client,'duplicate.txt')
    for material in (a,b):associate(client,material['id'])
    first=extract(client,a['id'])
    def forbidden(*args,**kwargs):raise AssertionError('Content should be cached')
    monkeypatch.setattr('backend.source_import.parse_source',forbidden)
    second=extract(client,b['id'])
    assert second['output']['cached'] is True
    assert first['output']['source_id']!=second['output']['source_id']


def test_new_association_creates_new_snapshot_without_rewriting_old_questions(course):
    client,_=course
    scan(client)
    material=named(client,'duplicate.txt')
    associate(client,material['id'])
    old_id=extract(client,material['id'])['output']['source_id']
    associate(client,material['id'],week=7,topic='New topic',course='Second course')
    assert named(client,'duplicate.txt')['status']=='changed'
    new_id=extract(client,material['id'])['output']['source_id']
    old=client.get('/api/local/sources/'+old_id).json()
    new=client.get('/api/local/sources/'+new_id).json()
    assert old['course']=='HAP' and old['week']==4
    assert new['course']=='Second course' and new['week']==7


def test_file_changed_after_scan_is_rejected_before_parse(course):
    client,root=course
    scan(client)
    material=named(client,'duplicate.txt')
    associate(client,material['id'])
    (root/'duplicate.txt').write_text('Unscanned new version',encoding='utf-8')
    result=extract(client,material['id'],status='failed')
    assert '掃描後已變更' in result['error']
    assert client.get('/api/local/sources').json()==[]
    assert named(client,'duplicate.txt')['status']=='changed'


def test_missing_files_and_root_changes_do_not_expose_prior_root(course,monkeypatch,tmp_path):
    client,root=course
    scan(client)
    material=named(client,'duplicate.txt')
    # Only remove a disposable test fixture, never actual course files.
    (root/'duplicate.txt').unlink()
    scan(client)
    assert named(client,'duplicate.txt')['status']=='missing'
    assert client.post(f"/api/materials/{material['id']}/extract",json={}).status_code==422
    other=tmp_path/'another-root';other.mkdir()
    monkeypatch.setenv('COURSE_MATERIALS_DIR',str(other))
    assert items(client)==[]
    assert client.get(f"/api/materials/{material['id']}/content").status_code==404
    assert client.patch(f"/api/materials/{material['id']}/association",json={'course':'HAP','week':1,'topic':'Test'}).status_code==404


@pytest.mark.parametrize('relative',['../private.txt','/private.txt','C:/private.txt','notes/../../private.txt','notes\\private.txt'])
def test_database_path_traversal_is_rejected(course,relative):
    client,_=course
    scan(client)
    material=named(client,'duplicate.txt')
    associate(client,material['id'])
    with database() as conn:conn.execute('UPDATE material_files SET relative_path=? WHERE id=?',(relative,material['id']))
    assert client.post(f"/api/materials/{material['id']}/extract",json={}).status_code==403


def test_symlink_or_windows_junction_is_not_scanned_or_read(course,tmp_path):
    client,root=course
    outside=tmp_path/'private';outside.mkdir();(outside/'secret.txt').write_text('never expose this')
    link=root/'escape'
    if os.name=='nt':
        import _winapi
        if not hasattr(_winapi,'CreateJunction'):pytest.skip('Junction creation unavailable')
        _winapi.CreateJunction(str(outside),str(link))
    else:
        link.symlink_to(outside,target_is_directory=True)
    try:
        result=scan(client)
        assert not any('secret' in m['filename'] for m in items(client))
        assert any('略過連結' in w for w in result['output']['warnings'])
        with pytest.raises(Exception) as error:library.resolve_relative(root,'escape/secret.txt')
        assert error.value.status_code==403
    finally:
        # Remove just the disposable link; leave its target and contents untouched.
        if os.name=='nt':link.rmdir()
        else:link.unlink()


def test_unknown_ids_and_arbitrary_paths_in_request_are_rejected(course):
    client,_=course
    scan(client)
    material=named(client,'duplicate.txt')
    associate(client,material['id'])
    assert client.post('/api/materials/unknown/extract',json={}).status_code==404
    assert client.post(f"/api/materials/{material['id']}/extract",json={'path':'C:/Users/private.txt'}).status_code==422
    assert client.get('/api/materials?limit=201').status_code==422


def test_unconfigured_library_does_not_break_games(course,monkeypatch):
    client,_=course
    monkeypatch.delenv('COURSE_MATERIALS_DIR')
    assert client.get('/api/materials').json()['configured'] is False
    assert client.post('/api/materials/scan').status_code==503
    assert client.post('/api/attempts',json={'question_id':'w1-01','answer':'Medial'}).json()['status']=='correct'
    initialize()
    assert client.get('/api/progress').json()['attempts']==1


def test_backend_env_loads_configured_external_root_and_respects_environment(tmp_path,monkeypatch):
    from backend.config import load_backend_env
    envfile=tmp_path/'backend.env'
    envfile.write_text('COURSE_MATERIALS_DIR="D:/NTU/Human_Anatomy_and_Physiology"\n',encoding='utf-8')
    monkeypatch.delenv('COURSE_MATERIALS_DIR',raising=False)
    assert load_backend_env(envfile)
    assert os.environ['COURSE_MATERIALS_DIR']=='D:/NTU/Human_Anatomy_and_Physiology'
    monkeypatch.setenv('COURSE_MATERIALS_DIR',str(tmp_path))
    load_backend_env(envfile)
    assert os.environ['COURSE_MATERIALS_DIR']==str(tmp_path)


def test_external_pdf_extraction_keeps_page_numbers_and_original_bytes(course):
    pymupdf=pytest.importorskip('pymupdf')
    client,root=course
    pdf=root/'handout.pdf'
    with pymupdf.open() as document:
        document.new_page().insert_text((30,30),'First lecture page.')
        document.new_page().insert_text((30,30),'Second lecture page.')
        document.save(pdf)
    original=pdf.read_bytes()
    scan(client)
    material=named(client,'handout.pdf')
    associate(client,material['id'])
    extract(client,material['id'])
    chunks=client.get(f"/api/materials/{material['id']}/content").json()['chunks']
    assert [c['page'] for c in chunks]==[1,2]
    assert pdf.read_bytes()==original


def test_manually_associated_notes_can_match_a_differently_named_video(course):
    client,root=course
    (root/'videos'/'camera_recording.mp4').write_bytes(b'second video fixture')
    scan(client)
    video=named(client,'camera_recording.mp4');notes=named(client,'Week99_unreliable.txt')
    assert video['companions']==[]
    associate(client,video['id'],week=5,topic='Manual link')
    associate(client,notes['id'],week=5,topic='Manual link')
    updated=named(client,'camera_recording.mp4')
    assert [c['id'] for c in updated['companions']]==[notes['id']]
    assert extract(client,video['id'])['output']['reference']=='Week99_unreliable.txt'

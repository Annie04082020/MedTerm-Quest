import json
import time

from backend.test_material_library import course,scan,items,named,wait
from backend.material_classification import filename_proposal
from backend.storage import database


def suggest(client):
    result=client.post('/api/materials/classifications/suggest')
    assert result.status_code==202
    wait(client,result.json()['id'])
    return client.get('/api/materials/classifications').json()


def batch_item(proposal,week=4,topic='Blood vessels'):
    return {k:proposal[k] for k in ('material_id','content_hash','course')}|{'week':week,'topic':topic}


def test_structured_filename_hints_do_not_treat_dates_or_week99_as_valid():
    p=filename_proposal('Handout 4-1_Peripheral circulation system.pdf')
    assert p['week']==4 and p['lecture_code']=='4-1' and p['topic']=='Peripheral circulation system'
    assert filename_proposal('Lecture 5-2_Lung cancer.pdf · Oct 11 — notes.md')['week']==5
    assert filename_proposal('Anatomy & Physiology_Sep 2026.pdf')['week'] is None
    assert filename_proposal('Week99_unreliable.txt')['week'] is None


def test_suggestions_never_apply_classifications_without_confirmation(course):
    client,root=course
    (root/'Handout 4-1_Blood.txt').write_text('Arteries carry blood away from the heart.',encoding='utf-8')
    scan(client);proposals=suggest(client)
    p=next(p for p in proposals if p['filename']=='Handout 4-1_Blood.txt')
    assert p['week']==4
    assert named(client,'Handout 4-1_Blood.txt')['week'] is None
    assert client.get('/api/local/sources').json()==[]
    response=client.post('/api/materials/classifications/confirm',json={'items':[batch_item(p,7,'Corrected topic')]})
    assert response.status_code==200
    actual=named(client,'Handout 4-1_Blood.txt')
    assert actual['week']==7 and actual['topic']=='Corrected topic' and actual['pipeline_stage']=='classified'
    confirmed=next(p for p in client.get('/api/materials/classifications').json() if p['material_id']==actual['id'])
    assert confirmed['week']==7 and confirmed['topic']=='Corrected topic' and confirmed['status']=='confirmed'


def test_batch_conflict_rolls_back_every_association(course):
    client,_=course
    scan(client);proposals=suggest(client)
    first,second=proposals[:2]
    with database() as c:c.execute('UPDATE material_files SET content_hash=? WHERE id=?',('0'*64,second['material_id']))
    response=client.post('/api/materials/classifications/confirm',json={'items':[batch_item(first),batch_item(second)]})
    assert response.status_code==409
    assert all(m['week'] is None for m in items(client))


def test_batch_extracts_text_sequentially_but_never_transcribes_video(course,monkeypatch):
    from backend.local_processing import ProcessingQueue
    client,_=course
    scan(client);proposals=suggest(client)
    selected=[p for p in proposals if p['filename'] in ('lecture.mp4','lecture.srt')]
    def forbidden(*args,**kwargs):raise AssertionError('Batch classification must not transcribe')
    monkeypatch.setattr(ProcessingQueue,'transcribe',forbidden)
    response=client.post('/api/materials/classifications/confirm',json={'items':[batch_item(p) for p in selected],'extract_text':True})
    assert response.status_code==200,response.text
    assert len(response.json()['job_ids'])==1 and len(response.json()['videos_not_transcribed'])==1
    wait(client,response.json()['job_ids'][0])
    assert named(client,'lecture.srt')['pipeline_stage']=='ready_for_generation'
    assert named(client,'lecture.mp4')['status']=='classified'


def test_pdf_metadata_is_preserved_as_review_evidence(course):
    import pytest
    pymupdf=pytest.importorskip('pymupdf')
    client,root=course
    path=root/'General handout.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((25,25),'Respiratory physiology')
        doc.set_metadata({'title':'Lecture 5-1 Respiratory physiology'})
        doc.save(path)
    scan(client)
    proposal=next(p for p in suggest(client) if p['filename']==path.name)
    assert proposal['week']==5
    assert proposal['metadata']['pdf_title']=='Lecture 5-1 Respiratory physiology'
    assert proposal['metadata']['first_heading']=='Respiratory physiology'

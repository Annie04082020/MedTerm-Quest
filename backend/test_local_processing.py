import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
import httpx
import pytest
from pydantic import ValidationError

from backend.main import app, initialize
from backend import local_processing as local
from backend.ollama_local import LocalAIError, OllamaLocal, ResourceReleaseError
from backend.source_import import transcript_chunks, split_text
from backend.storage import database

SOURCE = 'Arteries carry blood away from the heart.'
GENERATED = {
    'kind':'multiple_choice', 'prompt':'Which vessels carry blood away from the heart?',
    'prompt_zh':'哪一類血管將血液帶離心臟？', 'difficulty':'Foundation',
    'answer':'Arteries', 'explanation_zh':'動脈將血液帶離心臟，依照血流方向定義。',
    'terms':['artery 動脈'], 'choices':['Arteries','Veins','Venules','Lymphatics'],
    'evidence':SOURCE, 'uncertain':True,
}
MODEL = {'name':'qwen3:4b', 'size':2500000000, 'digest':'test-digest', 'details':{'quantization_level':'Q4_K_M'}}


def fake_request(self, method, endpoint, payload=None, timeout=4):
    if endpoint == '/api/tags':
        return {'models':[MODEL]}
    if endpoint == '/api/show':
        return {'details': {'family':'qwen3'}}
    if endpoint == '/api/ps':
        return {'models':[]}
    if endpoint == '/api/generate':
        return {'done':True, 'response':json.dumps(GENERATED)}
    raise AssertionError('Unexpected endpoint: '+endpoint)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH', str(tmp_path/'test.sqlite3'))
    monkeypatch.setattr(local, 'IMPORTS', tmp_path/'imports')
    monkeypatch.setattr(OllamaLocal, 'request', fake_request)
    monkeypatch.setattr(local, 'hardware_status', lambda:{'ram_available_gib':8,'ram_total_gib':16,'gpus':[{'name':'test GPU','total_mib':6144,'free_mib':6000}],'warnings':[],'ffmpeg':True})
    with TestClient(app) as client:
        yield client


def wait_job(client, job_id, expected='completed'):
    end = time.monotonic()+8
    while time.monotonic()<end:
        response = client.get('/api/local/jobs/'+job_id)
        assert response.status_code == 200
        job = response.json()
        if job['status'] in ('completed','failed','cancelled'):
            assert job['status'] == expected, job
            return job
        time.sleep(.03)
    pytest.fail('Queue did not finish in time')


def import_text(client, content=SOURCE, filename='lecture.txt', week=4):
    response = client.post('/api/local/imports', params={'filename':filename,'week':week,'topic':'Imported vascular lesson'}, content=content.encode())
    assert response.status_code == 202, response.text
    return wait_job(client, response.json()['id'])['output']['source_id']


def generate(client, source_id, **options):
    response = client.post('/api/local/generate', json={'source_id':source_id,'count':1,**options})
    assert response.status_code == 202, response.text
    return wait_job(client, response.json()['id'])


def test_import_model_draft_cannot_be_published_by_learner_flags_and_preserves_progress(client):
    client.post('/api/attempts',json={'question_id':'w1-01','answer':'Medial'})
    source_id=import_text(client)
    assert client.get('/api/local/sources').json()[0]['week']==4
    generate(client,source_id)
    assert len(client.get('/api/questions').json())==16
    draft=client.get('/api/local/drafts').json()[0]
    assert draft['payload']['source']['source_id']==source_id
    assert draft['payload']['source']['quote']==SOURCE
    endpoint='/api/local/drafts/'+draft['id']+'/publish'
    assert client.post(endpoint,json={'question':draft['payload'],'reviewed':False}).status_code==422
    assert client.post(endpoint,json={'question':draft['payload'],'reviewed':True}).status_code==422
    response=client.post(endpoint,json={'question':draft['payload'],'reviewed':True,'acknowledge_uncertainty':True})
    assert response.status_code==409
    assert response.json()['detail']['assessment']['status']=='needs_expert_review'
    assert len(client.get('/api/questions?week=4').json())==0
    initialize()
    assert client.get('/api/progress').json()['attempts']==1
    assert client.get('/api/progress').json()['total_questions']==16
    assert len(client.get('/api/local/drafts').json())==1


def test_repeated_generation_reuses_validated_cache(client, monkeypatch):
    source_id=import_text(client)
    calls=[]
    def counting(self,model,prompt,schema,cpu=False):
        calls.append(model)
        return schema.model_validate(GENERATED)
    monkeypatch.setattr(OllamaLocal,'generate',counting)
    first=generate(client,source_id)
    second=generate(client,source_id)
    assert first['output']['draft_ids']==second['output']['draft_ids']
    assert len(calls)==1


def test_source_evidence_and_invalid_json_never_publish(client, monkeypatch):
    source_id=import_text(client)
    def invented(self,*args,**kwargs):
        return local.GeneratedContent.model_validate({**GENERATED,'evidence':'Invented evidence that does not exist in this lecture.'})
    monkeypatch.setattr(OllamaLocal,'generate',invented)
    response=client.post('/api/local/generate',json={'source_id':source_id,'count':1})
    job=wait_job(client,response.json()['id'],'failed')
    assert '證據不在來源' in job['error']
    assert client.get('/api/local/drafts').json()==[]
    assert len(client.get('/api/questions').json())==16


def test_english_terms_and_chinese_explanation_are_required():
    with pytest.raises(ValidationError):
        local.GeneratedContent.model_validate({**GENERATED,'explanation_zh':'English only explanation'})
    with pytest.raises(ValidationError):
        local.GeneratedContent.model_validate({**GENERATED,'terms':['動脈']})


def test_invalid_activity_geometry_and_matching_are_rejected():
    from backend.schemas import Source
    base={**GENERATED,'id':'test','week':1,'topic':'Test','source':Source(title='Test',section='Page 1').model_dump()}
    with pytest.raises(ValueError):
        local.validate_activity({**base,'kind':'matching','pairs':[{'id':'x','definition':'test'}],'answer':{'y':'wrong'}})
    with pytest.raises(ValueError):
        local.validate_activity({**base,'kind':'crossword','entries':[{'id':'1','row':20,'col':0,'direction':'across','length':5,'clue':'test'}],'answer':{'1':'HEART'}})


def test_timestamp_and_line_provenance_survives_chunking():
    chunks=transcript_chunks('1\n00:00:01,000 --> 00:00:03,500\n'+SOURCE+'\n\n2\n00:00:04,000 --> 00:00:06,000\nSecond source sentence.\n','.srt')
    assert chunks[0]['start']==1 and chunks[0]['end']==6
    assert len(chunks[0]['segments'])==2
    assert chunks[0]['segments'][1]['start']==4
    vtt=transcript_chunks('WEBVTT\n\n00:01.000 --> 00:03.500 align:start\n<b>artery</b>\n','.vtt')
    assert vtt[0]['text']=='artery' and vtt[0]['start']==1
    lines=transcript_chunks('first line\nsecond line','.txt')
    assert lines[0]['segments'][0]['line']==1 and lines[0]['segments'][1]['line']==2
    assert all(len(chunk['text'])<=1200 for chunk in split_text('a'*3000,'Page 1',page=1))


def test_pdf_page_reference_and_scan_error(tmp_path):
    pymupdf=pytest.importorskip('pymupdf')
    path=tmp_path/'notes.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((30,30),SOURCE)
        doc.save(path)
    chunks=local.parse_source(path)
    assert chunks[0]['page']==1 and chunks[0]['locator']=='Page 1'
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(tmp_path/'scan.pdf')
    with pytest.raises(ValueError,match='OCR'):
        local.parse_source(tmp_path/'scan.pdf')


def test_ollama_absent_does_not_break_games_or_imports(client, monkeypatch):
    def unavailable(*args,**kwargs):
        raise LocalAIError('Ollama unavailable')
    monkeypatch.setattr(OllamaLocal,'request',unavailable)
    status=client.get('/api/local/status').json()
    assert status['ollama']['available'] is False
    assert client.get('/api/health').json()['ai_enabled'] is False
    assert client.post('/api/attempts',json={'question_id':'w1-01','answer':'Medial'}).json()['status']=='correct'
    source_id=import_text(client)
    assert client.post('/api/local/generate',json={'source_id':source_id}).status_code==503


def test_cloud_models_and_aliases_are_rejected(client,monkeypatch):
    with pytest.raises(LocalAIError):
        OllamaLocal().check_model('qwen3:4b-cloud')
    with pytest.raises(LocalAIError):
        OllamaLocal().check_model('https://external/model')
    def remote(self,method,endpoint,payload=None,timeout=4):
        if endpoint=='/api/show':return {'remote_host':'https://external.example','remote_model':'cloud'}
        return fake_request(self,method,endpoint,payload,timeout)
    monkeypatch.setattr(OllamaLocal,'request',remote)
    with pytest.raises(LocalAIError,match='雲端'):
        OllamaLocal().check_model('qwen3:4b')


def test_ollama_options_and_unload_even_for_invalid_json(monkeypatch):
    calls=[]
    def request(self,method,endpoint,payload=None,timeout=4):
        calls.append((method,endpoint,payload))
        if endpoint=='/api/generate' and payload.get('prompt'):
            return {'done':True,'response':'not json'}
        return fake_request(self,method,endpoint,payload,timeout)
    monkeypatch.setattr(OllamaLocal,'request',request)
    with pytest.raises(ValidationError):
        OllamaLocal().generate('qwen3:4b','Test',local.GeneratedContent,cpu=True)
    generation=next(p for _,ep,p in calls if ep=='/api/generate' and p.get('prompt'))
    assert generation['options']['num_ctx']==4096 and generation['options']['num_gpu']==0
    assert generation['keep_alive']==0 and generation['think'] is False
    assert generation['format']['type']=='object'
    assert any(ep=='/api/generate' and p=={'model':'qwen3:4b','keep_alive':0,'stream':False} for _,ep,p in calls)
    assert all(ep not in ('/api/pull','/api/chat') for _,ep,_ in calls)


def test_http_client_uses_loopback_without_proxies_or_redirects(monkeypatch):
    captured={}
    class Client:
        def __init__(self,**kwargs):captured.update(kwargs)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,*args,**kwargs):return httpx.Response(302,headers={'location':'https://external.example'})
    monkeypatch.setattr(httpx,'Client',Client)
    with pytest.raises(LocalAIError,match='重新導向'):
        OllamaLocal().request('GET','/api/tags')
    assert captured['base_url']=='http://127.0.0.1:11434'
    assert captured['trust_env'] is False and captured['follow_redirects'] is False


def test_gpu_failure_can_fall_back_to_cpu_without_download(client,monkeypatch):
    source_id=import_text(client)
    calls=[]
    def oom(self,model,prompt,schema,cpu=False):
        calls.append(cpu)
        if not cpu:raise LocalAIError('CUDA out of memory')
        return schema.model_validate(GENERATED)
    monkeypatch.setattr(OllamaLocal,'generate',oom)
    generate(client,source_id)
    assert calls==[False,True]


def test_unconfirmed_release_prevents_all_fallback(client,monkeypatch):
    source_id=import_text(client)
    calls=[]
    def release_failed(self,model,prompt,schema,cpu=False):
        calls.append(cpu)
        raise ResourceReleaseError('out of memory; unload not confirmed')
    monkeypatch.setattr(OllamaLocal,'generate',release_failed)
    response=client.post('/api/local/generate',json={'source_id':source_id,'count':1})
    wait_job(client,response.json()['id'],'failed')
    assert calls==[False]


def test_queue_is_serial_and_cancellation_keeps_games_usable(client,monkeypatch):
    source_id=import_text(client)
    entered=threading.Event();release=threading.Event()
    def slow(self,model,prompt,schema,cpu=False):
        entered.set()
        assert release.wait(5)
        return schema.model_validate(GENERATED)
    monkeypatch.setattr(OllamaLocal,'generate',slow)
    first=client.post('/api/local/generate',json={'source_id':source_id,'count':1}).json()['id']
    assert entered.wait(4)
    second=client.post('/api/local/generate',json={'source_id':source_id,'count':1}).json()['id']
    try:
        assert client.get('/api/local/jobs/'+second).json()['status']=='queued'
        assert client.get('/api/progress').status_code==200
        assert client.post('/api/local/jobs/'+first+'/cancel').status_code==200
        assert client.post('/api/local/jobs/'+second+'/cancel').status_code==200
    finally:
        release.set()
    wait_job(client,first,'cancelled');wait_job(client,second,'cancelled')


def test_concept_grading_is_advisory_until_confirmed(client,monkeypatch):
    attempt=client.post('/api/attempts',json={'question_id':'w1-05','answer':'The anterior side of the human body.'}).json()
    advice={'concept_correct':True,'confidence':.8,'explanation_zh':'概念符合前側的定義。','spelling_errors':[],'missing_concepts':[]}
    def grade(self,model,prompt,schema,cpu=False):return schema.model_validate(advice)
    monkeypatch.setattr(OllamaLocal,'generate',grade)
    job_id=client.post('/api/local/grade',json={'attempt_id':attempt['attempt_id']}).json()['id']
    result=wait_job(client,job_id)['output']
    assert result['requires_confirmation'] is True and result['advice']['concept_correct'] is True
    assert client.get('/api/progress').json()['accuracy'] is None
    client.patch(f"/api/attempts/{attempt['attempt_id']}/review",json={'correct':True})
    assert client.get('/api/progress').json()['accuracy']==100


def test_queue_validates_limits_and_upload_paths(client):
    assert client.post('/api/local/imports?filename=notes.exe',content=b'bad').status_code==422
    assert client.post('/api/local/imports?filename=notes.txt',content=b'').status_code==422
    assert client.post('/api/local/imports?filename=notes.txt&week=0',content=b'text').status_code==422
    assert client.post('/api/local/generate',json={'source_id':'missing','count':9}).status_code==422
    assert client.post('/api/local/jobs/missing/cancel').status_code==404
    source_id=import_text(client,filename='../../lecture.txt')
    assert local.source_record(source_id)['filename']=='lecture.txt'


def test_restart_marks_interrupted_work_for_explicit_retry(client):
    client.app.state.processing_queue.close()
    job_id=local.create_job('import',{'stored_name':'missing.txt'})['id']
    local.update_job(job_id,status='running')
    replacement=local.ProcessingQueue();replacement.start()
    try:
        job=wait_job(client,job_id,'failed')
        assert '後端曾中斷' in job['error']
    finally:
        replacement.close()


def test_smaller_fallback_requires_preinstalled_model_and_permission(client,monkeypatch):
    source_id=import_text(client)
    calls=[]
    monkeypatch.setattr(OllamaLocal,'models',lambda self:[MODEL,{**MODEL,'name':'qwen3:1.7b'}])
    def generate(self,model,prompt,schema,cpu=False):
        calls.append((model,cpu))
        if model=='qwen3:4b':raise LocalAIError('out of memory')
        return schema.model_validate(GENERATED)
    monkeypatch.setattr(OllamaLocal,'generate',generate)
    response=client.post('/api/local/generate',json={'source_id':source_id,'count':1,'allow_smaller':True})
    wait_job(client,response.json()['id'])
    assert calls==[('qwen3:4b',False),('qwen3:1.7b',False)]
    assert client.get('/api/local/drafts').json()[0]['model']=='qwen3:1.7b'


def test_transcription_cuda_failure_exits_stage_before_cpu_fallback(client,monkeypatch,tmp_path):
    model=tmp_path/'small'
    model.mkdir()
    for name in ('model.bin','config.json','tokenizer.json'):(model/name).write_bytes(b'local fixture')
    monkeypatch.setenv('MEDTERM_WHISPER_MODEL_PATH',str(model))
    original_find_spec=local.importlib.util.find_spec
    monkeypatch.setattr(local.importlib.util,'find_spec',lambda name:object() if name=='faster_whisper' else original_find_spec(name))
    monkeypatch.setattr(local.shutil,'which',lambda name:'ffmpeg')
    class Extractor:
        returncode=0
        def __init__(self,*args,**kwargs):pass
        def poll(self):return 0
        def wait(self,*args,**kwargs):return 0
    monkeypatch.setattr(local.subprocess,'Popen',Extractor)
    devices=[]
    def transcribe(self,job_id,model_path,audio,device):
        devices.append(device)
        if device=='cuda':raise LocalAIError('CUDA out of memory; GPU process exited')
        return [{'text':SOURCE,'start':1,'end':5}]
    monkeypatch.setattr(local.ProcessingQueue,'transcribe_child',transcribe)
    response=client.post('/api/local/imports?filename=lecture.mp4&week=5&topic=Test',content=b'media fixture')
    job=wait_job(client,response.json()['id'])
    assert devices==['cuda','cpu']
    chunks=local.source_record(job['output']['source_id'])['chunks']
    assert chunks[0]['start']==1 and chunks[0]['end']==5


def test_other_ollama_gpu_models_force_cpu_transcription(client,monkeypatch,tmp_path):
    model=tmp_path/'small';model.mkdir()
    for name in ('model.bin','config.json','tokenizer.json'):(model/name).write_bytes(b'local fixture')
    monkeypatch.setenv('MEDTERM_WHISPER_MODEL_PATH',str(model))
    original_find_spec=local.importlib.util.find_spec
    monkeypatch.setattr(local.importlib.util,'find_spec',lambda name:object() if name=='faster_whisper' else original_find_spec(name))
    monkeypatch.setattr(local.shutil,'which',lambda name:'ffmpeg')
    monkeypatch.setattr(OllamaLocal,'running',lambda self:[{'name':'unrelated-user-model','size_vram':2000}])
    class Extractor:
        returncode=0
        def __init__(self,*args,**kwargs):pass
        def poll(self):return 0
        def wait(self,*args,**kwargs):return 0
    monkeypatch.setattr(local.subprocess,'Popen',Extractor)
    devices=[]
    def transcribe(self,job_id,model_path,audio,device):
        devices.append(device)
        return [{'text':SOURCE,'start':2,'end':6}]
    monkeypatch.setattr(local.ProcessingQueue,'transcribe_child',transcribe)
    response=client.post('/api/local/imports?filename=lecture.mp4&week=5&topic=Test',content=b'media fixture')
    wait_job(client,response.json()['id'])
    assert devices==['cpu']


def test_missing_tokenizer_prevents_any_transcription_model_load(tmp_path):
    from backend.transcribe_worker import missing_model_files
    (tmp_path/'model.bin').write_bytes(b'test')
    (tmp_path/'config.json').write_text('{}')
    assert missing_model_files(tmp_path)==['tokenizer.json']


def test_inference_read_timeout_is_not_reported_as_missing_ollama(monkeypatch):
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,*args,**kwargs):
            raise httpx.ReadTimeout('Timed out waiting for generated tokens',request=httpx.Request('POST','http://127.0.0.1:11434/api/generate'))
    monkeypatch.setattr(httpx,'Client',Client)
    with pytest.raises(LocalAIError,match='推論逾時') as error:
        OllamaLocal().request('POST','/api/generate',{'model':'qwen3:4b'},timeout=180)
    assert '請安裝' not in str(error.value) and '180' in str(error.value)

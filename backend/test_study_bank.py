import copy
import json
import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import Question,Source
from backend.study_bank import AtomicClaim,Verdict,validate_question,source_check,save_claim
from backend.storage import database

TEXT='All arteries carry blood away from the heart. All veins carry blood to the heart. Capillaries are the smallest blood vessels.'


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDTERM_DB_PATH',str(tmp_path/'bank.sqlite3'))
    with TestClient(app) as c:yield c


def fixtures():
    claim=AtomicClaim(category='function',focus_term='arteries',statement_en='All arteries carry blood away from the heart.',
      evidence=TEXT,explanation_zh='動脈將血液帶離心臟。',english_terms=['arteries'],directly_stated=True)
    q=Question(id='provisional-test',week=4,topic='Circulation',kind='multiple_choice',prompt='Which vessels carry blood away from the heart?',prompt_zh='何種血管將血液帶離心臟？',
      answer='arteries',choices=['arteries','veins','Capillaries'],explanation_zh=claim.explanation_zh,terms=['arteries'],difficulty='Foundation',source=Source(title='Lecture',section='Page 15',sample=False,source_id='s',chunk_id='c',quote=TEXT))
    verdict=Verdict(answer_supported=True,explanation_supported=True,no_contradiction=True,safe_source_only=True,distinct_aspect=True,ambiguous=False,reason_zh='符合原文',
      choices=[{'choice':x,'correct':x=='arteries','evidence':TEXT} for x in q.choices])
    return claim,q,verdict


def test_source_grounded_function_can_pass_without_definition_template():
    c,q,v=fixtures();assert source_check(c,TEXT)==[];assert validate_question(q,c,TEXT,v)==[]


@pytest.mark.parametrize('change,expected',[
 ({'explanation_zh':'動脈將血液送回心臟。'},'reversed_explicit_relationship'),
 ({'explanation_zh':'Resistance is determined by pressure difference.'},'incorrect_causality_or_direction'),
 ({'choices':['arteries','veins','insulin']},'unsupported_distractor'),
 ({'choices':['arteries','arteries','veins']},'schema'),
 ({'prompt':'A patient needs treatment. Which drug should be prescribed?'},'unsafe_clinical_extrapolation_tier_C')])
def test_adversarial_questions_fail_even_with_approving_model(change,expected):
    c,q,v=fixtures();q=q.model_copy(update=change)
    if expected=='schema':
        with pytest.raises(ValueError):validate_question(q,c,TEXT,v)
    else:assert expected in validate_question(q,c,TEXT,v)


def test_multiple_correct_verdict_and_alias_choices_are_blocked():
    c,q,v=fixtures();v.choices[1].correct=True
    assert 'ambiguous_or_incomplete_choice_verdict' in validate_question(q,c,TEXT,v)
    q=q.model_copy(update={'choices':['arteries','Artery','veins']})
    assert 'duplicate_or_alias_choices' in validate_question(q,c,TEXT,v)
    from backend.study_bank import explicit_alias
    assert explicit_alias('blood vessels','vascular system','the blood vessels or vascular system')
    assert explicit_alias('Leukocytes','white blood cells','Leukocytes (white blood cells) are involved in immune defenses.')


def test_evidence_reconstruction_never_changes_assertion(client):
    c,q,v=fixtures();c=c.model_copy(update={'evidence':'A corrupted model quote.', 'directly_stated':False})
    source={'id':'s','course':'A&P','week':4,'topic':'Circulation','title':'Lecture'}
    identity,cid,reasons=save_claim(source,{'id':'c','locator':'Page 15','text':TEXT},c)
    assert not reasons
    with database() as db:
        payload=json.loads(db.execute('SELECT payload FROM study_claims WHERE id=?',(identity,)).fetchone()[0])
        assert payload['evidence_reconstructed'] and payload['statement_en']==c.statement_en
        assert payload['raw_model_claim']['evidence']=='A corrupted model quote.'
    bad=c.model_copy(update={'statement_en':'All arteries carry blood to the heart.'})
    assert save_claim(source,{'id':'c','locator':'Page 15','text':TEXT},bad)[2]


def test_provisional_answers_do_not_change_mastery_and_reports_preserve_history(client):
    claim,q,v=fixtures()
    with database() as c:
        c.execute('INSERT INTO questions VALUES (?,?)',(q.id,q.model_dump_json()))
        c.execute('INSERT INTO study_publications VALUES (?,?,?,?,?,?,?)',(q.id,'claim','B','active',q.model_dump_json(),'','now'))
    assert client.post('/api/attempts',json={'question_id':q.id,'answer':'arteries'}).json()['status']=='correct'
    assert client.get('/api/progress').json()['mastered']==0
    assert client.post('/api/study-bank/questions/'+q.id+'/report',json={'reason':'unclear','hide':True}).status_code==200
    assert all(x['id']!=q.id for x in client.get('/api/questions').json())
    assert client.get('/api/progress').json()['attempts']==1


def test_explicit_negation_conflicts_quarantine_both_claims(client):
    c,q,v=fixtures();s={'id':'s','course':'A&P','week':4,'topic':'Circulation','title':'Lecture'}
    text='All arteries carry blood away from the heart. All arteries do not carry blood away from the heart.'
    chunk={'id':'c','locator':'Page 15','text':text}
    save_claim(s,chunk,c.model_copy(update={'evidence':text}))
    negative=c.model_copy(update={'statement_en':'All arteries do not carry blood away from the heart.','evidence':text})
    assert 'explicit_contradiction_between_claims' in save_claim(s,chunk,negative)[2]
    with database() as db:assert db.execute("SELECT COUNT(*) FROM study_claims WHERE status='supported'").fetchone()[0]==0


def test_cached_resume_after_cancel_does_not_publish_partial_question(client,monkeypatch):
    from backend.local_processing import ProcessingQueue
    from backend.ollama_local import OllamaLocal
    from backend.study_bank import Extraction,QuestionSeed,IndependentAnswer
    claim,q,v=fixtures()
    with database() as db:
        db.execute('INSERT INTO local_sources(id,title,week,topic,filename,chunks,created_at,course) VALUES (?,?,?,?,?,?,?,?)',
          ('s','Lecture',4,'Circulation','lecture.txt',json.dumps([{'id':'c','locator':'Page 15','text':TEXT}]),'now','A&P'))
    monkeypatch.setattr(OllamaLocal,'check_model',lambda *a,**kw:{'digest':'fixed'})
    calls=[]
    def llm(self,jid,params,prompt,schema):
        calls.append(schema.__name__)
        if schema is Extraction:return Extraction(claims=[claim]),'local-test'
        if schema is QuestionSeed:return QuestionSeed(prompt='What direction does blood in arteries travel relative to the heart?',prompt_zh='動脈血流相對於心臟的方向？',answer='away from the heart',explanation_zh='動脈將血液帶離心臟。'),'local-test'
        assert schema is IndependentAnswer
        with database() as db:db.execute('UPDATE local_jobs SET cancel_requested=1 WHERE id=?',(jid,))
        return IndependentAnswer(decision='supported',expected_answer='away from the heart',source_quote=TEXT,reason_zh='符合來源'),'local-test'
    monkeypatch.setattr(ProcessingQueue,'llm',llm)
    def wait(jid):
        for _ in range(160):
            j=client.get('/api/local/jobs/'+jid).json()
            if j['status'] in ('completed','failed','cancelled'):return j
            time.sleep(.03)
        pytest.fail('queue timeout')
    first=client.post('/api/study-bank/generate',json={'source_ids':['s'],'variants_per_claim':1}).json()['id']
    assert wait(first)['status']=='cancelled'
    completed_calls=list(calls)
    assert len(client.get('/api/questions').json())==16
    second=client.post('/api/local/jobs/'+first+'/retry').json()['id']
    job=wait(second);assert job['status']=='completed',job
    assert len(job['output']['published_ids'])==1
    assert calls==completed_calls
    assert calls.count('QuestionSeed')==calls.count('IndependentAnswer')==1


def test_mapping_item_ids_are_not_mistaken_for_lecture_numeric_claims():
    claim,q,v=fixtures()
    matching=q.model_copy(update={'kind':'matching','answer':{'1':'arteries','2':'veins'},'choices':[],
      'pairs':[{'id':'1','definition':'carry blood away from the heart'},{'id':'2','definition':'carry blood to the heart'}]})
    assert validate_question(matching,claim,TEXT,v)==[]
    crossword=q.model_copy(update={'kind':'crossword','answer':{'1':'ARTERIES'},'choices':[],
      'entries':[{'id':'1','row':0,'col':0,'direction':'across','length':8,'clue':'Carry blood away from the heart.'}]})
    assert validate_question(crossword,claim,TEXT,v)==[]


def test_quantity_spelling_checks_do_not_change_evidence_matching():
    from backend.study_bank import number_tokens,unit_text,present,reference_tokens
    assert '3' in number_tokens('The three components are listed.')
    assert '30' in number_tokens('約30毫米汞柱')
    assert unit_text('15 millimeters Hg')=='15 mmHg'
    assert reference_tokens('15 millimeters Hg')==reference_tokens('15 mmHg')
    assert not present('15 mmHg','15 millimeters Hg')  # Quotes remain literal.


def test_distinct_choices_with_multiple_explicit_correct_answers_are_rejected():
    text='Neutrophils are phagocytes. Monocytes are phagocytes. Macrophages are large phagocytes.'
    c,q,v=fixtures();c=c.model_copy(update={'focus_term':'Neutrophils','statement_en':'Neutrophils are phagocytes.','evidence':text,'english_terms':['Neutrophils'],'explanation_zh':'原文明述其為吞噬細胞。'})
    q=q.model_copy(update={'prompt':'Which cells are phagocytes?','answer':'Neutrophils','choices':['Neutrophils','Monocytes','Macrophages'],'explanation_zh':'原文明述其為吞噬細胞。','source':q.source.model_copy(update={'quote':text})})
    assert 'multiple_explicit_source_answers' in validate_question(q,c,text,v)


def test_incomplete_and_pronoun_claims_do_not_inflate_coverage():
    c,q,v=fixtures()
    c=c.model_copy(update={'statement_en':'Blood vessels can be divided into arteries, v','focus_term':'Blood vessels','evidence':'Blood vessels can be divided into arteries, venules, and veins.','english_terms':['Blood vessels']})
    assert 'claim_ends_inside_source_word' in source_check(c,c.evidence)
    c=c.model_copy(update={'statement_en':'Anemia is a decrease in oxygen-carrying capacity due to:','focus_term':'Anemia','evidence':'Anemia is a decrease in oxygen-carrying capacity due to: a decrease in erythrocytes.','english_terms':['Anemia']})
    assert 'incomplete_atomic_statement' in source_check(c,c.evidence)
    assert 'unresolved_pronoun_focus' in source_check(c.model_copy(update={'focus_term':'they'}),c.evidence)


def test_unproven_translation_is_withheld_without_discarding_english_fact(client):
    text='Leukocytes (white blood cells) are involved in immune defenses.'
    c=AtomicClaim(category='function',focus_term='Leukocytes',statement_en=text,evidence=text,english_terms=['Leukocytes'],
      explanation_zh='白血球參與防禦，包括產生抗體。',directly_stated=True)
    source={'id':'s','course':'A&P','week':4,'topic':'Circulation','title':'Lecture'}
    identity,cid,reasons=save_claim(source,{'id':'c','locator':'Page 10','text':text},c)
    assert not reasons
    with database() as db:p=json.loads(db.execute('SELECT payload FROM study_claims WHERE id=?',(identity,)).fetchone()[0])
    assert '抗體' not in p['explanation_zh'] and text in p['explanation_zh']
    assert '抗體' in p['raw_model_claim']['explanation_zh']
    assert p['translation_status']=='source_frame_instead_of_unproven_translation'


def test_same_source_fact_does_not_move_concepts_when_model_focus_changes(client):
    c,q,v=fixtures();s={'id':'s','course':'A&P','week':4,'topic':'Circulation','title':'Lecture'};chunk={'id':'c','locator':'Page 15','text':TEXT}
    first=save_claim(s,chunk,c)
    second=save_claim(s,chunk,c.model_copy(update={'focus_term':'the heart','english_terms':['the heart']}))
    assert first[0]==second[0] and first[1]==second[1]


def test_reference_answer_must_belong_to_target_claim_and_prompt_not_damaged():
    c,q,v=fixtures()
    other=c.model_copy(update={'statement_en':'All veins carry blood to the heart.','focus_term':'veins','english_terms':['veins']})
    assert 'answer_not_bound_to_target_claim' in validate_question(q,other,TEXT,v)
    assert 'damaged_question_text' in validate_question(q.model_copy(update={'prompt':'What is the circ:system role?'}),c,TEXT,v)


def test_withdrawal_removes_review_task_and_blocks_new_attempts_without_erasing_history(client):
    c,q,v=fixtures()
    with database() as db:
        db.execute('INSERT INTO questions VALUES (?,?)',(q.id,q.model_dump_json()))
        db.execute('INSERT INTO study_publications VALUES (?,?,?,?,?,?,?)',(q.id,'claim','B','active',q.model_dump_json(),'','now'))
    assert client.post('/api/attempts',json={'question_id':q.id,'answer':'veins'}).status_code==200
    assert client.get('/api/progress').json()['review_count']==1
    client.post('/api/study-bank/questions/'+q.id+'/report',json={'reason':'possible_error','hide':True})
    p=client.get('/api/progress').json();assert p['review_count']==0 and p['attempts']==1
    assert client.post('/api/attempts',json={'question_id':q.id,'answer':'arteries'}).status_code==410


def test_current_coverage_uses_real_page_locators_and_handles_learner_withdrawal(client):
    c,q,v=fixtures();source={'id':'s','course':'A&P','week':4,'topic':'Circulation','title':'Lecture'};chunk={'id':'c','locator':'Page 15','text':TEXT}
    with database() as db:db.execute('INSERT INTO local_sources(id,title,week,topic,filename,chunks,created_at,course) VALUES (?,?,?,?,?,?,?,?)',('s','Lecture',4,'Circulation','lecture.txt',json.dumps([chunk]),'now','A&P'))
    identity,cid,_=save_claim(source,chunk,c)
    with database() as db:db.execute('INSERT INTO study_publications VALUES (?,?,?,?,?,?,?)',(q.id,identity,'B','withdrawn',q.model_dump_json(),'learner_report','now'))
    result=client.get('/api/study-bank/coverage?source_id=s');assert result.status_code==200
    result=result.json();assert result['represented_concepts']==0
    assert 's / Page 15' in result['pages']
    assert result['remaining_gaps'][0]['locator']=='Page 15'
    assert 'learner_report' in result['remaining_gaps'][0]['details']

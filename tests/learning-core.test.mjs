import test from 'node:test';
import assert from 'node:assert/strict';
import {DAY,defaults,grade,schedule,selectDaily,startSession,nextItem,record} from '../src/learning/core.ts';
const at=new Date('2026-10-31T04:00:00Z');
function q(id,week=4,cid=id,kind='multiple_choice'){return {id,concept_id:cid,revision:1,eligible:true,deleted:false,kind,course:defaults.course,week,topic:'Circulation',prompt:id,answer:'A',accepted_answers:[],choices:['A','B'],source:{title:'Lecture',section:'Page 2',quote:'A'},explanation_zh:'原文',terms:['A'],entries:[],pairs:[],assessment:{status:'deterministic_source_verified',medically_verified:false}};}
function state(qs){return {schema:1,installation:'test',questions:qs,concepts:[],events:[],sessions:[],settings:{...defaults,count:10,minutes:30},reports:[]};}
function event(question,delta=0,rating='correct',id=crypto.randomUUID()){return {id,concept_id:question.concept_id,question_id:question.id,at:new Date(at.getTime()+delta).toISOString(),rating,eligible:true,mode:question.kind,latency_ms:3000,hint:false};}
test('scheduler spaces retrieval and never credits same-day repetitions',()=>{
 const a=q('a');const e=[event(a),event(a,3000),event(a,DAY),event(a,DAY+5000)];
 assert.equal(schedule(e,'a').level,2);assert.equal(schedule(e,'a').due,at.getTime()+DAY+3*DAY);
 assert.equal(schedule([...e,event(a,2*DAY,'incorrect')],'a').level,0);
 assert.equal(schedule([event(a,0,'hinted')],'a').level,0);
 assert.equal(schedule([event(a,0,'partial')],'a').level,0);
 assert.equal(schedule([{...event(a),eligible:false}],'a').last,null);
});
test('weekly 80/20 uses only previously learned due material and adapts without duplicates',()=>{
 const current=Array.from({length:12},(_,i)=>q('c'+i)),old=Array.from({length:4},(_,i)=>q('o'+i,2));
 const s=state([...current,...old,q('unlearned',1)]);s.events=old.map(x=>event(x,-4*DAY));
 const selected=selectDaily(s,at);assert.equal(selected.filter(q=>q.week===4).length,8);assert.equal(selected.filter(q=>q.week===2).length,2);
 s.questions=[...current.slice(0,2),...old];const adapted=selectDaily(s,at);assert.equal(adapted.length,6);assert.equal(new Set(adapted.map(q=>q.id)).size,6);
});
test('exam scope, weak concepts, hidden reports and variant rotation retain history',()=>{
 const qs=[q('a',4,'c'),q('b',4,'c'),q('outside',1)];const s=state(qs);s.events=[event(qs[0],-DAY,'incorrect')];s.settings={...s.settings,mode:'exam',scopeWeeks:[4],count:1};
 assert.equal(selectDaily(s,at)[0].id,'b');s.reports=[{question_id:'b'}];assert.equal(selectDaily(s,at)[0].id,'a');
 s.settings.week=1;assert.equal(s.events.length,1);
});
test('all six modes grade locally and mathematical distinctions survive normalization',()=>{
 for(const mode of ['multiple_choice','short_answer','true_false','clinical'])assert.equal(grade({...q(mode),kind:mode},'A'),'correct');
 for(const mode of ['matching','crossword']){const x={...q(mode),kind:mode,answer:{one:'ARTERY',two:'VEIN'}};assert.equal(grade(x,{one:'artery',two:'vein'}),'correct');assert.equal(grade(x,{one:'artery'}),'incorrect');}
 assert.equal(grade({...q('d'),answer:'6.3'},'63'),'incorrect');
 assert.equal(grade({...q('d'),answer:'HR * SV'},'HR + SV'),'incorrect');
 assert.equal(grade({...q('z'),kind:'short_answer',answer:'venous return',accepted_answers:['靜脈回流']},'靜脈回流'),'correct');
 assert.equal(grade({...q('z'),kind:'clinical'},'an unrecognized interpretation'),'needs_review');
});
test('remediation requires intervening questions, distinct successful variants and a fixed extra cap',()=>{
 const qs=[q('a',4,'target'),q('b',4,'target'),q('x'),q('y'),q('z')];const s=state(qs);s.settings.count=5;
 const session=startSession(s,at,'session');session.items=['a','x','y','z'].map(id=>({question_id:id,after:0,done:false,remedial:false}));
 record(s,session,nextItem(session),event(qs[0],0,'incorrect','fail'));
 assert.equal(session.extra,1);assert.equal(nextItem(session).question_id,'x');
 record(s,session,nextItem(session),event(qs[2],1,'correct','x'));
 // Complete intervening items and then the alternative retrieval.
 record(s,session,nextItem(session),event(qs[3],2,'correct','y'));
 const z=nextItem(session);record(s,session,z,event(qs[4],3,'correct','z'));
 record(s,session,nextItem(session),event(qs[1],4,'correct','b'));
 assert.equal(session.remediation.target.complete,false);assert.equal(session.remediation.target.successes.length,1);
 assert.equal(session.status,'complete');assert.equal(session.extra,1); // no endless/immediate final repetition
 const retry=startSession(s,at,'second');retry.items=['a','x','b','y','z'].map(id=>({question_id:id,after:0,done:false,remedial:false}));retry.remediation.target={successes:[],complete:false};
 for(const id of ['a','x','b']){const item=nextItem(retry);assert.equal(item.question_id,id);record(s,retry,item,event(qs.find(q=>q.id===id),10,'correct','success-'+id));}
 assert.equal(retry.remediation.target.complete,true);
 assert.equal(schedule(s.events,'target').level,0); // immediate corrections do not undo today's failed long-term recall
});
test('provisional success cannot be promoted and repeated submissions are idempotent',()=>{
 const a={...q('p'),assessment:{tier:'B'}},s=state([a]);const session=startSession(s,at,'p'),item=nextItem(session),e=event(a);
 record(s,session,item,e);record(s,session,item,e);assert.equal(s.events.length,1);assert.equal(s.events[0].eligible,false);assert.equal(schedule(s.events,'p').level,0);
});
test('partial recall, zero extra budget, pause and serialized resume preserve observations',()=>{
 const a=q('a'),s=state([a,q('b',4,'a'),q('x')]);s.settings.maxExtra=0;const session=startSession(s,at,'s');
 record(s,session,nextItem(session),event(s.questions.find(q=>q.id===nextItem(session).question_id),0,'partial'));
 assert.equal(session.extra,0);session.status='paused';const resumed=JSON.parse(JSON.stringify(session));resumed.status='active';assert.deepEqual(resumed.items,session.items);assert.equal(s.events.length,1);
});
test('a pending variant after a mistake waits for another concept',()=>{
 const qs=[q('a',4,'c'),q('b',4,'c'),q('x')],s=state(qs),session=startSession(s,at,'s');
 session.items=qs.map(q=>({question_id:q.id,done:false,after:0,remedial:false}));
 record(s,session,nextItem(session),event(qs[0],0,'incorrect'));
 assert.equal(nextItem(session).question_id,'x');
});
test('repeated failures remain bounded by extra budget',()=>{
 const qs=[q('a',4,'c'),q('b',4,'c'),...Array.from({length:8},(_,i)=>q('other'+i))],s=state(qs);s.settings.maxExtra=2;
 const session=startSession(s,at,'s');let tries=0;
 while(nextItem(session)){const item=nextItem(session),question=qs.find(q=>q.id===item.question_id);record(s,session,item,event(question,tries++,'incorrect'));assert.ok(tries<=12);}
 assert.ok(session.extra<=2);assert.equal(session.status,'complete');
});
test('offline numeric proof grading accepts equivalent fractions without eval or unit guessing',()=>{
 const x={...q('n'),kind:'short_answer',answer:'4',assessment:{construction_proof:{template:'ratio_calculation',result:'4'}}};
 for(const a of ['4','4.0','8/2','4 milliliter/minute'])assert.equal(grade(x,a),'correct');
 for(const a of ['40','4 mmHg','1/0','Math.random()'])assert.equal(grade(x,a),'incorrect');
});
test('daily extra budget is shared across weekly and exam sessions',()=>{
 const qs=[q('a',4,'c'),q('b',4,'c'),q('x'),q('y')],s=state(qs);s.settings.maxExtra=1;
 const earlier=startSession(s,at,'earlier');earlier.extra=1;earlier.status='complete';s.sessions.push(earlier);
 const next=startSession(s,at,'exam');next.items=['a','x','y'].map(id=>({question_id:id,done:false,after:0,remedial:false}));
 record(s,next,nextItem(next),event(qs[0],0,'incorrect'));assert.equal(next.extra,0);
});
test('demo questions are opt-in and never dilute a default course challenge',()=>{
 const course=q('course'),sample={...q('sample'),source:{title:'Demo',section:'Example',sample:true}},s=state([course,sample]);
 assert.deepEqual(selectDaily(s,at).map(q=>q.id),['course']);s.settings.includeSamples=true;
 assert.equal(selectDaily(s,at).length,2);
});
test('source hints remain assisted after pause or hiding the hint',()=>{
 const a=q('a'),s=state([a]),session=startSession(s,at,'s'),item=nextItem(session);item.hint_used=true;
 const saved=JSON.parse(JSON.stringify(session));record(s,saved,nextItem(saved),event(a));
 assert.equal(s.events[0].hint,true);assert.equal(s.events[0].rating,'hinted');assert.equal(schedule(s.events,'a').level,0);
});

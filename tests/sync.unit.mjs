import test from 'node:test';import assert from 'node:assert/strict';
import {createPackage,parsePackage,mergeSnapshot,fingerprint,effectiveReviews} from '../src/learning/sync.ts';
import {defaults,schedule} from '../src/learning/core.ts';
function fixture(){const q={id:'q',concept_id:'c',revision:2,deleted:false,eligible:true,kind:'multiple_choice',week:4,topic:'Circulation',course:defaults.course,prompt:'Which?',prompt_zh:'哪個？',answer:'Arteries',accepted_answers:[],choices:['Arteries','Veins'],pairs:[],entries:[],terms:['Arteries'],explanation_zh:'依原文所述。',difficulty:'Foundation',source:{title:'Lecture',section:'Page 15',quote:'Arteries carry blood away from the heart.'},assessment:{status:'deterministic_source_verified',medically_verified:false}};
 const e={id:'event',concept_id:'c',question_id:'q',at:'2026-10-31T04:00:00Z',rating:'correct',eligible:true,mode:q.kind,latency_ms:1000,hint:false};
 return {schema:1,installation:'local-test',questions:[q],concepts:[{concept_id:'c',revision:2,title:'Arteries',course:q.course,week:4,topic:q.topic,core_mechanism:'Blood travels away from the heart.',sources:[{source_id:'source',chunk_id:'p15',locator:'Page 15',quote:q.source.quote}],tags:['circulation']}],events:[e],settings:{...defaults},sessions:[],reports:[]};}
test('versioned packages round trip without recomputing or overwriting immutable events',async()=>{
 const original=fixture(),pack=await createPackage(original),parsed=await parsePackage(JSON.stringify(pack));
 const {state,report}=mergeSnapshot({...fixture(),questions:[],concepts:[],events:[]},{schema:1,...parsed.body});
 assert.equal(state.events.length,1);assert.equal(report.events_added,1);assert.deepEqual(state.settings,original.settings);assert.deepEqual(state.concepts,original.concepts);
 assert.equal(mergeSnapshot(state,{schema:1,...parsed.body}).report.events_added,0);
 assert.equal(mergeSnapshot(state,{schema:1,...parsed.body}).state.events.length,1);
});
test('revision updates, stale banks and deletions preserve progress and stable IDs',()=>{
 const original=fixture(),updated=structuredClone(original);updated.questions[0].revision++;updated.questions[0].prompt='New prompt';
 const a=mergeSnapshot(original,updated).state;assert.equal(a.questions[0].prompt,'New prompt');assert.deepEqual(a.events,original.events);
 assert.equal(mergeSnapshot(a,original).report.stale_ignored,1);
 const deleted=structuredClone(updated);deleted.questions[0].revision++;deleted.questions[0].deleted=true;
 const b=mergeSnapshot(a,deleted).state;assert.equal(b.questions[0].deleted,true);assert.equal(b.events.length,1);assert.equal(schedule(b.events,'c').level,1);
 assert.equal(mergeSnapshot(b,original).state.questions[0].deleted,true);
});
test('content and immutable event conflicts reject the entire merge without mutating inputs',()=>{
 const original=fixture(),incoming=structuredClone(original);incoming.questions[0].prompt='Conflicting same revision';const saved=JSON.stringify(original);
 assert.throws(()=>mergeSnapshot(original,incoming),/衝突/);assert.equal(JSON.stringify(original),saved);
 incoming.questions[0].revision++;incoming.events[0].rating='incorrect';assert.throws(()=>mergeSnapshot(original,incoming),/複習事件 ID 內容衝突/);assert.equal(JSON.stringify(original),saved);
});
test('tampering, wrong schema, ungrounded policy escalation and unsafe objects are blocked',async()=>{
 const p=await createPackage(fixture());p.body.questions[0].prompt='tampered';await assert.rejects(()=>parsePackage(JSON.stringify(p)),/完整性/);
 for(const change of [s=>s.questions[0].eligible=true,s=>s.questions[0].choices=['Arteries','Arteries'],s=>s.questions[0].source.relative_path='D:/secret']){
  const s=fixture();s.questions[0].assessment.tier='B';change(s);const bad=await createPackage(s);await assert.rejects(()=>parsePackage(JSON.stringify(bad)));
 }
 const falseCertification=fixture();falseCertification.concepts[0].assessment={medically_verified:true};await assert.rejects(()=>createPackage(falseCertification).then(p=>parsePackage(JSON.stringify(p))),/概念不可/);
 const schema=await createPackage(fixture());schema.body.schema=99;schema.sha256=await fingerprint(schema.body);await assert.rejects(()=>parsePackage(JSON.stringify(schema)),/版本/);
});
test('progress-only import requires the matching question bank and concept mapping',async()=>{
 const s=fixture(),p=await createPackage(s,'progress'),parsed=await parsePackage(JSON.stringify(p));
 assert.throws(()=>mergeSnapshot({...s,questions:[],concepts:[],events:[]},{schema:1,...parsed.body}),/題庫/);
 assert.equal(mergeSnapshot({...s,events:[]},{schema:1,...parsed.body}).state.events.length,1);
});
test('a later policy downgrade excludes provisional history without erasing it or crediting hints',()=>{
 const s=fixture();s.questions[0].assessment.tier='B';s.questions[0].eligible=false;
 assert.equal(schedule(effectiveReviews(s),'c').level,0);assert.equal(s.events.length,1);assert.equal(s.events[0].eligible,true);
 const hinted=fixture();hinted.events[0].hint=true;assert.equal(schedule(effectiveReviews(hinted),'c').level,0);
});

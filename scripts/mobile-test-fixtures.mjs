// Copies EXISTING demo exercises for CI tests. No AI and no course materials.
import fs from 'node:fs/promises';
import {createPackage,parsePackage} from '../src/learning/sync.ts';
import {defaults} from '../src/learning/core.ts';
const samples=JSON.parse(await fs.readFile('backend/sample_questions.json','utf8'));
const questions=samples.map(q=>({...q,concept_id:'sample:'+q.id,revision:1,deleted:false,eligible:false,accepted_answers:q.accepted_answers||[],choices:q.kind==='matching'?Object.values(q.answer):q.choices||[],pairs:q.pairs||[],entries:q.entries||[],assessment:{status:'sample_only',label:'測試示範題，非課程醫學驗證',medically_verified:false}}));
const concepts=questions.map(q=>({concept_id:q.concept_id,title:q.topic,course:q.course||defaults.course,week:q.week,topic:q.topic,revision:1}));
questions.forEach(q=>q.course=q.course||defaults.course);
const state={schema:1,installation:'android-test-only',questions,concepts,events:[],sessions:[],reports:[],settings:{...defaults,mode:'exam',scopeWeeks:[...new Set(questions.map(q=>q.week))],scopeTopics:[],count:16,minutes:60,includeSamples:true}};
const pkg=await createPackage(state,'bank');await parsePackage(JSON.stringify(pkg));
await fs.mkdir('data/acceptance/phase5',{recursive:true});await fs.writeFile('data/acceptance/phase5/sample-bank.json',JSON.stringify(pkg));
if(process.argv.includes('--android-assets')){const folder='android/app/src/androidTest/assets';await fs.mkdir(folder,{recursive:true});await fs.writeFile(folder+'/test-state.json',JSON.stringify(state));await fs.writeFile(folder+'/test-bank.json',JSON.stringify(pkg));}
console.log('Existing 16 demonstrations prepared as disposable test fixtures.');

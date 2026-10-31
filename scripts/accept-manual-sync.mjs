// Actual desktop-bank transfer between isolated persistent browser profiles.
import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
import {parsePackage,createPackage} from '../src/learning/sync.ts';
const root='http://127.0.0.1:8000',folder='data/acceptance/phase4';await fs.mkdir(folder,{recursive:true});
const before=await(await fetch(root+'/api/progress')).json();
const launch=profile=>chromium.launchPersistentContext(profile,{channel:'msedge',headless:true,args:['--disable-gpu']});
async function open(c){const p=await c.newPage();await p.goto(root);await p.getByRole('button',{name:'Weekly learning',exact:true}).click();return p;}
async function state(p){return p.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('medterm-learning');r.onsuccess=()=>{const tx=r.result.transaction('state'),get=tx.objectStore('state').get('root');get.onsuccess=()=>resolve(get.result);get.onerror=()=>reject(get.error);};}));}
async function exportFile(p,label,path){const d=p.waitForEvent('download');await p.getByRole('button',{name:label,exact:true}).click();await(await d).saveAs(path);return parsePackage(await fs.readFile(path,'utf8'));}
async function apply(p,path){await p.getByLabel('匯入題庫或進度檔案').setInputFiles(path);await p.getByRole('button',{name:'套用已驗證的匯入檔'}).click();await p.getByText(/匯入完成。既有作答/).waitFor();}
const a=await launch('data/acceptance/phase3/browser-profile');let b;
try{
 const pa=await open(a);await pa.getByRole('button',{name:'更新本機題庫（保留進度）'}).click();
 await pa.getByText(/54 道本機題目/).waitFor();
 const source=await state(pa);if(!source.events.length)throw Error('Missing real history');
 const combinedPath=folder+'/actual-course-and-progress.json';const pack=await exportFile(pa,'匯出題庫與進度備份',combinedPath);
 b=await launch(folder+'/receiver-final-profile');const pb=await open(b);let requests=0;await pb.route('**/api/**',r=>{requests++;return r.abort();});
 await apply(pb,combinedPath);const initial=await state(pb);
 if(JSON.stringify(initial.events)!==JSON.stringify([...source.events].sort((a,b)=>Date.parse(a.at)-Date.parse(b.at)||a.id.localeCompare(b.id))))throw Error('Review history did not survive transfer');
 if(initial.questions.filter(q=>!q.deleted).length!==54)throw Error('Question bank mismatch');
 // Repeat the same file to prove idempotency.
 await apply(pb,combinedPath);if((await state(pb)).events.length!==initial.events.length)throw Error('Duplicate history');
 await pb.getByLabel('每日題數',{exact:true}).fill('3');await pb.getByLabel('約需分鐘',{exact:true}).fill('10');await pb.getByLabel('目前週次',{exact:true}).selectOption('4');
 const start=pb.getByRole('button',{name:'開始今日挑戰'});if(await start.count())await start.click();
 await pb.locator('.question-card').waitFor();let played=0;
 while(await pb.locator('.question-card').count()){
  const id=await pb.locator('.question-card').getAttribute('data-question-id'),q=initial.questions.find(x=>x.id===id);
  if(q.kind==='multiple_choice')await pb.locator('.choices').getByText(q.answer,{exact:true}).click();
  if(q.kind==='matching')for(const [key,value] of Object.entries(q.answer))await pb.locator('#pair-'+key).selectOption(value);
  if(q.kind==='crossword')for(const e of q.entries)await pb.getByLabel(`Clue ${e.id} ${e.direction}`).fill(q.answer[e.id]);
  if(q.kind==='short_answer'||q.kind==='clinical')await pb.getByRole('textbox',{name:/Your answer/}).fill(q.answer);
  if(q.kind==='true_false'){await pb.getByText(q.answer==='True'?'True · 正確':'False · 錯誤',{exact:true}).click();if(q.answer!=='True')await pb.getByPlaceholder('Enter the corrected word or phrase…').fill(q.answer.replace(/^False:\s*/,''));}
  await pb.getByRole('button',{name:'Check answer',exact:true}).click();await pb.getByText('That’s a connection made.',{exact:true}).waitFor();await pb.getByRole('button',{name:'下一題',exact:true}).click();played++;
 }
 if(played!==3)throw Error('Incomplete receiver acceptance');
 const progressPath=folder+'/receiver-progress.json';const progress=await exportFile(pb,'匯出進度',progressPath);
 await pa.route('**/api/**',r=>r.abort());await apply(pa,progressPath);const merged=await state(pa);
 if(merged.events.length!==source.events.length+played)throw Error('New progress was not merged');
 for(const e of source.events)if(JSON.stringify(merged.events.find(x=>x.id===e.id))!==JSON.stringify(e))throw Error('Original event overwritten');
 const after=await(await fetch(root+'/api/progress')).json();if(after.attempts!==before.attempts)throw Error('SQLite attempts unexpectedly changed');
 await pb.screenshot({path:folder+'/manual-sync.png',fullPage:true});
 const report={actual_bank_questions:initial.questions.filter(q=>!q.deleted).length,archived_questions:initial.questions.filter(q=>q.deleted).length,
   source_history:source.events.length,receiver_new_attempts:played,merged_history:merged.events.length,duplicate_import_added_events:0,
   api_requests_during_receiver_import_and_play:requests,desktop_attempts_before:before.attempts,desktop_attempts_after:after.attempts,
   schema:pack.body.schema,progress_schema:progress.body.schema,real_bank_not_mocked:true,original_events_unchanged:true};
 await fs.writeFile(folder+'/real-sync.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{if(b)await b.close();await a.close();}

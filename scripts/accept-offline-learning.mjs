import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const root='http://127.0.0.1:8000',folder='data/acceptance/phase3';await fs.mkdir(folder,{recursive:true});
const snapshot=await(await fetch(root+'/api/learning/snapshot')).json();
const before=await(await fetch(root+'/api/progress')).json();
const context=await chromium.launchPersistentContext(folder+'/course-only-complete-profile',{channel:'msedge',headless:true,args:['--disable-gpu']});
let calls=0;const results=[];
try{
 const page=await context.newPage();await page.goto(root);await page.getByRole('button',{name:'Weekly learning',exact:true}).click();
 await page.getByRole('button',{name:'更新本機題庫（保留進度）'}).click();await page.getByText(`${snapshot.questions.filter(q=>!q.deleted).length} 道本機題目`,{exact:false}).waitFor();
 await page.getByLabel('每日題數',{exact:true}).fill('12');await page.getByLabel('約需分鐘',{exact:true}).fill('20');
 await page.getByLabel('目前週次',{exact:true}).selectOption('4');
 await page.route('**/api/**',route=>{calls++;return route.abort();});
 await page.getByRole('button',{name:'開始今日挑戰'}).click();await page.locator('.question-card').waitFor();
 while(await page.locator('.question-card').count()){
  const id=await page.locator('.question-card').getAttribute('data-question-id'),q=snapshot.questions.find(x=>x.id===id);if(!q)throw Error('Missing question');
  if(q.kind==='multiple_choice')await page.locator('.choices').getByText(q.answer,{exact:true}).click();
  if(q.kind==='matching')for(const [key,value] of Object.entries(q.answer))await page.locator('#pair-'+key).selectOption(value);
  if(q.kind==='crossword')for(const e of q.entries)await page.getByLabel(`Clue ${e.id} ${e.direction}`).fill(q.answer[e.id]);
  if(q.kind==='short_answer'||q.kind==='clinical')await page.getByRole('textbox',{name:/Your answer/}).fill(q.answer);
  if(q.kind==='true_false'){await page.getByText(q.answer==='True'?'True · 正確':'False · 錯誤',{exact:true}).click();if(q.answer!=='True')await page.getByPlaceholder('Enter the corrected word or phrase…').fill(q.answer.replace(/^False:\s*/,''));}
  await page.getByRole('button',{name:'Check answer',exact:true}).click();await page.getByText('That’s a connection made.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'下一題',exact:true}).click();results.push({id:q.id,kind:q.kind,source:q.source,tier:q.assessment?.tier||q.assessment?.status});
  if(results.length===3){await page.getByRole('button',{name:'暫停並保存'}).click();await page.reload();await page.getByRole('button',{name:'Weekly learning',exact:true}).click();await page.getByRole('button',{name:'繼續挑戰'}).click();await page.locator('.question-card').waitFor();calls=0;}
 }
 if(results.length!==12||new Set(results.map(q=>q.kind)).size!==6)throw Error('Incomplete real-course six-mode acceptance');if(calls)throw Error('Gameplay used API requests');if(results.some(q=>q.source.sample))throw Error('Course-only challenge selected samples');
 await page.screenshot({path:folder+'/offline-challenge.png',fullPage:true});
 const stored=await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('medterm-learning');r.onsuccess=()=>{const tx=r.result.transaction('state'),get=tx.objectStore('state').get('root');get.onsuccess=()=>resolve(get.result);get.onerror=()=>reject(get.error);};}));
 const after=await(await fetch(root+'/api/progress')).json();
 if(before.attempts!==after.attempts)throw Error('Offline activity unexpectedly changed desktop attempts');
 await fs.writeFile(folder+'/real-offline.json',JSON.stringify({results,api_calls_during_gameplay:calls,desktop_attempts_before:before.attempts,desktop_attempts_after:after.attempts,local_events:stored.events.length,session:stored.sessions.at(-1),scheduler:'interval-v1',not_fsrs:true},null,2));
 console.log(JSON.stringify({played:results.length,modes:[...new Set(results.map(x=>x.kind))],api_calls:calls,desktop_history_preserved:true}));
}finally{await context.close();}

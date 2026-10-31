import {test,expect} from '@playwright/test';
import {createPackage} from '../src/learning/sync';
import {defaults} from '../src/learning/core';

test('portable challenge plays all six modes without APIs, pauses and persists across reload',async({page,request})=>{
 const bank=(await (await request.get('http://127.0.0.1:8001/api/learning/snapshot')).json()).questions.filter((q:any)=>!q.deleted);
 await page.goto('/');await page.getByRole('button',{name:'Weekly learning',exact:true}).click();
 await page.getByRole('button',{name:'更新本機題庫（保留進度）'}).click();
 await expect(page.getByText(/道本機題目 ·/)).toContainText(`${bank.length} 道`);
 await page.getByLabel('學習模式').selectOption('exam');
 await page.getByLabel('加入示範題（預設關閉）',{exact:true}).check();
 for(const w of [...new Set(bank.map((q:any)=>q.week))]){const box=page.getByLabel(`Week ${w}`,{exact:true});if(!await box.isChecked())await box.check();}
 await page.getByLabel('每日題數',{exact:true}).fill('30');await page.getByLabel('約需分鐘',{exact:true}).fill('60');
 const attemptsBefore=(await (await request.get('http://127.0.0.1:8001/api/progress')).json()).attempts;
 let apiRequests=0;await page.route('**/api/**',route=>{apiRequests++;return route.abort();});
 await page.getByRole('button',{name:'開始今日挑戰'}).evaluate(e=>{(e as HTMLElement).click();(e as HTMLElement).click();});
 await page.locator('.question-card').waitFor();
 const modes=new Set();let played=0;
 while(await page.locator('.question-card').count()){
  const id=await page.locator('.question-card').getAttribute('data-question-id'),q=bank.find((x:any)=>x.id===id);expect(q).toBeTruthy();modes.add(q.kind);
  if(q.kind==='multiple_choice')await page.locator('.choices').getByText(q.answer,{exact:true}).click();
  if(q.kind==='matching')for(const [key,value] of Object.entries(q.answer))await page.locator('#pair-'+key).selectOption(value as string);
  if(q.kind==='crossword')for(const e of q.entries)await page.getByLabel(`Clue ${e.id} ${e.direction}`).fill(q.answer[e.id]);
  if(q.kind==='short_answer'||q.kind==='clinical')await page.getByRole('textbox',{name:/Your answer/}).fill(q.answer);
  if(q.kind==='true_false'){await page.getByText(q.answer==='True'?'True · 正確':'False · 錯誤',{exact:true}).click();if(q.answer!=='True')await page.getByPlaceholder('Enter the corrected word or phrase…').fill(q.answer.replace(/^False:\s*/,''));}
  await page.getByRole('button',{name:'Check answer',exact:true}).click();await expect(page.getByText('That’s a connection made.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'下一題',exact:true}).click();played++;
  if(played===2){await page.getByRole('button',{name:'暫停並保存'}).click();await expect(page.getByRole('button',{name:'繼續挑戰'})).toBeVisible();await page.reload();await page.getByRole('button',{name:'Weekly learning',exact:true}).click();await page.getByRole('button',{name:'繼續挑戰'}).click();await page.locator('.question-card').waitFor();apiRequests=0;}
 }
 expect([...modes].sort()).toEqual(['clinical','crossword','matching','multiple_choice','short_answer','true_false']);expect(played).toBeGreaterThanOrEqual(16);expect(apiRequests).toBe(0);
 await expect(page.getByText(/今日進度/)).toContainText('complete');
 const sessions=await page.evaluate(()=>new Promise<number>((resolve,reject)=>{const r=indexedDB.open('medterm-learning');r.onsuccess=()=>{const get=r.result.transaction('state').objectStore('state').get('root');get.onsuccess=()=>resolve(get.result.sessions.length);get.onerror=()=>reject(get.error);};}));expect(sessions).toBe(1);
 expect((await (await request.get('http://127.0.0.1:8001/api/progress')).json()).attempts).toBe(attemptsBefore);
});

test('reading a source before answering records an assisted attempt across pause and reload',async({page,request})=>{
 const snapshot=await(await request.get('http://127.0.0.1:8001/api/learning/snapshot')).json();
 const q=snapshot.questions.find((q:any)=>q.kind==='multiple_choice'&&q.eligible&&!q.deleted);expect(q).toBeTruthy();
 const pack=await createPackage({schema:1,installation:'hint-ui',questions:[q],concepts:snapshot.concepts.filter((c:any)=>c.concept_id===q.concept_id),events:[],sessions:[],reports:[],settings:{...defaults,course:q.course,week:q.week,count:1}});
 await page.goto('/');await page.getByRole('button',{name:'Weekly learning',exact:true}).click();await page.getByLabel('匯入題庫或進度檔案').setInputFiles({name:'hint.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(pack))});await page.getByRole('button',{name:'套用已驗證的匯入檔'}).click();
 await page.getByRole('button',{name:'開始今日挑戰'}).click();await page.locator('.question-card').waitFor();
 await page.getByText(`離線來源 · ${q.source.title} · ${q.source.section}`,{exact:true}).click();await expect(page.getByText('本題已使用提示；暫停後仍保留記錄。',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'暫停並保存'}).click();await page.reload();await page.getByRole('button',{name:'Weekly learning',exact:true}).click();await page.getByRole('button',{name:'繼續挑戰'}).click();await page.locator('.question-card').waitFor();
 await page.locator('.choices').getByText(q.answer,{exact:true}).click();await page.getByRole('button',{name:'Check answer',exact:true}).click();await expect(page.getByText('That’s a connection made.',{exact:true})).toBeVisible();
 const event=await page.evaluate(()=>new Promise<any>((resolve,reject)=>{const r=indexedDB.open('medterm-learning');r.onsuccess=()=>{const get=r.result.transaction('state').objectStore('state').get('root');get.onsuccess=()=>resolve(get.result.events.at(-1));get.onerror=()=>reject(get.error);};}));expect(event.hint).toBe(true);expect(event.rating).toBe('hinted');
});

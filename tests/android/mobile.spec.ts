import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const path=fs.existsSync('data/exports/peripheral-circulation-bank-v1.json')?'data/exports/peripheral-circulation-bank-v1.json':'data/acceptance/phase5/sample-bank.json';
const bank=JSON.parse(fs.readFileSync(path,'utf8')).body;
test('empty offline shell imports a local bank and plays six modes without APIs',async({page,context})=>{
 let apis=0;await page.route('**/api/**',r=>{apis++;return r.abort();});
 await page.goto('/');await expect(page.getByText('先匯入課程題庫',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'題庫交換',exact:true}).click();
 await page.getByLabel('匯入題庫或進度檔案').setInputFiles(path);await page.getByRole('button',{name:'套用已驗證的匯入檔'}).click();await expect(page.getByText(/匯入完成。既有作答/)).toBeVisible();
 await page.getByRole('button',{name:'每日挑戰',exact:true}).click();
 if(bank.questions.some((q:any)=>q.source.sample))await page.getByLabel('加入示範題（預設關閉）').check();
 await page.getByLabel('學習模式').selectOption('exam');
 const weeks=[...new Set<number>(bank.questions.filter((q:any)=>!q.deleted).map((q:any)=>q.week))];
 for(const w of weeks)await page.getByLabel('Week '+w,{exact:true}).check();
 await page.getByLabel('每日題數',{exact:true}).fill('16');await page.getByLabel('約需分鐘',{exact:true}).fill('60');
 await context.setOffline(true);await page.getByRole('button',{name:'開始今日挑戰'}).click();await page.locator('.question-card').waitFor();
 const modes=new Set();let played=0;
 while(await page.locator('.question-card').count()){
  const id=await page.locator('.question-card').getAttribute('data-question-id'),q=bank.questions.find((x:any)=>x.id===id);expect(q).toBeTruthy();modes.add(q.kind);
  if(q.kind==='multiple_choice')await page.locator('.choices').getByText(q.answer,{exact:true}).click();
  if(q.kind==='matching')for(const [key,value] of Object.entries(q.answer))await page.locator('#pair-'+key).selectOption(value as string);
  if(q.kind==='crossword')for(const e of q.entries)await page.getByLabel(`Clue ${e.id} ${e.direction}`).fill(q.answer[e.id]);
  if(q.kind==='short_answer'||q.kind==='clinical')await page.getByRole('textbox',{name:/Your answer/}).fill(q.answer);
  if(q.kind==='true_false'){await page.getByText(q.answer==='True'?'True · 正確':'False · 錯誤',{exact:true}).click();if(q.answer!=='True')await page.getByPlaceholder('Enter the corrected word or phrase…').fill(q.answer.replace(/^False:\s*/,''));}
  await page.getByRole('button',{name:'Check answer',exact:true}).click();await expect(page.locator('.answer-result.correct')).toBeVisible();await page.getByRole('button',{name:'下一題',exact:true}).click();played++;
 }
 expect(modes.size).toBe(6);expect(played).toBe(16);expect(apis).toBe(0);
 await page.screenshot({path:'test-results/mobile-offline.png',fullPage:true});
 await context.setOffline(false);await page.reload();await expect(page.getByText(/今日進度/)).toContainText('complete');
 await page.getByRole('button',{name:'學習紀錄',exact:true}).click();await expect(page.getByText(/16 筆作答/)).toBeVisible();
});
test('free practice uses local sessions and retains them after restart',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'題庫交換',exact:true}).click();await page.getByLabel('匯入題庫或進度檔案').setInputFiles(path);await page.getByRole('button',{name:'套用已驗證的匯入檔'}).click();
 await page.getByRole('button',{name:'每日挑戰',exact:true}).click();if(bank.questions.some((q:any)=>q.source.sample))await page.getByLabel('加入示範題（預設關閉）').check();
 await page.getByRole('button',{name:'自由練習',exact:true}).click();await page.getByLabel('自由練習玩法').selectOption('multiple_choice');await page.getByRole('button',{name:'開始自由練習',exact:true}).click();await page.locator('.question-card').waitFor();
 const id=await page.locator('.question-card').getAttribute('data-question-id');
 await page.getByRole('button',{name:'暫停自由練習',exact:true}).click();await page.reload();await page.getByRole('button',{name:'自由練習',exact:true}).click();await page.getByRole('button',{name:'繼續自由練習',exact:true}).click();await expect(page.locator('.question-card')).toHaveAttribute('data-question-id',id!);
 const q=bank.questions.find((q:any)=>q.id===id);await page.locator('.choices').getByText(q.answer,{exact:true}).click();await page.getByRole('button',{name:'Check answer',exact:true}).click();await expect(page.locator('.answer-result.correct')).toBeVisible();
});

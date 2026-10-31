// Real production SQLite/browser acceptance. No intercepted requests or model mocks.
import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
const root=process.env.MEDTERM_ACCEPTANCE_URL;
if(!root)throw Error('Set MEDTERM_ACCEPTANCE_URL to a backend using a SQLite COPY. This script writes acceptance attempts; do not use a learner database.');
const before=await (await fetch(root+'/api/progress')).json();
const questions=(await (await fetch(root+'/api/questions')).json()).filter(q=>q.assessment?.tier==='B');
const answers=JSON.parse(await fs.readFile('data/acceptance/meaningful-bank/playable-questions.json','utf8'));
for(const q of questions)q.answer=answers.find(x=>x.id===q.id)?.answer;
if(!questions.length)throw Error('No real provisional questions');
const browser=await chromium.launch({channel:'msedge',args:['--disable-gpu']});
const page=await browser.newPage();const results=[];
try {
 await page.goto(root);
 await page.getByRole('button',{name:'Practice studio',exact:true}).click();
 await page.getByLabel('Practice bank').selectOption('provisional');
 for(const q of questions){
  await page.getByLabel('Search questions or terms').fill(q.prompt);
  for(let i=0;i<questions.length;i++){
   if(await page.locator('.question-card').getAttribute('data-question-id')===q.id)break;
   await page.getByRole('button',{name:/Next activity|Back to first/}).click();
  }
  if(await page.locator('.question-card').getAttribute('data-question-id')!==q.id)throw Error('Question not found '+q.id);
  if(q.kind==='multiple_choice')await page.locator('.choices').getByText(q.answer,{exact:true}).click();
  if(q.kind==='matching')for(const [key,value] of Object.entries(q.answer))await page.locator('#pair-'+key).selectOption(value);
  if(q.kind==='crossword')for(const e of q.entries)await page.getByLabel(`Clue ${e.id} ${e.direction}`).fill(q.answer[e.id]);
  if(q.kind==='short_answer'||q.kind==='clinical')await page.getByRole('textbox',{name:/Your answer/}).fill(q.answer);
  if(q.kind==='true_false'){
   const yes=q.answer==='True';await page.getByText(yes?'True · 正確':'False · 錯誤',{exact:true}).click();
   if(!yes)await page.getByPlaceholder('Enter the corrected word or phrase…').fill(q.answer.replace(/^False:\s*/,''));
  }
  await page.getByRole('button',{name:'Check answer',exact:true}).click();
  await page.getByText('That’s a connection made.',{exact:true}).waitFor();
  const link=page.getByRole('link',{name:'查看原文頁碼／時間戳',exact:true});
  const source=await page.request.get(new URL(await link.getAttribute('href'),root).href);
  if(!source.ok())throw Error('Source unavailable '+q.id);
  results.push({id:q.id,kind:q.kind,status:'correct',source_status:source.status(),source:q.source});
 }
 await page.screenshot({path:'data/acceptance/meaningful-bank/real-gameplay.png',fullPage:true});
 const after=await (await fetch(root+'/api/progress')).json();
 if(after.mastered!==before.mastered)throw Error('Provisional practice advanced mastery');
 if(after.attempts-before.attempts!==questions.length)throw Error('Attempt persistence mismatch');
 await fs.writeFile('data/acceptance/meaningful-bank/real-gameplay.json',JSON.stringify({before,after,results,no_mock_requests:true},null,2));
 console.log(JSON.stringify({played:results.length,modes:[...new Set(results.map(x=>x.kind))],mastered_before:before.mastered,mastered_after:after.mastered}));
} finally {await browser.close();}

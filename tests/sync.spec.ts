import {test,expect} from '@playwright/test';
import {createPackage} from '../src/learning/sync';
import {defaults,type State} from '../src/learning/core';

test('manual file import updates and retires questions while retaining progress; conflicts roll back',async({page,request})=>{
 const snapshot=await(await request.get('http://127.0.0.1:8001/api/learning/snapshot')).json();
 const question=snapshot.questions.find((q:any)=>q.kind==='multiple_choice'&&!q.deleted);
 const data:State={...snapshot,installation:'sync-ui',settings:{...defaults},sessions:[],reports:[],events:[{id:'sync-review',question_id:question.id,concept_id:question.concept_id,mode:question.kind,at:'2026-10-31T03:00:00Z',rating:'correct',eligible:false,hint:false,latency_ms:2200}]};
 await page.goto('/');await page.getByRole('button',{name:'Weekly learning',exact:true}).click();await expect(page.getByText(/0 道本機題目/)).toBeVisible();
 let requests=0;await page.route('**/api/**',r=>{requests++;return r.abort();});
 async function upload(state:State){const p=await createPackage(state);await page.getByLabel('匯入題庫或進度檔案').setInputFiles({name:'study.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(p))});}
 async function apply(){await page.getByRole('button',{name:'套用已驗證的匯入檔'}).click();await expect(page.getByText(/匯入完成。既有作答/)).toBeVisible();}
 await upload(data);await expect(page.getByText(/尚未寫入。/)).toBeVisible();await expect(page.getByText(/0 道本機題目/)).toBeVisible();await apply();await expect(page.getByText(/道本機題目 ·/)).toContainText('1 筆歷史');
 const updated=structuredClone(data);const target=updated.questions.find(q=>q.id===question.id)!;target.revision++;target.prompt+=' Updated wording.';
 await upload(updated);await apply();await expect(page.getByText(/道本機題目 ·/)).toContainText('1 筆歷史');
 const conflicting=structuredClone(updated);conflicting.questions[0].revision++;conflicting.questions[0].prompt+=' Candidate change.';conflicting.events[0].rating='incorrect';
 await upload(conflicting);await expect(page.getByRole('alert')).toContainText('衝突');await expect(page.getByRole('button',{name:'套用已驗證的匯入檔'})).toHaveCount(0);
 const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'匯出題庫與進度備份',exact:true}).click();const download=await downloadEvent;const stream=await download.createReadStream();let text='';for await(const chunk of stream!)text+=chunk.toString();const exported=JSON.parse(text);expect(exported.body.events[0].rating).toBe('correct');expect(exported.body.questions.find((q:any)=>q.id===question.id).prompt).toBe(target.prompt);
 const retired=structuredClone(updated);const tombstone=retired.questions.find(q=>q.id===question.id)!;tombstone.revision++;tombstone.deleted=true;await upload(retired);await apply();await expect(page.getByText(/道本機題目 ·/)).toContainText('1 筆歷史');
 expect(requests).toBe(0);
});

test('IndexedDB transaction abort leaves the original state intact',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Weekly learning',exact:true}).click();await expect(page.getByText(/0 道本機題目/)).toBeVisible();
 const result=await page.evaluate(async()=>{
  const {updateState,readState}=await import('/src/learning/store.ts' as string);
  const before=await readState();try{await updateState((s:any)=>{s.settings.week=99;s.events.push({id:'must-not-persist'});throw Error('simulated failure');});}catch{}
  return {before,after:await readState()};
 });expect(result.after).toEqual(result.before);
});

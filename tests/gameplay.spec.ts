import { test, expect } from '@playwright/test';
import { existsSync } from 'node:fs';

test('six activity types, bilingual checking, self-review, and persistent progress', async ({page})=>{
  const aiRequests:string[]=[];
  page.on('request',request=>{if(request.url().includes('/api/local/'))aiRequests.push(request.url());});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'A good day to get curious.'})).toBeVisible();
  await expect(page.locator('.activity-card')).toHaveCount(6);
  await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true});
  await page.getByRole('button',{name:/Multiple choice 選擇題/}).click();
  await page.getByText('Medial',{exact:true}).click();
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();

  await page.getByRole('button',{name:'Term matching',exact:true}).click();
  await page.locator('#pair-a').selectOption('cardi/o');
  await page.locator('#pair-b').selectOption('neur/o');
  await page.locator('#pair-c').selectOption('oste/o');
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();

  await page.getByRole('button',{name:'True or false',exact:true}).click();
  await page.getByText('False · 錯誤').click();
  await page.getByPlaceholder('Enter the corrected word or phrase…').fill('遠離');
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();

  await page.getByRole('button',{name:'Short answer',exact:true}).click();
  await page.getByRole('textbox',{name:/Your answer/}).fill('前側');
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();

  await page.getByRole('button',{name:'Clinical connections',exact:true}).click();
  await page.getByRole('textbox',{name:/Your answer/}).fill('My answer needs a closer look.');
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('Different wording? Let’s reflect.')).toBeVisible();
  await page.getByRole('button',{name:'Review again',exact:true}).click();
  await expect(page.getByText('A useful moment to learn.')).toBeVisible();

  await page.getByRole('button',{name:'Medical crossword',exact:true}).click();
  await page.getByRole('textbox',{name:'Clue 1 across'}).fill('HEART');
  await page.getByRole('textbox',{name:'Clue 2 down'}).fill('HEMO');
  await page.getByRole('textbox',{name:'Clue 3 down'}).fill('TACHY');
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();

  await page.getByRole('button',{name:/My review/}).click();
  await expect(page.getByRole('heading',{name:/A report describes a wound/})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:/Questions practiced/})).toContainText('6');
  await expect(page.getByRole('button',{name:/Questions understood/})).toContainText('5/16');
  await expect(page.getByRole('button',{name:/Overall accuracy/})).toContainText('83%');
  await page.getByRole('button',{name:/My review/}).click();
  await page.getByRole('textbox',{name:/Your answer/}).fill('靠近體表');
  await page.getByRole('button',{name:'Check answer'}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();
  await expect(page.locator('.explanation')).toBeVisible();
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.getByRole('button',{name:/My review/}).click();
  await expect(page.getByRole('heading',{name:'A clean slate. Nice work.'})).toBeVisible();
  expect(aiRequests).toEqual([]);
});

test('mobile navigation, filters, empty state, and source library',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'A good day to get curious.'})).toBeVisible();
  await page.screenshot({path:'test-results/overview-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.getByRole('button',{name:'Open navigation'}).click();
  await page.getByRole('button',{name:'Study library'}).click();
  await expect(page.getByRole('heading',{name:'Your study library.'})).toBeVisible();
  await page.locator('.library-card').nth(1).getByRole('button',{name:'Practice'}).click();
  await expect(page.locator('#week-filter')).toHaveValue('2');
  await page.getByRole('button',{name:'Medical crossword',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Nothing here just yet.'})).toBeVisible();
  await page.locator('#week-filter').selectOption('');
  await expect(page.getByRole('textbox',{name:'Clue 1 across'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});

test('backend URL serves the built app and supports same-origin gameplay',async({page})=>{
  test.skip(!existsSync('dist/index.html'),'Run npm run build to verify single-server mode.');
  await page.goto('http://127.0.0.1:8001/');
  await expect(page.getByRole('heading',{name:'A good day to get curious.'})).toBeVisible();
  await page.getByRole('button',{name:/Multiple choice 選擇題/}).click();
  await page.getByText('Medial',{exact:true}).click();
  const response=page.waitForResponse(r=>r.url()==='http://127.0.0.1:8001/api/attempts'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Check answer'}).click();
  expect((await response).ok()).toBeTruthy();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();
});

test('local studio imports source-preserving transcripts without Ollama',async({page})=>{
  await page.route('**/api/local/status',route=>route.fulfill({json:{
    hardware:{ram_total_gib:15.7,ram_available_gib:1.1,gpus:[{name:'NVIDIA GeForce RTX 3060 Laptop GPU',total_mib:6144,free_mib:5900}],warnings:['可用 RAM 少於 3 GiB；請先關閉耗記憶體的程式。'],ffmpeg:true},
    ollama:{available:false,models:[],error:'無法連線本機 Ollama；遊戲仍可正常使用。'},
    transcription:{installed:false,model_available:false,default_model:'small'},
  }}));
  await page.goto('/');
  await page.getByRole('button',{name:'Local AI studio',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Local AI studio.'})).toBeVisible();
  await expect(page.getByText('6144 MiB VRAM')).toBeVisible();
  await expect(page.getByRole('button',{name:'Queue generation'})).toBeDisabled();
  await page.getByLabel('Lecture file',{exact:true}).setInputFiles({name:'anatomy.srt',mimeType:'text/plain',buffer:Buffer.from('1\n00:00:01,000 --> 00:00:03,500\nArteries carry blood away from the heart.\n')});
  await page.getByLabel('Course week',{exact:true}).fill('4');
  await page.getByLabel('Course topic',{exact:true}).fill('Blood vessels');
  await page.getByRole('button',{name:'Import locally',exact:true}).click();
  await expect(page.getByText('Import / transcribe · anatomy.srt')).toBeVisible();
  await expect(page.locator('.job-row').filter({hasText:'anatomy.srt'})).toContainText('completed',{timeout:15000});
  const source=page.getByLabel('Generation source',{exact:true});
  await source.selectOption({label:'W4 · anatomy.srt · 1 chunks'});
  await page.getByRole('button',{name:'Inspect source chunks'}).click();
  await expect(page.getByText('Chunk 1 · 00:00:01,000 → 00:00:03,500',{exact:true})).toBeVisible();
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'test-results/local-studio-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.locator('.sidebar').evaluate(el=>el.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/local-studio-mobile.png',fullPage:true});
});

test('learner readability controls cannot publish uncertain medical drafts',async({page})=>{
  let published=false;
  let submitted:Record<string,unknown>|null=null;
  let feedback:Record<string,unknown>|null=null;
  const payload={id:'local-browser-draft',week:4,topic:'Blood vessels',kind:'multiple_choice',prompt:'Which vessel carries blood away from the heart?',prompt_zh:'哪一類血管將血液帶離心臟？',difficulty:'Foundation',source:{title:'Local lecture',section:'Page 4',sample:false},terms:['artery 動脈'],explanation_zh:'動脈依血流方向定義，將血液帶離心臟。',answer:'Artery',accepted_answers:[],choices:['Artery','Vein','Venule','Lymphatic'],pairs:[],entries:[],rubric:[]};
  await page.route('**/api/local/status',route=>route.fulfill({json:{hardware:{ram_total_gib:16,ram_available_gib:8,gpus:[],warnings:[],ffmpeg:true},ollama:{available:true,models:[{name:'qwen3:4b',size:2500000000}],error:null},transcription:{installed:false,model_available:false,default_model:'small'}}}));
  await page.route('**/api/local/drafts',route=>route.fulfill({json:published?[]:[{id:'browser-draft',payload,evidence:'Arteries carry blood away from the heart.',uncertain:1,model:'qwen3:4b'}]}));
  await page.route('**/api/local/drafts/browser-draft/publish',async route=>{submitted=route.request().postDataJSON();published=true;await route.fulfill({json:{status:'approved',question_id:payload.id}});});
  await page.route('**/api/knowledge/drafts/browser-draft/feedback',async route=>{feedback=route.request().postDataJSON();await route.fulfill({json:{saved:true,published:false,medically_verified:false}});});
  await page.goto('/');
  await page.getByRole('button',{name:'Local AI studio',exact:true}).click();
  await expect(page.getByRole('heading',{name:payload.prompt})).toBeVisible();
  const approve=page.getByRole('button',{name:'儲存學習回饋'});
  await expect(approve).toBeDisabled();
  await page.getByRole('button',{name:'Inspect / edit full question JSON'}).click();
  await expect(page.getByLabel('Edit draft JSON')).toBeVisible();
  await page.getByLabel('我認為題目可讀、有用，而且來源相關。',{exact:true}).check();
  await expect(approve).toBeEnabled();
  await approve.click();
  await expect(page.getByText('學習回饋已儲存；沒有核准醫學內容或發布題目。',{exact:true})).toBeVisible();
  expect(feedback).toEqual({readable:true,useful:true,source_relevant:true});
  expect(submitted).toBeNull();
  expect(published).toBe(false);
});

test('external library scans, associates, reuses transcripts and opens local generation',async({page})=>{
  const aiCalls:string[]=[];
  page.on('request',r=>{if(r.url().includes('/api/local/generate')||r.url().includes('/api/local/grade'))aiCalls.push(r.url());});
  await page.goto('/');
  await page.getByRole('button',{name:'Course materials',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Course materials.'})).toBeVisible();
  await page.getByRole('button',{name:'Rescan materials',exact:true}).click();
  await expect(page.getByText('5 indexed files',{exact:true})).toBeVisible({timeout:15000});
  const video=page.locator('.material-card').filter({has:page.getByRole('heading',{name:'lecture.mp4',exact:true})});
  const unreliable=page.locator('.material-card').filter({has:page.getByRole('heading',{name:'Week99.txt',exact:true})});
  await expect(unreliable).toContainText('Week unassigned');
  await expect(unreliable).toContainText('相同內容：另有 1 個檔案');
  await expect(video.getByRole('button',{name:'Use transcript / notes',exact:true})).toBeDisabled();
  await video.getByRole('button',{name:'Edit association',exact:true}).click();
  await page.getByLabel('Material course',{exact:true}).fill('NTU HAP');
  await page.getByLabel('Material week',{exact:true}).fill('4');
  await page.getByLabel('Material topic',{exact:true}).fill('Blood vessels');
  await page.getByRole('button',{name:'Save association',exact:true}).click();
  await expect(video).toContainText('NTU HAP');
  await expect(video.getByRole('button',{name:'Transcribe video',exact:true})).toBeDisabled();
  await video.getByRole('button',{name:'Use transcript / notes',exact:true}).click();
  await expect(video).toContainText('Text ready',{timeout:15000});
  await video.getByRole('button',{name:'Inspect extracted text',exact:true}).click();
  await expect(page.getByText('Chunk 1 · 00:00:01,000 → 00:00:04,500',{exact:true})).toBeVisible();
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'test-results/material-library-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.locator('.sidebar').evaluate(el=>el.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/material-library-mobile.png',fullPage:true});
  await video.getByRole('button',{name:'Use in Local AI studio',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Local AI studio.'})).toBeVisible();
  await expect(page.getByLabel('Generation source',{exact:true}).locator('option:checked')).toContainText('lecture.srt');
  expect(aiCalls).toEqual([]);
});

test('classification proposals require batch confirmation and can queue text extraction',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'Course materials',exact:true}).click();
  await page.getByRole('button',{name:'Suggest classifications',exact:true}).click();
  const week=page.getByLabel('Suggested week Week99.txt',{exact:true});
  await expect(week).toBeVisible({timeout:15000});
  await expect(week).toHaveValue('');
  await week.fill('6');
  await page.getByLabel('Suggested course Week99.txt',{exact:true}).fill('NTU HAP');
  await page.getByLabel('Suggested topic Week99.txt',{exact:true}).fill('Blood vessels');
  await page.getByLabel('Select classification Week99.txt',{exact:true}).check();
  await page.getByLabel('確認後依序擷取所選 PDF／文字。影片仍須手動選配對或按轉錄。',{exact:true}).check();
  await page.getByRole('button',{name:'Confirm selected classifications',exact:true}).click();
  await expect(page.getByText('已確認 1 份教材；1 件文字擷取排入佇列。影片不會自動轉錄。',{exact:true})).toBeVisible();
  const material=page.locator('.material-card').filter({has:page.getByRole('heading',{name:'Week99.txt',exact:true})});
  await expect(material).toContainText('Week 6');
  await expect(material).toContainText('ready_for_generation',{timeout:15000});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'test-results/classification-milestone.png',fullPage:true});
});

test('concept approval selects a parent and varied-aspect question requests retain its stable id',async({page})=>{
  const response=await page.request.get('/api/local/sources');
  const source=(await response.json()).find((s:{filename:string})=>s.filename==='anatomy.srt');
  const content={title:'Arterial blood-flow direction',explanation_zh:'動脈依血流方向定義，將血液帶離心臟。',english_terms:[{english:'artery',synonyms:['arteries','動脈']}],core_mechanism:'動脈依血流方向定義。',learning_objectives:['Identify arterial flow direction'],difficulty:'Foundation',tags:['cardiovascular']};
  let approved=false;let generated:Record<string,unknown>|null=null;
  await page.route('**/api/local/status',route=>route.fulfill({json:{hardware:{ram_total_gib:16,ram_available_gib:8,gpus:[],warnings:[],ffmpeg:true},ollama:{available:true,models:[{name:'qwen3:4b',size:2500000000}],error:null},transcription:{installed:false,model_available:false,default_model:'small'}}}));
  await page.route('**/api/concepts?*',route=>route.fulfill({json:approved?[{concept_id:'concept-stable-test',title:content.title,variants:[],progress:{state:'unassessed'}}]:[]}));
  await page.route('**/api/concepts/drafts',route=>route.fulfill({json:approved?[]:[{id:'concept-browser-draft',concept_id:'concept-stable-test',source_id:source.id,chunk_id:'chunk-1',payload:content,evidence:'Arteries carry blood away from the heart.',source_title:'Course notes',source_locator:'Page 4',uncertain:1,model:'qwen3:4b'}]}));
  await page.route('**/api/concepts/drafts/concept-browser-draft/approve',async route=>{expect(route.request().postDataJSON()).toMatchObject({reviewed:true,acknowledge_uncertainty:true});approved=true;await route.fulfill({json:{concept_id:'concept-stable-test',status:'approved'}});});
  await page.route('**/api/local/generate',async route=>{generated=route.request().postDataJSON();await route.fulfill({json:{id:'mock-variant-job',status:'queued'}});});
  await page.goto('/');
  await page.getByRole('button',{name:'Local AI studio',exact:true}).click();
  await page.getByLabel('Generation source',{exact:true}).selectOption(source.id);
  const approve=page.getByRole('button',{name:'採用概念作為學習整理',exact:true});
  await expect(approve).toBeDisabled();
  await expect(page.getByText('qwen3:4b · Course notes · Page 4',{exact:true})).toBeVisible();
  await page.getByLabel('我認為這個概念可讀、有用，而且來源相關（不代表醫學核准）。',{exact:true}).check();
  await expect(approve).toBeDisabled();
  await page.getByLabel('我已看見不確定標記；這不是專業審查。',{exact:true}).check();
  await approve.click();
  await expect(page.getByLabel('Parent concept for variants',{exact:true})).toHaveValue('concept-stable-test');
  await page.getByLabel('Variant tested aspect',{exact:true}).selectOption('mechanism');
  await page.getByRole('button',{name:'Queue generation',exact:true}).click();
  await expect(page.getByText('產題工作已排入佇列；完成後請審核下方草稿。',{exact:true})).toBeVisible();
  expect(generated).toMatchObject({concept_id:'concept-stable-test',variant_aspect:'mechanism',count:1,source_id:source.id});
});


test('source definition can become playable without Ollama or learner medical approval',async({page})=>{
  const response=await page.request.post('/api/local/imports?filename=definition.txt&week=4&topic=Source%20definitions',
    {data:'Resistance is the measure of the friction that impedes flow.',headers:{'Content-Type':'application/octet-stream'}});
  expect(response.status()).toBe(202);
  const jobId=(await response.json()).id;
  let sourceId='';
  await expect.poll(async()=>{const job=await (await page.request.get('/api/local/jobs/'+jobId)).json();sourceId=job.output.source_id||'';return job.status;}).toBe('completed');
  await page.goto('/');
  await page.getByRole('button',{name:'Local AI studio',exact:true}).click();
  await page.getByLabel('Generation source',{exact:true}).selectOption(sourceId);
  const extracted=page.waitForResponse(r=>r.url().endsWith('/api/knowledge/extract')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Extract source claims · 擷取來源陳述',exact:true}).click();
  const extractionJob=(await (await extracted).json()).id;
  await expect.poll(async()=> (await (await page.request.get('/api/local/jobs/'+extractionJob)).json()).status,{timeout:15000}).toBe('completed');
  await expect(page.getByRole('button',{name:'建立原文定義練習',exact:true})).toBeVisible({timeout:7500});
  await page.getByRole('button',{name:'建立原文定義練習',exact:true}).click();
  await expect(page.getByText('原文定義題已通過檢查並加入遊戲；不代表獨立醫學驗證。',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Practice studio',exact:true}).click();
  await page.getByRole('textbox',{name:'Search questions or terms'}).fill('Complete the source definition');
  await expect(page.getByRole('heading',{name:/Complete the source definition/})).toBeVisible();
  await page.getByRole('textbox',{name:/Your answer/}).fill('Resistance');
  await page.getByRole('button',{name:'Check answer',exact:true}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();
  const link=page.getByRole('link',{name:'查看原文頁碼／時間戳'});
  const href=await link.getAttribute('href');expect(href).toContain('/api/knowledge/sources/');
  const evidence=await page.request.get(href!);expect(await evidence.text()).toContain('the friction that impedes flow');
});

test('lecture batch mixes practice families, reports skips and preserves progress on continuation',async({page})=>{
  const text='Pressure is the force exerted by the blood and is measured in mmHg (millimeters of mercury).\nFlow is the volume moved per unit time, and it is measured in milliliter/minute.\nResistance is the measure of the friction that impedes flow.\nF = ∆P/R';
  const response=await page.request.post('/api/local/imports?filename=batch-lecture.txt&week=4&topic=Batch%20circulation',
    {data:text,headers:{'Content-Type':'application/octet-stream'}});
  const jid=(await response.json()).id;let sourceId='';
  await expect.poll(async()=>{const j=await (await page.request.get('/api/local/jobs/'+jid)).json();sourceId=j.output.source_id||'';return j.status;}).toBe('completed');
  await page.goto('/');await page.getByRole('button',{name:'Local AI studio',exact:true}).click();
  await page.getByLabel('Generation source',{exact:true}).selectOption(sourceId);
  await page.getByRole('spinbutton',{name:'Batch question limit'}).fill('4');
  const posted=page.waitForResponse(r=>r.url().endsWith('/api/knowledge/batch')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Batch lecture practice · 整份講義產題',exact:true}).click();
  const bid=(await (await posted).json()).id;let output:{auto_published:string[];questions_per_mode:Record<string,number>}|null=null;
  await expect.poll(async()=>{const j=await (await page.request.get('/api/local/jobs/'+bid)).json();output=j.output;return j.status;},{timeout:15000}).toBe('completed');
  expect(output!.questions_per_mode).toEqual({matching:1,multiple_choice:1,short_answer:1,true_false:1});
  await expect(page.getByText(/本批自動發布 4 題/)).toBeVisible();
  await page.getByRole('button',{name:'Practice studio',exact:true}).click();
  await page.getByRole('textbox',{name:'Search questions or terms'}).fill('Hold ∆P fixed and double R');
  await expect(page.getByRole('heading',{name:/Using F=∆P\/R/})).toBeVisible();
  await page.locator('.choices').getByText('1/2',{exact:true}).click();
  await page.getByRole('button',{name:'Check answer',exact:true}).click();
  await expect(page.getByText('That’s a connection made.')).toBeVisible();
  const q=(await (await page.request.get('/api/questions')).json()).find((q:{id:string;kind:string})=>output!.auto_published.includes(q.id)&&q.kind==='multiple_choice');
  const repeat=await page.request.post('/api/knowledge/batch',{data:{source_id:sourceId,max_questions:4}});
  const rid=(await repeat.json()).id;let next:{auto_published:string[];duplicates_prevented:string[]}|null=null;
  await expect.poll(async()=>{const j=await (await page.request.get('/api/local/jobs/'+rid)).json();next=j.output;return j.status;},{timeout:15000}).toBe('completed');
  expect(next!.duplicates_prevented).toHaveLength(4);
  expect(next!.auto_published.every(id=>!output!.auto_published.includes(id))).toBe(true);
  const persisted=(await (await page.request.get('/api/questions')).json()).find((x:{id:string})=>x.id===q.id);
  expect(persisted.last_status).toBe('correct');
});

test('tiered study-bank UI selects provisional policy and reports concept-level coverage',async({page})=>{
  const source=(await (await page.request.get('/api/local/sources')).json())[0];
  let request:Record<string,unknown>|null=null;
  await page.route('**/api/study-bank/coverage?*',r=>r.fulfill({json:{meaningful_concepts:8,represented_concepts:6,concepts_with_distinct_variants:3,questions_per_mode:{multiple_choice:4,clinical:2},quarantine:[],unprocessed:[],pages:{}}}));
  await page.route('**/api/study-bank/jobs',r=>r.fulfill({json:[]}));
  await page.route('**/api/study-bank/generate',async r=>{request=r.request().postDataJSON();await r.fulfill({json:{id:'study-ui',status:'queued'}});});
  await page.route('**/api/local/jobs/study-ui',r=>r.fulfill({json:{id:'study-ui',status:'completed',stage:'暫定題庫已保存',progress:100,error:null,output:{meaningful_concepts:8,represented_concepts:6,concepts_with_distinct_variants:3,atomic_claims:12,supported_claims:10,questions_per_mode:{multiple_choice:4,clinical:2},categories:{function:5,pathway:3},quarantine:[],unprocessed:[],pages:{'Page 6':{claims:3,concepts:2,represented:2}}}}}));
  await page.goto('/');await page.getByRole('button',{name:'Local AI studio',exact:true}).click();
  await page.getByLabel('Generation source',{exact:true}).selectOption(source.id);
  await page.getByRole('button',{name:'Generate study bank',exact:true}).click();
  await expect(page.getByText('擷取的有意義概念：8；有題目：6；有不同面向變化題：3。',{exact:true})).toBeVisible();
  expect(request).toMatchObject({source_ids:[source.id],publication:'provisional_b',variants_per_claim:2});
});

test('provisional bank is labeled and reporting hides questions without medical approval',async({page})=>{
  let hidden=false;let submitted:Record<string,unknown>|null=null;
  const q={id:'provisional-ui',week:4,topic:'Circulation',kind:'multiple_choice',prompt:'What is the main function of erythrocytes?',prompt_zh:'紅血球的主要功能？',difficulty:'Foundation',source:{title:'Lecture',section:'Page 6'},terms:['erythrocytes'],choices:['gas transport','clotting','immune defense'],pairs:[],entries:[],assessment:{tier:'B',label:'暫具來源依據，未經獨立醫學驗證',medically_verified:false,long_term_mastery_eligible:false}};
  await page.route('**/api/questions',r=>r.fulfill({json:hidden?[]:[q]}));
  await page.route('**/api/study-bank/questions/provisional-ui/report',async r=>{submitted=r.request().postDataJSON();hidden=true;await r.fulfill({json:{saved:true,hidden:true,history_preserved:true}});});
  await page.goto('/');await page.getByRole('button',{name:'Practice studio',exact:true}).click();
  await page.getByLabel('Practice bank',{exact:true}).selectOption('provisional');
  await expect(page.getByText('Tier B 暫定練習 · 未經獨立醫學驗證，不計長期掌握度',{exact:true})).toBeVisible();
  page.once('dialog',d=>d.accept('來源不清楚'));
  await page.getByRole('button',{name:'回報並隱藏此題（保留紀錄）',exact:true}).click();
  await expect(page.getByRole('heading',{name:q.prompt,exact:true})).toHaveCount(0);
  expect(submitted).toMatchObject({hide:true,reason:'possible_error',note:'來源不清楚'});
});


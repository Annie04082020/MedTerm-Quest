import StudyBankPanel from './StudyBankPanel';
import KnowledgePanel, {type Assessment} from './KnowledgePanel';
import ConceptAuthoring from './ConceptAuthoring';
import { useEffect, useState, type FormEvent } from 'react';
import { AlertCircle, BookOpen, Check, ChevronRight, Cpu, FileUp, RefreshCw, ShieldCheck, Sparkles, X } from 'lucide-react';

type Model = { name:string; size:number; details?:{quantization_level?:string} };
type LocalStatus = { hardware:{ram_total_gib:number|null;ram_available_gib:number|null;gpus:{name:string;total_mib:number;free_mib:number}[];warnings:string[];ffmpeg:boolean};ollama:{available:boolean;models:Model[];error:string|null};transcription:{installed:boolean;model_available:boolean;default_model:string} };
type LocalSource = {id:string;title:string;week:number;topic:string;course?:string;chunk_count:number};
type Advice = {concept_correct:boolean;confidence:number;explanation_zh:string;spelling_errors:string[];missing_concepts:string[]};
type Job = {id:string;kind:string;status:string;stage:string;progress:number;error:string|null;cancel_requested:number;params:{filename?:string;model?:string};output:{message?:string;advice?:Advice;model?:string;requires_confirmation?:boolean}};
type Draft = {id:string;payload:Record<string,unknown>;evidence:string;uncertain:number;model:string;assessment?:Assessment};
type Settings = {model:string;device:'auto'|'cpu';allow_cpu:boolean;allow_smaller:boolean};
const initial:Settings={model:'qwen3:4b',device:'auto',allow_cpu:true,allow_smaller:false};
const kinds=[['multiple_choice','Multiple choice · 選擇題'],['short_answer','Short answer · 簡答題'],['clinical','Clinical connections · 臨床因果'],['true_false','True or false · 是非訂正'],['matching','Term matching · 詞彙配對'],['crossword','Crossword · 填字題']];

async function localApi<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch('/api/local'+path,{...init,headers:{'Content-Type':'application/json',...init?.headers}});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'本機處理失敗，請查看工作錯誤訊息。');}
  return response.json();
}
function savedSettings():Settings{try{return {...initial,...JSON.parse(localStorage.getItem('medterm-local-settings')||'{}')};}catch{return initial;}}
function saveSettings(value:Settings){try{localStorage.setItem('medterm-local-settings',JSON.stringify(value));}catch{/* Browser privacy mode may disable preferences. */}}
const isActive=(j:Job)=>j.status==='queued'||j.status==='running';

function ModelSettings({status,value,onChange}:{status:LocalStatus|null;value:Settings;onChange:(s:Settings)=>void}){
  function change(next:Settings){onChange(next);saveSettings(next);}
  return <div className="model-settings"><label>Installed Ollama model · 已安裝模型<select value={value.model} onChange={e=>change({...value,model:e.target.value})}>
    {!status?.ollama.models.some(m=>m.name===value.model)&&<option value={value.model}>{value.model}（尚未偵測到）</option>}
    {status?.ollama.models.map(m=><option key={m.name} value={m.name}>{m.name} · {(m.size/1e9).toFixed(1)} GB · {m.details?.quantization_level||'local'}</option>)}
  </select></label><label>Processing device · 執行裝置<select value={value.device} onChange={e=>change({...value,device:e.target.value as Settings['device']})}><option value="auto">GPU when available · 可用時使用 GPU</option><option value="cpu">CPU only · 僅使用 CPU</option></select></label>
  <label className="check-label"><input type="checkbox" checked={value.allow_cpu} onChange={e=>change({...value,allow_cpu:e.target.checked})}/>GPU 失敗時允許 CPU fallback（仍需要 RAM）</label>
  <label className="check-label"><input type="checkbox" checked={value.allow_smaller} onChange={e=>change({...value,allow_smaller:e.target.checked})}/>VRAM 不足時允許改用已安裝的 qwen3:1.7b</label>
  <p className="processing-hint">4K context · 每次一題 · 每批最多 8 個片段 · 不自動下載模型</p></div>;
}

export default function LocalStudio({onPublished,initialSourceId=''}:{onPublished:()=>Promise<void>;initialSourceId?:string}){
  const [status,setStatus]=useState<LocalStatus|null>(null);
  const [settings,setSettings]=useState<Settings>(savedSettings);
  const [sources,setSources]=useState<LocalSource[]>([]);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [drafts,setDrafts]=useState<Draft[]>([]);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [checking,setChecking]=useState(false);
  const [busy,setBusy]=useState(false);
  const [file,setFile]=useState<File|null>(null);
  const [week,setWeek]=useState(1);
  const [topic,setTopic]=useState('');
  const [sourceId,setSourceId]=useState(initialSourceId);
  const [conceptId,setConceptId]=useState('');
  const [aspect,setAspect]=useState('definition');
  const [kind,setKind]=useState('multiple_choice');
  const [start,setStart]=useState(1);
  const [count,setCount]=useState(2);
  const [sourcePreview,setSourcePreview]=useState<{title:string;chunks:{id:string;text:string;locator:string}[]}|null>(null);
  async function refresh(){const [s,j,d]=await Promise.all([localApi<LocalSource[]>('/sources'),localApi<Job[]>('/jobs'),localApi<Draft[]>('/drafts')]);setSources(s);setJobs(j);setDrafts(d);}
  async function check(){setChecking(true);try{setStatus(await localApi<LocalStatus>('/status'));}catch(e){setError((e as Error).message);}finally{setChecking(false);}}
  useEffect(()=>{let live=true; const poll=()=>{if(live)refresh().catch(e=>{if(live)setError(e.message);});};poll();void check();const timer=setInterval(poll,2000);return()=>{live=false;clearInterval(timer);};},[]);
  const selected=sources.find(s=>s.id===sourceId);
  const installed=!!status?.ollama.available&&status.ollama.models.some(m=>m.name===settings.model);
  async function perform(action:()=>Promise<unknown>,message:string){setBusy(true);setError('');setNotice('');try{await action();setNotice(message);await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function upload(e:FormEvent){e.preventDefault();if(!file)return;await perform(async()=>{
    const query=new URLSearchParams({filename:file.name,week:String(week),topic,device:settings.device,allow_cpu:String(settings.allow_cpu)});
    const response=await fetch('/api/local/imports?'+query,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});
    if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.detail||'匯入失敗。');}
  },'檔案已送到本機佇列。完成後可在來源選單選取，不會自動產題。');}
  async function generate(e:FormEvent){e.preventDefault();await perform(()=>localApi('/generate',{method:'POST',body:JSON.stringify({...settings,source_id:sourceId,kind,start_chunk:start-1,count:conceptId?1:count,concept_id:conceptId||null,variant_aspect:conceptId?aspect:null})}),'產題工作已排入佇列；完成後請審核下方草稿。');}
  return <>
    <div className="page-heading"><div><div className="eyebrow">YOUR MATERIALS. YOUR MODELS. YOUR MACHINE.</div><h1>Local AI studio.</h1><p>教材留在本機。先處理，再審核；遊戲不需要 AI 常駐。</p></div><button className="secondary-button" disabled={checking} onClick={check}><RefreshCw size={15}/>{checking?'Checking…':'Check hardware & models'}</button></div>
    <div className="library-notice"><ShieldCheck size={24}/><div><strong>零付費 API · 無訂閱 · 不上傳外部服務</strong><p>產題與轉錄依序執行，模型在每個階段結束後釋放。請勿在其他程式同時執行 GPU 模型。</p></div></div>
    {error&&<div className="error-banner" role="alert">{error}<button aria-label="Dismiss error" onClick={()=>setError('')}>×</button></div>}
    {notice&&<div className="processing-notice" role="status"><Check size={16}/>{notice}</div>}
    <div className="processing-grid">
      <section className="processing-panel"><div className="panel-title"><Cpu size={20}/><h2>Local setup · 本機狀態</h2></div>
        {status?<><div className="hardware-facts"><span>System RAM<strong>{status.hardware.ram_total_gib??'—'} GiB <small>· {status.hardware.ram_available_gib??'—'} GiB available</small></strong></span>{status.hardware.gpus.map(g=><span key={g.name}>{g.name}<strong>{g.total_mib} MiB VRAM <small>· {g.free_mib} MiB free</small></strong></span>)}</div>{status.hardware.warnings.map(w=><p className="processing-warning" key={w}><AlertCircle size={15}/>{w}</p>)}
          {!status.ollama.available&&<div className="processing-warning"><AlertCircle size={17}/><div>{status.ollama.error}<p>自行安裝 Ollama 並啟動後，按上方 Check hardware & models。</p></div></div>}
          {status.ollama.available&&!status.ollama.models.length&&<p className="processing-warning">未找到已安裝的本機模型；程式不會自動下載。</p>}
          <ModelSettings status={status} value={settings} onChange={setSettings}/>
          <details className="setup-details"><summary>Model setup instructions · 模型設定</summary><p>先在啟動 Ollama 的終端機設定下列環境變數，再重新啟動 Ollama，停用雲端功能：</p><pre>$env:OLLAMA_NO_CLOUD = '1'<br/>$env:OLLAMA_NUM_PARALLEL = '1'<br/>ollama serve</pre><p>確認願意下載模型後，再自行執行（約 2.5 GB）：</p><pre>ollama pull qwen3:4b</pre><p>較小備選需另行下載：<code>ollama pull qwen3:1.7b</code>。安裝後按 Check hardware & models。</p></details>
          <div className="transcription-state"><strong>faster-whisper small</strong><span>套件：{status.transcription.installed?'已安裝':'尚未安裝'} · 模型：{status.transcription.model_available?'已備妥':'尚未備妥'} · FFmpeg：{status.hardware.ffmpeg?'可用':'未找到'}</span><p>僅讀取 models/faster-whisper-small；設定方式見 README。不會在背景下載。</p></div>
        </>:<p className="processing-hint">Checking local hardware and Ollama… 遊戲仍可使用。</p>}
      </section>
      <div className="processing-forms"><section className="processing-panel"><div className="panel-title"><FileUp size={20}/><h2>1. Import material · 匯入教材</h2></div><form onSubmit={upload} className="processing-form"><label>Lecture file · 教材檔案<input aria-label="Lecture file" type="file" accept=".pdf,.txt,.srt,.vtt,.mp4,.mp3,.wav,.m4a,.webm,.mkv" onChange={e=>setFile(e.target.files?.[0]||null)}/></label><div className="input-pair"><label>Week · 週次<input aria-label="Course week" type="number" min="1" max="100" value={week} onChange={e=>setWeek(Number(e.target.value))} required/></label><label>Topic · 主題<input aria-label="Course topic" placeholder="e.g. Nervous system" value={topic} maxLength={150} onChange={e=>setTopic(e.target.value)} required/></label></div><p className="processing-hint">PDF / TXT / SRT / VTT ≤ 50 MB；影片／音訊 ≤ 500 MB。沒有 Ollama 也能匯入文字教材。</p><button className="primary-button" disabled={busy||!file||!topic.trim()} type="submit"><FileUp size={15}/>{busy?'Working…':'Import locally'}</button></form></section>
      <section className="processing-panel"><div className="panel-title"><Sparkles size={20}/><h2>2. Generate drafts · 分批產題</h2></div><form onSubmit={generate} className="processing-form"><label>Source · 已匯入教材<select aria-label="Generation source" value={sourceId} onChange={e=>{setSourceId(e.target.value);setConceptId('');setStart(1);setSourcePreview(null);}} required><option value="">Select a source…</option>{sources.map(s=><option key={s.id} value={s.id}>W{s.week} · {s.title} · {s.chunk_count} chunks</option>)}</select></label>{selected&&<button type="button" className="text-button" onClick={()=>perform(async()=>setSourcePreview(await localApi('/sources/'+sourceId)),'來源片段已載入下方。')}><BookOpen size={14}/> Inspect source chunks</button>}
      <label>Activity · 題型<select value={kind} onChange={e=>setKind(e.target.value)}>{kinds.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>{conceptId&&<label>Tested aspect · 不同測試面向<select aria-label="Variant tested aspect" value={aspect} onChange={e=>setAspect(e.target.value)}>{['definition','terminology','mechanism','comparison','application','quantitative'].map(a=><option key={a}>{a}</option>)}</select></label>}<div className="input-pair"><label>Start chunk · 起始片段<input type="number" min="1" max={selected?.chunk_count||1} disabled={!!conceptId} value={start} onChange={e=>setStart(Number(e.target.value))} required/></label><label>Batch size · 每批題數<input type="number" min="1" max={conceptId?1:8} value={conceptId?1:count} onChange={e=>setCount(Number(e.target.value))} required/></label></div><button className="primary-button" type="submit" disabled={busy||!sourceId||!installed}><Sparkles size={15}/>Queue generation</button>{!installed&&<p className="processing-hint">請先啟動 Ollama 並選取已安裝的模型；不影響一般遊戲。</p>}</form></section></div>
    </div>
    <StudyBankPanel sourceId={sourceId} week={selected?.week} course={selected?.course} settings={settings} onPublished={onPublished}/>
    <KnowledgePanel sourceId={sourceId} chunkCount={selected?.chunk_count||0} onPublished={onPublished} settings={settings}/>
    <ConceptAuthoring sourceId={sourceId} chunkCount={selected?.chunk_count||0} settings={settings} enabled={installed} selectedConcept={conceptId} onSelect={id=>{setConceptId(id);if(id)setCount(1);}}/>
    {sourcePreview&&<section className="processing-panel source-preview"><div className="panel-title"><BookOpen size={20}/><h2>{sourcePreview.title}</h2><button className="icon-button" aria-label="Close source preview" onClick={()=>setSourcePreview(null)}><X size={18}/></button></div><p className="processing-hint">共 {sourcePreview.chunks.length} 個片段；每個片段保留頁碼、原始時間戳記或行號。</p><div className="source-chunk-list">{sourcePreview.chunks.map((c,i)=><details key={c.id}><summary>Chunk {i+1} · {c.locator}</summary><pre>{c.text}</pre></details>)}</div></section>}
    <section className="processing-panel queue-panel"><div className="section-heading"><div><h2>Processing queue · 循序處理佇列</h2><p>一次一件工作。取消會等待目前模型請求結束；轉錄子程序可提早終止。</p></div><span className="subtle-pill">{jobs.filter(isActive).length} active / queued</span></div>{!jobs.length?<p className="processing-hint">還沒有工作。先匯入一份講義或逐字稿。</p>:jobs.map(j=><div className={`job-row ${j.status}`} key={j.id}><div className="job-main"><div className="job-heading"><strong>{j.kind==='import'?'Import / transcribe':j.kind==='practice_batch'?'Lecture practice batch':j.kind==='claims_extract'?'Source statements':j.kind==='generate'?'Question generation':j.kind==='concept_generate'?'Concept draft generation':j.kind==='library_scan'?'Directory scan':j.kind==='library_extract'?'External material extraction':j.kind==='library_transcribe'?'Explicit video transcription':'Conceptual grading'}{j.params.filename?' · '+j.params.filename:''}</strong><span>{j.status}</span></div><p>{j.stage}</p><div className="progress-track" role="progressbar" aria-label={j.stage} aria-valuenow={j.progress} aria-valuemin={0} aria-valuemax={100}><span style={{width:`${j.progress}%`}}/></div>{j.error&&<p className="job-error">{j.error}</p>}{j.output.advice&&<div className="job-advice"><strong>AI 建議（需自行確認） · {Math.round(j.output.advice.confidence*100)}% confidence</strong><p>{j.output.advice.explanation_zh}</p><p>拼字：{j.output.advice.spelling_errors.join('；')||'未指出'} · 概念缺漏：{j.output.advice.missing_concepts.join('；')||'未指出'}</p></div>}</div><div className="job-actions">{isActive(j)&&<button className="text-button" disabled={!!j.cancel_requested||busy} onClick={()=>perform(()=>localApi(`/jobs/${j.id}/cancel`,{method:'POST'}),'已要求取消。')}>Cancel</button>}{(j.status==='failed'||j.status==='cancelled')&&<button className="text-button" disabled={busy} onClick={()=>perform(()=>localApi(`/jobs/${j.id}/retry`,{method:'POST'}),'已建立新的重試工作。')}><RefreshCw size={13}/>Retry</button>}</div></div>)}</section>
    <section className="draft-section"><div className="section-heading"><div><h2>3. Review before practice · 題目審核</h2><p>模型自由生成的內容尚未獲語意證明；學習者只需回饋可讀性、用途及來源相關性，無須核准醫學主張。</p></div><span className="subtle-pill">{drafts.length} pending</span></div>{!drafts.length?<div className="empty-state"><ShieldCheck size={32}/><h2>No drafts waiting.</h2><p>產題完成後，待審題目會出現在這裡。</p></div>:drafts.map(d=><DraftReview key={d.id} draft={d} disabled={busy} onReject={()=>perform(()=>localApi(`/drafts/${d.id}/reject`,{method:'POST'}),'草稿已捨棄。')} onApprove={question=>perform(async()=>{void question;const response=await fetch(`/api/knowledge/drafts/${d.id}/feedback`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({readable:true,useful:true,source_relevant:true})});if(!response.ok)throw new Error('回饋儲存失敗。');},'學習回饋已儲存；沒有核准醫學內容或發布題目。')}/>)}</section>
  </>;
}

function DraftReview({draft,disabled,onReject,onApprove}:{draft:Draft;disabled:boolean;onReject:()=>void;onApprove:(q:Record<string,unknown>)=>void}){
  const [reviewed,setReviewed]=useState(false);
  
  const [editing,setEditing]=useState(false);
  const [json,setJson]=useState(JSON.stringify(draft.payload,null,2));
  const [error,setError]=useState('');
  const q=draft.payload;
  const source=q.source as {title:string;section:string};
  function approve(){try{const edited=JSON.parse(json);if(!edited||typeof edited!=='object'||Array.isArray(edited))throw new Error('請提供題目物件。');onApprove(edited);}catch(e){setError((e as Error).message);}}
  return <article className="processing-panel draft-card"><div className="job-heading"><span className="question-type sage">{String(q.kind)} · {draft.model}</span>{!!draft.uncertain&&<span className="uncertainty-badge">Uncertain · 需要專業審查</span>}</div><h3>{String(q.prompt)}</h3><p lang="zh-Hant">{String(q.prompt_zh)}</p><div className="draft-reference"><strong>{source.title} · {source.section}</strong><blockquote>{draft.evidence}</blockquote></div><dl><dt>Reference answer</dt><dd>{typeof q.answer==='string'?q.answer:JSON.stringify(q.answer)}</dd><dt>繁體中文解釋</dt><dd>{String(q.explanation_zh)}</dd><dt>Medical terms</dt><dd>{(q.terms as string[]).join(' · ')}</dd>{!!(q.rubric as string[])?.length&&<><dt>Grading rubric</dt><dd>{(q.rubric as string[]).join('；')}</dd></>}</dl><button className="text-button" onClick={()=>setEditing(!editing)}><ChevronRight size={14}/>{editing?'Hide editor':'Inspect / edit full question JSON'}</button>{editing&&<textarea className="draft-json" aria-label="Edit draft JSON" spellCheck={false} rows={14} value={json} onChange={e=>{setJson(e.target.value);setReviewed(false);}}/>}<p className="processing-hint">來源檢查與內容狀態：{draft.assessment?.label||'尚未檢查，保留供專業審查'}。這些自由生成草稿不會因學習者勾選而發布；請使用上方原文定義練習。</p><label className="check-label"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>我認為題目可讀、有用，而且來源相關。</label>{error&&<p className="inline-error">{error}</p>}<div className="draft-actions"><button disabled={disabled} className="secondary-button" onClick={onReject}>Reject draft</button><button disabled={disabled||!reviewed} className="primary-button" onClick={approve}><Check size={15}/>儲存學習回饋</button></div></article>;
}

export function LocalGrader({attemptId,onApply}:{attemptId:number;onApply:(correct:boolean)=>void}){
  const [open,setOpen]=useState(false);
  const [status,setStatus]=useState<LocalStatus|null>(null);
  const [settings,setSettings]=useState<Settings>(savedSettings);
  const [job,setJob]=useState<Job|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{if(!job||!isActive(job))return;let live=true;const timer=setInterval(()=>{localApi<Job>('/jobs/'+job.id).then(next=>{if(live)setJob(next);}).catch(e=>{if(live)setError(e.message);});},1200);return()=>{live=false;clearInterval(timer);};},[job?.id,job?.status]);
  async function show(){setOpen(!open);if(!open){try{setStatus(await localApi('/status'));}catch(e){setError((e as Error).message);}}}
  async function grade(){setBusy(true);setError('');try{const next=await localApi<{id:string}>('/grade',{method:'POST',body:JSON.stringify({...settings,attempt_id:attemptId})});setJob(await localApi('/jobs/'+next.id));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const advice=job?.output.advice;
  return <div className="local-grader"><button className="text-button" onClick={show}><Sparkles size={14}/>Optional local AI feedback · 本機概念批改</button>{open&&<div className="grader-content"><p>僅在你按下按鈕後使用 Ollama。AI 建議不會自動改變分數。</p>{!status?.ollama.available&&<p>{status?.ollama.error||'Checking Ollama…'}</p>}<ModelSettings status={status} value={settings} onChange={setSettings}/><button className="secondary-button" disabled={busy||!!job&&isActive(job)||!status?.ollama.models.some(m=>m.name===settings.model)} onClick={grade}>Queue local grading</button>{job&&<p role="status">{job.stage}{job.status==='failed'?' · '+job.error:''}</p>}{error&&<p className="inline-error">{error}</p>}{advice&&<div className="job-advice"><strong>{advice.concept_correct?'概念符合':'概念需再檢查'} · 信心 {Math.round(advice.confidence*100)}%</strong><p>{advice.explanation_zh}</p><p>拼字：{advice.spelling_errors.join('；')||'未指出'}</p><p>概念缺漏：{advice.missing_concepts.join('；')||'未指出'}</p>{advice.confidence<.7&&<p>信心較低，請自行比對來源。</p>}<button className="primary-button" onClick={()=>onApply(advice.concept_correct)}>我已檢查，採用此建議</button></div>}</div>}</div>;
}

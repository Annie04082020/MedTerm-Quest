import {useEffect,useRef,useState} from 'react';

type Settings={model:string;device:'auto'|'cpu';allow_cpu:boolean;allow_smaller:boolean};
type Coverage={meaningful_concepts:number;represented_concepts:number;concepts_with_distinct_variants:number;atomic_claims:number;supported_claims:number;questions_per_mode:Record<string,number>;categories:Record<string,number>;quarantine:{question_id?:string;claim_id?:string;reason:string|string[]}[];unprocessed:{locator:string;reason:string}[];remaining_gaps?:{claim_id:string;locator:string;statement_en:string;reason:string;details:string[]}[];pages:Record<string,{claims:number;concepts:number;represented:number}>;message:string};
type Job={id:string;status:string;stage:string;progress:number;error:string|null;output:Partial<Coverage>};
async function api<T>(path:string,init?:RequestInit):Promise<T>{const r=await fetch('/api'+path,{...init,headers:{'Content-Type':'application/json'}});const body=await r.json();if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:'本機處理失敗。');return body;}

export default function StudyBankPanel({sourceId,week,course,settings,onPublished}:{sourceId:string;week?:number;course?:string;settings:Settings;onPublished:()=>Promise<void>}){
 const [scope,setScope]=useState('lecture'),[policy,setPolicy]=useState('provisional_b'),[limit,setLimit]=useState(40),[variants,setVariants]=useState(2);
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const refreshed=useRef('');
 const [current,setCurrent]=useState<Coverage|null>(null);
 useEffect(()=>{let live=true;setCurrent(null);if(sourceId)void api<Coverage>('/study-bank/coverage?source_id='+encodeURIComponent(sourceId)).then(c=>{if(live)setCurrent(c);}).catch(()=>{});return()=>{live=false;};},[sourceId,job?.status]);
 useEffect(()=>{let live=true;void api<Job[]>('/study-bank/jobs').then(j=>{if(live)setJob(j[0]||null);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[]);
 useEffect(()=>{if(!job||!['queued','running'].includes(job.status))return;let live=true;const timer=setInterval(async()=>{try{const next=await api<Job>('/local/jobs/'+job.id);if(live){setJob(next);if(next.status==='completed'&&refreshed.current!==next.id){refreshed.current=next.id;await onPublished();}}}catch(e){if(live)setError((e as Error).message);}},1500);return()=>{live=false;clearInterval(timer);};},[job?.id,job?.status,onPublished]);
 async function run(){setBusy(true);setError('');try{const queued=await api<{id:string}>('/study-bank/generate',{method:'POST',body:JSON.stringify({...settings,source_ids:scope==='lecture'?[sourceId]:[],week:scope==='week'?week:null,course:course||'Human Anatomy and Physiology',max_questions:limit,variants_per_claim:variants,publication:policy})});setJob({id:queued.id,status:'queued',stage:'等待循序處理',progress:0,error:null,output:{}});}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const active=!!job&&['queued','running'].includes(job.status),o=scope==='lecture'&&current?current:job?.output;
 return <section className="processing-panel"><h2>Generate study bank · 建立完整學習題庫</h2>
  <p>使用本機 Ollama 擷取結構、功能、分類、路徑與機制，不再限於定義句。Tier B 是經來源及答案檢查的暫定內容，不代表醫學驗證，也不計入長期掌握度。</p>
  <div className="processing-form"><label>範圍<select value={scope} onChange={e=>setScope(e.target.value)}><option value="lecture">目前完整講義</option><option value="week" disabled={!week}>整個已分類週次（不自動轉錄影片）</option></select></label>
   <label>發布政策<select aria-label="Study bank publication policy" value={policy} onChange={e=>setPolicy(e.target.value)}><option value="provisional_b">允許通過檢查的 Tier B 暫定練習</option><option value="tier_a_only">嚴格政策：本輪模型題目只保存、不發布</option></select></label>
   <div className="input-pair"><label>題數上限<input type="number" min={1} max={120} value={limit} onChange={e=>setLimit(Number(e.target.value))}/></label><label>每個主張最多不同題型<select value={variants} onChange={e=>setVariants(Number(e.target.value))}><option value={1}>1</option><option value={2}>2</option></select></label></div>
   <button className="primary-button" disabled={busy||active||!sourceId||limit<1||limit>120} onClick={run}>Generate study bank</button>
  </div>{error&&<p role="alert">{error}</p>}
  {job&&<article className="concept-draft"><h3>{job.status} · {job.progress}%</h3><p role="status">{job.stage}</p>{job.error&&<p role="alert">{job.error}</p>}
   {active&&<button className="secondary-button" onClick={()=>api('/local/jobs/'+job.id+'/cancel',{method:'POST'}).catch(e=>setError(e.message))}>取消（保留已完成快取）</button>}
   {['cancelled','failed'].includes(job.status)&&<button className="secondary-button" onClick={async()=>{try{const r=await api<{id:string}>('/local/jobs/'+job.id+'/retry',{method:'POST'});setJob({...job,id:r.id,status:'queued',stage:'從已完成快取繼續'});}catch(e){setError((e as Error).message);}}}>從保存進度繼續</button>}
   {o?.meaningful_concepts!==undefined&&<><p>擷取的有意義概念：{o.meaningful_concepts}；有題目：{o.represented_concepts}；有不同面向變化題：{o.concepts_with_distinct_variants}。</p><p>這是「已擷取概念」的涵蓋情況，不是整份講義的醫學知識覆蓋率。</p><ul>{Object.entries(o.questions_per_mode||{}).map(([k,v])=><li key={k}>{k}: {v}</li>)}</ul>
    <p>這裡計算新原子主張所連結的暫定題；既有確定性練習仍保留在 Practice studio。主張／題型組合的差異不保證完全沒有語意重疊。</p>
    <details><summary>類別與頁碼分布</summary><pre>{JSON.stringify({categories:o.categories,pages:o.pages},null,2)}</pre></details>
    <details><summary>未涵蓋的主張與原因（題數上限不等於不支援）</summary><ul>{o.remaining_gaps?.map(g=><li key={g.claim_id}>{g.locator} · {g.statement_en}<br/>{g.reason==='configured_question_limit'?'已達本批題數上限，可接續產題':g.reason==='validation_hold'?'題目尚未通過檢查':'尚無合適題目'}<details><summary>詳細原因</summary>{g.details.join('；')}</details></li>)}</ul></details>
    <details><summary>隔離與未處理內容</summary><ul>{o.quarantine?.map((h,i)=><li key={'h'+i}>{h.question_id||h.claim_id}: {String(h.reason)}</li>)}{o.unprocessed?.map((h,i)=><li key={'u'+i}>{h.locator}: {h.reason}</li>)}</ul></details></>}
  </article>}
 </section>;
}

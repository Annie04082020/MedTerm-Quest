import {useEffect, useState} from 'react';

export type Assessment={status:string;label:string;medically_verified:false;tier?:'A'|'B'|'C';long_term_mastery_eligible?:boolean;bindings?:{source_id?:string;chunk_id?:string;locator?:string}[];checks?:{code:string;method:string;passed:boolean}[]};
type Claim={claim_id:string;source_id:string;chunk_id:string;locator:string;text:string;term:string|null;assessment:Assessment;structured_kind?:string};
type BatchReport={source_claims_extracted:number;accepted_claims:number;rejected_or_unsupported_claims?:number;skipped_question_families?:{claim_id?:string;reason:string}[];skipped_claims:{claim_id?:string;locator?:string;reason:string}[];questions_per_mode:Record<string,number>;auto_published:string[];duplicates_prevented:string[];blocked_questions:{question_id:string;reason:string}[];message:string};
type BatchJob={id:string;status:string;stage:string;progress:number;error:string|null;output:Partial<BatchReport>};
export function sourceHref(sourceId:string,chunkId:string){return `/api/knowledge/sources/${encodeURIComponent(sourceId)}/chunks/${encodeURIComponent(chunkId)}/view`;}
async function api<T>(path:string,body?:unknown):Promise<T>{
  const r=await fetch('/api/knowledge'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
  const value=await r.json();if(!r.ok)throw new Error(typeof value.detail==='string'?value.detail:'來源檢查未通過，未發布。');return value;
}
export default function KnowledgePanel({sourceId,chunkCount,onPublished,settings}:{sourceId:string;chunkCount:number;onPublished:()=>Promise<void>;settings?:{model:string;device:'auto'|'cpu';allow_cpu:boolean;allow_smaller:boolean}}){
  const [claims,setClaims]=useState<Claim[]>([]),[start,setStart]=useState(1),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[error,setError]=useState('');
  const [limit,setLimit]=useState(16),[useOllama,setUseOllama]=useState(false),[batch,setBatch]=useState<BatchJob|null>(null);
  useEffect(()=>{let live=true;setBatch(null);if(sourceId)void api<BatchJob[]>('/batches?source_id='+encodeURIComponent(sourceId)).then(j=>{if(live)setBatch(j[0]||null);}).catch(e=>{if(live)setError((e as Error).message);});return()=>{live=false;};},[sourceId]);
  useEffect(()=>{if(!batch||!['queued','running'].includes(batch.status))return;let live=true;const timer=setInterval(async()=>{try{const r=await fetch('/api/local/jobs/'+batch.id);if(!r.ok)throw new Error('無法讀取批次工作。');const next=await r.json() as BatchJob;if(live){setBatch(next);if(next.status==='completed')await onPublished();}}catch(e){if(live)setError((e as Error).message);}},1000);return()=>{live=false;clearInterval(timer);};},[batch?.id,batch?.status,onPublished]);
  useEffect(()=>{let live=true;setStart(1);setClaims([]);async function refresh(){if(!sourceId)return;try{const c=await api<Claim[]>('/claims?source_id='+encodeURIComponent(sourceId));if(live)setClaims(c);}catch(e){if(live)setError((e as Error).message);}}void refresh();const timer=setInterval(refresh,2500);return()=>{live=false;clearInterval(timer);};},[sourceId]);
  async function run(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="processing-panel"><h2>Source-first practice · 先讀來源，再建立練習</h2>
    <p>不需要你判斷醫學正確性。先擷取原文陳述，只有通過固定定義模板的低風險題目可自動加入遊戲；其他內容保留為未證明或待專業審查。</p>
    <p className="processing-hint">來源檢查不是醫學驗證。可整份講義產生雙向配對、原文選擇題及受限公式練習；不會自動發布自由臨床推論。</p>
    <div className="processing-form"><label>整份講義最多新增題數<input aria-label="Batch question limit" type="number" min={1} max={60} value={limit} onChange={e=>setLimit(Number(e.target.value))}/></label>
      <label className="check-label"><input type="checkbox" checked={useOllama} onChange={e=>setUseOllama(e.target.checked)}/>可選：請本機 Ollama 提出原文擷取提示（仍需相同規則驗證；不是正確性保證）</label>
      <button className="primary-button" disabled={busy||!sourceId||limit<1||limit>60||!!batch&&['queued','running'].includes(batch.status)} onClick={()=>run(async()=>{const job=await api<{id:string}>('/batch',{...settings,source_id:sourceId,max_questions:limit,use_ollama:useOllama});setBatch({id:job.id,status:'queued',stage:'等待循序處理',progress:0,error:null,output:{}});setNotice('整份講義已排入批次產題；不需要逐題確認醫學正確性。');})}>Batch lecture practice · 整份講義產題</button>
    </div>
    {batch&&<div className="concept-draft"><h3>批次結果 · {batch.status}</h3><p role="status">{batch.stage} · {batch.progress}%</p>{batch.error&&<p role="alert">{batch.error}</p>}{batch.output.auto_published&&<><p>來源陳述 {batch.output.source_claims_extracted}；接受 {batch.output.accepted_claims}；略過 {batch.output.rejected_or_unsupported_claims??batch.output.skipped_claims?.length}。</p><p>本批自動發布 {batch.output.auto_published.length} 題；阻擋 {batch.output.blocked_questions?.length} 題；避免重複 {batch.output.duplicates_prevented?.length} 題。</p><ul>{Object.entries(batch.output.questions_per_mode||{}).map(([kind,count])=><li key={kind}>{kind}: {count}</li>)}</ul><p>未建立的題型：{batch.output.skipped_question_families?.length||0}。</p><details><summary>查看略過與阻擋原因</summary><ul>{batch.output.skipped_claims?.map((s,i)=><li key={'s'+i}>{s.locator} · {s.reason}</li>)}{batch.output.blocked_questions?.map((s,i)=><li key={'b'+i}>{s.question_id} · {s.reason}</li>)}{batch.output.skipped_question_families?.map((s,i)=><li key={'f'+i}>{s.reason}</li>)}</ul></details></>}</div>}
    <label>來源片段<input aria-label="Knowledge source chunk" type="number" min={1} max={chunkCount||1} value={start} onChange={e=>setStart(Number(e.target.value))}/></label>
    <button className="primary-button" disabled={busy||!sourceId||start<1||start>chunkCount} onClick={()=>run(async()=>{await api('/extract',{source_id:sourceId,start_chunk:start-1,count:1});setNotice('已排入循序佇列；不需 Ollama，也不會自動轉錄影片。');})}>Extract source claims · 擷取來源陳述</button>
    {notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}
    {claims.map(c=><article className="concept-draft" key={c.claim_id}><strong>{c.assessment.label}</strong><p>{c.text}</p><a href={sourceHref(c.source_id,c.chunk_id)} target="_blank" rel="noreferrer">查看來源 · {c.locator}</a>
      {c.assessment.status==='deterministic_source_verified'&&c.term&&!c.structured_kind&&<div><button className="secondary-button" disabled={busy} onClick={()=>run(async()=>{await api(`/claims/${c.claim_id}/practice`,{});await onPublished();setNotice('原文定義題已通過檢查並加入遊戲；不代表獨立醫學驗證。');})}>建立原文定義練習</button></div>}
      <details><summary>檢查依據</summary><ul>{c.assessment.checks?.map((check,i)=><li key={i}>{check.method} · {check.code} · {check.passed?'通過':'保留／未證明'}</li>)}</ul></details>
    </article>)}
  </section>;
}

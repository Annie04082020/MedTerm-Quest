import {type Assessment} from './KnowledgePanel';
import { useEffect, useState } from 'react';
import { Check, Layers, Sparkles } from 'lucide-react';

type Settings={model:string;device:'auto'|'cpu';allow_cpu:boolean;allow_smaller:boolean};
type Concept={concept_id:string;title:string;variants:{question_id:string;aspect:string}[];progress:{state:string}};
type Draft={id:string;concept_id:string;payload:Record<string,unknown>;evidence:string;uncertain:number;model:string;source_id:string;chunk_id:string;source_title?:string;source_locator?:string;assessment?:Assessment};
async function api<T>(path:string,init?:RequestInit):Promise<T>{const r=await fetch('/api/concepts'+path,{...init,headers:{'Content-Type':'application/json'}});if(!r.ok){const b=await r.json().catch(()=>null);throw new Error(typeof b?.detail==='string'?b.detail:'概念操作失敗，請檢查欄位及後端訊息。');}return r.json();}

export default function ConceptAuthoring({sourceId,chunkCount,settings,enabled,selectedConcept,onSelect}:{sourceId:string;chunkCount:number;settings:Settings;enabled:boolean;selectedConcept:string;onSelect:(id:string)=>void}){
  const [concepts,setConcepts]=useState<Concept[]>([]);
  const [drafts,setDrafts]=useState<Draft[]>([]);
  const [chunk,setChunk]=useState(1);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  async function refresh(){const [c,d]=await Promise.all([api<Concept[]>('?status=approved&source_id='+encodeURIComponent(sourceId)),api<Draft[]>('/drafts')]);setConcepts(c);setDrafts(d.filter(x=>x.source_id===sourceId));}
  useEffect(()=>{let live=true;setChunk(1);async function poll(){try{const [c,d]=await Promise.all([api<Concept[]>('?status=approved&source_id='+encodeURIComponent(sourceId)),api<Draft[]>('/drafts')]);if(live){setConcepts(c);setDrafts(d.filter(x=>x.source_id===sourceId));}}catch(e){if(live)setError((e as Error).message);}}void poll();const timer=setInterval(poll,2000);return()=>{live=false;clearInterval(timer);};},[sourceId]);
  async function action(fn:()=>Promise<unknown>,message:string){setBusy(true);setError('');try{await fn();setNotice(message);await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="processing-panel concept-authoring"><div className="panel-title"><Layers size={20}/><h2>Concept-first authoring · 先概念，再變化題</h2></div><p className="processing-hint">先選已擷取來源，產生一個有原文證據的概念草稿。採用僅表示學習整理，不代表醫學驗證。自由生成的變化題需另過來源檢查；上方原文定義題可自動發布。模型不會自動下載。</p>{error&&<p className="inline-error" role="alert">{error}</p>}{notice&&<p className="processing-notice" role="status">{notice}</p>}<div className="concept-generate-controls"><label>Source chunk · 來源片段<input aria-label="Concept source chunk" type="number" min="1" max={chunkCount||1} value={chunk} onChange={e=>setChunk(Number(e.target.value))}/></label><button className="secondary-button" disabled={busy||!sourceId||!enabled||chunk<1||chunk>chunkCount} onClick={()=>action(()=>api('/generate',{method:'POST',body:JSON.stringify({...settings,source_id:sourceId,chunk_index:chunk-1})}),'概念草稿已排入循序佇列。完成後請比對原文並審核。')}><Sparkles size={14}/>Queue concept draft</button></div>
    <label className="concept-select">Parent concept for question variants<select aria-label="Parent concept for variants" value={selectedConcept} onChange={e=>onSelect(e.target.value)}><option value="">Independent question · 保留舊流程（待整理概念）</option>{concepts.map(c=><option key={c.concept_id} value={c.concept_id}>{c.title} · {c.variants.length} variants</option>)}</select></label><p className="processing-hint">長期掌握度尚未啟用；舊作答及當天練習不會在此里程碑被誤算為長期記憶。</p>
    {drafts.map(d=><ConceptReview key={d.id} draft={d} disabled={busy} onApprove={content=>action(async()=>{const result=await api<{concept_id:string}>(`/drafts/${d.id}/approve`,{method:'POST',body:JSON.stringify({content,reviewed:true,acknowledge_uncertainty:true})});onSelect(result.concept_id);},'概念已核准；可在下方一次產生一個不同面向的題目。')} onReject={()=>action(()=>api(`/drafts/${d.id}/reject`,{method:'POST'}),'概念草稿已捨棄。')}/>)}
  </section>;
}

function ConceptReview({draft,disabled,onApprove,onReject}:{draft:Draft;disabled:boolean;onApprove:(content:Record<string,unknown>)=>void;onReject:()=>void}){
  const [reviewed,setReviewed]=useState(false);const [ack,setAck]=useState(false);const [json,setJson]=useState(JSON.stringify(draft.payload,null,2));const [error,setError]=useState('');
  function approve(){try{const content=JSON.parse(json);if(!content||typeof content!=='object'||Array.isArray(content))throw new Error('請提供概念物件。');onApprove(content);}catch(e){setError((e as Error).message);}}
  return <article className="concept-draft"><h3>{String(draft.payload.title)}</h3><p>{String(draft.payload.explanation_zh)}</p><p className="processing-warning">{draft.assessment?.label||'暫具來源依據，未經獨立醫學驗證'}</p><div className="draft-reference"><strong>{draft.model} · {draft.source_title||draft.source_id} · {draft.source_locator||draft.chunk_id}</strong><blockquote>{draft.evidence}</blockquote></div>{!!draft.uncertain&&<p className="processing-warning">Uncertain · 未經獨立醫學驗證，需專業審查。</p>}<details><summary>Inspect / edit concept JSON</summary><textarea aria-label="Edit concept JSON" className="draft-json" rows={14} value={json} onChange={e=>{setJson(e.target.value);setReviewed(false);setAck(false);}}/></details><label className="check-label"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>我認為這個概念可讀、有用，而且來源相關（不代表醫學核准）。</label>{!!draft.uncertain&&<label className="check-label"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>我已看見不確定標記；這不是專業審查。</label>}{error&&<p className="inline-error">{error}</p>}<div className="draft-actions"><button className="secondary-button" disabled={disabled} onClick={onReject}>Reject concept</button><button className="primary-button" disabled={disabled||!reviewed||!!draft.uncertain&&!ack} onClick={approve}><Check size={15}/>採用概念作為學習整理</button></div></article>;
}

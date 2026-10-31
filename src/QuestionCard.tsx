import {useState,type FormEvent,type ReactNode} from 'react';
import {ArrowDown,ArrowRight,BookOpen,Check,CheckCheck,ChevronLeft,ChevronRight,CircleHelp,ClipboardList,Heart,ListChecks,Network,Puzzle,RotateCcw,ShieldCheck,X} from 'lucide-react';
import type {Assessment} from './KnowledgePanel';
import type {LocalAnswer} from './LearningPanel';
const sourceHref=(source:string,chunk:string)=>'/api/knowledge/sources/'+encodeURIComponent(source)+'/chunks/'+encodeURIComponent(chunk)+'/view';
export type Kind = 'crossword' | 'multiple_choice' | 'matching' | 'true_false' | 'short_answer' | 'clinical';
export type Status = 'correct' | 'incorrect' | 'needs_review';
export type Question = { id: string; week: number; topic: string; kind: Kind; prompt: string; prompt_zh: string; difficulty: string; terms: string[]; source: {title: string; section: string;source_id?:string;chunk_id?:string}; assessment?:Assessment; choices: string[]; pairs: {id: string; definition: string}[]; entries: Entry[]; last_status?: Status };
export type Entry = {id: string; row: number; col: number; direction: 'across' | 'down'; length: number; clue: string};
export type Result = {attempt_id: number; status: Status; answer: string | Record<string,string>; explanation_zh: string; feedback: string};
export const activities: {kind: Kind; name: string; zh: string; description: string; icon: typeof Puzzle; color: string}[] = [
  {kind:'crossword',name:'Medical crossword',zh:'醫學填字',description:'Build your vocabulary, one clue at a time.',icon:Puzzle,color:'sage'},
  {kind:'multiple_choice',name:'Multiple choice',zh:'選擇題',description:'Put your understanding to the test.',icon:ListChecks,color:'peach'},
  {kind:'matching',name:'Term matching',zh:'詞彙配對',description:'Make connections that stick.',icon:Network,color:'lavender'},
  {kind:'true_false',name:'True or false',zh:'是非與訂正',description:'Spot the error. Explain the correction.',icon:CheckCheck,color:'blue'},
  {kind:'short_answer',name:'Short answer',zh:'簡答題',description:'Explain it in your own words.',icon:ClipboardList,color:'sand'},
  {kind:'clinical',name:'Clinical connections',zh:'臨床因果',description:'Turn concepts into cause and effect.',icon:Heart,color:'rose'},
];
export type CardServices={submit:(id:string,answer:string|Record<string,string>,latency:number)=>Promise<Result>;assess:(id:number,correct:boolean)=>Promise<{status:Status}>;report:(id:string,note:string)=>Promise<unknown>;renderGrader?:(id:number,apply:(correct:boolean)=>Promise<void>)=>ReactNode};
export type CardProps={question:Question;number:number;total:number;onSaved:()=>Promise<void>;onNext:()=>void;onPrevious:()=>void;onAnswer?:LocalAnswer;onReport?:()=>Promise<void>;services?:CardServices;allowDesktopSources?:boolean};
export default function QuestionCard({question:q,number,total,onSaved,onNext,onPrevious,onAnswer,onReport,services,allowDesktopSources=true}:CardProps) {
  const [startedAt] = useState(()=>Date.now());
  const [text,setText] = useState('');
  const [mapping,setMapping] = useState<Record<string,string>>({});
  const [truth,setTruth] = useState('');
  const [result,setResult] = useState<Result|null>(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const a = activities.find(a=>a.kind===q.kind)!;
  const complete = q.kind==='matching' ? q.pairs.every(p=>mapping[p.id]) : q.kind==='crossword' ? q.entries.every(e=>mapping[e.id]?.trim().length===e.length) : q.kind==='true_false' ? truth && (truth==='True' || text.trim()) : text.trim();
  async function submit(e: FormEvent) {
    e.preventDefault(); if (busy || !complete) return;
    setBusy(true);setError('');
    try {const answer = q.kind==='matching' || q.kind==='crossword' ? mapping : q.kind==='true_false' ? truth==='True'?'True':`False: ${text}` : text; const saved = onAnswer?await onAnswer(answer,Math.min(86400000,Date.now()-startedAt)):await services!.submit(q.id,answer,Math.min(86400000,Date.now()-startedAt));setResult(saved);await onSaved();}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function assess(correct: boolean) {
    if (!result) return;setBusy(true);setError('');
    try {const saved=await services!.assess(result.attempt_id,correct);setResult({...result,status:saved.status,feedback:'Your self-assessment has been saved.'});await onSaved();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <article className="question-card" data-question-id={q.id}><div className="question-card-top"><span className={`question-type ${a.color}`}><a.icon size={16}/>{a.name}</span><span className={`difficulty ${q.difficulty.toLowerCase()}`}><span/>{q.difficulty}</span></div><div className="question-context">WEEK {q.week} <span> / </span> {q.topic}</div><h2>{q.prompt}</h2><p className="question-zh" lang="zh-Hant">{q.prompt_zh}</p><form onSubmit={submit}>
    <fieldset disabled={busy || !!result} className="answer-fieldset"><legend className="sr-only">Your answer</legend>
      {q.kind==='multiple_choice' && <div className="choices">{q.choices.map((choice,i)=><label key={choice} className={`choice ${text===choice?'chosen':''}`}><input type="radio" name={`answer-${q.id}`} value={choice} checked={text===choice} onChange={()=>setText(choice)}/><span className="choice-letter">{String.fromCharCode(65+i)}</span><span>{choice}</span>{text===choice && <Check size={18}/>}</label>)}</div>}
      {q.kind==='matching' && <div className="matching-list">{q.pairs.map(p=><div className="matching-row" key={p.id}><label htmlFor={`pair-${p.id}`}>{p.definition}</label><ArrowRight size={16}/><select id={`pair-${p.id}`} value={mapping[p.id]||''} onChange={e=>setMapping({...mapping,[p.id]:e.target.value})}><option value="">Choose a term</option>{q.choices.map(c=><option key={c}>{c}</option>)}</select></div>)}</div>}
      {q.kind==='crossword' && <Crossword entries={q.entries} values={mapping} onChange={setMapping}/>}
      {q.kind==='true_false' && <div className="true-false"><div className="truth-options">{['True','False'].map(v=><label className={`choice ${truth===v?'chosen':''}`} key={v}><input type="radio" name={`truth-${q.id}`} checked={truth===v} onChange={()=>setTruth(v)}/>{v==='True'?<Check size={18}/>:<X size={18}/>}<span>{v} · {v==='True'?'正確':'錯誤'}</span></label>)}</div>{truth==='False' && <label className="text-answer-label">Your correction · 請訂正<input autoComplete="off" className="text-answer" placeholder="Enter the corrected word or phrase…" value={text} maxLength={2000} onChange={e=>setText(e.target.value)}/></label>}</div>}
      {(q.kind==='short_answer'||q.kind==='clinical') && <label className="text-answer-label">Your answer · 你的答案<textarea className="text-answer" rows={4} maxLength={2000} placeholder="Think it through. Answer in English or 繁體中文…" value={text} onChange={e=>setText(e.target.value)}/><span className="answer-hint">Accepted phrases are checked offline. Other wording is offered for self-review.</span></label>}
    </fieldset>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!result && <div className="answer-actions"><span><ShieldCheck size={14}/> Your answer stays on this device</span><button className="primary-button" type="submit" disabled={!complete||busy}>{busy?'Saving…':'Check answer'}<ArrowRight size={16}/></button></div>}
  </form>
  {result && <div className={`answer-result ${result.status}`} role="status"><div className="result-heading">{result.status==='correct'?<CheckCheck size={21}/>:result.status==='incorrect'?<RotateCcw size={21}/>:<CircleHelp size={21}/>}<h3>{result.status==='correct'?'That’s a connection made.':result.status==='incorrect'?'A useful moment to learn.':'Different wording? Let’s reflect.'}</h3></div><p>{result.feedback}</p><div className="model-answer"><strong>Reference answer</strong>{typeof result.answer==='string'?<p>{result.answer}</p>:<ul>{Object.entries(result.answer).map(([key,v])=><li key={key}>{q.kind==='matching'?q.pairs.find(p=>p.id===key)?.definition:`Clue ${key}`}: <strong>{v}</strong></li>)}</ul>}</div><p className="explanation" lang="zh-Hant">{result.explanation_zh}</p>{result.status==='needs_review' && !onAnswer && <div className="self-review">{(q.kind==='short_answer'||q.kind==='clinical')&&services?.renderGrader?.(result.attempt_id,assess)}<p>Did your answer express the same idea? This is your self-assessment, not AI grading.</p><button disabled={busy} className="secondary-button" onClick={()=>assess(false)}><RotateCcw size={15}/> Review again</button><button disabled={busy} className="primary-button" onClick={()=>assess(true)}><Check size={15}/> I understood this</button></div>}</div>}
  {q.assessment?.tier==='B'&&<div className="processing-warning"><strong>Tier B 暫定練習 · 未經獨立醫學驗證，不計長期掌握度</strong><button className="text-button" onClick={async()=>{if(onReport){await onReport();return;}const note=window.prompt('可回報不清楚、疑似錯誤或來源不符之處；不需要你確認醫學正確性。','');if(note===null)return;try{await services!.report(q.id,note);await onSaved();}catch(e){setError((e as Error).message);}}}>回報並隱藏此題（保留紀錄）</button></div>}<div className="question-source"><BookOpen size={15}/><div><strong>{q.source.title}</strong><span>{q.source.section}</span>{allowDesktopSources&&q.source.source_id&&q.source.chunk_id&&(!onAnswer||!!result)&&<a href={sourceHref(q.source.source_id,q.source.chunk_id)} target="_blank" rel="noreferrer">{onAnswer?'桌面原始來源（需要桌面連線）':'查看原文頁碼／時間戳'}</a>}{q.assessment&&<small>{q.assessment.label}</small>}{allowDesktopSources&&q.assessment?.bindings?.filter((b,i,all)=>b.source_id&&b.chunk_id&&b.chunk_id!==q.source.chunk_id&&all.findIndex(x=>x.source_id===b.source_id&&x.chunk_id===b.chunk_id)===i).map(b=><a key={b.chunk_id} href={sourceHref(b.source_id!,b.chunk_id!)} target="_blank" rel="noreferrer">其他來源依據 · {b.locator}</a>)}</div></div>{(!onAnswer||!!result)&&<div className="term-chips">{q.terms.map(t=><span key={t}>{t}</span>)}</div>}<div className="question-navigation"><button className="text-button" disabled={number===1||!!onAnswer} onClick={onPrevious}><ChevronLeft size={16}/> Previous</button><span>{number} of {total}</span><button className="text-button" disabled={!!onAnswer&&!result} onClick={onNext}>{onAnswer?'下一題':number===total?'Back to first':'Next activity'}<ChevronRight size={16}/></button></div>
  </article>;
}

function Crossword({entries,values,onChange}:{entries:Entry[];values:Record<string,string>;onChange:(v:Record<string,string>)=>void}) {
  const rows=Math.max(...entries.map(e=>e.row+(e.direction==='down'?e.length:1)));
  const cols=Math.max(...entries.map(e=>e.col+(e.direction==='across'?e.length:1)));
  const cells=Array.from({length:rows*cols},(_,i)=>({row:Math.floor(i/cols),col:i%cols}));
  function at(e: Entry,row:number,col:number) {const offset=e.direction==='across'?col-e.col:row-e.row;return offset>=0&&offset<e.length&&(e.direction==='across'?row===e.row:col===e.col)?offset:-1;}
  function update(entry:Entry,value:string) {
    const cleaned=value.toUpperCase().replace(/[^A-Z]/g,'').slice(0,entry.length); const next={...values,[entry.id]:cleaned};
    // Keep both words synchronized at their shared letter.
    for(const other of entries) {if(other.id===entry.id)continue;for(let i=0;i<entry.length;i++){const row=entry.row+(entry.direction==='down'?i:0),col=entry.col+(entry.direction==='across'?i:0),offset=at(other,row,col);if(offset>=0){const chars=(next[other.id]||'').padEnd(other.length,' ').split('');chars[offset]=cleaned[i]||' ';next[other.id]=chars.join('');}}}
    onChange(next);
  }
  return <div className="crossword-layout"><div className="crossword-grid" role="img" aria-label="Crossword grid; enter words using the clue fields" style={{gridTemplateColumns:`repeat(${cols}, 42px)`}}>{cells.map(({row,col})=>{const entry=entries.find(e=>at(e,row,col)>=0);const start=entries.filter(e=>e.row===row&&e.col===col);return <div key={`${row}-${col}`} className={`crossword-cell ${entry?'white':'blank'}`}>{start.length>0&&<small>{start.map(e=>e.id).join(',')}</small>}{entry&&<span>{values[entry.id]?.[at(entry,row,col)]||''}</span>}</div>;})}</div><div className="crossword-clues">{entries.map(e=><label key={e.id}><strong>{e.id} {e.direction==='across'?<ArrowRight size={13}/>:<ArrowDown size={13}/>} {e.direction} · {e.length} letters</strong><span>{e.clue}</span><input aria-label={`Clue ${e.id} ${e.direction}`} autoComplete="off" spellCheck={false} value={values[e.id]||''} maxLength={e.length} onChange={ev=>update(e,ev.target.value)}/></label>)}</div></div>;
}

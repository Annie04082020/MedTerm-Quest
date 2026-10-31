import {useEffect,useRef,useState} from 'react';
import QuestionCard,{activities} from '../QuestionCard';
import {readState,updateState} from '../learning/store';
import {grade,record,nextItem,startSession,localDay,type State,type Mode,type Answer} from '../learning/core';

export default function MobilePractice(){
 const [state,setState]=useState<State|null>(null),[pending,setPending]=useState<State|null>(null),[kind,setKind]=useState<Mode|''>(''),[week,setWeek]=useState(''),[search,setSearch]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[hint,setHint]=useState(false);
 const hintSeen=useRef(false);
 useEffect(()=>{readState().then(setState).catch(e=>setError(String(e)));},[]);
 if(!state)return <p>{error||'開啟本機練習…'}</p>;
 const day=localDay(new Date()),session=[...state.sessions].reverse().find(s=>s.purpose==='free'&&s.day===day);
 const item=session?.status==='active'?nextItem(session):undefined,q=item&&state.questions.find(q=>q.id===item.question_id);
 const pool=state.questions.filter(q=>!q.deleted&&q.course===state.settings.course&&!state.reports.some(r=>r.question_id===q.id)&&(state.settings.includeSamples||q.source.sample!==true)&&(state.settings.includeProvisional||q.assessment?.tier!=='B')&&(!kind||q.kind===kind)&&(!week||q.week===Number(week))&&`${q.prompt} ${q.prompt_zh} ${q.terms.join(' ')}`.toLowerCase().includes(search.toLowerCase()));
 async function change(fn:(s:State)=>void){try{const saved=await updateState(fn);setState(saved);setPending(null);return saved;}catch(e){setError(String(e));throw e;}}
 async function begin(){setBusy(true);setError('');try{await change(s=>{if(s.sessions.some(x=>x.day===day&&x.purpose==='free'&&['active','paused'].includes(x.status)))return;
  const scoped={...s,questions:pool,settings:{...s.settings,course:pool[0]?.course||s.settings.course,mode:'exam' as const,scopeWeeks:[...new Set(pool.map(q=>q.week))],scopeTopics:[],timed:false,minutes:60}};
  const next=startSession(scoped,new Date(),crypto.randomUUID());next.purpose='free';s.sessions.push(next);
 });hintSeen.current=false;setHint(false);}catch{}finally{setBusy(false);}}
 async function answer(value:Answer,latency:number){
  if(!q||!session)throw Error('請重新開啟本回練習');const status=grade(q,value),hinted=hintSeen.current||!!item?.hint_used;
  const saved=await updateState(s=>{const live=s.sessions.find(x=>x.id===session.id)!;const active=nextItem(live);if(!active||active.question_id!==q.id)throw Error('此題已保存，請繼續下一題。');
   record(s,live,active,{id:crypto.randomUUID(),concept_id:q.concept_id,question_id:q.id,at:new Date().toISOString(),rating:status==='correct'?(hinted?'hinted':'correct'):status==='needs_review'?'partial':'incorrect',eligible:q.eligible,mode:q.kind,latency_ms:latency,hint:hinted});live.elapsed_ms+=latency;
  });setPending(saved);
  return {attempt_id:0,status,answer:q.answer,explanation_zh:q.explanation_zh,feedback:status==='correct'?'已離線保存。':'請比較原文與答案。未辨識的措辭不計成功回憶，不需要你核准醫學正確性。'};
 }
 async function showHint(show:boolean){setHint(show);if(!show||pending||!q||!session)return;hintSeen.current=true;try{await change(s=>{const current=nextItem(s.sessions.find(x=>x.id===session.id)!);if(current?.question_id===q.id)current.hint_used=true;});}catch{}}
 return <section><h1>自由練習</h1><p>選擇玩法或週次；錯題補強可能切換到同概念的其他玩法。本日加題仍受每日上限限制。</p>{error&&<p role="alert">{error}</p>}
 {(!session||['complete','skipped'].includes(session.status))&&<><div className="mobile-practice-filters"><label>玩法<select aria-label="自由練習玩法" value={kind} onChange={e=>setKind(e.target.value as Mode|'')}><option value="">混合六種玩法</option>{activities.map(a=><option key={a.kind} value={a.kind}>{a.zh} · {a.name}</option>)}</select></label><label>週次<select aria-label="自由練習週次" value={week} onChange={e=>setWeek(e.target.value)}><option value="">全部週次</option>{[...new Set(state.questions.filter(q=>!q.deleted&&q.course===state.settings.course).map(q=>q.week))].sort((a,b)=>a-b).map(w=><option key={w} value={w}>Week {w}</option>)}</select></label><label>搜尋<input aria-label="搜尋自由練習" value={search} onChange={e=>setSearch(e.target.value)} placeholder="英文術語／中文題目"/></label></div><p>{pool.length} 題符合條件；示範題與暫定題設定沿用每日挑戰。</p><button className="primary-button" disabled={busy||!pool.length} onClick={begin}>開始自由練習</button></>}
 {session&&<div className="challenge-state"><p>本回進度 {session.items.filter(i=>i.done).length}/{session.items.length} · {session.status}</p>{session.note&&<p>{session.note}</p>}{session.status==='paused'&&<button className="primary-button" onClick={()=>change(s=>{s.sessions.find(x=>x.id===session.id)!.status='active';})}>繼續自由練習</button>}{session.status==='active'&&<><button className="secondary-button" onClick={()=>change(s=>{s.sessions.find(x=>x.id===session.id)!.status='paused';})}>暫停自由練習</button><button className="text-button" onClick={()=>change(s=>{s.sessions.find(x=>x.id===session.id)!.status='skipped';})}>結束本回（保留紀錄）</button></>}</div>}
 {q&&item&&<div key={q.id+'@'+q.revision+session!.items.filter(i=>i.done).length}><label><input type="checkbox" disabled={!!pending} checked={hint} onChange={e=>showHint(e.target.checked)}/>原文提示（會記錄使用）</label>{item.hint_used&&<p>本題已使用提示；暫停後仍保留。</p>}{hint&&<blockquote>{q.source.quote||q.explanation_zh}</blockquote>}
 <QuestionCard question={q} number={1} total={1} onAnswer={answer} onSaved={async()=>{}} onPrevious={()=>{}} onNext={()=>{if(pending){setState(pending);setPending(null);setHint(false);hintSeen.current=false;if(pending.sessions.find(s=>s.id===session!.id)?.status==='complete')window.dispatchEvent(new Event('medterm-session-complete'));}}} allowDesktopSources={false} onReport={async()=>{await change(s=>{s.reports.push({id:crypto.randomUUID(),question_id:q.id,at:new Date().toISOString(),note:'本機回報並隱藏'});const live=s.sessions.find(x=>x.id===session!.id)!;const current=nextItem(live);if(current?.question_id===q.id)current.done=true;if(!nextItem(live))live.status='complete';});hintSeen.current=false;setHint(false);}}/>
 <details onToggle={e=>{if(e.currentTarget.open&&!pending)void showHint(true);}}><summary>離線來源 · {q.source.title} · {q.source.section}</summary><blockquote>{q.source.quote||'示範題來源標記'}</blockquote></details></div>}
 </section>;
}

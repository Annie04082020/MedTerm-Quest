import {useEffect,useState,useRef,type ReactNode} from 'react';
import {grade,record,startSession,nextItem,localDay,schedule,type StudyQuestion,type Answer,type State,type Snapshot,type Settings} from './learning/core';
import {readState,updateState} from './learning/store';
import SyncPanel from './SyncPanel';
import {mergeSnapshot,validateSnapshot,effectiveReviews} from './learning/sync';

export type LocalAnswer=(answer:Answer,latency:number)=>Promise<{attempt_id:number;status:'correct'|'incorrect'|'needs_review';answer:Answer;explanation_zh:string;feedback:string}>;
export default function LearningPanel({renderQuestion,mobile=false}:{mobile?:boolean;renderQuestion:(q:StudyQuestion,answer:LocalAnswer,report:()=>Promise<void>,next:()=>void)=>ReactNode}){
 const [state,setState]=useState<State|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[hint,setHint]=useState(false);
 const [pending,setPending]=useState<State|null>(null);
 const settingsVersion=useRef(0);
 const hintSeen=useRef(false);
 useEffect(()=>{const refresh=()=>{readState().then(setState).catch(e=>setError(String(e)));};refresh();window.addEventListener('medterm-data-changed',refresh);return()=>window.removeEventListener('medterm-data-changed',refresh);},[]);
 async function mutate(fn:(s:State)=>void){try{const next=await updateState(fn);setState(next);setPending(null);return next;}catch(e){setError('本機保存失敗：'+String(e));throw e;}}
 async function copy(){setBusy(true);setError('');try{
  const response=await fetch('/api/learning/snapshot');if(!response.ok)throw Error('請先啟動桌面後端，或使用題庫檔案匯入。');
  const data:Snapshot=await response.json();validateSnapshot(data);
  await mutate(s=>{Object.assign(s,mergeSnapshot(s,data).state);
    if(!s.questions.some(q=>q.week===s.settings.week))s.settings.week=s.questions[0]?.week||1;});
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function setting(update:Partial<Settings>){const version=++settingsVersion.current;setState(s=>s?{...s,settings:{...s.settings,...update}}:s);try{const saved=await updateState(s=>Object.assign(s.settings,update));if(version===settingsVersion.current)setState(saved);}catch(e){setError('設定保存失敗：'+String(e));}}
 async function begin(){setBusy(true);setHint(false);hintSeen.current=false;try{await mutate(s=>{const day=localDay(new Date());if(!s.sessions.some(x=>x.purpose!=='free'&&x.day===day&&x.settings.mode===s.settings.mode))s.sessions.push(startSession(s,new Date(),crypto.randomUUID()));});}catch{}finally{setBusy(false);}}
 if(!state)return <section><p>{error||'開啟本機學習資料…'}</p></section>;
 const o=state.settings,day=localDay(new Date()),session=[...state.sessions].reverse().find(s=>s.purpose!=='free'&&s.day===day&&s.settings.mode===o.mode);
 const item=session?.status==='active'?nextItem(session):undefined,q=item&&state.questions.find(q=>q.id===item.question_id);
 const weeks=[...new Set(state.questions.filter(q=>q.course===o.course).map(q=>q.week))].sort((a,b)=>a-b);
 const topics=[...new Set(state.questions.filter(q=>q.week===o.week&&q.course===o.course).map(q=>q.topic))];
 async function answer(value:Answer,latency:number){
  if(!q||!session||!item)throw Error('練習已結束');const status=grade(q,value);
  const usedHint=hintSeen.current||!!item.hint_used;
  const saved=await updateState(s=>{const live=s.sessions.find(x=>x.id===session.id)!;const current=nextItem(live);if(!current||current.question_id!==q.id)throw Error('此題已在其他視窗作答，請重新開啟練習。');
   record(s,live,current,{id:crypto.randomUUID(),concept_id:q.concept_id,question_id:q.id,at:new Date().toISOString(),rating:status==='correct'?(usedHint?'hinted':'correct'):status==='needs_review'?'partial':'incorrect',eligible:q.eligible,mode:q.kind,latency_ms:latency,hint:usedHint});live.elapsed_ms+=latency;
   if(live.settings.timed&&live.elapsed_ms>=live.settings.minutes*60000){live.status='complete';live.note='已達設定的模擬測驗時間；已保存作答。';}});
  setPending(saved);
  return {attempt_id:0,status,answer:q.answer,explanation_zh:q.explanation_zh,feedback:status==='correct'?'已離線保存。':'請參考來源原文與答案；未辨識的措辭不計為成功回憶，不需要你判定醫學正確性。'};
 }
 async function showHint(show:boolean){setHint(show);if(!show||!q||!session||pending)return;hintSeen.current=true;try{await mutate(s=>{const live=s.sessions.find(x=>x.id===session.id);if(!live)return;const current=nextItem(live);if(current?.question_id===q.id)current.hint_used=true;});}catch{}}
 const mastered=new Set(state.events.filter(e=>e.eligible).map(e=>e.concept_id));
 return <section className="learning-panel"><div className="page-heading"><div><h1>每週學習與每日挑戰</h1><p>{mobile?'作答、排程與紀錄都儲存在裝置上，離線可用。':'題庫複製到此瀏覽器後，作答、排程與紀錄皆在本機完成。'}</p></div>{!mobile&&<button className="secondary-button" disabled={busy} onClick={copy}>更新本機題庫（保留進度）</button>}</div>
 {error&&<p role="alert">{error}</p>}
 <p>{state.questions.filter(q=>!q.deleted).length} 道本機題目 · {state.events.length} 筆歷史 · {Array.from(mastered).filter(cid=>schedule(effectiveReviews(state),cid).level>1).length} 個有間隔回憶紀錄的概念</p>
 <div className="learning-settings">
 <label>學習模式<select aria-label="學習模式" value={o.mode} onChange={e=>setting({mode:e.target.value as Settings['mode']})}><option value="weekly">每週聚焦（約 80/20）</option><option value="exam">考前複習（手動範圍）</option></select></label>
 <label>課程<select aria-label="學習課程" value={o.course} onChange={e=>setting({course:e.target.value,topic:''})}>{[...new Set(state.questions.map(q=>q.course))].map(c=><option key={c}>{c}</option>)}</select></label>
 {o.mode==='weekly'?<><label>目前週次<select aria-label="目前週次" value={o.week} onChange={e=>setting({week:Number(e.target.value),topic:''})}>{weeks.map(w=><option key={w} value={w}>Week {w}</option>)}</select></label><label>主題<select aria-label="學習主題" value={o.topic} onChange={e=>setting({topic:e.target.value})}><option value="">本週全部主題</option>{topics.map(t=><option key={t}>{t}</option>)}</select></label></>:<><fieldset><legend>考試週次範圍</legend>{weeks.map(w=><label key={w}><input type="checkbox" checked={o.scopeWeeks.includes(w)} onChange={e=>setting({scopeWeeks:e.target.checked?[...o.scopeWeeks,w]:o.scopeWeeks.filter(x=>x!==w)})}/> Week {w}</label>)}</fieldset><label>考試主題（可複選；不選表示全部）<select aria-label="考試主題範圍" multiple value={o.scopeTopics} onChange={e=>setting({scopeTopics:Array.from(e.target.selectedOptions).map(x=>x.value)})}>{[...new Set(state.questions.filter(q=>o.scopeWeeks.includes(q.week)).map(q=>q.topic))].map(t=><option key={t}>{t}</option>)}</select></label><label><input type="checkbox" checked={o.timed} onChange={e=>setting({timed:e.target.checked})}/>計時模擬測驗（依作答累積時間）</label></>}
 {([['count','每日題數',1,30],['minutes','約需分鐘',1,60],['maxExtra','每日補強上限',0,20]] as const).map(([k,label,min,max])=><label key={k}>{label}<input aria-label={label} type="number" min={min} max={max} value={o[k]} onChange={e=>setting({[k]:Math.min(max,Math.max(min,Number(e.target.value)||min))})}/></label>)}
 <label><input type="checkbox" checked={o.includeProvisional} onChange={e=>setting({includeProvisional:e.target.checked})}/>加入 Tier B 暫定題（不累計長期精熟度）</label></div>
 <label><input type="checkbox" checked={o.includeSamples} onChange={e=>setting({includeSamples:e.target.checked})}/>加入示範題（預設關閉）</label>
 <p>本機課程題 {state.questions.filter(q=>!q.deleted&&q.source.sample!==true).length} 道；示範題 {state.questions.filter(q=>!q.deleted&&q.source.sample===true).length} 道。未勾選時不會把示範題混入每日挑戰。</p>
 <p>預設以目前週次為主，搭配已學過且到期的舊概念；題數不足會調整比例。切換週次不會清除歷史；設定於下次挑戰套用，進行中會保留原範圍。未經來源確定性驗證的題目不累計長期精熟度。</p>
 {!session&&<button className="primary-button" disabled={busy||!state.questions.some(q=>!q.deleted)} onClick={begin}>開始今日挑戰</button>}
 {session&&<div className="challenge-state"><p>今日進度 {session.items.filter(i=>i.done).length} / {session.items.length} · 補強 {session.extra}/{session.settings.maxExtra} · {session.status}</p>{session.note&&<p>{session.note}</p>}
 {session.status==='paused'&&<button className="primary-button" onClick={()=>mutate(s=>{s.sessions.find(x=>x.id===session.id)!.status='active';})}>繼續挑戰</button>}
 {session.status==='active'&&<><button className="secondary-button" onClick={()=>mutate(s=>{s.sessions.find(x=>x.id===session.id)!.status='paused';})}>暫停並保存</button><button className="text-button" onClick={()=>mutate(s=>{s.sessions.find(x=>x.id===session.id)!.status='skipped';})}>結束今天（保留進度）</button></>}
 <p>{Object.values(session.remediation).filter(r=>r.complete).length} 個概念完成兩次不同題目的補強；今日補強不會取消日後複習排程。</p></div>}
 {q&&item&&<div key={q.id+session!.items.filter(i=>i.done).length}>
 <label><input type="checkbox" disabled={!!pending} checked={hint} onChange={e=>showHint(e.target.checked)}/>顯示原文提示（會記錄提示使用）</label>{item.hint_used&&<small>本題已使用提示；暫停後仍保留記錄。</small>}{hint&&<blockquote>{q.source.quote||q.explanation_zh}</blockquote>}
 {renderQuestion(q,answer,async()=>{await mutate(s=>{s.reports.push({id:crypto.randomUUID(),question_id:q.id,at:new Date().toISOString(),note:'學習者回報；本機隱藏，不要求醫學核准'});const live=s.sessions.find(x=>x.id===session!.id)!;const current=nextItem(live);if(current?.question_id===q.id)current.done=true;if(!nextItem(live))live.status='complete';});setPending(null);hintSeen.current=false;},()=>{if(pending){setState(pending);setPending(null);setHint(false);hintSeen.current=false;if(pending.sessions.find(s=>s.id===session!.id)?.status==='complete')window.dispatchEvent(new Event('medterm-session-complete'));}})}
 <details onToggle={e=>{if(e.currentTarget.open&&!pending)void showHint(true);}}><summary>離線來源 · {q.source.title} · {q.source.section}</summary><blockquote>{q.source.quote||'此舊題僅有來源標記，沒有可攜引文。'}</blockquote></details>
 </div>}
 <p className="answer-hint">初版使用可測試的固定間隔排程（1、3、7、14、30、60 天），不是 FSRS，也不保證記憶成效。未滿 24 小時的重複練習不算長期回憶。本機保存題庫與進度；可選用加密 Gist 同步，並保留檔案備份。</p>
 {!mobile&&<SyncPanel onChanged={next=>{setState(next);setPending(null);setHint(false);hintSeen.current=false;}}/>}
 </section>;
}

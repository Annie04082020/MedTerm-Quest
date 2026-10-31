import {useEffect,useState} from 'react';
import {BookOpen,CalendarDays,History,ArrowLeftRight,WifiOff} from 'lucide-react';
import LearningPanel from './LearningPanel';
import QuestionCard from './QuestionCard';
import SyncPanel from './SyncPanel';
import MobilePractice from './mobile/Practice';
import {bootstrap} from './mobile/bootstrap';
import {readState} from './learning/store';
import {effectiveReviews,schedule,type State,type Rating} from './learning/core';
import './mobile.css';
type Tab='daily'|'practice'|'history'|'sync';
export default function MobileApp(){
 const [ready,setReady]=useState(false),[error,setError]=useState(''),[tab,setTab]=useState<Tab>('daily'),[state,setState]=useState<State|null>(null);
 useEffect(()=>{bootstrap().then(s=>{setState(s);setReady(true);}).catch(e=>setError('本機資料未變更：'+(e as Error).message));},[]);
 async function navigate(next:Tab){setTab(next);try{setState(await readState());}catch(e){setError(String(e));}window.scrollTo({top:0});}
 const tabs=[{id:'daily' as const,label:'每日挑戰',icon:CalendarDays},{id:'practice' as const,label:'自由練習',icon:BookOpen},{id:'history' as const,label:'學習紀錄',icon:History},{id:'sync' as const,label:'題庫交換',icon:ArrowLeftRight}];
 return <div className="mobile-app"><header className="mobile-header"><strong>MedTerm Quest</strong><span><WifiOff size={16}/>離線學習</span></header><main>
 {error&&<p role="alert">{error}</p>}
 {!ready?<div className="empty-state"><h1>{error?'無法開啟本機資料':'準備本機題庫…'}</h1><p>原始資料不會被自動清除。{error?'請保留備份，關閉後重試。':'第一次開啟會載入隨附的現有課程題。'}</p></div>:<>
 {state&&!state.questions.some(q=>!q.deleted)&&<div className="library-notice"><div><strong>先匯入課程題庫</strong><p>APK 不包含教材或個人進度。將 Windows 匯出的題庫 JSON 複製到手機，再從「題庫交換」匯入。</p><button className="primary-button" onClick={()=>navigate('sync')}>前往題庫交換</button></div></div>}
 {tab==='daily'&&<LearningPanel mobile renderQuestion={(q,answer,report,next)=><QuestionCard key={q.id+'@'+q.revision} question={q} number={1} total={1} onSaved={async()=>{}} onNext={next} onPrevious={()=>{}} onAnswer={answer} onReport={report} allowDesktopSources={false}/>}/>}
 {tab==='practice'&&<MobilePractice/>}
 {tab==='history'&&state&&<LearningHistory state={state}/>}
 {tab==='sync'&&<><h1>題庫與進度交換</h1><p>由 Windows 處理教材與產題。這裡只匯入既有題庫、保存與交換學習進度。</p><SyncPanel onChanged={setState}/></>}
 </>}
 </main><nav className="mobile-tabs" aria-label="行動學習導覽">{tabs.map(t=><button key={t.id} aria-current={tab===t.id?'page':undefined} onClick={()=>navigate(t.id)}><t.icon size={21}/>{t.label}</button>)}</nav></div>;
}
function LearningHistory({state}:{state:State}){
 const labels:Record<Rating,string>={correct:'無提示答對',hinted:'提示後答對',partial:'措辭未辨識',incorrect:'答錯',observed:'歷史答對（協助程度未知）'};
 const eligible=effectiveReviews(state),concepts=[...new Set(state.events.map(e=>e.concept_id))];
 const graded=state.events.filter(e=>e.rating!=='partial'),correct=graded.filter(e=>['correct','hinted','observed'].includes(e.rating)).length;
 return <section><h1>學習紀錄</h1><p>{state.events.length} 筆作答 · {graded.length?Math.round(100*correct/graded.length)+'% 已辨識答案正確率':'尚無作答'}</p><p>{concepts.filter(cid=>schedule(eligible,cid).level>1).length} 個概念有間隔回憶紀錄。暫定題與提示作答不增加長期精熟度。</p>
 <ul className="mobile-history">{[...state.events].reverse().slice(0,60).map(e=>{const q=state.questions.find(q=>q.id===e.question_id);return <li key={e.id}><strong>{q?.prompt||'已封存的題目'}</strong><span>{labels[e.rating]} · {new Date(e.at).toLocaleString('zh-TW')}</span><small>{q?.source.title} · {q?.source.section}</small></li>;})}</ul></section>;
}

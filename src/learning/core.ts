// Pure portable domain logic. No fetch, browser storage, clock or model dependencies.
export type Mode='crossword'|'multiple_choice'|'matching'|'true_false'|'short_answer'|'clinical';
export type Rating='correct'|'hinted'|'partial'|'incorrect'|'observed';
export type Answer=string|Record<string,string>;
export type StudyQuestion={id:string;concept_id:string;revision:number;deleted:boolean;eligible:boolean;kind:Mode;week:number;topic:string;course:string;prompt:string;prompt_zh:string;answer:Answer;accepted_answers:string[];explanation_zh:string;choices:string[];pairs:{id:string;definition:string}[];entries:{id:string;row:number;col:number;length:number;direction:'across'|'down';clue:string}[];terms:string[];difficulty:string;variant_aspect?:string;source:{title:string;section:string;sample?:boolean;quote?:string;source_id?:string;chunk_id?:string};assessment?:{status:string;label:string;medically_verified:false;tier?:'A'|'B'|'C'}};
export type Concept={concept_id:string;title:string;course:string;week:number;topic:string;revision:number;deleted?:boolean;explanation_zh?:string;core_mechanism?:string;difficulty?:string;tags?:string[];learning_objectives?:string[];english_terms?:unknown[];sources?:{source_id?:string;chunk_id?:string;locator:string;quote:string}[];assessment?:{status?:string;tier?:'A'|'B'|'C';medically_verified?:false}};
export type Review={id:string;concept_id:string;question_id:string;at:string;rating:Rating;eligible:boolean;mode:Mode;latency_ms:number|null;hint:boolean};
export type Settings={mode:'weekly'|'exam';course:string;week:number;topic:string;scopeWeeks:number[];scopeTopics:string[];count:number;minutes:number;maxExtra:number;timed:boolean;includeProvisional:boolean;includeSamples:boolean};
export type Item={question_id:string;remedial:boolean;after:number;done:boolean;event_id?:string;hint_used?:boolean};
export type Session={id:string;purpose?:'daily'|'free';day:string;status:'active'|'paused'|'complete'|'skipped';started:string;elapsed_ms:number;items:Item[];remediation:Record<string,{successes:string[];complete:boolean}>;extra:number;note:string;settings:Settings};
export type Snapshot={schema:1;questions:StudyQuestion[];concepts:Concept[];events:Review[]};
export type State=Snapshot & {installation:string;settings:Settings;sessions:Session[];reports:{id:string;question_id:string;at:string;note:string}[]};
export const DAY=86400000;
export const defaults:Settings={mode:'weekly',course:'Human Anatomy and Physiology',week:4,topic:'',scopeWeeks:[4],scopeTopics:[],count:10,minutes:8,maxExtra:6,timed:false,includeProvisional:true,includeSamples:false};
export function localDay(at:Date){return `${at.getFullYear()}-${String(at.getMonth()+1).padStart(2,'0')}-${String(at.getDate()).padStart(2,'0')}`;}
export function normalize(s:string){return s.normalize('NFKC').toLocaleLowerCase().trim().replace(/\s+/g,'').replace(/[。.!！?？]+$/,'');}
export function grade(q:StudyQuestion,answer:Answer):'correct'|'incorrect'|'needs_review'{
 if(typeof q.answer==='object')return typeof answer==='object'&&Object.keys(answer).length===Object.keys(q.answer).length&&Object.entries(q.answer).every(([k,v])=>normalize(answer[k]||'')===normalize(v))?'correct':'incorrect';
 if(typeof answer!=='string')return 'incorrect';
 const proof=(q.assessment as {construction_proof?:{template:string;result:string}}|undefined)?.construction_proof;
 if(q.kind==='short_answer'&&proof?.template==='ratio_calculation'){
  function fraction(value:string){const m=value.match(/^\s*([+-]?\d{1,16})(?:\.(\d{1,12}))?(?:\/(\d{1,16}))?\s*(?:milliliter\/minute)?\s*$/);if(!m)return null;const scale=10n**BigInt((m[2]||'').length),sign=m[1].startsWith('-')?-1n:1n,n=BigInt(m[1])*scale+sign*BigInt(m[2]||0),d=BigInt(m[3]||1)*scale;return d?[n,d]:null;}
  const a=fraction(answer),b=fraction(proof.result);return a&&b&&a[0]*b[1]===b[0]*a[1]?'correct':'incorrect';
 }
 if([q.answer,...q.accepted_answers].some(v=>normalize(v)===normalize(answer)))return 'correct';
 return ['short_answer','clinical','true_false'].includes(q.kind)?'needs_review':'incorrect';
}
export function schedule(events:Review[],cid:string){
 let level=0,last:number|null=null,due=0,attempts=0;const intervals=[1,3,7,14,30,60];
 const ordered=[...events].filter(e=>e.concept_id===cid).sort((a,b)=>Date.parse(a.at)-Date.parse(b.at)||a.id.localeCompare(b.id));
 for(const e of ordered){
  attempts++;const at=Date.parse(e.at);if(!e.eligible||e.rating==='observed')continue;
  // Rehearsal within a day never counts as another long-term retrieval.
  if(e.rating==='incorrect'||e.rating==='partial'){level=0;due=at+DAY;last=at;continue;}
  if(e.rating==='hinted'){due=due?Math.min(due,at+DAY):at+DAY;last=at;continue;}
  if(last===null||at-last>=DAY){due=at+intervals[Math.min(level,intervals.length-1)]*DAY;level=Math.min(level+1,intervals.length);last=at;}
 }
 return {version:'interval-v1',level,last,due,attempts};
}
export function effectiveReviews(s:State){const qs=new Map(s.questions.map(q=>[q.id,q]));return s.events.map(e=>({...e,rating:e.rating==='correct'&&e.hint?'hinted' as const:e.rating,eligible:e.eligible&&qs.get(e.question_id)?.eligible===true&&qs.get(e.question_id)?.assessment?.tier!=='B'}));}
export function selectDaily(s:State,at:Date):StudyQuestion[]{
 const o=s.settings,now=at.getTime(),reviews=effectiveReviews(s),groups=new Map<string,Review[]>(),variantCounts=new Map<string,number>(),stats=new Map<string,ReturnType<typeof schedule>>();
 for(const e of reviews){const group=groups.get(e.concept_id)||[];group.push(e);groups.set(e.concept_id,group);variantCounts.set(e.question_id,(variantCounts.get(e.question_id)||0)+1);}
 for(const [cid,events] of groups){events.sort((a,b)=>Date.parse(a.at)-Date.parse(b.at)||a.id.localeCompare(b.id));stats.set(cid,schedule(events,cid));}
 const scores=new Map(s.questions.map(q=>{const es=groups.get(q.concept_id)||[],last=es.at(-1),p=stats.get(q.concept_id);return [q.id,(last?.rating==='incorrect'||last?.rating==='partial'?1000:0)+(p?.due&&p.due<=now?500:0)+(es.length?100:0)-(variantCounts.get(q.id)||0)*12-Math.min(es.length,20)];}));
 const priority=(q:StudyQuestion)=>scores.get(q.id)||0;
 const pool=s.questions.filter(q=>!q.deleted&&!s.reports.some(r=>r.question_id===q.id)&&q.course===o.course&&(o.includeSamples||q.source.sample!==true)&&(o.includeProvisional||q.assessment?.tier!=='B'));
 const active=(q:StudyQuestion)=>q.week===o.week&&(!o.topic||q.topic===o.topic);
 const scoped=(q:StudyQuestion)=>o.scopeWeeks.includes(q.week)&&(!o.scopeTopics.length||o.scopeTopics.includes(q.topic));
 const rank=(xs:StudyQuestion[])=>xs.sort((a,b)=>priority(b)-priority(a)||a.id.localeCompare(b.id));
 const current=rank(pool.filter(o.mode==='exam'?scoped:active));
 const previous=rank(pool.filter(q=>!active(q)&&groups.has(q.concept_id)&&(stats.get(q.concept_id)?.due||0)<=now));
 const result:StudyQuestion[]=[],used=new Set<string>(),concepts=new Map<string,number>(),modes=new Map<string,number>();
 function take(xs:StudyQuestion[],count:number){
  while(count-->0){const choices=xs.filter(q=>!used.has(q.id)).sort((a,b)=>
    (concepts.get(a.concept_id)||0)*500+(modes.get(a.kind)||0)*15-priority(a)-((concepts.get(b.concept_id)||0)*500+(modes.get(b.kind)||0)*15-priority(b))||a.id.localeCompare(b.id));
   const q=choices[0];if(!q)break;result.push(q);used.add(q.id);concepts.set(q.concept_id,(concepts.get(q.concept_id)||0)+1);modes.set(q.kind,(modes.get(q.kind)||0)+1);
  }
 }
 const count=Math.min(o.count,o.timed?o.count:Math.max(1,Math.floor(o.minutes*60/40)));
 if(o.mode==='exam'){take(current,count);return result;}
 const priorTarget=Math.floor(count*.2);take(current,count-priorTarget);take(previous,priorTarget);take(current,count-result.length);take(previous,count-result.length);return result;
}
export function startSession(s:State,at:Date,id:string):Session{
 const chosen=selectDaily(s,at);
 return {id,day:localDay(at),status:chosen.length?'active':'complete',started:at.toISOString(),elapsed_ms:0,items:chosen.map(q=>({question_id:q.id,remedial:false,after:0,done:false})),remediation:{},extra:0,note:chosen.length?'':'所選範圍沒有可用題目。',settings:{...s.settings}};
}
export function nextItem(session:Session){const done=session.items.filter(i=>i.done).length;return session.items.find(i=>!i.done&&i.after<=done);}
export function record(s:State,session:Session,item:Item,event:Review){
 if(item.done||s.events.some(e=>e.id===event.id))return;
 const q=s.questions.find(q=>q.id===item.question_id);if(!q||event.question_id!==q.id||event.concept_id!==q.concept_id)throw Error('Review does not match question');
 // Provisional content can never promote long-term mastery, even if a caller requests it.
 const hinted=event.hint||!!item.hint_used;
 event={...event,hint:hinted,rating:hinted&&event.rating==='correct'?'hinted':event.rating,eligible:q.eligible&&q.assessment?.tier!=='B'&&event.eligible};
 s.events.push(event);item.done=true;item.event_id=event.id;
 const cid=event.concept_id;
 if(event.rating==='incorrect'||event.rating==='partial'||event.rating==='hinted'){
  session.remediation[cid]={successes:[],complete:false};
  const completed=session.items.filter(i=>i.done).length;
  for(const waiting of session.items)if(!waiting.done&&s.questions.find(q=>q.id===waiting.question_id)?.concept_id===cid)waiting.after=Math.max(waiting.after,completed+1);
 } else if(event.rating==='correct'&&session.remediation[cid]){
  const r=session.remediation[cid];if(!r.successes.includes(q.id))r.successes.push(q.id);r.complete=r.successes.length>=2;
 }
 const r=session.remediation[cid];
 if(r&&!r.complete&&!session.items.some(i=>!i.done&&s.questions.find(q=>q.id===i.question_id)?.concept_id===cid)){
  const used=session.items.map(i=>i.question_id),completed=session.items.filter(i=>i.done).length;
  const alternative=s.questions.filter(x=>!x.deleted&&(session.settings.includeProvisional||x.assessment?.tier!=='B')&&(session.settings.includeSamples||x.source.sample!==true)&&x.id!==q.id&&x.concept_id===cid&&!r.successes.includes(x.id)&&!s.reports.some(r=>r.question_id===x.id));
  alternative.sort((a,b)=>used.filter(id=>id===a.id).length-used.filter(id=>id===b.id).length||a.id.localeCompare(b.id));
  const other=alternative[0];
  // Require an intervening DIFFERENT concept. Do not invent immediate repetition at the end.
  const pending=session.items.filter(i=>!i.done&&s.questions.find(x=>x.id===i.question_id)?.concept_id!==cid);
  if(other&&session.extra+s.sessions.filter(x=>x.day===session.day&&x.id!==session.id).reduce((n,x)=>n+x.extra,0)<session.settings.maxExtra&&pending.length){session.items.push({question_id:other.id,remedial:true,after:completed+1,done:false});session.extra++;}
  else session.note='本日補強有上限；題型或間隔不足的概念保留待複習，不算補強完成。';
 }
 if(!nextItem(session)){session.status='complete';if(session.items.some(i=>!i.done))session.note='沒有可插入的其他概念，補強保留待日後複習；不立即重複或無限加題。';}
}

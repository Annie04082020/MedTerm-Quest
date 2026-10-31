import {schedule,effectiveReviews,type State,type Snapshot,type StudyQuestion,type Review,type Concept} from './core.ts';
export {effectiveReviews} from './core.ts';

export type PackageBody={format:'medterm-quest';schema:1;id:string;origin:string;created_at:string;kind:'bank'|'progress'|'combined';questions:StudyQuestion[];concepts:Concept[];events:Review[];mastery:Record<string,ReturnType<typeof schedule>>;scheduler:'interval-v1'};
export type StudyPackage={body:PackageBody;sha256:string};
export function canonical(value:unknown):string{
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(value&&typeof value==='object')return '{'+Object.keys(value).filter(k=>(value as any)[k]!==undefined).sort().map(k=>JSON.stringify(k)+':'+canonical((value as any)[k])).join(',')+'}';
 return JSON.stringify(value);
}
export async function fingerprint(value:unknown){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value))))].map(b=>b.toString(16).padStart(2,'0')).join('');}
export async function createPackage(s:State,kind:PackageBody['kind']='combined'):Promise<StudyPackage>{
 const mastery:PackageBody['mastery']={};if(kind!=='bank')for(const cid of new Set(s.events.map(e=>e.concept_id)))mastery[cid]=schedule(effectiveReviews(s),cid);
 const body:PackageBody={format:'medterm-quest',schema:1,id:crypto.randomUUID(),origin:s.installation,created_at:new Date().toISOString(),kind,
   questions:kind==='progress'?[]:s.questions,concepts:kind==='progress'?[]:s.concepts,events:kind==='bank'?[]:s.events,mastery,scheduler:'interval-v1'};
 return {body,sha256:await fingerprint(body)};
}
function requireThat(value:unknown,message:string):asserts value{if(!value)throw Error(message);}
function str(value:unknown,max=20000){return typeof value==='string'&&value.trim().length>0&&value.length<=max;}
const modes=['crossword','multiple_choice','matching','true_false','short_answer','clinical'];
function cleanTree(value:unknown,depth=0){
 requireThat(depth<25,'檔案巢狀過深');if(!value||typeof value!=='object')return;
 for(const [k,v] of Object.entries(value)){requireThat(!['__proto__','constructor','prototype'].includes(k),'不允許的 JSON 屬性');requireThat(!/^(?:api_key|openai_api_key|password|course_materials_dir|absolute_path|relative_path)$/i.test(k),'套件不可包含秘密或原始檔案路徑');cleanTree(v,depth+1);}
}
export function validateSnapshot(s:Snapshot){
 requireThat(s&&s.schema===1&&Array.isArray(s.questions)&&Array.isArray(s.concepts)&&Array.isArray(s.events),'題庫結構／版本不相容');
 requireThat(s.questions.length<=10000&&s.concepts.length<=10000&&s.events.length<=200000,'題庫或歷史超過單次匯入限制');cleanTree(s);
 const ids=new Set<string>();
 for(const q of s.questions){
  requireThat(str(q.id,160)&&!ids.has(q.id),'題目 ID 重複或無效');ids.add(q.id);
  requireThat(str(q.concept_id,160)&&Number.isInteger(q.revision)&&q.revision>0,'題目缺少穩定概念／修訂版本');
  requireThat(modes.includes(q.kind)&&str(q.prompt,4000)&&str(q.prompt_zh,4000)&&str(q.explanation_zh,10000),'題幹、說明或玩法無效');
  requireThat(str(q.course,300)&&str(q.topic,300)&&Number.isInteger(q.week)&&q.week>0&&q.week<=100,'課程分類無效');
  requireThat(typeof q.deleted==='boolean'&&typeof q.eligible==='boolean','缺少發布／學習政策');
  requireThat(q.assessment?.tier!=='B'||!q.eligible,'Tier B 不可累計長期精熟度');
  requireThat(!q.eligible||q.assessment?.status==='deterministic_source_verified','長期學習政策缺少來源檢查狀態');
  requireThat(!q.assessment||q.assessment.medically_verified===false||q.assessment.medically_verified===undefined,'不能以此檔案宣稱獨立醫學驗證');
  requireThat(q.assessment?.tier!=='C'||q.deleted,'Tier C 不能進入自動練習題庫');
  requireThat(q.source&&str(q.source.title,1000)&&str(q.source.section,1000),'缺少來源定位');
  requireThat(!q.source.quote||str(q.source.quote,30000),'來源引文過長');
  requireThat(Array.isArray(q.choices)&&Array.isArray(q.accepted_answers)&&Array.isArray(q.terms)&&q.terms.length>0&&Array.isArray(q.pairs)&&Array.isArray(q.entries),'題型欄位不完整');
  requireThat(q.choices.length<=100&&q.accepted_answers.length<=100&&q.terms.length<=64&&q.pairs.length<=50&&q.entries.length<=50,'題型項目過多');
  requireThat([...q.choices,...q.accepted_answers,...q.terms].every(x=>str(x,4000)),'答案／術語欄位無效');
  requireThat(q.answer&&(['matching','crossword'].includes(q.kind)?typeof q.answer==='object':str(q.answer,4000)),'答案型態無效');
  if(q.kind==='multiple_choice')requireThat(q.choices.length>=2&&new Set(q.choices).size===q.choices.length&&q.choices.includes(q.answer as string),'選擇題答案或選項無效');
  if(typeof q.answer==='object'){
   const entries=q.kind==='matching'?q.pairs:q.entries;
   requireThat(entries.length>0&&entries.length<=50&&Object.keys(q.answer).length===entries.length&&new Set(entries.map(e=>e.id)).size===entries.length,'配對／填字項目不完整');
   for(const e of entries)requireThat(str(e.id,80)&&str(q.answer[e.id],2000),'配對／填字答案缺漏');
   if(q.kind==='matching')requireThat(q.pairs.every(p=>str(p.definition,4000)&&q.choices.includes((q.answer as Record<string,string>)[p.id])),'配對定義或選項缺漏');
   if(q.kind==='crossword')requireThat(q.entries.every(e=>Number.isInteger(e.row)&&e.row>=0&&e.row<=60&&Number.isInteger(e.col)&&e.col>=0&&e.col<=60&&Number.isInteger(e.length)&&e.length>0&&e.length<=60&&['across','down'].includes(e.direction)&&str(e.clue,4000)&&/^[A-Za-z]+$/.test((q.answer as Record<string,string>)[e.id])&&(q.answer as Record<string,string>)[e.id].length===e.length),'填字格線無效');
  }
 }
 ids.clear();for(const c of s.concepts){requireThat(str(c.concept_id,160)&&!ids.has(c.concept_id)&&str(c.title,1000)&&str(c.course,300)&&str(c.topic,300)&&Number.isInteger(c.week)&&c.week>0&&Number.isInteger(c.revision)&&c.revision>0,'概念 ID／內容無效');ids.add(c.concept_id);
  requireThat(c.deleted===undefined||typeof c.deleted==='boolean','概念封存標記無效');
  if(c.assessment)requireThat(typeof c.assessment==='object'&&(c.assessment.medically_verified===false||c.assessment.medically_verified===undefined),'概念不可宣稱獨立醫學驗證');
  if(c.sources)requireThat(Array.isArray(c.sources)&&c.sources.length<=100&&c.sources.every(r=>str(r.locator,1000)&&typeof r.quote==='string'&&r.quote.length<=30000),'概念來源定位無效');
 }
 ids.clear();for(const e of s.events){requireThat(str(e.id,200)&&!ids.has(e.id)&&str(e.concept_id,160)&&str(e.question_id,160)&&Number.isFinite(Date.parse(e.at))&&['correct','hinted','partial','incorrect','observed'].includes(e.rating)&&modes.includes(e.mode)&&typeof e.eligible==='boolean'&&typeof e.hint==='boolean'&&(e.latency_ms===null||Number.isInteger(e.latency_ms)&&e.latency_ms>=0&&e.latency_ms<=86400000),'複習事件 ID／內容無效');ids.add(e.id);}
}
export async function parsePackage(text:string):Promise<StudyPackage>{
 requireThat(new TextEncoder().encode(text).length<=30*1024*1024,'套件超過 30 MiB 限制');const p=JSON.parse(text) as StudyPackage;
 requireThat(p?.body?.format==='medterm-quest'&&p.body.schema===1,'不是支援的 MedTerm Quest 套件版本');
 requireThat(str(p.body.id,200)&&str(p.body.origin,200)&&Number.isFinite(Date.parse(p.body.created_at))&&['bank','progress','combined'].includes(p.body.kind)&&p.body.scheduler==='interval-v1','套件標頭無效');
 requireThat(typeof p.sha256==='string'&&p.sha256===await fingerprint(p.body),'檔案完整性檢查失敗');
 validateSnapshot({schema:1,questions:p.body.questions,concepts:p.body.concepts,events:p.body.events});
 requireThat(p.body.kind!=='bank'||!p.body.events.length,'題庫套件不可夾帶複習歷史');requireThat(p.body.kind!=='progress'||!p.body.questions.length&&!p.body.concepts.length,'進度套件不可改寫題庫');
 return p;
}
export function mergeSnapshot(current:State,incoming:Snapshot){
 validateSnapshot(incoming);const next=JSON.parse(JSON.stringify(current)) as State;
 const report={added:0,updated:0,archived:0,events_added:0,stale_ignored:0,duplicates:0};
 function merge<T extends {revision:number;deleted?:boolean}>(old:T[],items:T[],id:(item:T)=>string){
  const map=new Map(old.map(x=>[id(x),x]));for(const value of items){const prior=map.get(id(value));
   if(prior){if(value.revision<prior.revision){report.stale_ignored++;continue;}if(value.revision===prior.revision){requireThat(canonical(prior)===canonical(value),'同一 ID／版本內容衝突：'+id(value));report.duplicates++;continue;}report.updated++;}else report.added++;
   if(value.deleted&&!prior?.deleted)report.archived++;map.set(id(value),value);
  }return [...map.values()];
 }
 next.questions=merge(next.questions,incoming.questions,x=>x.id);next.concepts=merge(next.concepts,incoming.concepts,x=>x.concept_id);
 const concepts=new Map(next.concepts.map(c=>[c.concept_id,c])),questions=new Map(next.questions.map(q=>[q.id,q]));
 for(const q of next.questions){requireThat(concepts.has(q.concept_id),'缺少父概念：'+q.concept_id);requireThat(q.deleted||!concepts.get(q.concept_id)?.deleted,'可用題目指向已刪除概念');}
 const events=new Map(next.events.map(e=>[e.id,e]));for(const e of incoming.events){const prior=events.get(e.id);if(prior){requireThat(canonical(prior)===canonical(e),'同一複習事件 ID 內容衝突：'+e.id);report.duplicates++;continue;}
  requireThat(questions.get(e.question_id)?.concept_id===e.concept_id,'進度缺少相符題庫；請先匯入題庫：'+e.question_id);events.set(e.id,e);report.events_added++;
 }
 next.events=[...events.values()].sort((a,b)=>Date.parse(a.at)-Date.parse(b.at)||a.id.localeCompare(b.id));
 // Keep historical content/events. Retire pending items, without fabricating attempts.
 for(const session of next.sessions){let retired=false;for(const item of session.items)if(!item.done&&questions.get(item.question_id)?.deleted){item.done=true;retired=true;}if(retired){session.note='更新已撤下部分未作答題目；所有作答歷史均保留。';if(session.items.every(i=>i.done))session.status='complete';}}
 return {state:next,report};
}

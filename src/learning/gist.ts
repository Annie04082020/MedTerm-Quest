import {encrypt,decrypt} from './encryption.ts';
import {createPackage,parsePackage,mergeSnapshot,type StudyPackage} from './sync.ts';
import type {State} from './core.ts';
export type SyncStore={read:()=>Promise<State>;update:(change:(s:State)=>void)=>Promise<State>};
type Options={gistId:string;token:string;password:string;store:SyncStore;fetcher?:typeof fetch;signal?:AbortSignal;onCreated?:(id:string)=>void};
const MAX=16*1024*1024, slot=/^medterm-device-[0-9a-f-]{36}\.json$/i;
function assert(ok:unknown,message:string):asserts ok{if(!ok)throw Error(message);}
async function bounded(response:Response){
 const length=Number(response.headers.get('content-length'));if(length>MAX)throw Error('遠端同步資料過大，請改用檔案交換。');
 const reader=response.body?.getReader();if(!reader)throw Error('遠端回應無效');let size=0;const chunks:Uint8Array[]=[];
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>MAX)throw Error('遠端同步資料過大，請改用檔案交換。');chunks.push(value);}}finally{await reader.cancel();}
 const all=new Uint8Array(size);let offset=0;for(const c of chunks){all.set(c,offset);offset+=c.length;}return new TextDecoder('utf-8',{fatal:true}).decode(all);
}
export function selectInitialCourse(s:State,fresh:boolean){if(fresh){const q=s.questions.find(q=>!q.deleted);if(q){s.settings.course=q.course;s.settings.week=q.week;s.settings.topic='';s.settings.scopeWeeks=[q.week];}}}
export async function exchangeGist(o:Options){
 assert(o.token.trim()&&!/[\r\n]/.test(o.token),'請設定有效的 GitHub Token。');assert(!o.gistId||/^[a-f0-9]{20,64}$/i.test(o.gistId),'Gist ID 格式無效，請貼上 ID 而非整個網址。');
 const fetcher=o.fetcher||fetch;
 async function request(path:string,body?:unknown,method=body?'PATCH':'GET',raw=false){
  const controller=new AbortController(),abort=()=>controller.abort();o.signal?.addEventListener('abort',abort,{once:true});if(o.signal?.aborted)abort();const timeout=setTimeout(abort,25000);
  try{
   const r=await fetcher(raw?path:'https://api.github.com'+path,{method,credentials:'omit',redirect:'error',cache:'no-store',signal:controller.signal,headers:raw?{}:{Authorization:'Bearer '+o.token.trim(),Accept:'application/vnd.github+json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
   if(!r.ok)throw Error(r.status===401?'GitHub Token 無效或已過期。':r.status===403?'GitHub 權限不足或已達請求限制，請檢查 Gists 讀寫權限後稍後重試。':r.status===404?'找不到 Gist 或沒有存取權限。':`GitHub 同步失敗（HTTP ${r.status}）。`);
   return await bounded(r);
  }catch(e){if(controller.signal.aborted)throw Error('同步已取消或連線逾時；本機作答已保留。');if(e instanceof TypeError)throw Error('無法連接 GitHub；可繼續離線練習，稍後再同步。');throw e;}
  finally{clearTimeout(timeout);o.signal?.removeEventListener('abort',abort);}
 }
 let id=o.gistId;const remote:StudyPackage[]=[];const initial=await o.store.read();
 if(id){
  const gist=JSON.parse(await request('/gists/'+id));assert(gist.public===false,'請使用 Secret Gist；不會將學習資料寫入公開 Gist。');assert(!gist.truncated,'Gist 檔案列表不完整，已停止同步。');assert(gist.files&&typeof gist.files==='object','Gist 檔案格式無效');
  const files=Object.entries(gist.files).filter(([name])=>slot.test(name));assert(files.length>0&&files.length<=16,'此 Gist 沒有支援的裝置資料，或裝置數超過 16。');
  assert(files.length<16||files.some(([name])=>name==='medterm-device-'+initial.installation+'.json'),'此 Gist 已有 16 個裝置，請使用檔案交換或新的 Gist。');
  for(const [,v] of files){
   const f=v as {content?:string;truncated?:boolean;raw_url?:string};let text=f.content;
   if(f.truncated){const u=new URL(f.raw_url||'');const parts=u.pathname.split('/');assert(u.protocol==='https:'&&u.hostname==='gist.githubusercontent.com'&&!u.username&&!u.password&&parts[2]===id&&parts[3]==='raw'&&/^[0-9a-f]{40,64}$/i.test(parts[4]||''),'不安全的 Gist 原始檔案網址');text=await request(u.href,undefined,'GET',true);}
   assert(typeof text==='string'&&text.length<MAX,'遠端裝置資料缺漏或過大');remote.push(await parsePackage(await decrypt(JSON.parse(text),o.password)));
  }
 }
 // Validate the complete merge against a fresh local transaction before any write.
 const state=await o.store.update(s=>{const fresh=!s.questions.length;for(const p of remote)Object.assign(s,mergeSnapshot(s,p.body).state);selectInitialCourse(s,fresh);});
 assert(/^[0-9a-f-]{36}$/i.test(state.installation),'本機裝置 ID 無效，請先備份資料。');
 const filename='medterm-device-'+state.installation+'.json',content=JSON.stringify(await encrypt(JSON.stringify(await createPackage(state)),o.password));
 if(o.signal?.aborted)throw Error('同步已取消；本機資料保留。');
 if(id)await request('/gists/'+id,{files:{[filename]:{content}}});
 else{const created=JSON.parse(await request('/gists',{description:'MedTerm Quest encrypted study sync v1',public:false,files:{[filename]:{content}}},'POST'));assert(typeof created.id==='string'&&/^[0-9a-f]{20,64}$/i.test(created.id),'GitHub 未回傳有效的 Gist ID');id=created.id;o.onCreated?.(id);}
 // Each installation patches only its own slot. Concurrent devices never replace
 // one another's events. New local answers during upload remain for the next sync.
 return {gistId:id,state,devices:remote.length||1};
}

import {encrypt,decrypt,type Encrypted} from './learning/encryption';
import {exchangeGist} from './learning/gist';
import {readState,updateState} from './learning/store';
import {localDay} from './learning/core';
export type GistConfig={id:string;auto:boolean;lastSync?:string;tokenBox?:Encrypted};
const KEY='medterm-gist-v1';let unlocked:{token:string;password:string}|null=null,active:Promise<void>|null=null,controller:AbortController|null=null,lastAuto=0,autoTimer:ReturnType<typeof setTimeout>|undefined;
export function config():GistConfig{try{const c=JSON.parse(localStorage.getItem(KEY)||'{}');return {id:typeof c.id==='string'?c.id:'',auto:c.auto===true,lastSync:c.lastSync,tokenBox:c.tokenBox};}catch{return {id:'',auto:false};}}
function save(c:GistConfig){localStorage.setItem(KEY,JSON.stringify(c));window.dispatchEvent(new Event('medterm-sync-status'));}
export function connected(){return !!unlocked;}
export async function unlock(token:string,password:string,id:string,auto:boolean,remember:boolean){
 const prior=config();const secret=token.trim()||(prior.tokenBox?await decrypt(prior.tokenBox,password):'');if(!secret)throw Error('請輸入 GitHub Token。');
 // Validate passphrase even when credential persistence is off.
 const box=await encrypt(secret,password);save({id:id.trim(),auto,lastSync:prior.id===id.trim()?prior.lastSync:undefined,...(remember?{tokenBox:box}:{})});unlocked={token:secret,password};window.dispatchEvent(new Event('medterm-sync-status'));
}
export function lock(){controller?.abort();clearTimeout(autoTimer);unlocked=null;window.dispatchEvent(new Event('medterm-sync-status'));}
export function forget(){lock();localStorage.removeItem(KEY);window.dispatchEvent(new Event('medterm-sync-status'));}
export async function synchronize(){
 if(active)return active;if(!unlocked)throw Error('請先解鎖 Gist 同步。');const auth=unlocked,c=config();controller=new AbortController();
 async function run(){
  const before=await readState();if(before.sessions.some(s=>s.day===localDay(new Date())&&s.status==='active'))throw Error('請先暫停目前挑戰再同步；避免在作答途中更新題目。');
  const result=await exchangeGist({gistId:c.id,token:auth.token,password:auth.password,store:{read:readState,update:updateState},signal:controller!.signal,onCreated:id=>{if(unlocked===auth)save({...config(),id});}});
  if(unlocked===auth)save({...config(),id:result.gistId,lastSync:new Date().toISOString()});window.dispatchEvent(new Event('medterm-data-changed'));
 }
 active=(async()=>{try{if(navigator.locks)await navigator.locks.request('medterm-gist-sync',run);else await run();}finally{active=null;controller=null;}})();return active;
}
export function automaticSync(event?:Event){
 if(!unlocked||!config().auto||!navigator.onLine)return;
 if(active){const retry=()=>{clearTimeout(autoTimer);autoTimer=setTimeout(()=>automaticSync(event),200);};void active.then(retry,retry);return;}
 const remaining=30000-(Date.now()-lastAuto);if(remaining>0&&event?.type!=='medterm-session-complete'){clearTimeout(autoTimer);autoTimer=setTimeout(()=>automaticSync(),remaining);return;}lastAuto=Date.now();
 void synchronize().then(()=>window.dispatchEvent(new CustomEvent('medterm-sync-message',{detail:'已自動同步題庫與作答紀錄。'}))).catch(e=>window.dispatchEvent(new CustomEvent('medterm-sync-message',{detail:(e as Error).message})));
}

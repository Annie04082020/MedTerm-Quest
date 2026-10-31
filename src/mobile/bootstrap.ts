import {readState,updateState} from '../learning/store';
import {parsePackage,mergeSnapshot} from '../learning/sync';
// Only fetch an APK asset on an empty install, never a backend or external URL.
export async function bootstrap(){
 const current=await readState();if(current.questions.length)return current;
 const info=await fetch('./bank-info.json');
 if(info.ok&&(await info.json()).bundled===false)return current;
 const response=await fetch('./banks/starter.json');if(!response.ok)throw Error('找不到隨附題庫；請重新安裝完整 APK。');
 const bank=await parsePackage(await response.text());
 if(bank.body.kind!=='bank'||bank.body.events.length)throw Error('隨附題庫不可包含學習紀錄。');
 return updateState(s=>{if(s.questions.length)return;Object.assign(s,mergeSnapshot(s,{schema:1,questions:bank.body.questions,concepts:bank.body.concepts,events:[]}).state);});
}

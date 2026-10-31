import {useState} from 'react';
import {createPackage,parsePackage,mergeSnapshot,type StudyPackage,type PackageBody} from './learning/sync';
import {readState,updateState} from './learning/store';
import type {State} from './learning/core';
import {nativeAndroid,LocalDocuments} from './platform';

export default function SyncPanel({onChanged}:{onChanged:(s:State)=>void}){
 const [error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[prepared,setPrepared]=useState<StudyPackage|null>(null);
 async function exportFile(kind:PackageBody['kind']){setBusy(true);setError('');try{
  const p=await createPackage(await readState(),kind),text=JSON.stringify(p,null,2),blob=new Blob([text],{type:'application/json'});
  if(blob.size>30*1024*1024)throw Error('套件超過 30 MiB 限制，未匯出。');
  const name=`medterm-${kind}-${p.body.created_at.slice(0,10)}.json`;
  if(nativeAndroid){const result=await LocalDocuments.savePackage({text,name});setMessage(result.cancelled?'已取消匯出，資料不變。':'已將檔案儲存到你選擇的位置。');return;}
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download=`medterm-${kind}-${p.body.created_at.slice(0,10)}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  setMessage('已匯出；檔案含題目答案／來源摘錄或個人進度，請自行保存。');
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function nativeImport(){setPrepared(null);setBusy(true);setError('');try{const result=await LocalDocuments.openPackage();if(result.cancelled){setMessage('已取消匯入，資料不變。');return;}if(typeof result.text!=='string')throw Error('無法讀取題庫檔');await inspect(new File([result.text],result.name||'bank.json',{type:'application/json'}));}catch(e){setError('未匯入，原資料保留：'+(e as Error).message);}finally{setBusy(false);}}
 async function inspect(file:File){setPrepared(null);setBusy(true);setError('');setMessage('');try{
  if(file.size>30*1024*1024)throw Error('套件超過 30 MiB 限制');
  const parsed=await parsePackage(await file.text()),preview=mergeSnapshot(await readState(),{schema:1,questions:parsed.body.questions,concepts:parsed.body.concepts,events:parsed.body.events});
  setPrepared(parsed);setMessage(`驗證完成：新增 ${preview.report.added} 筆內容，更新 ${preview.report.updated}，封存 ${preview.report.archived}，新增 ${preview.report.events_added} 筆歷史；略過舊版本 ${preview.report.stale_ignored}。尚未寫入。`);
 }catch(e){setError('未匯入，原資料保留：'+(e as Error).message);}finally{setBusy(false);}}
 async function commit(){if(!prepared)return;setBusy(true);setError('');try{
  const next=await updateState(current=>{const merged=mergeSnapshot(current,{schema:1,questions:prepared.body.questions,concepts:prepared.body.concepts,events:prepared.body.events});Object.assign(current,merged.state);});
  onChanged(next);setPrepared(null);setMessage('匯入完成。既有作答、週次設定及歷史已保留；精熟狀態依歷史重新計算。');
 }catch(e){setError('交易已取消，原資料保留：'+(e as Error).message);}finally{setBusy(false);}}
 return <section className="processing-panel"><h2>題庫檔案與進度交換</h2><p>完全手動，不使用雲端帳號或網路。先驗證整份檔案，再以單一交易保存。同一 ID／版本內容衝突會停止匯入，避免覆寫進度。</p>
 <div className="processing-form"><button className="secondary-button" disabled={busy} onClick={()=>exportFile('bank')}>匯出題庫</button><button className="secondary-button" disabled={busy} onClick={()=>exportFile('progress')}>匯出進度</button><button className="secondary-button" disabled={busy} onClick={()=>exportFile('combined')}>匯出題庫與進度備份</button>
 {nativeAndroid?<button className="secondary-button" disabled={busy} onClick={nativeImport}>選擇本機題庫或進度檔案</button>:<label>匯入 MedTerm Quest 檔案<input aria-label="匯入題庫或進度檔案" type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)void inspect(file);e.target.value='';}}/></label>}</div>
 {message&&<p role="status">{message}</p>}{error&&<p role="alert">{error}</p>}{prepared&&<button className="primary-button" disabled={busy} onClick={commit}>套用已驗證的匯入檔</button>}
 <p className="processing-hint">檔案使用穩定 ID、修訂版與 SHA-256 完整性檢查。完整性檢查不是醫學驗證。更新會保留撤下題目的歷史；暫定題永遠不計長期精熟度。進度檔須搭配對應題庫。來源引文可離線閱讀，完整 PDF／影片仍留在桌面外部教材目錄。</p></section>;
}

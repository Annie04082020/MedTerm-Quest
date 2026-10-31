import {useEffect,useState} from 'react';
import {nativeAndroid} from './platform';
import {reminderConfig,reminderStatus,saveReminders,testReminder} from './reminderRuntime';
import {reminderDefaults,type Reminders} from './learning/reminders';
export default function ReminderPanel(){
 const [value,setValue]=useState<Reminders>({...reminderDefaults}),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[count,setCount]=useState(0),[permission,setPermission]=useState(false);
 async function inspect(){try{const s=await reminderStatus();setCount(s.count);setPermission(s.permission);}catch(e){setMessage((e as Error).message);}}
 useEffect(()=>{try{setValue(reminderConfig());}catch(e){setMessage((e as Error).message);}void inspect();window.addEventListener('medterm-reminders-changed',inspect);return()=>window.removeEventListener('medterm-reminders-changed',inspect);},[]);
 async function save(){setBusy(true);try{await saveReminders(value);setMessage('提醒設定已保存於此手機。');await inspect();}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}}
 async function test(){setBusy(true);try{await testReminder();setMessage('已傳送本機測試提醒，請查看通知欄。');await inspect();}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}}
 if(!nativeAndroid)return <section><h1>本機提醒</h1><p>每日與每週的原生提醒在 Android APK 提供。網站可練習與同步；關閉網頁後不會發送提醒。</p></section>;
 return <section><h1>本機提醒</h1><p>此手機自行排程，電腦關機或沒有網路也能提醒。首次啟用時會詢問 Android 通知權限。</p><p>通知權限：{permission?'已允許':'尚未允許'} · {count} 個已排程提醒</p>
 <div className="processing-form"><label><input type="checkbox" aria-label="每日提醒" checked={value.daily} onChange={e=>setValue({...value,daily:e.target.checked})}/>每日練習提醒</label><label>每日時間<input type="time" aria-label="每日提醒時間" value={value.dailyTime} onChange={e=>setValue({...value,dailyTime:e.target.value})}/></label>
 <label><input type="checkbox" aria-label="每週提醒" checked={value.weekly} onChange={e=>setValue({...value,weekly:e.target.checked})}/>每週複習提醒</label><label>每週時間<input type="time" aria-label="每週提醒時間" value={value.weeklyTime} onChange={e=>setValue({...value,weeklyTime:e.target.value})}/></label><label>每週星期<select aria-label="每週提醒星期" value={value.weekday} onChange={e=>setValue({...value,weekday:Number(e.target.value)})}>{['日','一','二','三','四','五','六'].map((day,i)=><option key={day} value={i+1}>星期{day}</option>)}</select></label>
 <button className="primary-button" disabled={busy} onClick={save}>儲存提醒設定</button><button className="secondary-button" disabled={busy} onClick={test}>傳送測試提醒</button><button className="text-button" disabled={busy} onClick={inspect}>重新檢查提醒</button></div>
 {message&&<p role="status">{message}</p>}<p className="processing-hint">依手機當地時間排程；省電模式與系統政策可能延後送達，不保證準點。沒有要求精準鬧鐘權限。提醒設定只保存在此手機，不會跟 Gist 同步。若系統停用了通知，請在 Android 設定重新允許。</p></section>;
}

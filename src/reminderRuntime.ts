import {LocalNotifications} from '@capacitor/local-notifications';
import {nativeAndroid} from './platform';
import {reminderDefaults,validateReminders,reminderPlan,changeReminders,type Reminders,type ReminderDriver} from './learning/reminders';
const KEY='medterm-reminders-v1';let tail:Promise<unknown>=Promise.resolve();
export function reminderConfig(){const raw=localStorage.getItem(KEY);return raw?validateReminders(JSON.parse(raw)):{...reminderDefaults};}
const driver:ReminderDriver={permission:async()=>(await LocalNotifications.checkPermissions()).display==='granted',request:async()=>(await LocalNotifications.requestPermissions()).display==='granted',channel:()=>LocalNotifications.createChannel({id:'study-reminders',name:'學習提醒',description:'每日與每週的本機練習提醒',importance:3}),cancel:ids=>LocalNotifications.cancel({notifications:ids.map(id=>({id}))}),schedule:notifications=>LocalNotifications.schedule({notifications})};
export function saveReminders(c:Reminders){
 if(!nativeAndroid)return Promise.reject(Error('原生本機提醒只在 Android APK 提供。'));
 const job=tail.then(()=>changeReminders(c,reminderConfig(),driver,value=>localStorage.setItem(KEY,JSON.stringify(value)))).then(value=>{window.dispatchEvent(new Event('medterm-reminders-changed'));return value;});tail=job.catch(()=>{});return job;
}
export async function reminderStatus(){if(!nativeAndroid)return {permission:false,count:0};await tail;return {permission:await driver.permission(),count:(await LocalNotifications.getPending()).notifications.filter(n=>[63001,63002].includes(n.id)).length};}
export async function restoreReminders(){
 if(!nativeAndroid)return;const c=reminderConfig();if(!await driver.permission())return;if(reminderPlan(c).length)await saveReminders(c);
}
export async function testReminder(){
 if(!nativeAndroid)throw Error('測試提醒需使用 Android APK。');if(!await driver.permission()&&!await driver.request())throw Error('通知權限未開啟，無法傳送測試提醒。');await driver.channel();
 await LocalNotifications.schedule({notifications:[{id:63003,title:'MedTerm Quest · 測試提醒',body:'本機提醒已連接；點擊可開啟每日挑戰。',channelId:'study-reminders',smallIcon:'ic_stat_study',isExactNotification:false,extra:{target:'daily'}}]});
}
export async function watchReminderActions(){
 if(!nativeAndroid)return ()=>{};
 const listener=await LocalNotifications.addListener('localNotificationActionPerformed',e=>{if(e.notification.extra?.target==='daily')window.dispatchEvent(new Event('medterm-open-daily'));});return ()=>{void listener.remove();};
}

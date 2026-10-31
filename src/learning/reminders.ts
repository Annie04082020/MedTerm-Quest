export type Reminders={schema:1;daily:boolean;dailyTime:string;weekly:boolean;weeklyTime:string;weekday:number};
export const reminderDefaults:Reminders={schema:1,daily:false,dailyTime:'20:00',weekly:false,weeklyTime:'19:00',weekday:1};
export const reminderIds=[63001,63002];
export function validateReminders(value:unknown):Reminders{
 const c=value as Reminders;if(!c||c.schema!==1||typeof c.daily!=='boolean'||typeof c.weekly!=='boolean'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(c.dailyTime)||!/^([01]\d|2[0-3]):[0-5]\d$/.test(c.weeklyTime)||!Number.isInteger(c.weekday)||c.weekday<1||c.weekday>7)throw Error('提醒設定無效；請選擇有效時間與星期。');
 return {schema:1,daily:c.daily,dailyTime:c.dailyTime,weekly:c.weekly,weeklyTime:c.weeklyTime,weekday:c.weekday};
}
export function reminderPlan(value:Reminders){
 const c=validateReminders(value);const result:{id:number;title:string;body:string;channelId:string;smallIcon:string;isExactNotification:false;extra:{target:string};schedule:{on:{hour:number;minute:number;second:number;weekday?:number};repeats:true;allowWhileIdle:true}}[]=[];
 function add(id:number,time:string,weekly:boolean){const [hour,minute]=time.split(':').map(Number);result.push({id,title:weekly?'MedTerm Quest · 本週複習':'MedTerm Quest · 每日練習',body:weekly?'回顧本週與到期概念，花幾分鐘繼續學習。':'今天的短練習已在裝置上，離線也能開始。',channelId:'study-reminders',smallIcon:'ic_stat_study',isExactNotification:false,extra:{target:'daily'},schedule:{on:{hour,minute,second:0,...(weekly?{weekday:c.weekday}:{})},repeats:true,allowWhileIdle:true}});}
 if(c.daily)add(63001,c.dailyTime,false);if(c.weekly)add(63002,c.weeklyTime,true);return result;
}
export type ReminderDriver={permission:()=>Promise<boolean>;request:()=>Promise<boolean>;channel:()=>Promise<unknown>;cancel:(ids:number[])=>Promise<unknown>;schedule:(notifications:ReturnType<typeof reminderPlan>)=>Promise<unknown>};
export async function changeReminders(next:Reminders,previous:Reminders,driver:ReminderDriver,save:(value:Reminders)=>void){
 const clean=validateReminders(next),plan=reminderPlan(clean),prior=reminderPlan(previous);
 if(plan.length&&!await driver.permission()&&!await driver.request())throw Error('通知權限未開啟，沒有啟用提醒。可在 Android 設定允許後再試。');
 await driver.channel();
 try{await driver.cancel(reminderIds);if(plan.length)await driver.schedule(plan);save(clean);}
 catch{try{await driver.cancel(reminderIds);if(prior.length)await driver.schedule(prior);}catch{throw Error('提醒排程失敗且無法恢復；本機學習資料未變更，請重新檢查提醒設定。');}throw Error('提醒設定未保存，已恢復原排程；本機學習資料未變更。');}
 return clean;
}

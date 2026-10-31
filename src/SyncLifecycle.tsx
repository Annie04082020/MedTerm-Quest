import {useEffect,useState} from 'react';
import {automaticSync} from './gistRuntime';
export default function SyncLifecycle(){
 const [message,setMessage]=useState('');
 useEffect(()=>{
  const resume=()=>{if(document.visibilityState==='visible')automaticSync();};const status=(e:Event)=>setMessage((e as CustomEvent<string>).detail);
  window.addEventListener('online',automaticSync);window.addEventListener('medterm-session-complete',automaticSync);document.addEventListener('visibilitychange',resume);window.addEventListener('medterm-sync-message',status);automaticSync();
  return()=>{window.removeEventListener('online',automaticSync);window.removeEventListener('medterm-session-complete',automaticSync);document.removeEventListener('visibilitychange',resume);window.removeEventListener('medterm-sync-message',status);};
 },[]);
 return message?<aside className="library-notice sync-toast" role="status"><span>{message}</span><button className="text-button" onClick={()=>setMessage('')}>關閉同步訊息</button></aside>:null;
}

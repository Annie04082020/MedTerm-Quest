import {defaults,type State} from './core';
import {LearningData,nativeAndroid} from '../platform';
import {createSerializedStore} from './serializedStore';
function empty():State{return {schema:1,installation:crypto.randomUUID(),questions:[],concepts:[],events:[],settings:{...defaults},sessions:[],reports:[]};}
function open():Promise<IDBDatabase>{return new Promise((resolve,reject)=>{const r=indexedDB.open('medterm-learning',1);r.onupgradeneeded=()=>r.result.createObjectStore('state');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
// Single read/write transaction prevents partial saves and cross-tab lost updates.
export async function updateState(change:(s:State)=>void):Promise<State>{
 if(nativeAndroid)return nativeUpdate(change);
 const db=await open();return new Promise((resolve,reject)=>{const tx=db.transaction('state','readwrite'),store=tx.objectStore('state');let next:State;
  const r=store.get('root');r.onsuccess=()=>{try{next=r.result||empty();next.settings={...defaults,...next.settings};change(next);store.put(next,'root');}catch(e){tx.abort();reject(e);}};
  tx.oncomplete=()=>{db.close();resolve(next);};tx.onabort=()=>{db.close();reject(tx.error||Error('Local save cancelled'));};tx.onerror=()=>reject(tx.error);
 });
}
const nativeUpdate=createSerializedStore(LearningData,empty);
export function readState(){return updateState(()=>{});}

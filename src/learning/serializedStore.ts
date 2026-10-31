import {defaults,type State} from './core.ts';
export type StateAdapter={load:()=>Promise<{payload:string|null;revision:number}>;commit:(value:{payload:string;expectedRevision:number})=>Promise<unknown>};
// Serialize native writes. SQLite also checks revisions within its transaction.
export function createSerializedStore(adapter:StateAdapter,initial:()=>State){
 let tail:Promise<unknown>=Promise.resolve();
 return function update(change:(s:State)=>void):Promise<State>{
  const operation=tail.then(async()=>{
   const prior=await adapter.load(),next:State=prior.payload?JSON.parse(prior.payload):initial();
   if(next.schema!==1||!Array.isArray(next.questions)||!Array.isArray(next.events))throw Error('本機資料版本不相容；原資料未變更。');
   next.settings={...defaults,...next.settings};change(next);
   const payload=JSON.stringify(next);
   if(payload!==prior.payload)await adapter.commit({payload,expectedRevision:prior.revision});
   return JSON.parse(payload) as State;
  });
  tail=operation.then(()=>undefined,()=>undefined);return operation;
 };
}

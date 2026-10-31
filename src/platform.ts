import {Capacitor,registerPlugin} from '@capacitor/core';
export const nativeAndroid=Capacitor.getPlatform()==='android';
export const LearningData=registerPlugin<{
 load():Promise<{payload:string|null;revision:number}>;
 commit(options:{payload:string;expectedRevision:number}):Promise<{revision:number}>;
}>('LearningData');
export const LocalDocuments=registerPlugin<{
 openPackage():Promise<{cancelled:boolean;text?:string;name?:string}>;
 savePackage(options:{text:string;name:string}):Promise<{cancelled:boolean}>;
}>('LocalDocuments');

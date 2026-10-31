import fs from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
// Cloud CI builds an empty app. Course banks remain local and are imported on-device.
// An explicitly supplied local bank can be bundled for local acceptance only.
const bank=process.env.MEDTERM_MOBILE_BANK;
const text=bank?await fs.readFile(bank,'utf8'):null,parsed=text?JSON.parse(text):null;
if(parsed&&(parsed.body?.format!=='medterm-quest'||parsed.body.kind!=='bank'||parsed.body.events?.length))throw Error('Mobile starter must be a bank-only package without progress');
const result=spawnSync(process.execPath,['node_modules/vite/bin/vite.js','build','--mode','android','--outDir','dist-android'],{stdio:'inherit'});
if(result.status!==0)process.exit(result.status||1);
if(text){await fs.mkdir('dist-android/banks',{recursive:true});await fs.writeFile('dist-android/banks/starter.json',text);}
await fs.writeFile('dist-android/bank-info.json',JSON.stringify({bundled:!!text,sha256:parsed?.sha256,active_questions:parsed?.body.questions.filter(q=>!q.deleted).length||0}));
console.log(text?'Existing bank bundled for local acceptance only.':'Empty APK shell prepared; no course materials, questions or progress uploaded to CI.');

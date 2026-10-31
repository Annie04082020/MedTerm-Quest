// Versioned authenticated encryption for optional user-owned Gist storage.
const LIMIT=6*1024*1024, ITERATIONS=600000;
export type Encrypted={format:'medterm-encrypted';schema:1;kdf:'PBKDF2-SHA256';iterations:600000;cipher:'AES-256-GCM';salt:string;iv:string;data:string};
function encode(bytes:Uint8Array){let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s);}
function decode(s:string,max:number){if(typeof s!=='string'||s.length>4*Math.ceil(max/3)||!/^[A-Za-z0-9+/]*={0,2}$/.test(s))throw Error('加密資料格式無效');const raw=atob(s);if(raw.length>max)throw Error('加密資料過大');return Uint8Array.from(raw,c=>c.charCodeAt(0));}
async function key(password:string,salt:Uint8Array){
 if(typeof password!=='string'||password.length<12||password.length>1024)throw Error('同步密碼需為 12–1024 個字元；其他裝置請使用相同密碼。');
 const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveKey']);
 return crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt:salt as BufferSource,iterations:ITERATIONS},material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
const aad=new TextEncoder().encode('medterm-encrypted:v1');
export async function encrypt(text:string,password:string):Promise<Encrypted>{
 const plain=new TextEncoder().encode(text);if(plain.length>LIMIT)throw Error('同步資料超過 6 MiB，請改用檔案備份。');
 const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
 const data=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad},await key(password,salt),plain);
 return {format:'medterm-encrypted',schema:1,kdf:'PBKDF2-SHA256',iterations:ITERATIONS,cipher:'AES-256-GCM',salt:encode(salt),iv:encode(iv),data:encode(new Uint8Array(data))};
}
export async function decrypt(value:unknown,password:string){
 const e=value as Encrypted;
 if(!e||e.format!=='medterm-encrypted'||e.schema!==1||e.kdf!=='PBKDF2-SHA256'||e.iterations!==ITERATIONS||e.cipher!=='AES-256-GCM')throw Error('不支援的加密版本；本機資料未變更。');
 const salt=decode(e.salt,16),iv=decode(e.iv,12),bytes=decode(e.data,LIMIT+16);if(salt.length!==16||iv.length!==12)throw Error('加密參數無效');
 try{return new TextDecoder('utf-8',{fatal:true}).decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:iv as BufferSource,additionalData:aad},await key(password,salt),bytes as BufferSource));}
 catch{throw Error('同步密碼不正確或加密檔已損壞；未套用遠端資料。');}
}

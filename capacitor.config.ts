import type {CapacitorConfig} from '@capacitor/cli';
const config:CapacitorConfig={
 appId:'local.medtermquest.app',appName:'MedTerm Quest',webDir:'dist-android',
 server:{hostname:'localhost',androidScheme:'https'},
 android:{allowMixedContent:false},
};
export default config;

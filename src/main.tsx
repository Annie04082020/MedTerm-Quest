import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles.css';
import SyncLifecycle from './SyncLifecycle';

// Separate entry graphs keep desktop authoring and API clients out of the APK.
const {default:App}=(import.meta.env.MODE==='android'||import.meta.env.MODE==='pages')?await import('./MobileApp'):await import('./App');
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /><SyncLifecycle/></React.StrictMode>);

# GitHub Pages learning app

Open https://annie04082020.github.io/MedTerm-Quest/ and import a bank-only JSON under **題庫交換**. Questions and learning history stay in this browser's IndexedDB. Importing files does not upload them. Use exports to back up history or move it to Android; browser and APK storage are separate.

Pages serves the portable learning interface. Windows FastAPI, SQLite authoring, external materials and Ollama processing remain local. No course questions, original materials or personal progress are bundled in the public deployment. The initial screen therefore asks for a question bank.

The original white screen came from publishing `main:/` directly: its `index.html` refers to `/src/main.tsx`, which Pages cannot compile. The **Deploy learning app to GitHub Pages** Actions workflow now builds the `pages` mode, tests the `/MedTerm-Quest/` subpath, uploads only `dist-pages` and deploys that artifact. Repository **Settings → Pages → Source** must be **GitHub Actions**.

Local checks:

```powershell
npm run build:pages
$env:PLAYWRIGHT_CHANNEL='msedge'
npm run test:pages
```

The tests import an existing bank, exercise all six game modes without API calls and check persisted history. CI uses public demonstration fixtures. `build:pages` ignores `MEDTERM_MOBILE_BANK` so an accidental local override cannot publish a private bank.

Pages needs a connection to load or reload the website; it does not install an offline app shell. Once loaded, practice and file exchange use local storage without FastAPI. Use the APK for fully offline startup. Clearing browser/site data removes local progress unless exported first.

Build configuration follows [Vite's Pages deployment guide](https://vite.dev/guide/static-deploy.html#github-pages) and [GitHub's custom Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

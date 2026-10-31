# Android APK via GitHub Actions

Use the **Android offline APK** workflow in the repository's Actions tab. Pushes to `main` and pull requests run validation; **Run workflow** supports a manual build. Standard Ubuntu runners supply Java/Android tools. The Windows machine needs no local Android SDK/JDK.

The workflow runs backend, portable-core, desktop-browser and mobile-browser regressions, native SQLite tests, then an actual Android emulator with airplane mode enabled. Native tests exercise all six game renderers, activity restart, local document import/cancel/export and SQLite persistence. Public demonstration fixtures are used in CI, never private course banks or learner records. Native tests are only passed when the remote workflow actually succeeds.

After success, download `medterm-quest-android-<run number>` from **Artifacts**, unzip it, and transfer the APK to your Android device. Install it using Android's per-source install permission. No Google Play publishing or cloud account is required during app use. The app targets Android 7+ with a modern Android System WebView; the CI emulator uses API 35. Physical-device/OEM testing remains distinct from emulator acceptance.

## First use

The CI APK is intentionally empty. Export a **bank-only** JSON from Windows; copy it to the phone over USB or your chosen local transfer method. Open **題庫交換 → 選擇本機題庫或進度檔案**, inspect the validation preview, then apply. Source excerpts/page/timestamps are included in the bank, while full lecture PDFs/videos stay on Windows. All normal play, scheduling, history and further file imports/exports work offline.

Use **每日挑戰** for weekly/exam study and **自由練習** to choose among all six suitable modes. Demonstrations are opt-in. Unrecognized conceptual wording remains partial recall. Tier B remains provisional and never advances long-term mastery. **學習紀錄** shows local reviews. There are no mobile AI/model controls.

Android stores the portable state in app-private SQLite. A failed transaction preserves the previous state. Explicit local document selection avoids storage-wide permissions. The APK requests no INTERNET permission and disables automatic cloud backup. Use manual exports for backup; uninstalling an app normally removes its private data.

## Signing and updates

Default builds are **preview/debug APKs** with a temporary runner-generated debug key. A different run may use a different key; Android will reject an in-place update signed by another key. Export progress before replacing a preview installation. Do not uninstall an app containing the only copy of your progress.

For stable signed APK updates, add repository **Actions secrets**:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

Then run the workflow manually with `signing: stable`. Keep the same private keystore for future releases. Signing secrets are developer build credentials, not cloud API keys or mobile user accounts. They are never committed, bundled in the APK or uploaded as artifacts. No signing keys are created or uploaded automatically by this project.

## Local validation without Android tools

```powershell
npm ci
npm run test:core
npm run build
$env:PLAYWRIGHT_CHANNEL='msedge'
npm run test:e2e
node --experimental-strip-types scripts/mobile-test-fixtures.mjs
npm run build:android
npm run test:mobile
```

`npm run build:android` builds a local static shell only. `npm run android:sync` copies those assets into the Android project but does not compile an APK locally. For explicit private local acceptance, `MEDTERM_MOBILE_BANK` may point to a bank-only file; generated assets stay Git-ignored. CI clears that variable and checks that the production APK contains no bank, original materials or progress.

Current browser storage and Android SQLite synchronize through the same versioned files. Imports preserve history; they do not write portable events back into legacy desktop `attempts`. Notifications/reminder settings remain Phase 6.

Primary references: [Capacitor Android](https://capacitorjs.com/docs/android), [local native plugins](https://capacitorjs.com/docs/android/custom-code), [Android documents](https://developer.android.com/training/data-storage/shared/documents-files), [SQLiteOpenHelper](https://developer.android.com/reference/android/database/sqlite/SQLiteOpenHelper).

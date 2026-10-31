# Android APK via GitHub Actions

Use the **Android offline APK** workflow in the repository's Actions tab. Code changes pushed to `main` automatically validate and build an APK; documentation-only pushes skip the APK workflow. Pull requests validate without release-signing credentials. **Run workflow** supports `auto`, `stable` and `preview` builds. Standard Ubuntu runners supply Java/Android tools. The Windows machine needs no local Android SDK/JDK.

The workflow runs backend, portable-core, desktop-browser and mobile-browser regressions, native SQLite tests, then an actual Android emulator with airplane mode enabled. Native tests exercise all six game renderers, activity restart, local document import/cancel/export and SQLite persistence. Public demonstration fixtures are used in CI, never private course banks or learner records. Native tests are only passed when the remote workflow actually succeeds.

After success, download `medterm-quest-android-<run number>` from **Artifacts**, unzip it, and transfer the APK to your Android device. Install it using Android's per-source install permission. No Google Play publishing or cloud account is required during app use. The app targets Android 7+ with a modern Android System WebView; the CI emulator uses API 35. Physical-device/OEM testing remains distinct from emulator acceptance.

## First use

The CI APK is intentionally empty. Export a **bank-only** JSON from Windows; copy it to the phone over USB or your chosen local transfer method. Open **題庫交換 → 選擇本機題庫或進度檔案**, inspect the validation preview, then apply. Source excerpts/page/timestamps are included in the bank, while full lecture PDFs/videos stay on Windows. All normal play, scheduling, history and further file imports/exports work offline.

Use **每日挑戰** for weekly/exam study and **自由練習** to choose among all six suitable modes. Demonstrations are opt-in. Unrecognized conceptual wording remains partial recall. Tier B remains provisional and never advances long-term mastery. **學習紀錄** shows local reviews. There are no mobile AI/model controls.

Android stores the portable state in app-private SQLite. A failed transaction preserves the previous state. Explicit local document selection avoids storage-wide permissions. INTERNET permission enables optional [encrypted Gist sync](gist-sync.md); no requests are required for gameplay. Automatic cloud backup remains disabled. Use manual exports for backup; uninstalling an app normally removes its private data.

## Signing and updates

Automatic builds use the stable signing identity when all four signing secrets exist. Future stable builds can update that installation without clearing app data. Explicit **preview/debug** builds use a temporary runner-generated debug key; a different run may have a different key. The first transition from an older preview to a stable APK requires exporting progress before reinstalling, then importing it. Do not uninstall an app containing the only copy of your progress.

For stable signed APK updates, add repository **Actions secrets**:

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

These four secrets were provisioned once for this repository at the user's request for automatic APK builds. They are separate from the Gist token, which remains user-configured at runtime. No key is regenerated during builds. The local encrypted PKCS#12 and Windows-account-protected recovery bundle are under Git-ignored `data/signing/`; retain a secure backup of the signing identity and Windows profile/recovery material. Keep the same key for future releases. Signing secrets are never committed, bundled in the APK or uploaded as artifacts.

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

Current browser storage and Android SQLite synchronize through versioned files or optional encrypted Gist. Imports preserve history; they do not write portable events back into legacy desktop `attempts`. **提醒設定** provides local daily and weekly reminders, notification permission checks and a test notification. It uses the official Capacitor Local Notifications plugin. Reminders are inexact, device-local calendar schedules, with no exact-alarm permission or server push. Android battery policies can delay delivery; force-stopping an app can suppress reminders until it is opened again. Real-device/OEM behavior remains distinct from emulator acceptance.

Primary references: [Capacitor Android](https://capacitorjs.com/docs/android), [local native plugins](https://capacitorjs.com/docs/android/custom-code), [Android documents](https://developer.android.com/training/data-storage/shared/documents-files), [SQLiteOpenHelper](https://developer.android.com/reference/android/database/sqlite/SQLiteOpenHelper).

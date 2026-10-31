# Phase 4–6 implementation and acceptance — 2026-11-01

Code commit: `6f9f7d318f2512020c66a74f6ab18978db668722`.

[Successful Android workflow](https://github.com/Annie04082020/MedTerm-Quest/actions/runs/41228265104), [successful Pages workflow](https://github.com/Annie04082020/MedTerm-Quest/actions/runs/41228265003).

## Implemented

- Optional encrypted Gist bank/review synchronization, per-device slots, revision/tombstone conflict rules and immutable review merging. Token persistence is encrypted; passphrases remain in memory. Sync is opt-in and normal gameplay remains local.
- Manual files remain supported. No source materials, model credentials or individual learning records are committed or bundled in public builds. Source processing and generation remain local on Windows.
- Android has the optional sync network permission while all six games, scheduling, history and file exchange remain playable without a connection or desktop service.
- Local Android daily and weekly reminders, permission checks, pending schedule status, restart restoration, disable controls and a real test notification. Reminder taps route to the daily view in code. Settings remain device-local; no server push or exact-alarm permission.
- Main-branch code pushes automatically validate and build APKs; documentation-only pushes skip APK compilation. Repository signing secrets supply a persistent release identity. PRs never use those secrets. Manual auto/stable/preview builds remain available.

## Actual test results

| Verification | Result |
|---|---|
| Backend regression | 128 passed on GitHub |
| Portable core, file sync, encryption/Gist, native adapter and reminder scheduling | 34 passed locally and on GitHub |
| Desktop browser | 16 passed locally and on GitHub |
| Mobile browser | 3 passed locally and on GitHub |
| Pages subpath browser | 3 passed locally and on GitHub |
| Native SQLite reopen, stale-write protection, invalid-schema preservation | 3 passed on GitHub |
| Actual API 35 Android emulator in airplane mode | 3 passed on GitHub |
| Release APK signature and privacy checks | Passed on GitHub; downloaded checksum/privacy rechecked locally |
| Live Pages rendering, missing assets, JS errors and default API requests | Passed against the deployed URL; zero errors/default API calls |

The emulator tests run all six games and retain 16 reviews across activity recreation; use the real document picker for import/cancel/export; schedule two native reminders, recreate the activity, observe an actual notification through Android's NotificationManager, and disable the reminders. CI uses existing public demonstrations.

The browser Gist test uses two independent browser installations with real Web Crypto, UI and persistent storage; only the GitHub HTTP transport is intercepted. It checks automatic sync after finishing practice, cross-device review merging, encrypted stored credentials and restart unlock. Pure protocol tests include concurrent uploads, tampering, wrong passwords, stale deletions, conflicting revisions and truncated response handling.

## Release artifact

[Stable APK artifact](https://github.com/Annie04082020/MedTerm-Quest/actions/runs/41228265104/artifacts/13052229347) (30-day retention).

APK SHA-256: `f57e6cc39a6a6c2fc7215a54a726ee595ff1e23853f242f7e094127fd70087a3`.

Signing certificate SHA-256: `db4215c6825917a71be802657c89b3ca2a0937ab461ec841be158dc4dcceef64`.

The first move from a previously installed preview APK requires exporting a combined backup before replacing the differently signed installation. Future stable builds retain the same identity and can update in place. The release APK is signed and inspected; the instrumentation tests run the debug build of the same sources, not the signed release on a physical phone.

## Still unverified / limitations

- Live Gist authentication, real GitHub CORS/upload/download and a physical desktop-to-phone synchronization require the user's new runtime token. No real Gist was created or modified during this increment.
- Physical-device/OEM reminder behavior, reboot delivery, future daily/weekly clock-time delivery and notification-tap routing were not manually verified. The emulator verifies scheduled persistence and immediate actual notification delivery. Android may delay inexact alarms or suppress them after force-stop.
- No independent cryptographic security audit. Passphrase loss requires a new Gist or an existing plaintext manual backup; no recovery service exists.
- In-progress challenges, local error reports, weekly preferences and reminders remain device-local. Portable reviews do not overwrite legacy FastAPI attempts. Aggregate mastery is recomputed rather than synchronized as an authoritative counter.
- The backend database was compared against the earlier local baseline and all relevant rows remained unchanged. No new course questions were generated for this work.

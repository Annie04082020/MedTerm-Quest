# Android-only offline architecture

The React frontend is retained. The shared question renderer implements all six existing modes. The Android build has its own entry graph; desktop material processing, model controls and API adapters remain on Windows.

The portable TypeScript core owns grading, selection, review evidence, scheduling and remediation. Browser storage uses transactional IndexedDB. Android uses a small local Capacitor bridge over Android SQLiteOpenHelper. Native writes are serialized and use a revision-checked SQLite transaction; failures do not return false success or reset data.

Native document import/export uses user-selected local Storage Access Framework documents. Full packages are validated before a single storage transaction. APK assets support cold start; the CI APK contains no courses, secrets or progress. Import banks locally after installation.

The APK does not request INTERNET permission, and automatic cloud/device backup is disabled; manual file backup is available. Native Android tests run on a GitHub Actions emulator with network disabled. Workflow results, not mocked tests, determine native acceptance.

Phase 6 reminders remain separate. No iOS, cloud inference, accounts during play, Google Play publishing or paid service is introduced.

[Build, artifact and signing details](android-apk.md). [Manual file protocol](phase4-manual-sync.md).

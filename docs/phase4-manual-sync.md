# Versioned manual question-bank and progress exchange

Open Weekly learning on Windows, then update the local bank. Export a bank-only, progress-only or combined JSON file. Transfer it manually to another browser or Android device. Android uses its local system document picker; no storage-wide permission, cloud account or runtime service is required.

Files carry schema version 1, stable IDs, question/concept revisions, source metadata, SHA-256 integrity, optional immutable review events and informational interval-scheduler summaries. Concept records include explanations, terminology, objectives, mechanisms and provenance. No original lectures or machine-specific paths are exported.

Imports validate the complete package before preview. Commit rereads current storage and merges transactionally. Same-ID/same-version content conflicts or changed immutable event IDs cancel the entire import. Duplicate history is idempotent; older content cannot resurrect newer tombstones. Updates retain review history. Mastery is recomputed from events and policy, never overwritten by a received summary.

Tier B is provisional, not independently medically verified, and never promotes long-term mastery. Package checksums are integrity checks, not medical certification or authenticity signatures.

Progress-only files need the matching bank. Local settings, unfinished sessions and local report notes are not transferred; the receiving device maintains its own sessions. Imports do not write portable reviews back into legacy desktop SQLite attempts.

Automated playback is kept out of real learner statistics through additive acceptance-attempt annotations. Original rows remain retained. Detailed private acceptance reports, banks and progress stay under Git-ignored `data/`; public documentation never publishes personal learning records.

[Android APK build and installation](android-apk.md).

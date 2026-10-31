# First milestone: concept-ready desktop authoring

This increment preserves the current desktop architecture. It does **not** produce an Android APK, offline mobile runtime, daily challenge, scheduler, reminder or synchronization package yet. The Android-only implementation order and acceptance criteria are in [the architecture assessment](android_learning_architecture.md).

## Classification and a real course week

1. Restart FastAPI and open **Course materials**. Existing scans remain available.
2. Press **Suggest classifications**. This local sequential job uses explicit filename week/lecture hints, PDF title/first-heading metadata and related files. It does not invoke AI or apply classifications.
3. Inspect and correct course, week and topic in the proposal table. Dates and filenames are hints, not authoritative course schedules. Explicit week values outside the conservative 1–30 suggestion range remain blank; manual confirmation still allows weeks 1–100.
4. Select one actual course week and press **Confirm selected classifications**. The whole batch validates source hashes/metadata before committing. A stale/conflicting file rejects the whole batch.
5. Optionally check text extraction after confirmation. Selected PDF/MD/TXT/SRT/VTT files enter the existing sequential queue; videos do not transcribe automatically. Use their existing transcript/notes association or the explicit transcription action.

Pipeline metadata distinguishes discovered, classified and ready-for-generation content. The existing `extracted` status remains compatible; the processing job reports extraction and source validation before readiness. Proposals do not change original materials.

## Source-grounded concepts and varied questions

1. In **Local AI studio**, select an extracted source. The **Concept-first authoring** panel uses the same installed local model/device settings and sequential queue as existing question generation.
2. Choose one source chunk and request **Queue concept draft**. Each request generates one concept, preserving English terms, synonyms, Traditional Chinese explanation, mechanism, objectives, difficulty, tags and a verbatim source quote. No model is downloaded.
3. Review the quote and source locator. Expand the concept JSON to correct the teaching content. Confirm the review, including any uncertainty flag, then **Approve concept**. The stable concept ID is assigned by the server and retained through approval.
4. The approved parent becomes selected for question variants. Choose one of the six existing game types plus a tested aspect: definition, terminology, mechanism, comparison, application or quantitative. Parent-based generation is one question per request and uses the concept's reviewed source chunk.
5. Review and approve each question through the existing draft workflow. Published variants reference the same parent concept. Reusing an already-published aspect or an identical normalized English/Chinese question stem is rejected transactionally, even if an older pending draft attempts to publish later.

These deterministic checks cannot prove semantic variety or medical correctness. Human review must verify that the task actually tests a new aspect/representation, not simply the same recognizable answer pattern. Only request aspects supported by the lecture; do not invent quantitative or clinical facts to force coverage.

The independent-question workflow remains for compatibility. Its published questions receive separate unreviewed legacy concept placeholders, rather than being misrepresented as reviewed course concepts. New content intended for future mobile synchronization should use approved parents.

## Existing progress and schema migration

The migration is additive, transactionally applied and safe to rerun. Existing question IDs and payloads are not rewritten by the migration, and attempt rows remain unchanged. Previously independent questions receive stable legacy concept placeholders; no speculative merging of different questions is performed. Missing legacy links/events added by an older backend process are filled on a later restart.

Concept data is normalized across concepts, terms, accepted synonyms, objectives, tags, evidence and variant links. Review events have installation-scoped stable IDs to prepare for future progress transfer without treating another device's attempt #1 as the same event. A separate concept-progress table starts unassessed with no due date or retention streak.

Existing accuracy and self-review continue to work. New desktop submissions capture wall-clock response latency when available and whether a hint was used; historical observations preserve unknown values. Self-assessment updates its existing event. **No observation in this milestone advances long-term mastery**, and immediate retrieval is not treated as a spaced review. FSRS/interval scheduling and active-time measurement during paused challenges are subsequent work.

## Acceptance status

Automated checks cover populated-database migration/idempotency, source evidence, review-event preservation, installation-scoped IDs, concept approval, duplicate/aspect conflicts, batch-classification rollback and existing gameplay. AI responses in tests are mocked. A live local Ollama model is required to generate genuine course concepts and questions; the absence of that service does not prevent classification, extraction or existing gameplay.

Synchronization conflict rules, blocked-network mobile gameplay, scheduler behavior and Android notification tests belong to the later milestones and are not claimed as implemented tests here.

## Endpoints

- `/api/materials/classifications`: list proposals; `/suggest` queues suggestions; `/confirm` applies an atomic reviewed batch.
- `/api/concepts`: list concepts; `/{id}` includes normalized terms, evidence, variants, raw question accuracy and unassessed concept progress.
- `/api/concepts/generate`: request one source-bound local concept draft.
- `/api/concepts/drafts`: inspect drafts; `/{id}/approve` or `/{id}/reject` requires explicit review actions.
- Existing `/api/local/generate` accepts optional `concept_id` and `variant_aspect`; published variants use the existing question review endpoint.

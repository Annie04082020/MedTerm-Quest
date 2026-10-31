# Optional encrypted Gist synchronization (Phase 4)

Local storage remains authoritative for offline play. Enable Gist only when cross-device synchronization is wanted. Source PDFs/videos/full transcripts and desktop AI processing stay on Windows. Only the existing versioned question/concept/review package, including source excerpts, is encrypted and uploaded. Manual JSON exchange remains available.

In **題庫交換**, enter a GitHub token with Gists read/write permission, a passphrase of at least 12 characters and (on other devices) the same Gist ID. Unlock, then synchronize. A blank ID creates a new Secret Gist. Optionally remember an encrypted token on this device; the passphrase is never persisted. Enter it again after restarting. Forgetting it makes the old encrypted Gist unreadable; retain manual exports. There is no token in source, environment build variables, exported banks or CI.

The envelope is versioned AES-256-GCM with random salt/IV and PBKDF2-SHA256 (600,000 iterations). Secret Gists are not private, so plaintext study records are never uploaded. This implementation uses standard Web Crypto; it has not undergone an independent cryptographic security audit.

Each installation PATCHes only `medterm-device-<installation UUID>.json`. Other device files remain intact, avoiding whole-snapshot last-writer data loss between devices. A sync downloads/decrypts/validates every slot, atomically merges questions by revision and immutable reviews by ID, then uploads its own encrypted combined snapshot. Browser tabs serialize through Web Locks. Concurrent answers created during an upload remain local and are included in the next sync. After both devices sync, they converge; this is not real-time collaborative editing or a cross-device transaction.

Same-ID/same-revision contradictions stop the merge. A bad password, unsupported schema or damaged package never partially applies remote data. A failed upload may leave successfully downloaded reviews locally; retrying is idempotent. Higher-revision tombstones prevent resurrection by stale devices. Mastery is derived from merged history and existing eligibility policy, not copied aggregate scores. Provisional answers remain excluded from long-term mastery.

Automatic sync is opt-in after unlock, on foreground/reconnection and after finishing a practice session. Active challenges must first be paused for sync so questions do not change during an answer. Sessions, hint checkpoints, local reports, study preferences and reminder configuration remain device-local. Nothing prevents offline play when the token is absent, locked, expired or the network fails.

Limits: 16 device slots, 6 MiB plaintext per encrypted slot, bounded 16 MiB network responses. Larger banks retain the 30 MiB manual file pathway. Truncated API content is retrieved from a validated, revision-pinned `gist.githubusercontent.com` URL without forwarding authorization. Tokens support the permissions documented by GitHub; old TaskDesk assumptions about token prefixes are not reused.

Acceptance so far: six encryption/Gist protocol tests, all 29 core tests, and three Pages browser tests passed locally. The browser sync test uses two independent installations and an intercepted GitHub transport; it tests real encryption, storage, UI and game reviews. No real Gist has been created or uploaded: live GitHub/CORS/token acceptance is pending the user's new token.

References: [Gist API](https://docs.github.com/en/rest/gists/gists), [Secret Gist visibility](https://docs.github.com/en/get-started/writing-on-github/editing-and-sharing-content-with-gists/creating-gists).

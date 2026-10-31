# MedTerm Quest

**Current status (2026-11-01):** Six-mode portable learning runs in the desktop browser, [GitHub Pages](https://annie04082020.github.io/MedTerm-Quest/) and Android APK. Phase 4 adds optional [encrypted Gist sync](docs/gist-sync.md) alongside manual files. Phase 5/6 integrate native SQLite, stable automatic APK builds and local daily/weekly reminders; native acceptance results are recorded by the actual [Actions runs](https://github.com/Annie04082020/MedTerm-Quest/actions). Live Gist acceptance is pending the user-provided runtime token.

A local-first, bilingual medical terminology and physiology study app for engineering students. React + TypeScript + Vite + Tailwind CSS, FastAPI, SQLite, and optional fully local AI through Ollama. All six existing games remain playable without any AI service running. No payment details, subscription, cloud inference, or API key is used.

**Authoring policy:** deterministic extractive exercises may publish as Tier A; meaning-based local-model exercises enter an explicitly provisional Tier B bank only after source and answer checks. Tier B never advances long-term mastery. Complex/unsupported clinical reasoning stays quarantined. The learner is never asked to certify medical correctness. Source matching, JSON validation and package hashes are not independent medical verification.

**Local processing:** [本機 AI 使用說明](docs/local_ai.md) · [Incremental development plan and hardware audit](docs/development_plan.md). The Local AI studio supports source-preserving imports, a sequential processing queue, optional faster-whisper small transcription, and conceptual grading suggestions. Earlier documentation of learner medical approval is superseded by the source-first policy above.

**External library:** [外部教材庫設定與操作](docs/external_materials.md). Set `COURSE_MATERIALS_DIR` in `backend/.env`, open **Course materials**, and rescan. Original videos, PDFs and notes stay outside Git. Scanning never automatically transcribes videos or generates questions.

The earlier [concept foundation](docs/concept_authoring_milestone.md) and [Android architecture](docs/android_learning_architecture.md) remain historical design records. Existing SQLite games, questions and attempts are retained. Portable learning uses browser IndexedDB; file imports merge into that portable store and do not overwrite the desktop SQLite attempts.

## Requirements

- Node.js 20.19+ or 22.12+ (tested with Node 24)
- Python 3.10+ (tested with Python 3.13)
- Internet access for the initial dependency installation only

## Start on Windows (PowerShell)

### Simple single-server mode

After installing the dependencies below, run `npm run build` once, then start the backend. Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** to use the complete app from one server; a separate Vite process is not needed. Rebuild after changing frontend code. If no build exists, the backend root page displays startup instructions instead of a 404.

### Development mode

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm install
```

Start the backend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
npm run dev
```

Open **[http://127.0.0.1:5173](http://127.0.0.1:5173)**. Both terminals must remain running. Use `Ctrl+C` to stop each server. If PowerShell blocks `npm.ps1`, use `npm.cmd` for the same commands.

## Start on macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm install
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, run `npm run dev` and open the URL above.

## What to try

1. Choose **Start learning**, a practice card, or a course week.
2. Answer a question and choose **Check answer**. Review its reference answer, Traditional Chinese explanation, source section, and medical terms.
3. Try all six activities: a real intersecting mini-crossword, multiple choice, terminology matching, modified true/false with a correction, short answers, and clinical connections.
4. For conceptual questions, answer in English or Traditional Chinese. Accepted phrases are matched locally after case, whitespace, and terminal punctuation normalization. Mathematical operators and decimal points are preserved.
5. Other free-text wording is marked **needs review**, rather than automatically called wrong. Compare with the reference and choose **I understood this** or **Review again**. For conceptual short answers, you can explicitly request optional local Ollama feedback; concept gaps and spelling errors are shown separately. AI advice requires your confirmation before changing the score.
6. Open **My review** to revisit questions whose latest attempt was incorrect or ungraded. A review session retains its question list until you navigate away so that explanations remain visible after a successful retry.
7. Reload the page: attempts and progress remain in SQLite.

The app includes **16 activities across three sample weeks**. The [original sample notes](docs/sample_notes.md) contain the referenced sections and demonstrate the app, rather than representing uploaded lecture content. The clinical activities are simplified learning scenarios.

## Local data and offline behavior

- The backend creates `data/medterm.sqlite3` on first start and seeds it from `backend/sample_questions.json`.
- Question definitions, submitted answers, assessment status, self-assessment flags, and UTC timestamps are stored locally. Normal practice makes only requests to your local backend.
- No remote fonts, analytics, CDN resources, or cloud inference services are used. Ordinary practice never calls Ollama; only explicit AI jobs use the loopback service.
- “Offline” means **no internet connection is needed after installation**. The local frontend and backend must still be running. This is not an installable PWA and does not work with the backend stopped.
- The local profile is shared by browsers that connect to the same backend. It is not a multi-user service.
- Accuracy is correct attempts divided by all assessed attempts, including self-assessments. Pending answers are excluded. “Questions understood” counts questions whose latest attempt is correct; it is not a spaced-repetition or long-term mastery measure.
- To back up progress, stop the backend and copy `data/medterm.sqlite3`. To reset progress, stop it and remove that file; the next start creates a fresh database.
- Set `MEDTERM_DB_PATH` in the backend environment to use another database location. Relative paths resolve from the directory where the backend starts.

Copy `.env.example` to `backend/.env` for backend settings; it is now loaded automatically, without overriding existing process environment variables. `COURSE_MATERIALS_DIR` is the read-only external lecture directory. `MEDTERM_WHISPER_MODEL_PATH` selects the provisioned local transcription model, and `MEDTERM_IMPORTS_PATH` optionally selects storage for the older manual-upload workflow. Configure `OLLAMA_NO_CLOUD=1` in the Ollama process itself and restart Ollama to disable its cloud features; setting it only in the backend does not reconfigure an existing Ollama service. Imported files, databases, model files, secrets, and build artifacts are excluded by `.gitignore`; never commit lecture materials.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest backend -q
npm run build
```

Optional browser tests (initial browser installation needs internet):

```powershell
npx playwright install chromium
# Activate the venv so Playwright's server command uses its Python:
.\.venv\Scripts\Activate.ps1
npm run test:e2e
```

On macOS / Linux, use `.venv/bin/python` and `source .venv/bin/activate` instead. Browser tests start their own servers on ports 8001 and 5173; stop an existing frontend first. Each browser test run uses a fresh temporary SQLite database, separate from real progress. To use an already-installed Chrome instead of downloading Chromium, set `$env:PLAYWRIGHT_CHANNEL = 'chrome'` in PowerShell (or `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` on macOS / Linux).

`npm run build` checks TypeScript and generates `dist/`. FastAPI serves that build at port 8000, with gameplay using its same-origin `/api` endpoints. Alternatively, `npm run preview` previews the frontend build through Vite; gameplay still requires the backend. The Vite configuration includes an `/api` proxy for local preview as well as development.

## API

Interactive backend documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Offline mode and phase status |
| `GET /api/questions?week=1&kind=multiple_choice&review=false` | Questions without answer keys; all filters are optional |
| `POST /api/attempts` | Check and persist `{ "question_id": "w1-01", "answer": "Medial" }` |
| `PATCH /api/attempts/{id}/review` | Resolve unrecognized free text with `{ "correct": true }` |
| `GET /api/progress` | Accuracy, latest question status, weekly progress, and recent attempts |

Bind to `127.0.0.1` for this single-user local version. Authentication and network deployment are outside this local single-user version.

## Project layout

```text
backend/
  main.py                 Validated data, SQLite, checking, progress API
  sample_questions.json   Original bilingual sample bank
  requirements.txt
  test_main.py            API and persistence tests
src/
  App.tsx                 Dashboard, practice, review, source library
  styles.css              Responsive visual design and Tailwind entry
  main.tsx
tests/gameplay.spec.ts     Desktop and mobile browser scenarios
data/                     Ignored local runtime databases
imports/                  Ignored future lecture materials
```

## Incremental local-AI migration

The paid-provider integration plan has been replaced. See [the updated development plan](docs/development_plan.md) for the hardware audit and sequence, and [local AI setup](docs/local_ai.md) for exact optional installation steps.

- Existing games and SQLite progress are preserved. New source, job, and draft tables are additive.
- PDF/transcript imports preserve source locations and split text into small chunks.
- Ollama uses installed local models only: Qwen3 4B initially, with an explicitly allowed, already-installed 1.7B fallback. Context is limited to 4K, each request produces one question, and jobs handle at most eight chunks.
- Generation, transcription, and grading share a persistent sequential queue and processing lock. Models are released between stages; CUDA transcription runs in a separate process with CPU fallback.
- Questions use Pydantic and tiered source validation. Eligible source-extractive or provisional exercises publish under policy; uncertain free-form medical claims remain held, without learner medical approval.
- Local conceptual grading is advisory and separates spelling from concepts. Normal deterministic games and self-assessment remain available without Ollama.
- Optional model files, transcription packages, and CUDA runtimes are not installed automatically. Real-model quality, speed, and GPU execution need an acceptance check after local model provisioning.
- Versioned file exchange, optional encrypted Gist synchronization, offline Android packaging and native reminders are implemented. OCR and optional Wi-Fi synchronization remain future work.

Local endpoints under `/api/local`: `status`, `imports`, `sources`, `generate`, `grade`, `jobs`, and `drafts`. See [interactive API docs](http://127.0.0.1:8000/docs) for request schemas. Run one backend worker.

External-library endpoints are under `/api/materials`. See [the library guide](docs/external_materials.md). Metadata indexing comes first, text extraction and video transcription are explicit queued steps, and reviewed question generation continues through the existing local Ollama pipeline.


## Weekly learning and file exchange

1. Start the desktop app at http://127.0.0.1:8000 and open **Weekly learning**.
2. Click **更新本機題庫（保留進度）** once, then choose course/week/topic or manual exam scope.
3. Start a short challenge. Answers, source excerpts, progress and scheduling are local to this browser. Games require neither Ollama nor backend requests after the bank is copied. The web assets must already be loaded; full offline cold start is reserved for the Android milestone.
4. Export a bank, progress-only file, or combined backup. On another browser, choose the file, inspect the validation result, then apply. Import the bank before a progress-only file. Updated versions and withdrawals retain review history; same-ID conflicts abort the import.
5. Portable progress appears in Weekly learning; the original desktop Practice studio/Overview continues to use SQLite. File exchange currently synchronizes the portable core, not a reverse write into legacy SQLite attempts.

Validation commands (Windows PowerShell):

```powershell
python -m pytest backend -q
npm run test:core
$env:PLAYWRIGHT_CHANNEL='msedge'
npm run test:e2e
```

Use installed Edge for browser tests, or install Playwright Chromium separately if desired. The core tests use Node 24's TypeScript stripping. Detailed acceptance counts, real-course evidence and limitations are in the linked milestone reports.

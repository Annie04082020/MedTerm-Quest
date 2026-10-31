# Development plan

1. Source-aligned local authoring: external material library, extraction, provenance and tiered publication; existing desktop data preserved.
2. Portable learning core: six existing games, weekly focus, manual exam scope, bounded remediation and versioned interval scheduling.
3. Manual synchronization: transactional versioned bank/progress files with stable IDs and tombstones.
4. Android packaging: Capacitor, native SQLite, system document picker, packaged offline assets and GitHub Actions builds. Native acceptance is gated by the actual workflow results; a browser test is not an Android-device test.
5. Future: native daily/weekly reminders and refined synchronization. No iOS or Google Play publishing is planned.

Desktop authoring uses React/TypeScript/Vite, FastAPI, SQLite, FFmpeg/PyMuPDF, optional faster-whisper and local Ollama. An RTX 3060 Laptop with 6 GB VRAM and 16 GB RAM is the initial target: quantized Qwen3 4B, Whisper small, bounded context and sequential stages with resource release. Models are never downloaded automatically.

Android runs only the portable learning core. It requires neither the desktop computer nor models during play. Code builds on standard GitHub-hosted Linux runners; no Android SDK/JDK is installed locally by the build workflow.

See [authoring policy](tiered-bank-acceptance.md), [portable core](phase3-acceptance.md), [manual exchange](phase4-manual-sync.md), and [Android workflow](android-apk.md).

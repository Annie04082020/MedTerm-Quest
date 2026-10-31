# Portable weekly learning

Weekly learning copies a desktop snapshot into browser IndexedDB. Android uses app-private native SQLite through the same portable state boundary. Questions, concepts, review events, challenges and settings stay local.

Select the active course/week/topic manually. Weekly selection targets approximately 80% current content and 20% previously learned due material, adapting without identical-question duplication. Exam mode uses manually selected week/topic scope. Demonstrations are opt-in.

The versioned interval scheduler uses 1/3/7/14/30/60-day intervals, not FSRS. Initial learning, partial recall, hinted recall and unassisted spaced recall remain distinct. Immediate remediation cannot advance a long-term interval. Tier B never advances mastery.

Daily mistakes show the explanation, English terms and source excerpt. Alternatives wait for intervening concepts; two successful different variants are required for remediation completion. Daily extra-question limits prevent endless sessions. Insufficient variants remain explicitly incomplete. Pause/end preserve history.

Desktop legacy games retain their original SQLite data. Portable file exchange synchronizes the portable store, not a reverse write into legacy attempts. Native cold-start packaging and CI are described in [the Android guide](android-apk.md).

Run `npm run test:core`, `npm run test:e2e`, and `npm run test:mobile`. Real-course acceptance records and personal statistics are deliberately kept outside Git under local managed data.

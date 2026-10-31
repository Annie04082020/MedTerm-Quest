"""Disposable local API for browser tests; never touches the user's database."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

if __name__ == '__main__':
    with TemporaryDirectory(prefix='medterm-e2e-') as directory:
        os.environ['MEDTERM_DB_PATH'] = str(Path(directory) / 'test.sqlite3')
        os.environ['MEDTERM_IMPORTS_PATH'] = str(Path(directory) / 'imports')
        materials = Path(directory) / 'course-materials'
        (materials / 'videos').mkdir(parents=True)
        (materials / 'notes').mkdir()
        (materials / 'videos' / 'lecture.mp4').write_bytes(b'not decoded during directory scans')
        (materials / 'notes' / 'lecture.srt').write_text('1\n00:00:01,000 --> 00:00:04,500\nArteries carry blood away from the heart.\n',encoding='utf-8')
        (materials / 'notes' / 'lecture_notes.md').write_text('# Notes\nArteries carry blood away from the heart.',encoding='utf-8')
        (materials / 'Week99.txt').write_text('Arteries carry blood away from the heart.',encoding='utf-8')
        (materials / 'duplicate.txt').write_bytes((materials / 'Week99.txt').read_bytes())
        os.environ['COURSE_MATERIALS_DIR'] = str(materials)
        # Browser fixtures perform CPU parsing and mock all LLM calls. Do not
        # block a user's real GPU authoring job with this disposable test queue.
        from backend import local_processing
        local_processing.PROCESSING_LOCK_PATH = Path(directory) / 'processing.lock'
        uvicorn.run('backend.main:app', host='127.0.0.1', port=8001)

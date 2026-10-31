"""Source-preserving local parsing. No network access or OCR."""
from html import unescape
import re
from pathlib import Path

CHUNK_CHARS = 1200
MAX_TEXT_CHARS = 5_000_000


def split_text(text, locator, **metadata):
    chunks = []
    text = text.strip()
    offset = 0
    while offset < len(text):
        end = min(offset + CHUNK_CHARS, len(text))
        if end < len(text):
            boundary = max(text.rfind('\n', offset + CHUNK_CHARS // 2, end), text.rfind(' ', offset + CHUNK_CHARS // 2, end))
            if boundary > offset:
                end = boundary
        part = text[offset:end].strip()
        if part:
            chunks.append({'text': part, 'locator': locator, 'offset': offset, **metadata})
        offset = end
    return chunks


def timestamp_seconds(value):
    parts = value.replace(',', '.').split(':')
    return sum(float(part) * 60 ** i for i, part in enumerate(reversed(parts)))


def transcript_chunks(text, extension):
    if extension in ('.txt', '.md'):
        chunks = []
        for line_no, line in enumerate(text.splitlines(), 1):
            chunks.extend(split_text(line, f'Line {line_no}', line=line_no))
        return pack_transcript(chunks)
    chunks = []
    timing = re.compile(r'((?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,3}:)?\d{2}:\d{2}[.,]\d{3})')
    for block in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
        match = timing.search(block)
        if not match:
            continue
        content = unescape(re.sub(r'<[^>]+>', '', block[match.end():].split('\n', 1)[-1])).strip()
        start, end = match.groups()
        if timestamp_seconds(end) < timestamp_seconds(start):
            raise ValueError('字幕的結束時間早於開始時間。')
        chunks.extend(split_text(content, f'{start} → {end}', start=timestamp_seconds(start), end=timestamp_seconds(end)))
    if not chunks:
        raise ValueError('找不到有效字幕時間戳記；請使用有效的 SRT/VTT 或另存成 TXT。')
    return pack_transcript(chunks)


def pack_transcript(chunks):
    """Combine adjacent cues/lines while retaining every original locator."""
    packed = []
    for chunk in chunks:
        if packed and len(packed[-1]['text']) + len(chunk['text']) + 1 <= CHUNK_CHARS:
            target = packed[-1]
            target['text'] += '\n' + chunk['text']
            target['segments'].append(chunk)
            target['locator'] = f"{target['segments'][0]['locator']} → {chunk['locator']}"
            if 'end' in chunk:
                target['end'] = chunk['end']
        else:
            packed.append({**chunk, 'segments': [chunk]})
    return packed


def parse_source(path: Path):
    extension = path.suffix.lower()
    if extension == '.pdf':
        try:
            import pymupdf
        except ImportError as exc:
            raise ValueError('PDF 功能需要 PyMuPDF：pip install -r backend/requirements-import.txt') from exc
        chunks = []
        with pymupdf.open(path) as doc:
            if doc.needs_pass:
                raise ValueError('PDF 受到密碼保護，請先解鎖。')
            if len(doc) > 1000:
                raise ValueError('請將超過 1000 頁的 PDF 分成較小檔案。')
            total_chars = 0
            for i, page in enumerate(doc, 1):
                text = page.get_text('text')
                total_chars += len(text)
                if total_chars > MAX_TEXT_CHARS:
                    raise ValueError('PDF 文字過長，請分批匯入。')
                chunks.extend(split_text(text, f'Page {i}', page=i))
        if not chunks:
            raise ValueError('PDF 沒有可擷取文字；掃描講義需要先在本機進行 OCR。')
        return chunks
    if extension in ('.srt', '.vtt', '.txt', '.md'):
        if path.stat().st_size > 20_000_000:
            raise ValueError('文字檔超過 20 MB，請分批匯入。')
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('請將文字檔另存成 UTF-8 後重試。') from exc
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError('文字過長，請分批匯入。')
        chunks = transcript_chunks(text, extension)
        if not chunks:
            raise ValueError('來源檔案沒有可用文字。')
        return chunks
    raise ValueError('不支援此檔案格式。')

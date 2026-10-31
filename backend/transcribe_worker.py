"""One transcription stage per subprocess. Exit frees CTranslate2/CUDA state."""
import json
import os
from pathlib import Path
import sys


def emit(**payload):
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def missing_model_files(path):
    # tokenizer.json is essential: faster-whisper otherwise tries a remote tokenizer.
    return [name for name in ('model.bin', 'config.json', 'tokenizer.json') if not (Path(path) / name).is_file()]


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    model_path, audio_path, device = sys.argv[1:4]
    missing = missing_model_files(model_path)
    if missing:
        raise RuntimeError('本機 faster-whisper small 模型不完整：'+', '.join(missing)+'。請先自行備妥；程式不會自動下載。')
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('尚未安裝 faster-whisper。請執行 pip install -r backend/requirements-transcription.txt。') from exc
    model = WhisperModel(model_path, device=device, compute_type='int8_float16' if device == 'cuda' else 'int8',
                         local_files_only=True, cpu_threads=4, num_workers=1)
    try:
        segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=True)
        emit(type='info', duration=info.duration, device=device)
        for segment in segments:
            emit(type='segment', start=segment.start, end=segment.end, text=segment.text)
    finally:
        del model


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        emit(type='error', message=str(exc)[:1500])
        sys.exit(1)

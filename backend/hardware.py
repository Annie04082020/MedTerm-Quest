"""Small, read-only hardware probe; no model or CUDA runtime is loaded."""
import ctypes
import platform
import shutil
import subprocess


def hardware_status():
    result = {'system': platform.system(), 'ram_total_gib': None, 'ram_available_gib': None,
              'gpus': [], 'ffmpeg': bool(shutil.which('ffmpeg')), 'warnings': []}
    try:
        if platform.system() == 'Windows':
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                    (n, ctypes.c_ulonglong) for n in ['total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended']]
            memory = Memory()
            memory.length = ctypes.sizeof(memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                raise OSError('Windows memory query failed')
            total, available = memory.total, memory.available
        else:
            import os
            total = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
            available = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_AVPHYS_PAGES')
        result.update(ram_total_gib=round(total / 2**30, 2), ram_available_gib=round(available / 2**30, 2))
        if available < 3 * 2**30:
            result['warnings'].append('可用 RAM 少於 3 GiB；請先關閉耗記憶體的程式。CPU fallback 仍需要 RAM。')
    except (OSError, AttributeError, ValueError):
        result['warnings'].append('無法自動讀取 RAM。')
    try:
        output = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for line in output.stdout.splitlines():
            name, total, free = [part.strip() for part in line.split(',')]
            result['gpus'].append({'name': name, 'total_mib': int(total), 'free_mib': int(free)})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result['warnings'].append('NVIDIA GPU 狀態不可用；可使用 CPU 模式。')
    return result

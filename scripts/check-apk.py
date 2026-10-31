"""Check the actual production APK, never the separate instrumentation APK."""
import json,sys,zipfile
from pathlib import PurePosixPath
with zipfile.ZipFile(sys.argv[1]) as apk:
    names=apk.namelist()
    assert 'assets/public/index.html' in names,'Missing bundled app shell'
    info=json.loads(apk.read('assets/public/bank-info.json'))
    assert info['bundled'] is False and info['active_questions']==0,'CI must not package course questions'
    forbidden={'.pdf','.mp4','.srt','.vtt','.sqlite3','.db','.jks','.keystore'}
    for name in names:
        assert PurePosixPath(name).suffix.lower() not in forbidden,name
        assert '/banks/' not in name and not name.endswith('/.env'),name
    assert any(name.startswith('assets/public/assets/') and name.endswith('.js') for name in names),'Missing JS'
print('APK has a bundled offline shell, zero course questions, zero progress files and no lecture materials.')

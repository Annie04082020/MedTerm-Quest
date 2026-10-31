"""One-time, evidence-checked annotation; never removes attempts or changes answers."""
import json
from pathlib import Path
from backend.main import initialize
from backend.storage import database
proof=json.loads(Path('data/acceptance/meaningful-bank/real-gameplay.json').read_text(encoding='utf8'))
expected=[r['id'] for r in proof['results']]
assert len(expected)==22 and proof['before']['attempts']==27 and proof['after']['attempts']==49
initialize()
with database() as c:
    rows=c.execute('SELECT id,question_id FROM attempts WHERE id BETWEEN 27 AND 49 ORDER BY id').fetchall()
    assert len(rows)==23 and rows[0]['question_id']==expected[0]
    assert [r['question_id'] for r in rows[1:]]==expected,'Refusing to mark attempts that do not exactly match acceptance evidence'
    c.executemany('INSERT OR IGNORE INTO acceptance_attempts VALUES (?,?)',[(r['id'],'2026-10-31 automated real source-bank acceptance; retained, not learner recall') for r in rows])
Path('data/acceptance/phase4/acceptance-attempt-annotations.json').write_text(json.dumps({'marked_ids':[r['id'] for r in rows],'excluded_from_learning':23,'original_attempts_unchanged':26,'raw_attempts_retained':49},indent=2),encoding='utf8')
print('Retained 49 raw attempts; marked exactly 23 evidence-matched acceptance attempts; original 26 remain learning history.')

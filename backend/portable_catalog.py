"""Additive revision ledger; never edits source questions or learning history."""
import hashlib
import json

def initialize(c):
    c.execute('''CREATE TABLE IF NOT EXISTS portable_catalog(
      entity TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,content_hash TEXT NOT NULL,
      payload TEXT NOT NULL,PRIMARY KEY(entity,id))''')

def track(c,entity,identity,payload):
    body={k:v for k,v in payload.items() if k!='revision'}
    serialized=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    fingerprint=hashlib.sha256(serialized.encode()).hexdigest()
    old=c.execute('SELECT revision,content_hash FROM portable_catalog WHERE entity=? AND id=?',(entity,identity)).fetchone()
    # Revision 1 was used by Phase 3 snapshots before this ledger existed.
    revision=old['revision']+(old['content_hash']!=fingerprint) if old else 2
    value={**body,'revision':revision}
    c.execute('INSERT INTO portable_catalog VALUES (?,?,?,?,?) ON CONFLICT(entity,id) DO UPDATE SET revision=excluded.revision,content_hash=excluded.content_hash,payload=excluded.payload',
      (entity,identity,revision,fingerprint,json.dumps(value,ensure_ascii=False)))
    return value

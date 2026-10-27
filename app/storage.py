"""SQLite backing store. Catalogue writes are admin-only, projects stay client-local."""
import json
import sqlite3
from pathlib import Path
from contextlib import closing
from threading import Lock

_lock = Lock()
SEED = Path(__file__).with_name('seed.json')
EXAMPLE = Path(__file__).with_name('example.json')


def connect(path):
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=15000')
    con.execute('PRAGMA foreign_keys=ON')
    return con


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _lock, closing(connect(path)) as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('''CREATE TABLE IF NOT EXISTS equipment (
            id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS library_records (
            record_type TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
            PRIMARY KEY (record_type,id)
        )''')
        first_run = con.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 0
        con.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)')
        if first_run:
            for item in json.loads(SEED.read_text()):
                con.execute('INSERT INTO equipment(id,data) VALUES (?, ?)', (item['id'],json.dumps(item)))
        con.commit()


def all_equipment(path):
    with closing(connect(path)) as con:
        return [json.loads(row['data']) for row in con.execute('SELECT data FROM equipment ORDER BY id')]


def put_equipment(path, item):
    with _lock, closing(connect(path)) as con:
        con.execute('''INSERT INTO equipment(id,data) VALUES (?,?)
            ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=CURRENT_TIMESTAMP''',
            (item['id'],json.dumps(item)))
        con.commit()


def delete_equipment(path, id):
    with _lock, closing(connect(path)) as con:
        cur=con.execute('DELETE FROM equipment WHERE id=?',(id,))
        con.commit()
        return cur.rowcount != 0


def library_records(path):
    with closing(connect(path)) as con:
        return [{'id': row['id'], 'record_type': row['record_type'], 'data': json.loads(row['data'])}
                for row in con.execute('SELECT id,record_type,data FROM library_records')]


def put_library_pack(path, pack):
    # One transaction: malformed packs are rejected before any write occurs.
    with _lock, closing(connect(path)) as con:
        for record_type, key in [('manufacturer','manufacturers'), ('product','products')]:
            for item in pack[key]:
                con.execute('''INSERT INTO library_records(record_type,id,data) VALUES (?,?,?)
                    ON CONFLICT(record_type,id) DO UPDATE SET data=excluded.data''',
                    (record_type, item['id'], json.dumps(item)))
        con.commit()

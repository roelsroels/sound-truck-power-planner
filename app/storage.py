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

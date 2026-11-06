import sqlite3
from pathlib import Path
from meridian.db import init_db
from scripts.migrate_db import migrate


def test_legacy_sqlite_backed_up_and_migrated(tmp_path):
    db=tmp_path/'legacy.db'
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO items(sku,name) VALUES('LEGACY-01','Keep me')")
    backup=migrate(db)
    assert backup and backup.exists() and backup!=db
    with sqlite3.connect(backup) as conn:
        assert conn.execute('SELECT name FROM items WHERE sku=?',('LEGACY-01',)).fetchone()[0]=='Keep me'
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==5
        assert conn.execute('SELECT name FROM items WHERE sku=?',('LEGACY-01',)).fetchone()[0]=='Keep me'
        assert conn.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0]==0
    assert migrate(db) is None  # no redundant backup on every start


def test_fresh_install(tmp_path):
    db=tmp_path/'new.db'
    assert migrate(db) is None
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==5

"""Release contract checks for v0.6 frontend, routes, and safe schema upgrades."""
from pathlib import Path
import sqlite3
from fastapi.testclient import TestClient
from meridian.api import create_app
from meridian.db import init_db
from scripts.migrate_db import migrate


def test_ui_routes_and_workflow_controls(tmp_path):
    with TestClient(create_app(tmp_path/'sample.db',auth_required=False)) as c:
        home=c.get('/'); assert home.status_code==200
        assert 'flowFinishedForm' in home.text
        assert 'flowConfigForm' in home.text
        assert 'Meridian ERP v0.6' in home.text
        script=c.get('/enterprise-flow.js')
        assert script.status_code==200
        assert 'receive-finished' in script.text
        assert c.get('/api/finance/operational-config').json()['enabled'] is False
        assert c.get('/api/flow/finished-receipts').json()==[]


def test_v5_database_upgrade_backups_and_preserves_history(tmp_path):
    file=tmp_path/'legacy.db'
    init_db(file)
    with sqlite3.connect(file) as db:
        db.execute("INSERT INTO items(sku,name) VALUES ('OLD-LEGACY','Do not delete')")
        db.execute('PRAGMA user_version = 5')
    backup=migrate(file)
    assert backup is not None and backup.is_file()
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==5
        assert db.execute("SELECT name FROM items WHERE sku='OLD-LEGACY'").fetchone()[0]=='Do not delete'
    with sqlite3.connect(file) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==6
        assert db.execute("SELECT name FROM items WHERE sku='OLD-LEGACY'").fetchone()[0]=='Do not delete'
        assert db.execute('SELECT count(*) FROM finished_good_receipts').fetchone()[0]==0
    assert migrate(file) is None

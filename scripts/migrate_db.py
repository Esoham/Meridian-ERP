"""Backup an existing local SQLite database before additive v0.6 schema migration.

Only the development SQLite DB is supported. Never use this as an enterprise backup plan.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from meridian.db import init_db

TARGET_VERSION = 6


def migrate(path: Path, backup_dir: Path | None = None) -> Path | None:
    path = Path(path)
    backup = None
    old_version = 0
    if path.exists() and path.stat().st_size > 0:
        with sqlite3.connect(path) as src:
            row = src.execute('PRAGMA quick_check').fetchone()
            if row is None or row[0] != 'ok':
                raise RuntimeError('Database integrity check failed; not modifying database.')
            old_version = int(src.execute('PRAGMA user_version').fetchone()[0])
            if old_version < TARGET_VERSION:
                directory=Path(backup_dir) if backup_dir else path.parent/'backups'
                directory.mkdir(parents=True,exist_ok=True)
                stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                backup=directory / f'{path.stem}-before-v{TARGET_VERSION}-{stamp}.db'
                with sqlite3.connect(backup) as dst:
                    src.backup(dst)
    init_db(path)
    with sqlite3.connect(path) as db:
        db.execute(f'PRAGMA user_version = {TARGET_VERSION}')
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok':
            raise RuntimeError('Post-migration SQLite integrity check failed; restore backup.')
    return backup


if __name__=='__main__':
    db=Path(os.environ.get('MERIDIAN_DB_PATH','./meridian.db'))
    created=migrate(db)
    if created:
        print(f'Backup created: {created}')
    print(f'Meridian ERP schema ready (v{TARGET_VERSION}).')

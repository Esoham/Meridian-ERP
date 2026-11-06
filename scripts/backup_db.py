"""Offline/local operational backup and guarded restore for SQLite demonstration.

Backups use SQLite's online backup API; restore REQUIRES the server to be stopped.
This does not provide an enterprise retention, encryption or offsite recovery system.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def checksum(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda:fh.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def valid_sqlite(path:Path)->bool:
    if not path.is_file():return False
    try:
        with sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro',uri=True) as db:
            return db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    except (OSError,sqlite3.DatabaseError,TypeError):return False


def backup_database(db_path:Path,output_dir:Path)->Path:
    db_path=Path(db_path);output_dir=Path(output_dir)
    if not db_path.is_file() or not valid_sqlite(db_path):raise ValueError('Source database does not exist or failed SQLite integrity_check')
    output_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination=output_dir/f'{db_path.stem}-{stamp}.db'
    with sqlite3.connect(f'file:{db_path.resolve().as_posix()}?mode=ro',uri=True) as src:
        with sqlite3.connect(destination) as dst:src.backup(dst)
    if not valid_sqlite(destination):
        destination.unlink(missing_ok=True)
        raise ValueError('Backup failed integrity_check')
    meta={'type':'MeridianLocalSQLiteBackup','database':db_path.name,'backup':destination.name,
          'sha256':checksum(destination),'created_at_utc':datetime.now(timezone.utc).isoformat()}
    destination.with_suffix('.sha256.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return destination


def restore_database(backup_path:Path,destination:Path,*,confirm:bool=False)->None:
    """Manual local restore. Never automate this over a running ERP process."""
    if not confirm:raise ValueError('Restore requires explicit --confirm; stop Meridian ERP first')
    backup_path=Path(backup_path);destination=Path(destination)
    sidecar=backup_path.with_suffix('.sha256.json')
    if not sidecar.is_file():raise ValueError('Backup checksum manifest missing')
    meta=json.loads(sidecar.read_text(encoding='utf-8'))
    if meta.get('type')!='MeridianLocalSQLiteBackup' or meta.get('sha256')!=checksum(backup_path):
        raise ValueError('Backup checksum mismatch')
    if not valid_sqlite(backup_path):raise ValueError('Backup failed integrity_check')
    if destination.exists():raise ValueError('Destination exists: rename or move existing DB before restoring')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_name(destination.name+'.restore-tmp')
    if temp.exists():raise ValueError('Temporary restore path already exists')
    try:
        with sqlite3.connect(f'file:{backup_path.resolve().as_posix()}?mode=ro',uri=True) as src:
            with sqlite3.connect(temp) as target:src.backup(target)
        if not valid_sqlite(temp):raise ValueError('Restored copy failed integrity_check')
        os.replace(temp,destination)
    finally:temp.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description='Meridian ERP local SQLite backup/restore (development use only)')
    p=parser.add_subparsers(dest='action',required=True)
    b=p.add_parser('backup');b.add_argument('--db',default=os.environ.get('MERIDIAN_DB_PATH','./meridian.db'));b.add_argument('--out',default='./backups')
    r=p.add_parser('restore');r.add_argument('--from-backup',required=True);r.add_argument('--to',required=True);r.add_argument('--confirm',action='store_true')
    args=parser.parse_args()
    if args.action=='backup':print(f'Backup verified: {backup_database(Path(args.db),Path(args.out))}')
    else:restore_database(Path(args.from_backup),Path(args.to),confirm=args.confirm);print(f'Restore verified: {args.to}')
if __name__=='__main__':main()

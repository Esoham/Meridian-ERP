"""Interactive provisioning for the optional local demo login.

Run: python -m scripts.create_user --username admin --role admin
"""
import argparse
import getpass
import os
from pathlib import Path
from meridian.db import init_db
from meridian.security import add_user

def main():
    parser=argparse.ArgumentParser(description='Create a local demo ERP user')
    parser.add_argument('--db',default=os.environ.get('MERIDIAN_DB_PATH','./meridian.db'))
    parser.add_argument('--username',required=True)
    parser.add_argument('--role',choices=['admin','operator','viewer'],default='viewer')
    args=parser.parse_args()
    password=getpass.getpass('Choose a password (12+ characters): ')
    confirm=getpass.getpass('Confirm password: ')
    if password!=confirm:raise SystemExit('Passwords do not match')
    init_db(Path(args.db))
    add_user(Path(args.db),args.username,password,args.role)
    print('Local demo user created. No password was printed or stored in command history.')
if __name__=='__main__':main()

"""Opt-in local authentication demonstration; not enterprise identity management.

Requires MERIDIAN_REQUIRE_LOGIN=1 and an admin created with scripts/create_user.py.
Bearer tokens are short-lived and hashed in SQLite; passwords use PBKDF2-HMAC.
Transport security, lockouts, tenant-wide authorization and SSO are out of scope.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .db import connect, db_write

SECURITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_salt TEXT NOT NULL, password_digest TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','operator','viewer')),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)));
CREATE TABLE IF NOT EXISTS app_sessions (
 token_digest TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES app_users(id),
 expires_unix INTEGER NOT NULL, created_unix INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON app_sessions(expires_unix);
"""
ITERATIONS=500_000
DUMMY_SALT='00'*16
DUMMY_HASH=hashlib.pbkdf2_hmac('sha256',b'dummy-invalid-credentials',bytes.fromhex(DUMMY_SALT),ITERATIONS).hex()


def password_hash(password:str,salt:str)->str:
    return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),ITERATIONS).hex()


def add_user(db_path:Path,username:str,password:str,role:str='admin'):
    if role not in {'admin','operator','viewer'}:raise ValueError('Invalid role')
    if not 3<=len(username)<=60 or not username.replace('_','').replace('-','').isalnum():raise ValueError('Username must be 3-60 letters/digits/_/-')
    if not 12<=len(password)<=128:raise ValueError('Password must have 12-128 characters')
    salt=secrets.token_hex(16)
    with db_write(db_path) as db:
        db.execute('INSERT INTO app_users(username,password_salt,password_digest,role) VALUES (?,?,?,?)',
            (username,salt,password_hash(password,salt),role))

class LoginIn(BaseModel):
    username: str = Field(min_length=1,max_length=60)
    password: str = Field(min_length=1,max_length=128)


def install(app:FastAPI,db_path:Path,auth_required:bool):
    PUBLIC_PATHS={'/api/security/status','/api/security/login'}

    @app.middleware('http')
    async def require_auth(request:Request,call_next):
        route=request.url.path
        if not auth_required or route in PUBLIC_PATHS or route in {'/','/enterprise.css','/enterprise.js','/security.js','/enterprise-foundations.js','/enterprise-foundations.css','/favicon.ico'}:
            return await call_next(request)
        if route.startswith('/api/') or route in {'/docs','/redoc','/openapi.json'}:
            header=request.headers.get('authorization','')
            if not header.startswith('Bearer '):return JSONResponse({'detail':'Sign in to access this ERP workspace'},status_code=401)
            token=header[7:]
            if len(token)<20:return JSONResponse({'detail':'Invalid session'},status_code=401)
            digest=hashlib.sha256(token.encode('utf-8')).hexdigest()
            with connect(db_path) as db:
                row=db.execute('''SELECT u.id,u.username,u.role FROM app_sessions s
                    JOIN app_users u ON u.id=s.user_id WHERE s.token_digest=? AND s.expires_unix>?
                    AND u.enabled=1''',(digest,int(time.time()))).fetchone()
            if row is None:return JSONResponse({'detail':'Session expired or invalid'},status_code=401)
            request.state.meridian_user=dict(row)
            if request.method not in {'GET','HEAD','OPTIONS'}:
                role=row['role']
                if role=='viewer':return JSONResponse({'detail':'Read-only role cannot modify data'},status_code=403)
                if role!='admin' and (route.startswith('/api/finance/') or route.startswith('/api/security/')):
                    return JSONResponse({'detail':'Admin role required for this action'},status_code=403)
        return await call_next(request)

    @app.get('/api/security/status')
    def status():return {'login_required':auth_required,'roles':['admin','operator','viewer'],
        'warning':'Demo auth only; not certified for production identity or access control'}

    @app.post('/api/security/login')
    def login(body:LoginIn):
        if not auth_required:raise HTTPException(409,'Enable MERIDIAN_REQUIRE_LOGIN=1 to use demo sign-in')
        with db_write(db_path) as db:
            row=db.execute('SELECT * FROM app_users WHERE username=? AND enabled=1',(body.username,)).fetchone()
            salt=row['password_salt'] if row else DUMMY_SALT
            expected=row['password_digest'] if row else DUMMY_HASH
            if not hmac.compare_digest(password_hash(body.password,salt),expected) or row is None:
                raise HTTPException(401,'Invalid username or password')
            token=secrets.token_urlsafe(36)
            now=int(time.time())
            db.execute('INSERT INTO app_sessions(token_digest,user_id,expires_unix,created_unix) VALUES (?,?,?,?)',
                (hashlib.sha256(token.encode()).hexdigest(),row['id'],now+3600*8,now))
            return {'access_token':token,'token_type':'bearer','expires_in':28800,'username':row['username'],'role':row['role']}

    @app.get('/api/security/me')
    def current_user(request:Request):
        if not auth_required:return {'login_required':False,'role':'demo-unrestricted'}
        return {'login_required':True,**request.state.meridian_user}

    @app.post('/api/security/logout')
    def logout(request:Request):
        digest=hashlib.sha256(request.headers['authorization'][7:].encode()).hexdigest()
        with db_write(db_path) as db:db.execute('DELETE FROM app_sessions WHERE token_digest=?',(digest,))
        return {'signed_out':True}

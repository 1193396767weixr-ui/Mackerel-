# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

backend_dir = os.path.join(SPECPATH, 'backend')
frontend_dir = os.path.join(SPECPATH, 'frontend')

a = Analysis(
    ['run.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        (os.path.join(frontend_dir, 'index.html'), 'frontend'),
    ],
    hiddenimports=[
        'flask', 'flask_cors', 'flask_jwt_extended', 'werkzeug.security',
        'sqlite3', 'datetime', 'json', 'threading', 'webbrowser'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='英语每日记录',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\chuba\\Workspace\\VSF\\Pattern\\gui\\app.py'],
    pathex=['C:\\Users\\chuba\\Workspace\\VSF\\Pattern\\scripts', 'C:\\Users\\chuba\\Workspace\\VSF\\Pattern\\gui'],
    binaries=[],
    datas=[],
    hiddenimports=['scan', 'judge', 'synth', '_lib.aggregator', '_lib.candidate_schema', '_lib.claude_runner', '_lib.debate', '_lib.judge_prompts', '_lib.render_proposal', '_lib.skill_assemble', '_lib.skill_render', '_lib.skill_validate', '_lib.trace_loader'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Pattern',
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
    icon=['C:\\Users\\chuba\\Workspace\\VSF\\Pattern\\assets\\pattern.ico'],
)

"""Build Pattern.exe via Flet (Flutter engine, standalone Windows binary)."""
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 stdout so arrow/unicode chars don't crash on Windows cp1252
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
GUI = ROOT / "gui"
SCRIPTS = ROOT / "scripts"

env = {**os.environ, "PYTHONUTF8": "1", "FLET_CLI_NO_RICH_OUTPUT": "1"}

# ── Step 1: copy scripts/ into gui/ so Flet bundles them ─────────────────────
_copied: list[Path] = []

def _copy_scripts_into_gui() -> None:
    for src in SCRIPTS.iterdir():
        dst = GUI / src.name
        if dst.exists():
            continue  # don't overwrite existing gui files
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        _copied.append(dst)
        print(f"  + {src.name}")

def _remove_copied() -> None:
    for p in _copied:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()

print("Copying scripts/ into gui/ for bundling...")
_copy_scripts_into_gui()

# ── Step 2: flet build windows ───────────────────────────────────────────────
print("Building Pattern (flet + Flutter engine)...")
cmd = [
    "uv", "run", "flet", "build", "windows",
    "--project", "Pattern",
    "--product", "Pattern",
    "--org", "com.vsf",
    "--module-name", "app",
    "--no-rich-output",
    "--yes",
    str(GUI),
]
result = subprocess.run(cmd, cwd=ROOT, env=env)

# Clean up copied files regardless of build outcome
print("Cleaning up copied scripts from gui/...")
_remove_copied()

# flet exits 1 if only cmake install fails — exe may still have been produced
RELEASE = GUI / "build" / "flutter" / "build" / "windows" / "x64" / "runner" / "Release"
EXE = RELEASE / "Pattern.exe"
CMAKE_INSTALL = GUI / "build" / "flutter" / "build" / "windows" / "x64" / "cmake_install.cmake"

if result.returncode != 0 and not EXE.exists():
    print(f"Build failed before producing exe (exit {result.returncode})")
    sys.exit(result.returncode)

if result.returncode != 0 and CMAKE_INSTALL.exists():
    # ── Step 3: patch cmake_install.cmake ────────────────────────────────────
    # CMake tries to copy vcruntime140_1.dll from System32 (Windows protects it).
    VS_REDIST = Path(
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
        r"\VC\Redist\MSVC"
    )
    vc_dll = next(VS_REDIST.rglob("x64/Microsoft.VC143.CRT/vcruntime140_1.dll"), None)

    if vc_dll:
        text = CMAKE_INSTALL.read_text(encoding="utf-8")
        patched = re.sub(
            r"C:/WINDOWS/System32/vcruntime140_1\.dll",
            vc_dll.as_posix(),
            text,
        )
        CMAKE_INSTALL.write_text(patched, encoding="utf-8")
        print(f"Patched cmake_install.cmake → {vc_dll}")
    else:
        src = Path(r"C:\Windows\System32\vcruntime140_1.dll")
        if src.exists():
            shutil.copy2(src, RELEASE / "vcruntime140_1.dll")

    # ── Step 4: re-run cmake install ─────────────────────────────────────────
    cmake_exe = next(
        Path(r"C:\Program Files (x86)\Microsoft Visual Studio").rglob("cmake.exe"),
        None,
    )
    if cmake_exe:
        print(f"Re-running cmake install...")
        res2 = subprocess.run(
            [str(cmake_exe), "-DBUILD_TYPE=Release", "-P", str(CMAKE_INSTALL)],
            cwd=str(CMAKE_INSTALL.parent),
            env=env,
        )
        if res2.returncode != 0:
            print("cmake install still failed — using Release dir as output directly")

# ── Step 5: copy Release → gui/build/windows/ ────────────────────────────────
OUT = GUI / "build" / "windows"
if RELEASE.exists():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(RELEASE, OUT)
    exe = OUT / "Pattern.exe"
    print(f"\nBuild complete → {OUT}")
    print(f"Exe: {exe} ({exe.stat().st_size // 1024} KB)")
    sys.exit(0)
else:
    print("Build failed — Release directory not found")
    sys.exit(1)

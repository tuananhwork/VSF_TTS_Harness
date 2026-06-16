"""Build Pattern.exe via PyInstaller."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

sep = ";" if sys.platform == "win32" else ":"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "Pattern",
    "--icon", str(ROOT / "assets" / "pattern.ico"),
    "--add-data", f"{ROOT / 'scripts' / '_lib'}{sep}scripts/_lib",
    "--add-data", f"{ROOT / 'gui'}{sep}gui",
    str(ROOT / "gui" / "app.py"),
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build"),
    "--specpath", str(ROOT),
]

print("Building Pattern.exe...")
result = subprocess.run(cmd, cwd=ROOT)
sys.exit(result.returncode)

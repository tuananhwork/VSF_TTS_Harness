"""Build Pattern.exe via PyInstaller."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "Pattern",
    "--icon", str(ROOT / "assets" / "pattern.ico"),
    # Thêm scripts/ vào search path để PyInstaller tìm scan, judge, synth, _lib
    "--paths", str(ROOT / "scripts"),
    "--paths", str(ROOT / "gui"),
    # Bundle scan/judge/synth (dynamic import trong pipeline_runner không được
    # PyInstaller phát hiện tự động)
    "--hidden-import", "scan",
    "--hidden-import", "judge",
    "--hidden-import", "synth",
    "--hidden-import", "_lib.aggregator",
    "--hidden-import", "_lib.candidate_schema",
    "--hidden-import", "_lib.claude_runner",
    "--hidden-import", "_lib.debate",
    "--hidden-import", "_lib.judge_prompts",
    "--hidden-import", "_lib.render_proposal",
    "--hidden-import", "_lib.skill_assemble",
    "--hidden-import", "_lib.skill_render",
    "--hidden-import", "_lib.skill_validate",
    "--hidden-import", "_lib.trace_loader",
    str(ROOT / "gui" / "app.py"),
    "--distpath", str(ROOT / "dist"),
    "--workpath", str(ROOT / "build"),
    "--specpath", str(ROOT),
]

print("Building Pattern.exe...")
result = subprocess.run(cmd, cwd=ROOT)
sys.exit(result.returncode)

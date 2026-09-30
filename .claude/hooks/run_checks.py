"""PostToolUse hook: after Claude edits a Python file, run ruff and pytest.

If either fails, exit code 2 sends the output back to Claude so it fixes the problem.
Uses the project's .venv tools so results match the pinned versions. Skips quietly when
the edited file isn't Python, or when .venv (or a tool in it) doesn't exist.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV = ROOT / ".venv"
BIN = VENV / ("Scripts" if sys.platform == "win32" else "bin")


def venv_tool(name: str) -> Path | None:
    """Return the path to ``name`` inside .venv, or None if it isn't installed there."""
    for candidate in (BIN / f"{name}.exe", BIN / name):
        if candidate.is_file():
            return candidate
    return None


try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

path = str(event.get("tool_input", {}).get("file_path", ""))
if not path.endswith(".py") or not VENV.is_dir():
    sys.exit(0)

problems = []

ruff = venv_tool("ruff")
if ruff:
    r = subprocess.run(
        [str(ruff), "check", "src", "tests"], cwd=ROOT, capture_output=True, text=True
    )
    if r.returncode != 0:
        problems.append("ruff check failed:\n" + r.stdout + r.stderr)

pytest = venv_tool("pytest")
if pytest:
    r = subprocess.run([str(pytest), "-q", "--no-header"], cwd=ROOT, capture_output=True, text=True)
    # Exit code 5 means "no tests collected", which is fine early on.
    if r.returncode not in (0, 5):
        problems.append("pytest failed:\n" + r.stdout[-3000:] + r.stderr[-1000:])

if problems:
    print("\n\n".join(problems), file=sys.stderr)
    sys.exit(2)

sys.exit(0)

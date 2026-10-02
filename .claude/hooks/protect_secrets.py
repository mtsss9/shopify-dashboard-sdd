"""PreToolUse hook: block tool calls whose target is .env or credentials.json.

Enforces the CLAUDE.md security rules. .env.example is allowed.
Only the target of a call is checked: the file path for Read, Edit, Write and
NotebookEdit, the path, pattern or glob for Grep and Glob, and the command for
shell tools. Content being written to other files is never inspected, so a spec
or script that only mentions a secret file name is allowed.

Claude Code sends the tool call as JSON on stdin.
Exit code 2 blocks the call and shows the stderr message to Claude.
"""

import json
import re
import sys
from typing import Any

# A secret file name standing alone, not part of a longer name such as
# .env.example or my-credentials.json.
SECRET_TARGET = re.compile(
    r"(?<![\w.-])(?:\.env|credentials\.json)(?![\w.-])",
    re.IGNORECASE,
)

# The tool_input fields that name what a tool call acts on.
TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "Read": ("file_path",),
    "Edit": ("file_path",),
    "MultiEdit": ("file_path",),
    "Write": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "Grep": ("path", "pattern", "glob"),
    "Glob": ("path", "pattern"),
    "Bash": ("command",),
    "PowerShell": ("command",),
}

MESSAGE = (
    "Blocked by protect_secrets hook: credentials.json and .env must never be "
    "read, edited, searched or printed (CLAUDE.md security rules). "
    "Use environment variables in code, and fixtures in tests."
)


def is_blocked(event: dict[str, Any]) -> bool:
    """Return True when the tool call targets a secret file."""
    tool_input = event.get("tool_input") or {}
    for field in TARGET_FIELDS.get(event.get("tool_name", ""), ()):
        value = tool_input.get(field)
        if isinstance(value, str) and SECRET_TARGET.search(value):
            return True
    return False


def main() -> int:
    """Read the hook event from stdin and return the exit code."""
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if is_blocked(event):
        print(MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""PreToolUse hook: block tool calls whose target is .env or credentials.json.

Enforces the CLAUDE.md security rules. .env.example is allowed.
Only the target of a call is checked: the file path for Read, Edit, Write and
NotebookEdit, the path, pattern or glob for Grep and Glob, and the command for
shell tools. Content being written to other files is never inspected, so a spec
or script that only mentions a secret file name is allowed.

The message of a ``git commit -m``/``--message`` is not a target either, so it is
removed before a shell command is checked. Only a plain quoted message is removed:
one with ``$``, a backtick or a backslash could run a command, so it is still checked.

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
SHELL_TOOLS = {"Bash", "PowerShell"}

# "git commit", optionally with -C <dir> options in between.
GIT_COMMIT = re.compile(r"\bgit(?:\s+-C\s+(?:\"[^\"]*\"|'[^']*'|\S+))*\s+commit(?![\w-])")

# A message option and its quoted value, ending the argument. Double-quoted
# values may not contain $ ` or \, so no shell can expand anything inside them.
COMMIT_MESSAGE = re.compile(
    r"(?P<flag>--message(?:=|\s+)|-[A-Za-z]*m\s*)"
    r"(?:\"[^\"$`\\]*\"|'[^']*')"
    r"(?=\s|$|[;|&])"
)

# Any other quoted argument, copied as it is.
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")

# Characters that end a git commit and start another command.
COMMAND_END = set(";|&\n\r")

MESSAGE = (
    "Blocked by protect_secrets hook: credentials.json and .env must never be "
    "read, edited, searched or printed (CLAUDE.md security rules). "
    "Use environment variables in code, and fixtures in tests."
)


def strip_commit_messages(command: str) -> str:
    """Replace each plain ``git commit`` message with "" so it is not checked."""
    out: list[str] = []
    pos = 0
    for commit in GIT_COMMIT.finditer(command):
        if commit.start() < pos:
            continue
        out.append(command[pos : commit.end()])
        i = commit.end()
        while i < len(command) and command[i] not in COMMAND_END:
            message = COMMIT_MESSAGE.match(command, i) if command[i - 1].isspace() else None
            quoted = QUOTED.match(command, i)
            if message:
                out.append(message.group("flag") + '""')
                i = message.end()
            elif quoted:
                out.append(quoted.group())
                i = quoted.end()
            else:
                out.append(command[i])
                i += 1
        pos = i
    out.append(command[pos:])
    return "".join(out)


def is_blocked(event: dict[str, Any]) -> bool:
    """Return True when the tool call targets a secret file."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    for field in TARGET_FIELDS.get(tool_name, ()):
        value = tool_input.get(field)
        if not isinstance(value, str):
            continue
        if tool_name in SHELL_TOOLS:
            value = strip_commit_messages(value)
        if SECRET_TARGET.search(value):
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

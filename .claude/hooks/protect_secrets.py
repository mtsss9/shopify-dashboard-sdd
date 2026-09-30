"""PreToolUse hook: block any tool call that touches credentials.json or .env.

Claude Code sends the tool call as JSON on stdin.
Exit code 2 blocks the call and shows the stderr message to Claude.
.env.example is allowed; .env and credentials.json are not.
"""

import json
import re
import sys

BLOCKED = re.compile(r"credentials\.json|(?<![\w.-])\.env(?![\w.-])", re.IGNORECASE)

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)

tool_input = json.dumps(event.get("tool_input", {}))

if BLOCKED.search(tool_input):
    print(
        "Blocked by protect_secrets hook: credentials.json and .env must never be "
        "read, edited, searched or printed (CLAUDE.md security rules). "
        "Use environment variables in code, and fixtures in tests.",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)

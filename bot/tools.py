"""Tool implementations for the agentic loop."""

import asyncio
import glob as glob_module
import os
import re
import subprocess
from config import PROJECT_ROOT, BASH_TIMEOUT_SECONDS

# Hard limits to prevent runaway usage
BASH_OUTPUT_MAX_CHARS = 50_000
READ_MAX_LINES = 2000
GREP_MAX_RESULTS = 500

# Blocked bash patterns
BASH_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bsudo\b",
    r"\bchmod\b",
    r"\bgdrive\b",
    r"\bcurl\s+.*-X\s+DELETE",
    r">\s*/dev/sd",
]

# Tool schema definitions for Anthropic API
TOOLS = [
    {
        "name": "bash",
        "description": "Run a bash command in the project working directory. Use this to run python3 scripts/*, check files, compute checksums, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to run"}
            },
            "required": ["command"],
        },
    },
    {
        "name": "read",
        "description": "Read the contents of a file at the given path (relative to project root).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write",
        "description": "Write content to a file (creates parent directories if needed).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "glob",
        "description": "Find files matching a glob pattern relative to project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Directory to search in (optional, defaults to project root)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "grep",
        "description": "Search for a pattern in files. Returns matching lines with file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "File or directory to search"},
                "glob": {"type": "string", "description": "File glob filter (e.g. '*.md')"},
                "case_insensitive": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
]


async def dispatch_tool(name: str, input_dict: dict) -> str:
    """Dispatch to appropriate tool implementation."""
    if name == "bash":
        return await tool_bash(input_dict.get("command", ""))
    elif name == "read":
        return tool_read(input_dict.get("file_path", ""), input_dict.get("offset"), input_dict.get("limit"))
    elif name == "write":
        return tool_write(input_dict.get("file_path", ""), input_dict.get("content", ""))
    elif name == "glob":
        return tool_glob(input_dict.get("pattern", ""), input_dict.get("path"))
    elif name == "grep":
        return tool_grep(
            input_dict.get("pattern", ""),
            input_dict.get("path", "."),
            input_dict.get("glob"),
            input_dict.get("case_insensitive", False),
        )
    else:
        return f"[ERROR] Unknown tool: {name}"


async def tool_bash(command: str) -> str:
    """Run a bash command safely."""
    # Safety check
    for pattern in BASH_BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return f"[BLOCKED] Command matches blocked pattern"

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=PROJECT_ROOT,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=BASH_TIMEOUT_SECONDS)
        output = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        combined = output
        if err:
            combined += f"\n[STDERR]\n{err}"
        if len(combined) > BASH_OUTPUT_MAX_CHARS:
            combined = combined[:BASH_OUTPUT_MAX_CHARS] + "\n[TRUNCATED]"
        return combined if combined else "[No output]"
    except asyncio.TimeoutError:
        return f"[TIMEOUT] Command exceeded {BASH_TIMEOUT_SECONDS}s limit"
    except Exception as e:
        return f"[ERROR] {e}"


def tool_read(file_path: str, offset: int | None, limit: int | None) -> str:
    """Read a file safely."""
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, file_path))
    if not abs_path.startswith(PROJECT_ROOT):
        return "[ERROR] Path traversal not allowed"
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        start = (offset - 1) if offset else 0
        end = start + (limit if limit else READ_MAX_LINES)
        selected = lines[start:end]
        numbered = [f"{start + i + 1}→{line}" for i, line in enumerate(selected)]
        return "".join(numbered) if numbered else "[Empty file]"
    except FileNotFoundError:
        return f"[ERROR] File not found: {file_path}"
    except Exception as e:
        return f"[ERROR] {e}"


def tool_write(file_path: str, content: str) -> str:
    """Write to a file safely."""
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, file_path))
    if not abs_path.startswith(PROJECT_ROOT):
        return "[ERROR] Path traversal not allowed"
    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[OK] Written {len(content)} chars to {file_path}"
    except Exception as e:
        return f"[ERROR] {e}"


def tool_glob(pattern: str, path: str | None) -> str:
    """Find files matching a glob pattern."""
    search_root = os.path.normpath(os.path.join(PROJECT_ROOT, path or "."))
    if not search_root.startswith(PROJECT_ROOT):
        return "[ERROR] Path traversal not allowed"
    full_pattern = os.path.join(search_root, pattern)
    matches = glob_module.glob(full_pattern, recursive=True)
    # Return relative paths
    relative = [os.path.relpath(m, PROJECT_ROOT) for m in sorted(matches)]
    return "\n".join(relative) if relative else "[No matches]"


def tool_grep(pattern: str, path: str, glob_filter: str | None, case_insensitive: bool) -> str:
    """Search for a pattern in files."""
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, path))
    if not abs_path.startswith(PROJECT_ROOT):
        return "[ERROR] Path traversal not allowed"

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"[ERROR] Invalid regex: {e}"

    results = []

    if os.path.isfile(abs_path):
        files_to_search = [abs_path]
    else:
        if glob_filter:
            files_to_search = glob_module.glob(os.path.join(abs_path, "**", glob_filter), recursive=True)
        else:
            files_to_search = []
            for root, dirs, files in os.walk(abs_path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    files_to_search.append(os.path.join(root, fname))

    for fpath in sorted(files_to_search):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if regex.search(line):
                        rel = os.path.relpath(fpath, PROJECT_ROOT)
                        results.append(f"{rel}:{lineno}: {line.rstrip()}")
                        if len(results) >= GREP_MAX_RESULTS:
                            results.append("[TRUNCATED — limit reached]")
                            return "\n".join(results)
        except Exception:
            pass

    return "\n".join(results) if results else "[No matches]"

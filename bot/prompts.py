"""System prompt builder - reads .claude/commands/*.md files."""

import os
from config import PROJECT_ROOT

COMMAND_FILES = {
    "review-page": ".claude/commands/review-page.md",
    "brief": ".claude/commands/brief.md",
    "social-review": ".claude/commands/social-review.md",
}

BASE_SYSTEM_PROMPT = """You are the website analysis orchestration agent running inside a Telegram bot.

Working directory: {working_dir}

IMPORTANT: You are running in a Telegram bot environment with the following constraints:

1. **File paths**: All file paths must be relative to the working directory above. Use forward slashes.

2. **Google Drive**: Do NOT attempt gdrive uploads. The `gdrive` CLI is not available in this environment.
   - Skip all "Upload to Google Drive" or "gdrive upload" steps silently.
   - The review files will be sent to the user via Telegram file attachment instead.

3. **Telegram output format**:
   - Output a SUMMARY suitable for Telegram (max 3800 characters):
     - Overall score and category scores
     - Top 3-5 action items in priority order
     - Local file paths where full reviews were written
   - Do NOT output the full review text inline — it will be sent as a file attachment.
   - Full markdown review files will be automatically uploaded as Telegram documents.

4. **Clarifying questions**:
   - If you need to ask the user a clarifying question (e.g., "analyze section root or all sub-pages?"),
     output your question starting with the prefix: ASK_USER: <your question>
   - Then stop executing. The bot will relay the question to Telegram and resume with the user's reply.

5. **Tool use**: You have access to bash, read, write, glob, and grep tools. Use them freely to:
   - Run existing Python scripts (fetch_page.py, crawl_site.py, etc.)
   - Read CLAUDE.md, agent files, and command files for context
   - Write review output files to reviews/ or social-reviews/ directories
   - Search and list files as needed

---

{command_instructions}"""

COMMAND_INSTRUCTIONS_TEMPLATE = """COMMAND INSTRUCTIONS
====================

{raw_content}"""


def build_system_prompt(command: str, arguments: str) -> str:
    """Build system prompt for the agent from command file."""
    command_file = COMMAND_FILES.get(command)
    if not command_file:
        raise ValueError(f"Unknown command: {command}")

    abs_path = os.path.join(PROJECT_ROOT, command_file)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raise ValueError(f"Command file not found: {command_file}")

    # Replace $ARGUMENTS placeholder if present, otherwise append arguments as context
    if "$ARGUMENTS" in raw:
        instructions = raw.replace("$ARGUMENTS", arguments)
    else:
        instructions = raw + f"\n\nUser input: {arguments}"

    command_section = COMMAND_INSTRUCTIONS_TEMPLATE.format(raw_content=instructions)

    return BASE_SYSTEM_PROMPT.format(
        working_dir=PROJECT_ROOT,
        command_instructions=command_section,
    )

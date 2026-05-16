#!/usr/bin/env python3
"""LogSession - Daily logger for OpenCode sessions."""

import os
import sys
from datetime import datetime

VAULT_PATH = "/storage/emulated/0/Obsidian/opencode-vault"
LOGS_DIR = os.path.join(VAULT_PATH, "logs")


def get_git_diff_summary():
    """Get git diff summary for the day."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=os.path.expanduser("~/meu-backend"),
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() or "No changes"
    except Exception as e:
        return f"Error: {e}"


def get_git_status():
    """Get current git status."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=os.path.expanduser("~/meu-backend"),
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() or "Clean"
    except Exception as e:
        return f"Error: {e}"


def log_session(message: str):
    """Log a session message to today's log file."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOGS_DIR, f"{today}.md")
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    git_status = get_git_status()
    git_diff = get_git_diff_summary()
    
    content = f"""# {today}

## {timestamp} - Session Log

**Message:** {message}

**Git Status:**
```
{git_status}
```

**Git Diff:**
```
{git_diff}
```

---
"""
    
    # Append or create
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as f:
            existing = f.read()
        # Remove header if exists to avoid duplication
        if existing.startswith("# "):
            lines = existing.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("---"):
                    existing = "\n".join(lines[i+1:])
                    break
        content = existing + "\n" + content
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Logged to: {log_file}")
    return log_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python log_session.py <message>")
        sys.exit(1)
    
    message = " ".join(sys.argv[1:])
    log_session(message)
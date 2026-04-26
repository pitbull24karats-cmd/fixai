import subprocess
from pathlib import Path

from services.analyzer import call_ollama


async def generate_fix(file_path: Path, content: str, issues: dict) -> str:
    issue_summary = []
    for category, items in issues.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    issue_summary.append(f"[{category}] line {item.get('line', '?')}: {item.get('description', '')}")

    issues_text = "\n".join(issue_summary) if issue_summary else "General improvements needed."

    prompt = f"""You are an expert code fixer. Fix the following issues in the code.

File: {file_path.name}
Issues to fix:
{issues_text}

Original code:
```
{content}
```

Return ONLY the complete fixed file content. No explanations, no markdown fences, no comments about what changed. Just the raw fixed code."""

    return await call_ollama(prompt)


def git_commit_and_push(file_path: Path, commit_message: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=file_path.parent,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, "Not a git repository"
        repo_root = result.stdout.strip()

        for cmd in [
            ["git", "add", str(file_path)],
            ["git", "commit", "-m", commit_message],
            ["git", "push"],
        ]:
            r = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return False, f"Failed at `{' '.join(cmd)}`: {r.stderr.strip()}"

        return True, "committed and pushed"
    except subprocess.TimeoutExpired:
        return False, "git operation timed out"
    except Exception as e:
        return False, str(e)


async def auto_fix_file(file_path: Path, issues: dict) -> dict:
    try:
        original = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"success": False, "error": f"Could not read file: {e}"}

    fixed = await generate_fix(file_path, original[:3000], issues)
    if not fixed or len(fixed.strip()) < 10:
        return {"success": False, "error": "Fixer returned empty content"}

    try:
        file_path.write_text(fixed, encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": f"Could not write file: {e}"}

    low_count = sum(
        1 for cat in issues.values() if isinstance(cat, list)
        for item in cat if isinstance(item, dict) and item.get("severity") == "low"
    )
    commit_msg = f"auto-fix({file_path.name}): {low_count} low-severity issue(s) resolved by FixAI"
    ok, detail = git_commit_and_push(file_path, commit_msg)

    return {
        "success": ok,
        "file": str(file_path),
        "git": detail,
        "commit_message": commit_msg,
    }

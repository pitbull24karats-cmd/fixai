import httpx
import json
from pathlib import Path
from typing import Optional

OLLAMA_URL = "http://192.168.243.196:11434"
MODEL = "qwen2.5:7b"
ALLOWED_BASES = [
    Path.home() / "Desktop" / "Jarvis",
    Path.home() / "jarvis_server",
    Path.home() / "Desktop" / "devbrain",
]


def is_allowed_path(path: Path) -> bool:
    resolved = path.resolve()
    return any(
        resolved == base.resolve() or base.resolve() in resolved.parents
        for base in ALLOWED_BASES
    )


def collect_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rb", ".java", ".sh", ".yaml", ".yml", ".json"}
    return [f for f in path.rglob("*") if f.is_file() and f.suffix in exts]


def read_file_safe(path: Path, max_bytes: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except Exception as e:
        return f"[read error: {e}]"


async def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")


async def analyze_for_issues(file_path: Path, content: str) -> dict:
    prompt = f"""You are a code reviewer. Analyze the following code file and identify issues.

File: {file_path.name}
```
{content}
```

Return a JSON object with this exact structure (no markdown, just raw JSON):
{{
  "bugs": [{{"line": <int or null>, "description": "<str>", "severity": "high|medium|low"}}],
  "security": [{{"line": <int or null>, "description": "<str>", "severity": "high|medium|low"}}],
  "deprecated_apis": [{{"line": <int or null>, "description": "<str>", "severity": "high|medium|low"}}],
  "improvements": [{{"line": <int or null>, "description": "<str>", "severity": "high|medium|low"}}]
}}

If no issues in a category, use an empty array. Be concise."""

    raw = await call_ollama(prompt)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {
            "bugs": [],
            "security": [],
            "deprecated_apis": [],
            "improvements": [],
            "parse_error": raw[:300],
        }


async def analyze_for_refactor(file_path: Path, content: str) -> dict:
    prompt = f"""You are a refactoring expert. Analyze the following code and provide refactoring suggestions.

File: {file_path.name}
```
{content}
```

Return a JSON object with this exact structure (no markdown, just raw JSON):
{{
  "readability": [{{"description": "<str>", "suggestion": "<str>", "severity": "high|medium|low"}}],
  "duplicate_code": [{{"description": "<str>", "suggestion": "<str>", "severity": "high|medium|low"}}],
  "naming": [{{"description": "<str>", "suggestion": "<str>", "severity": "high|medium|low"}}],
  "module_separation": [{{"description": "<str>", "suggestion": "<str>", "severity": "high|medium|low"}}]
}}

If no suggestions in a category, use an empty array. Be concise. Do NOT apply any changes."""

    raw = await call_ollama(prompt)
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {
            "readability": [],
            "duplicate_code": [],
            "naming": [],
            "module_separation": [],
            "parse_error": raw[:300],
        }

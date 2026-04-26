import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.analyzer import is_allowed_path, collect_files, read_file_safe, analyze_for_issues
from services.auto_fixer import auto_fix_file
from services.redis_client import get_redis

router = APIRouter(prefix="/watch", tags=["watch"])

JARVIS_URL = "http://localhost:8001"


class RegisterRequest(BaseModel):
    path: str


class TriggerRequest(BaseModel):
    path: str


async def notify_jarvis(message: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{JARVIS_URL}/conversation/message",
                json={"message": message, "source": "fixai"},
            )
            return resp.status_code < 300
    except Exception:
        return False


@router.post("/register")
async def register_watch(req: RegisterRequest):
    target = Path(req.path).expanduser().resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    if not is_allowed_path(target):
        raise HTTPException(status_code=403, detail="Path not in allowed watch list")

    r = get_redis()
    key = f"fixai:watch:{target}"
    payload = json.dumps({
        "path": str(target),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    })
    await r.set(key, payload)
    await r.sadd("fixai:watch:paths", str(target))

    return {"registered": str(target), "redis_key": key}


@router.post("/trigger")
async def trigger_watch(req: TriggerRequest):
    target = Path(req.path).expanduser().resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    if not is_allowed_path(target):
        raise HTTPException(status_code=403, detail="Path not in allowed watch list")

    r = get_redis()
    registered = await r.sismember("fixai:watch:paths", str(target))
    if not registered:
        raise HTTPException(status_code=400, detail="Path not registered. Call /watch/register first.")

    files = collect_files(target)
    if not files:
        return {"path": str(target), "message": "No supported files found", "actions": []}

    actions = []
    for f in files:
        content = read_file_safe(f)
        issues = await analyze_for_issues(f, content)

        high_count = sum(
            1 for cat in issues.values() if isinstance(cat, list)
            for item in cat if isinstance(item, dict) and item.get("severity") == "high"
        )
        low_count = sum(
            1 for cat in issues.values() if isinstance(cat, list)
            for item in cat if isinstance(item, dict) and item.get("severity") == "low"
        )
        total = sum(len(v) for v in issues.values() if isinstance(v, list))

        if total == 0:
            actions.append({"file": str(f), "action": "clean", "issues": 0})
            continue

        if high_count > 0:
            queue_item = json.dumps({
                "file": str(f),
                "issues": issues,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "high": high_count,
                "low": low_count,
            })
            await r.rpush("fixai:pending:queue", queue_item)

            msg = (
                f"[FixAI] 重大な問題を検出しました\n"
                f"ファイル: {f.name}\n"
                f"High severity: {high_count}件\n"
                f"承認後に修正を適用します。fixai:pending:queue を確認してください。"
            )
            await notify_jarvis(msg)
            actions.append({"file": str(f), "action": "queued_for_approval", "high": high_count})

        elif low_count > 0:
            fix_result = await auto_fix_file(f, issues)
            result_msg = (
                f"[FixAI] 軽微な問題を自動修正しました\n"
                f"ファイル: {f.name}\n"
                f"Low severity: {low_count}件\n"
                f"Git: {fix_result.get('git', 'n/a')}\n"
                f"成功: {fix_result.get('success', False)}"
            )
            await notify_jarvis(result_msg)
            actions.append({"file": str(f), "action": "auto_fixed", "result": fix_result})

    return {"path": str(target), "files_checked": len(files), "actions": actions}

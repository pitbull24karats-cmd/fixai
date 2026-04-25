from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import httpx
from services.analyzer import is_allowed_path, collect_files, read_file_safe, analyze_for_refactor

router = APIRouter()

DEVBRAIN_INGEST_URL = "http://localhost:8003/ingest"


class ClearwingRequest(BaseModel):
    path: str


async def save_to_devbrain(payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DEVBRAIN_INGEST_URL, json=payload)
            return resp.status_code < 300
    except Exception:
        return False


@router.post("/clearwing")
async def clearwing(req: ClearwingRequest):
    target = Path(req.path).expanduser().resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")

    if not is_allowed_path(target):
        raise HTTPException(
            status_code=403,
            detail="Path not allowed. Permitted: ~/Desktop/Jarvis/, ~/jarvis_server/, ~/Desktop/devbrain/",
        )

    files = collect_files(target)
    if not files:
        raise HTTPException(status_code=422, detail="No supported source files found.")

    results = []
    for f in files:
        content = read_file_safe(f)
        suggestions = await analyze_for_refactor(f, content)
        total_suggestions = sum(
            len(v) for k, v in suggestions.items() if isinstance(v, list)
        )
        results.append({
            "file": str(f),
            "suggestions": suggestions,
            "summary": {
                "total": total_suggestions,
                "high": sum(
                    1 for cat in suggestions.values() if isinstance(cat, list)
                    for item in cat if isinstance(item, dict) and item.get("severity") == "high"
                ),
                "medium": sum(
                    1 for cat in suggestions.values() if isinstance(cat, list)
                    for item in cat if isinstance(item, dict) and item.get("severity") == "medium"
                ),
                "low": sum(
                    1 for cat in suggestions.values() if isinstance(cat, list)
                    for item in cat if isinstance(item, dict) and item.get("severity") == "low"
                ),
            },
        })

    devbrain_payload = {
        "title": f"Clearwing refactor suggestions: {target.name}",
        "content": str(results),
        "tags": ["fixai", "clearwing", "refactor"],
        "source": "fixai",
    }
    saved = await save_to_devbrain(devbrain_payload)

    return {
        "path": str(target),
        "files_analyzed": len(files),
        "results": results,
        "saved_to_devbrain": saved,
        "note": "Suggestions only — no changes applied.",
    }

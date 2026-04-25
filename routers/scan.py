from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from services.analyzer import is_allowed_path, collect_files, read_file_safe, analyze_for_issues

router = APIRouter()


class ScanRequest(BaseModel):
    path: str


@router.post("/scan")
async def scan(req: ScanRequest):
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

    if target.is_dir():
        files = files[:10]

    results = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            text = "\n".join(lines[:100]) if len(lines) > 100 else "\n".join(lines)
            content = text[:3000]
        except Exception as e:
            content = f"[read error: {e}]"
        issues = await analyze_for_issues(f, content)
        total_issues = sum(
            len(v) for k, v in issues.items() if isinstance(v, list)
        )
        results.append({
            "file": str(f),
            "issues": issues,
            "summary": {
                "total": total_issues,
                "high": sum(
                    1 for cat in issues.values() if isinstance(cat, list)
                    for item in cat if isinstance(item, dict) and item.get("severity") == "high"
                ),
                "medium": sum(
                    1 for cat in issues.values() if isinstance(cat, list)
                    for item in cat if isinstance(item, dict) and item.get("severity") == "medium"
                ),
                "low": sum(
                    1 for cat in issues.values() if isinstance(cat, list)
                    for item in cat if isinstance(item, dict) and item.get("severity") == "low"
                ),
            },
        })

    return {
        "path": str(target),
        "files_scanned": len(files),
        "results": results,
    }

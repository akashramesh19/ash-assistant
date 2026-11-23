"""Report on a crew run: where it is, or what came out. Read-only."""

import json

from crew.runner import crew_root

TOOL_DEFINITION = {
    "name": "crew_status",
    "description": (
        "Check a crew run started with run_crew: its status, current stage, and where the finished "
        "document is. With no run_id, reports on the most recent run."
    ),
    "parameters": {
        "type": "object",
        "properties": {"run_id": {"type": "string", "description": "Run id; omit for the latest run."}},
        "required": [],
    },
}


def run(run_id: str = "", **kwargs) -> str:
    root = crew_root()
    if run_id:
        folder = root / run_id
        if folder.resolve().parent != root.resolve():
            return "error: that isn't a crew run id"
    else:
        runs = sorted((p for p in root.glob("*/run.json")), key=lambda p: p.parent.name) if root.exists() else []
        if not runs:
            return "No crew runs yet."
        folder = runs[-1].parent
    meta_path = folder / "run.json"
    if not meta_path.exists():
        return f"error: no crew run '{folder.name}'"
    meta = json.loads(meta_path.read_text())

    status = meta["status"]
    lines = [f"Run {meta['id']}: {status}."]
    if status in ("queued", "running") and meta.get("current_stage"):
        lines.append(f"Now at: {meta['current_stage']}.")
    if status in ("done", "done-unreviewed"):
        lines.append(f"Finished document: {folder / 'final.md'}")
        if meta.get("unresearched"):
            lines.append("Note: research was unavailable, so the document is unresearched.")
        lines.append(f"Review: {len(meta.get('edits_applied', []))} edits applied, {len(meta.get('edits_skipped', []))} skipped, {len(meta.get('flags', []))} flags.")
        if meta.get("error"):
            lines.append(f"Note: {meta['error']}")
        for warning in meta.get("warnings", []):
            lines.append(f"Warning: {warning}.")
    if status == "failed":
        lines.append(f"Failed at {meta.get('failed_stage', 'start')}: {meta.get('error')}")
    return " ".join(lines)

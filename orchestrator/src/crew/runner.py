"""Document crew runner: Madhi -> Oli -> Thooya -> scripted checks -> Kural.

One straight pass, written step by step into a run folder so a run can be
inspected. Roles, models and fallbacks come from roster.json; the role prompts
are the files in docs/crew/. Stages are stateless: each call starts with an
empty history, and the crew uses its own provider instances (never the
conversation's).

Failure handling (see docs/crew/README.md): Thooya falls back to Claude; Oli is
skipped and the run marked unresearched; Madhi or Kural failing stops the run;
bad review output ships the draft unreviewed, and says so in run.json.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from crew.checks import run_checks
from providers.base import ProviderError

REPO_ROOT = Path(__file__).resolve().parents[3]
ROLES_DIR = REPO_ROOT / "docs" / "crew"
ROSTER_PATH = Path(__file__).resolve().parent / "roster.json"
DEFAULT_ROOT = REPO_ROOT / "ash-sandbox"
NO_RESEARCH = re.compile(r"research questions\W*:?\W*none", re.IGNORECASE)


class StageError(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage} failed: {message}")
        self.stage = stage


def load_roster() -> dict:
    return json.loads(ROSTER_PATH.read_text())


def load_role_prompt(role: str) -> str:
    """The role file without its front matter."""
    text = (ROLES_DIR / f"{role}.md").read_text()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def crew_root() -> Path:
    return Path(os.environ.get("ASH_CREW_ROOT") or DEFAULT_ROOT)


def prepare_run(task: str, root: Path | None = None, now: datetime | None = None) -> Path:
    """Create the run folder and a queued run.json. Returns the folder."""
    root = Path(root or crew_root())
    root.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    slug = "-".join(re.sub(r"[^a-z0-9 ]", "", task.lower()).split()[:5])[:30] or "task"
    run_dir, counter = root / f"{stamp}-{slug}", 1
    while True:
        try:
            run_dir.mkdir()
            break
        except FileExistsError:
            counter += 1
            run_dir = root / f"{stamp}-{slug}-{counter}"
    _write_json(run_dir / "run.json", {"id": run_dir.name, "task": task, "status": "queued", "stages": []})
    return run_dir


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _parse_review(text: str) -> dict:
    """Kural's JSON, tolerating a code fence or stray text around it."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("no JSON object in the review")
        data = json.loads(match.group(0))
    if data.get("verdict") not in ("approved", "edits"):
        raise ValueError(f"unknown verdict {data.get('verdict')!r}")
    edits = data.get("edits") or []
    if not isinstance(edits, list) or not all(
        isinstance(e, dict) and isinstance(e.get("find"), str) and isinstance(e.get("replace"), str) for e in edits
    ):
        raise ValueError("edits must be a list of {find, replace, reason}")
    data["edits"] = edits
    data["flags"] = [str(f) for f in (data.get("flags") or [])]
    return data


def _audit_research(research: str, searches: int, oli: dict, warnings: list) -> str:
    """Oli's search cap lives in its prompt, and Matilda searches on its own
    side, so it cannot be enforced; what we can do is measure and say so. No
    search activity and no URLs in the notes means the findings are from memory,
    and the notes are marked so the later stages treat them as unsourced."""
    cap = oli.get("max_searches")
    if cap and searches > cap:
        warnings.append(f"Oli made {searches} tool calls; the cap is {cap}")
    if searches == 0 and not re.search(r"https?://", research):
        warnings.append("Oli: no search activity detected and no sources in the notes; findings are from memory")
        research = "NOTE: no web search was detected and there are no sources; treat every finding below as unsourced.\n\n" + research
    return research


def apply_edits(draft: str, edits: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """Apply find/replace edits that match exactly once. Returns the new text,
    the edits applied, and the edits skipped (with the reason)."""
    applied, skipped = [], []
    for edit in edits:
        count = draft.count(edit["find"]) if edit["find"] else 0
        if count == 1:
            draft = draft.replace(edit["find"], edit["replace"], 1)
            applied.append(edit)
        else:
            skipped.append({**edit, "skipped": "not found" if count == 0 else f"matches {count} times"})
    return draft, applied, skipped


def run_document_crew(task: str, providers: dict, run_dir: Path, on_progress=None, clock=time.perf_counter) -> dict:
    """Run the crew in run_dir (from prepare_run). providers maps a name
    ("claude", "matilda") to a Provider; a missing name means unavailable.
    Returns the run.json contents."""
    roster = load_roster()
    run_dir = Path(run_dir)
    run = json.loads((run_dir / "run.json").read_text())
    run.update(status="running", unresearched=False, edits_applied=[], edits_skipped=[], flags=[], warnings=[])

    def save(**changes):
        run.update(changes)
        _write_json(run_dir / "run.json", run)

    def call(role: str, user_text: str, allow_fallback: bool = True) -> str:
        """One stage: the role's provider, falling back where the roster says so."""
        wanted = roster[role]["model"]
        order = [wanted] + ([roster[role]["fallback"]] if allow_fallback and roster[role].get("fallback") else [])
        record = {"role": role, "provider": None, "seconds": None, "fallback_from": None, "error": None, "server_tool_calls": 0}
        run["stages"].append(record)
        save(current_stage=role)
        if on_progress:
            on_progress(role)
        errors = []
        for name in order:
            provider = providers.get(name)
            if provider is None:
                errors.append(f"{name}: not available")
                record["fallback_from"] = name
                continue
            started = clock()
            try:
                provider.replace_history([])
                result = provider.run_turn(
                    user_text, load_role_prompt(role), [], lambda tool, args: "error: no tools in a crew stage"
                )
            except ProviderError as error:
                errors.append(f"{name}: {error}")
                record["fallback_from"] = name
                continue
            record.update(provider=name, seconds=round(clock() - started, 2), server_tool_calls=len(result.server_tool_calls))
            if errors:
                record["error"] = "; ".join(errors)
            save()
            return result.text
        record["error"] = "; ".join(errors)
        save()
        raise StageError(role, record["error"])

    try:
        brief = call("madhi", f"Task:\n{task}")
        (run_dir / "01-brief.md").write_text(brief)

        if NO_RESEARCH.search(brief):
            research = "No research needed: the brief has no research questions."
        else:
            try:
                research = call("oli", f"Research the questions in this brief.\n\n{brief}")
                research = _audit_research(research, run["stages"][-1]["server_tool_calls"], roster["oli"], run["warnings"])
            except StageError as error:
                research = f"UNRESEARCHED: research was unavailable ({error}). Treat every external fact as missing."
                run["unresearched"] = True
        (run_dir / "02-research.md").write_text(research)

        draft = call("thooya", f"## Brief\n{brief}\n\n## Research notes\n{research}")
        (run_dir / "03-draft.md").write_text(draft)

        findings = run_checks(draft)
        (run_dir / "04-checks.md").write_text(
            "# Scripted checks\n\n" + ("\n".join(f"- {f}" for f in findings) if findings else "No findings.") + "\n"
        )

        review_text = call(
            "kural",
            f"## Brief\n{brief}\n\n## Research notes\n{research}\n\n## Draft\n{draft}\n\n"
            "## Scripted check findings\n" + ("\n".join(f"- {f}" for f in findings) or "None."),
        )
        (run_dir / "05-review.json").write_text(review_text)
        try:
            review = _parse_review(review_text)
        except ValueError as error:
            (run_dir / "final.md").write_text(draft)
            save(status="done-unreviewed", error=f"Kural's review could not be used ({error}); draft shipped as is", current_stage=None)
            return run

        final, applied, skipped = apply_edits(draft, review["edits"]) if review["verdict"] == "edits" else (draft, [], [])
        (run_dir / "final.md").write_text(final)
        save(status="done", edits_applied=applied, edits_skipped=skipped, flags=review["flags"], current_stage=None)
    except StageError as error:
        save(status="failed", failed_stage=error.stage, error=str(error), current_stage=None)
    return run

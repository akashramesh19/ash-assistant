"""Run the same fixed prompts through each provider and write a results table.

    .venv/bin/python comparison/run_comparison.py                  # claude + matilda, prompts 1-3
    .venv/bin/python comparison/run_comparison.py --repeat 3       # three fresh runs per provider
    .venv/bin/python comparison/run_comparison.py --providers claude

Fairness setup (see comparison/method.md): every run starts from a fresh copy
of orchestrator/data/memory.example.json, so one provider's prompts never reach
the other's context and no personal memory is sent or written to the results.
Your real memory.json is hashed before and after and the run aborts if it changed.
It makes real API calls and needs ANTHROPIC_API_KEY and/or MATILDA_API_KEY.
"""

import argparse
import hashlib
import json
import re
import shutil
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator" / "src"))

import context  # noqa: E402
import handler  # noqa: E402
from providers import create_provider  # noqa: E402
from providers.base import ProviderConfigError, ProviderError  # noqa: E402
from providers.claude import DEFAULT_MODEL  # noqa: E402
from turn_log import TurnLog  # noqa: E402

PROMPTS = {
    1: "What's the weather in Melbourne?",
    2: "And in Sydney?",
    3: "What is the capital of France?",
}
NEEDS_MOVE_FILE = {4, 5}  # "Move report.txt into the Archive folder", "What did I just ask you to move?"
LONG_FOR_VOICE_WORDS = 40


def weather_check(city):
    def check(reply, tool_calls):
        calls = [c for c in tool_calls if c.name == "get_weather"]
        if not calls:
            return False, "did not call get_weather"
        if not any(city in str(c.arguments.get("location", "")).lower() for c in calls):
            return False, f"get_weather called without {city}: {[c.arguments for c in calls]}"
        return True, "called get_weather for " + city
    return check


def capital_check(reply, tool_calls):
    if tool_calls:
        return False, "called a tool for a general-knowledge question"
    if "paris" not in reply.lower():
        return False, "reply does not mention Paris"
    return True, "no tool, mentions Paris"


CHECKS = {1: weather_check("melbourne"), 2: weather_check("sydney"), 3: capital_check}


def parse_prompts(spec: str) -> list[int]:
    numbers = []
    for part in spec.split(","):
        low, _, high = part.partition("-")
        numbers.extend(range(int(low), int(high or low) + 1))
    if set(numbers) & NEEDS_MOVE_FILE:
        raise SystemExit("prompts 4 and 5 need the move_file tool, which isn't built yet")
    unknown = set(numbers) - set(PROMPTS)
    if unknown:
        raise SystemExit(f"unknown prompt numbers: {sorted(unknown)}")
    return numbers


def _hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _run_one(provider_name, run_number, prompt_numbers, build_provider, work_dir):
    run_dir = work_dir / f"{provider_name}-run{run_number}"
    run_dir.mkdir(parents=True)
    memory = run_dir / "memory.json"
    shutil.copy(context.MEMORY_TEMPLATE_PATH, memory)
    context.MEMORY_PATH = memory

    log_path = run_dir / "turns.jsonl"
    respond = handler.create_responder(build_provider(provider_name), TurnLog(log_path))

    rows = []
    for number in prompt_numbers:
        error = None
        try:
            respond(PROMPTS[number])
        except ProviderError as exc:
            error = str(exc)
        record = json.loads(log_path.read_text().splitlines()[-1])

        calls = [
            type("Call", (), {"name": c["name"], "arguments": c["arguments"]})
            for c in record["tool_calls"]
        ]
        reply = record["reply"] or ""
        if error:
            passed, detail = False, f"error: {error}"
        else:
            passed, detail = CHECKS[number](reply, calls)
        latency = record["latency"]
        rows.append(
            {
                "provider": provider_name,
                "run": run_number,
                "prompt_number": number,
                "prompt": PROMPTS[number],
                "passed": passed,
                "detail": detail,
                "tool_calls": record["tool_calls"],
                "reply": reply,
                "error": error,
                "total_seconds": latency["total_seconds"],
                "model_seconds": latency["model_seconds"],
                "tool_seconds": latency["tool_seconds"],
                "first_token_seconds": latency["first_token_seconds"],
            }
        )
    return rows


def run_all(providers, prompt_numbers, repeat, build_provider=create_provider, work_dir=None):
    """Each (provider, repeat) is a fresh run: new provider object, new copy of
    the example memory, all prompts in order."""
    work_dir = Path(work_dir or tempfile.mkdtemp(prefix="ash-comparison-"))
    real_memory = Path(context.MEMORY_PATH)
    hash_before = _hash(real_memory)
    rows = []
    try:
        for provider_name in providers:
            for run_number in range(1, repeat + 1):
                rows.extend(_run_one(provider_name, run_number, prompt_numbers, build_provider, work_dir))
    finally:
        context.MEMORY_PATH = real_memory
    if _hash(real_memory) != hash_before:
        raise RuntimeError("real memory file changed during the comparison; results discarded")
    return rows


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _fmt(value):
    return "n/a" if value is None else f"{value:.2f}"


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _notes(row):
    notes = []
    if row["reply"] and re.search(r"https?://|\bSources\b", row["reply"]):
        notes.append("reply contains citations/URLs not from our tool")
    words = len(row["reply"].split())
    if words > LONG_FOR_VOICE_WORDS:
        notes.append(f"long for voice ({words} words)")
    if not row["passed"]:
        notes.append(row["detail"])
    return "; ".join(notes)


def _calls_text(row):
    return "; ".join(
        f"{c['name']}({', '.join(f'{k}={v!r}' for k, v in c['arguments'].items())})"
        for c in row["tool_calls"]
    ) or "none"


def render_markdown(rows, repeat, providers, claude_model, python):
    out = [
        "# Ash provider comparison: results",
        "",
        "Generated by `comparison/run_comparison.py`. Method, fairness setup and "
        "limits: `comparison/method.md`.",
        "",
        f"- Run at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Providers: {', '.join(providers)}; fresh runs per provider: {repeat}",
        f"- Claude model: `{claude_model}`; Matilda model: not exposed by the SDK",
        "- Starting memory: copy of `orchestrator/data/memory.example.json` for every run",
        f"- Python: {python}",
        "- Timing covers the provider call only. `model` = total minus our tool time; "
        "for Matilda it also includes any server-side work. `1st token` is Matilda only.",
        "- 'Correct' is a mechanical check (right tool, right city, no tool for "
        "general knowledge); wording quality is not scored.",
        "",
        "## Summary",
        "",
        "| Provider | # | Prompt | Correct | Median total s | Median model s | Median tool s |",
        "|---|---|---|---|---|---|---|",
    ]
    for provider in providers:
        for number in sorted({r["prompt_number"] for r in rows}):
            group = [r for r in rows if r["provider"] == provider and r["prompt_number"] == number]
            if not group:
                continue
            passed = sum(r["passed"] for r in group)
            out.append(
                f"| {provider} | {number} | {_cell(PROMPTS[number])} | {passed}/{len(group)} | "
                f"{_fmt(_median([r['total_seconds'] for r in group]))} | "
                f"{_fmt(_median([r['model_seconds'] for r in group]))} | "
                f"{_fmt(_median([r['tool_seconds'] for r in group]))} |"
            )
    out += [
        "",
        "## Detail",
        "",
        "| Provider | Run | # | Correct | Tool calls | Total s | Model s | Tool s | 1st token s | Notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['provider']} | {r['run']} | {r['prompt_number']} | {'yes' if r['passed'] else 'NO'} | "
            f"{_cell(_calls_text(r))} | {_fmt(r['total_seconds'])} | {_fmt(r['model_seconds'])} | "
            f"{_fmt(r['tool_seconds'])} | {_fmt(r['first_token_seconds'])} | {_cell(_notes(r))} |"
        )
    out += ["", "## Replies", ""]
    for r in rows:
        reply = r["reply"] if len(r["reply"]) <= 600 else r["reply"][:600] + " […]"
        out += [f"**{r['provider']}, run {r['run']}, prompt {r['prompt_number']}** ({r['prompt']})", "",
                "> " + (reply.replace("\n", "\n> ") or f"(no reply; {r['error']})"), ""]
    out += ["## Analysis", "", "_To be written after reading this run. Numbers above are measurements; "
            "interpretation goes here, with the sample size in mind._", ""]
    return "\n".join(out)


def write_results(path: Path, text: str) -> None:
    path = Path(path)
    if path.exists():
        raise SystemExit(f"{path} already exists; delete it or pass --out to write elsewhere")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--providers", default="claude,matilda")
    parser.add_argument("--prompts", default="1-3", help="e.g. 1-3 or 1,3")
    parser.add_argument("--repeat", type=int, default=1, help="fresh runs per provider")
    parser.add_argument("--out", default=str(ROOT / "comparison" / "results.md"))
    args = parser.parse_args()

    providers = [p.strip().lower() for p in args.providers.split(",")]
    prompts = parse_prompts(args.prompts)
    if Path(args.out).exists():
        raise SystemExit(f"{args.out} already exists; delete it or pass --out to write elsewhere")

    try:
        rows = run_all(providers, prompts, args.repeat)
    except ProviderConfigError as error:
        raise SystemExit(f"error: {error}")

    raw = ROOT / "logs" / f"comparison-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    raw.parent.mkdir(exist_ok=True)
    raw.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    write_results(
        Path(args.out),
        render_markdown(rows, args.repeat, providers, DEFAULT_MODEL, sys.version.split()[0]),
    )
    failed = [r for r in rows if not r["passed"]]
    print(f"Wrote {args.out} and {raw}")
    print(f"{len(rows) - len(failed)}/{len(rows)} checks passed")
    for r in failed:
        print(f"  FAIL {r['provider']} run {r['run']} prompt {r['prompt_number']}: {r['detail']}")


if __name__ == "__main__":
    main()

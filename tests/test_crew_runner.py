import json

import pytest

from crew import runner
from providers.base import Provider, ProviderError, TurnResult

BRIEF = "# Brief\nPurpose: explain X.\n\n## Research questions\n1. When did X launch?"
BRIEF_NO_RESEARCH = "# Brief\nPurpose: explain X.\n\n## Research questions\nResearch questions: none"
RESEARCH = "1. X launched in 2024. Source: https://example.com/x"
DRAFT = "# X\n\nX launched in 2024 ([source](https://example.com/x)). It is very good indeed."
APPROVED = json.dumps({"verdict": "approved", "edits": [], "flags": []})


class Fake(Provider):
    """Answers by role (found in the system prompt); an Exception is raised."""

    def __init__(self, name, answers):
        self.name = name
        self.answers = answers
        self.calls = []
        self.history_resets = 0

    def replace_history(self, turns):
        assert turns == []
        self.history_resets += 1

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        role = next(r for r in ("Madhi", "Oli", "Thooya", "Kural") if f"You are {r}" in system_prompt)
        self.calls.append((role, user_text, tool_definitions))
        answer = self.answers[role]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, tuple):
            return TurnResult(text=answer[0], server_tool_calls=list(answer[1]))
        return TurnResult(text=answer)


def crew(tmp_path, claude_answers=None, matilda_answers=None, matilda=True, task="Write about X"):
    claude = Fake("claude", {"Madhi": BRIEF, "Kural": APPROVED, "Thooya": DRAFT, **(claude_answers or {})})
    providers = {"claude": claude}
    if matilda:
        providers["matilda"] = Fake("matilda", {"Oli": RESEARCH, "Thooya": DRAFT, **(matilda_answers or {})})
    run_dir = runner.prepare_run(task, tmp_path)
    return runner.run_document_crew(task, providers, run_dir), run_dir, providers


def test_happy_path_writes_every_file_and_ships_the_draft(tmp_path):
    run, run_dir, providers = crew(tmp_path)
    assert run["status"] == "done" and not run["unresearched"]
    assert sorted(p.name for p in run_dir.iterdir()) == [
        "01-brief.md", "02-research.md", "03-draft.md", "04-checks.md", "05-review.json", "final.md", "run.json",
    ]
    assert (run_dir / "final.md").read_text() == DRAFT
    assert [(s["role"], s["provider"]) for s in run["stages"]] == [
        ("madhi", "claude"), ("oli", "matilda"), ("thooya", "matilda"), ("kural", "claude"),
    ]


def test_each_stage_starts_with_empty_history_and_no_tools(tmp_path):
    _, _, providers = crew(tmp_path)
    assert providers["claude"].history_resets == 2 and providers["matilda"].history_resets == 2
    assert all(tools == [] for fake in providers.values() for _, _, tools in fake.calls)


def test_stages_pass_the_right_inputs_forward(tmp_path):
    _, _, providers = crew(tmp_path)
    thooya = next(text for role, text, _ in providers["matilda"].calls if role == "Thooya")
    assert BRIEF in thooya and RESEARCH in thooya
    kural = next(text for role, text, _ in providers["claude"].calls if role == "Kural")
    assert DRAFT in kural and RESEARCH in kural


def test_brief_with_no_research_questions_skips_oli(tmp_path):
    run, run_dir, providers = crew(tmp_path, claude_answers={"Madhi": BRIEF_NO_RESEARCH})
    assert [c[0] for c in providers["matilda"].calls] == ["Thooya"]
    assert "No research needed" in (run_dir / "02-research.md").read_text()
    assert not run["unresearched"]


def test_kural_edits_are_applied_when_unique_and_skipped_otherwise(tmp_path):
    review = json.dumps({
        "verdict": "edits",
        "edits": [
            {"find": "very good indeed", "replace": "good", "reason": "tone"},
            {"find": "not in the draft", "replace": "x", "reason": "r"},
            {"find": "X", "replace": "Y", "reason": "matches many times"},
        ],
        "flags": ["needs a second source"],
    })
    run, run_dir, _ = crew(tmp_path, claude_answers={"Kural": review})
    assert "It is good." in (run_dir / "final.md").read_text()
    assert len(run["edits_applied"]) == 1
    assert [e["skipped"] for e in run["edits_skipped"]] == ["not found", "matches 2 times"]
    assert run["flags"] == ["needs a second source"]


def test_review_in_a_code_fence_is_accepted(tmp_path):
    run, _, _ = crew(tmp_path, claude_answers={"Kural": f"```json\n{APPROVED}\n```"})
    assert run["status"] == "done"


def test_unusable_review_ships_the_draft_and_says_so(tmp_path):
    run, run_dir, _ = crew(tmp_path, claude_answers={"Kural": "Looks great to me!"})
    assert run["status"] == "done-unreviewed" and "could not be used" in run["error"]
    assert (run_dir / "final.md").read_text() == DRAFT


def test_matilda_unavailable_thooya_falls_back_and_run_is_unresearched(tmp_path):
    run, run_dir, providers = crew(tmp_path, matilda=False)
    assert run["status"] == "done" and run["unresearched"]
    assert "UNRESEARCHED" in (run_dir / "02-research.md").read_text()
    thooya = next(s for s in run["stages"] if s["role"] == "thooya")
    assert thooya["provider"] == "claude" and thooya["fallback_from"] == "matilda"
    oli = next(s for s in run["stages"] if s["role"] == "oli")
    assert oli["provider"] is None and "not available" in oli["error"]


def test_matilda_erroring_mid_run_falls_back_for_thooya(tmp_path):
    run, _, _ = crew(tmp_path, matilda_answers={"Oli": ProviderError("limit"), "Thooya": ProviderError("limit")})
    assert run["status"] == "done" and run["unresearched"]
    thooya = next(s for s in run["stages"] if s["role"] == "thooya")
    assert thooya["provider"] == "claude" and "limit" in thooya["error"]


@pytest.mark.parametrize("role, stage", [("Madhi", "madhi"), ("Kural", "kural")])
def test_madhi_or_kural_failing_stops_the_run(tmp_path, role, stage):
    run, run_dir, _ = crew(tmp_path, claude_answers={role: ProviderError("down")})
    assert run["status"] == "failed" and run["failed_stage"] == stage
    assert not (run_dir / "final.md").exists()


def test_thooya_failing_on_both_models_stops_the_run(tmp_path):
    run, _, _ = crew(tmp_path, claude_answers={"Thooya": ProviderError("a")}, matilda_answers={"Thooya": ProviderError("b")})
    assert run["status"] == "failed" and run["failed_stage"] == "thooya"


def test_scripted_findings_reach_kural(tmp_path):
    bad = "# X\n\n#### Deep\n\nSales rose 40% last year."
    _, run_dir, providers = crew(tmp_path, matilda_answers={"Thooya": bad})
    kural = next(text for role, text, _ in providers["claude"].calls if role == "Kural")
    assert "heading level jumps" in kural and "unsourced claim" in kural
    assert "heading level jumps" in (run_dir / "04-checks.md").read_text()


def test_run_folders_never_collide_and_stay_inside_the_root(tmp_path):
    a = runner.prepare_run("Write about X", tmp_path)
    b = runner.prepare_run("Write about X", tmp_path)
    assert a != b and a.parent == b.parent == tmp_path


def test_apply_edits_rejects_an_empty_find():
    text, applied, skipped = runner.apply_edits("abc", [{"find": "", "replace": "x", "reason": ""}])
    assert text == "abc" and applied == [] and skipped[0]["skipped"] == "not found"


def test_role_prompts_load_without_front_matter():
    for role in ("madhi", "oli", "thooya", "kural"):
        prompt = runner.load_role_prompt(role)
        assert prompt.startswith("You are") and "---" not in prompt.splitlines()[0]


def test_roster_names_match_the_role_files():
    roster = runner.load_roster()
    assert set(roster) == {"madhi", "oli", "thooya", "kural"}
    assert roster["thooya"]["reliability"] == "low" and roster["thooya"]["fallback"] == "claude"


# --- Oli's search cap: measured and flagged, since it cannot be enforced ----

def test_oli_with_sources_and_searches_has_no_warnings(tmp_path):
    run, _, _ = crew(tmp_path, matilda_answers={"Oli": (RESEARCH, ["web_search"] * 3)})
    assert run["warnings"] == []
    assert next(s for s in run["stages"] if s["role"] == "oli")["server_tool_calls"] == 3


def test_oli_over_the_cap_is_flagged(tmp_path):
    run, _, _ = crew(tmp_path, matilda_answers={"Oli": (RESEARCH, ["web_search"] * 7)})
    assert run["warnings"] == ["Oli made 7 tool calls; the cap is 5"]


def test_oli_with_no_searches_and_no_sources_is_marked_unsourced(tmp_path):
    run, run_dir, providers = crew(tmp_path, matilda_answers={"Oli": "X launched in 2024, I believe."})
    assert any("from memory" in w for w in run["warnings"])
    notes = (run_dir / "02-research.md").read_text()
    assert notes.startswith("NOTE: no web search was detected")
    thooya = next(text for role, text, _ in providers["matilda"].calls if role == "Thooya")
    assert "treat every finding below as unsourced" in thooya


def test_oli_with_sources_but_no_detected_searches_is_not_accused(tmp_path):
    # the events may not report server-side search; URLs in the notes are evidence enough
    run, _, _ = crew(tmp_path, matilda_answers={"Oli": RESEARCH})
    assert run["warnings"] == []

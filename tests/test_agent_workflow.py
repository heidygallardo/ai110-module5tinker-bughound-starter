from bughound_agent import BugHoundAgent
from llm_client import MockClient


class BlastRadiusMockClient:
    """
    Offline MockClient-style stub (same `complete(system_prompt, user_prompt)`
    shape as llm_client.MockClient) used to exercise the blast-radius guardrail.

    - For the analyzer prompt it returns valid JSON with a single Low-severity
      issue, so the score stays high before any structural penalties.
    - For the fixer prompt it returns a large rewrite of the file, which the
      blast-radius guardrail should flag as too big to auto-apply.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return '[{"type": "Code Quality", "severity": "Low", "msg": "print used"}]'
        # A sweeping rewrite (still keeps a return), far larger than one Low issue
        # justifies -> should trip the blast-radius budget.
        return (
            "import logging\n"
            "\n"
            "logger = logging.getLogger(__name__)\n"
            "\n"
            "def process(items):\n"
            "    doubled = [x * 2 for x in items]\n"
            "    grand_total = sum(doubled)\n"
            "    logger.info(\"total=%s\", grand_total)\n"
            "    return grand_total\n"
        )


def test_blast_radius_guardrail_blocks_autofix_on_large_rewrite():
    # A modestly sized snippet with only a Low-severity issue...
    code = (
        "def process(items):\n"
        "    results = []\n"
        "    for item in items:\n"
        "        value = item * 2\n"
        "        results.append(value)\n"
        "    total = sum(results)\n"
        "    print(total)\n"
        "    return total\n"
    )

    agent = BugHoundAgent(client=BlastRadiusMockClient())
    result = agent.run(code)

    risk = result["risk"]
    # The decision under test: the guardrail must refuse to auto-apply.
    assert risk["should_autofix"] is False
    # And it should be *because* the rewrite was too large (blast-radius reason).
    assert any(
        "rewrote" in reason or "blast-radius" in reason for reason in risk["reasons"]
    )
    # The agent should route to human review rather than auto-applying.
    assert any(
        entry["step"] == "REFLECT" and "not safe" in entry["message"].lower()
        for entry in result["logs"]
    )


def test_workflow_runs_in_offline_mode_and_returns_shape():
    agent = BugHoundAgent(client=None)  # heuristic-only
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert isinstance(result, dict)
    assert "issues" in result
    assert "fixed_code" in result
    assert "risk" in result
    assert "logs" in result

    assert isinstance(result["issues"], list)
    assert isinstance(result["fixed_code"], str)
    assert isinstance(result["risk"], dict)
    assert isinstance(result["logs"], list)
    assert len(result["logs"]) > 0


def test_offline_mode_detects_print_issue():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])


def test_offline_mode_proposes_logging_fix_for_print():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    fixed = result["fixed_code"]
    assert "logging" in fixed
    assert "logging.info(" in fixed


def test_mock_client_forces_llm_fallback_to_heuristics_for_analysis():
    # MockClient returns non-JSON for analyzer prompts, so agent should fall back.
    agent = BugHoundAgent(client=MockClient())
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    # Ensure we logged the fallback path
    assert any("Falling back to heuristics" in entry.get("message", "") for entry in result["logs"])

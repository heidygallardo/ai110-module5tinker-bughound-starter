from reliability.risk_assessor import assess_risk


def test_no_fix_is_high_risk():
    risk = assess_risk(
        original_code="print('hi')\n",
        fixed_code="",
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "print"}],
    )
    assert risk["level"] == "high"
    assert risk["should_autofix"] is False
    assert risk["score"] == 0


def test_low_risk_when_minimal_change_and_low_severity():
    original = "import logging\n\ndef add(a, b):\n    return a + b\n"
    fixed = "import logging\n\ndef add(a, b):\n    return a + b\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "minor"}],
    )
    assert risk["level"] in ("low", "medium")  # depends on scoring rules
    assert 0 <= risk["score"] <= 100


def test_high_severity_issue_drives_score_down():
    original = "def f():\n    try:\n        return 1\n    except:\n        return 0\n"
    fixed = "def f():\n    try:\n        return 1\n    except Exception as e:\n        return 0\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Reliability", "severity": "High", "msg": "bare except"}],
    )
    assert risk["score"] <= 60
    assert risk["level"] in ("medium", "high")


def test_blast_radius_vetoes_autofix_on_short_snippet():
    # A small in-budget change (one line, single Low issue -> 30% churn budget)
    # keeps the score high, but the snippet is under the 8-line floor, so the
    # blast-radius guardrail must still veto auto-apply.
    original = (
        "def f(x):\n"
        "    y = x + 1\n"
        "    z = y * 2\n"
        "    result = z - 1\n"
        "    print(result)\n"
        "    return result\n"
    )
    fixed = (
        "def f(x):\n"
        "    y = x + 1\n"
        "    z = y * 2\n"
        "    result = z - 1\n"
        "    print(result)  # tidy\n"
        "    return result\n"
    )
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[{"type": "Code Quality", "severity": "Low", "msg": "print"}],
    )

    assert risk["score"] >= 90  # clears the auto-fix score gate...
    assert risk["should_autofix"] is False  # ...but the guardrail still vetoes
    assert any("blast-radius" in reason for reason in risk["reasons"])


def test_missing_return_is_penalized():
    original = "def f(x):\n    return x + 1\n"
    fixed = "def f(x):\n    x + 1\n"
    risk = assess_risk(
        original_code=original,
        fixed_code=fixed,
        issues=[],
    )
    assert risk["score"] < 100
    assert any("Return" in r or "return" in r for r in risk["reasons"])

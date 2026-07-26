import difflib
from typing import Dict, List


def _change_ratio(original: str, fixed: str) -> float:
    """Fraction of the file that changed: 0.0 (identical) .. 1.0 (total rewrite)."""
    original_lines = original.splitlines()
    fixed_lines = fixed.splitlines()
    if not original_lines:
        return 1.0 if fixed_lines else 0.0
    ratio = difflib.SequenceMatcher(a=original_lines, b=fixed_lines).ratio()
    return 1.0 - ratio


def assess_risk(
    original_code: str,
    fixed_code: str,
    issues: List[Dict[str, str]],
) -> Dict[str, object]:
    """
    Simple, explicit risk assessment used as a guardrail layer.

    Returns a dict with:
    - score: int from 0 to 100
    - level: "low" | "medium" | "high"
    - reasons: list of strings explaining deductions
    - should_autofix: bool
    """

    reasons: List[str] = []
    score = 100

    if not fixed_code.strip():
        return {
            "score": 0,
            "level": "high",
            "reasons": ["No fix was produced."],
            "should_autofix": False,
        }

    original_lines = original_code.strip().splitlines()

    # ----------------------------
    # Issue severity based risk
    # ----------------------------
    for issue in issues:
        severity = str(issue.get("severity", "")).lower()

        if severity == "high":
            score -= 40
            reasons.append("High severity issue detected.")
        elif severity == "medium":
            score -= 20
            reasons.append("Medium severity issue detected.")
        elif severity == "low":
            score -= 5
            reasons.append("Low severity issue detected.")

    # ----------------------------
    # Structural change checks
    # ----------------------------
    # ----------------------------
    # Blast-radius guardrail
    # ----------------------------
    # A fix should touch only as much of the file as the issues justify.
    # Few/minor issues => small allowed change; many => more leeway (capped).
    # Very short snippets have noisy diff ratios, so they never auto-apply.
    churn = _change_ratio(original_code, fixed_code)
    max_churn = min(0.6, 0.15 + 0.15 * len(issues))
    too_small_to_trust = len(original_lines) < 8
    blast_radius_ok = churn <= max_churn and not too_small_to_trust

    if churn > max_churn:
        score -= 30
        reasons.append(
            f"Fix rewrote {churn:.0%} of the file (budget {max_churn:.0%}); "
            "too large to auto-apply."
        )
    if too_small_to_trust:
        reasons.append(
            "Snippet is too short to assess change size reliably; recommend manual review."
        )

    if "return" in original_code and "return" not in fixed_code:
        score -= 30
        reasons.append("Return statements may have been removed.")

    if "except:" in original_code and "except:" not in fixed_code:
        # This is usually good, but still risky.
        score -= 5
        reasons.append("Bare except was modified, verify correctness.")

    # ----------------------------
    # Clamp score
    # ----------------------------
    score = max(0, min(100, score))

    # ----------------------------
    # Risk level
    # ----------------------------
    if score >= 75:
        level = "low"
    elif score >= 40:
        level = "medium"
    else:
        level = "high"

    # ----------------------------
    # Auto-fix policy
    # ----------------------------
    # [part 3] Tightened the auto-fix gate: require score >= 90 (not just level
    # "low", i.e. >= 75), so borderline low-risk fixes are routed to manual review.
    # A fix must clear the score threshold AND stay within its blast-radius
    # budget. The blast-radius check can veto auto-apply even on a high score.
    should_autofix = level == "low" and score >= 90 and blast_radius_ok

    if level == "low" and score >= 90 and not blast_radius_ok:
        reasons.append(
            "Auto-apply vetoed by blast-radius guardrail; recommend manual review."
        )
    elif level == "low" and not should_autofix:
        reasons.append(
            "Score is below the auto-fix threshold (90); recommend manual review."
        )

    if not reasons:
        reasons.append("No significant risks detected.")

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "should_autofix": should_autofix,
    }

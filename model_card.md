# BugHound Mini Model Card (Reflection)

Fill this out after you run BugHound in **both** modes (Heuristic and Gemini).

---

## 1) What is this system?

**Name:** BugHound  
**Purpose:** Analyze a Python snippet, propose a fix, and run reliability checks before suggesting whether the fix should be auto-applied.

**Intended users:** Students learning agentic workflows and AI reliability concepts.

---

## 2) How does it work?

- **Plan:** the agent picks a scan-then-fix pass (fixed workflow).
- **Analyze:** find issues — heuristics scan for `print(`, bare `except:`, and `TODO`; Gemini returns a JSON list of issues.
- **Act:** propose a fix — heuristics do mechanical swaps (e.g. `print` → logging); Gemini rewrites the code.
- **Test:** `assess_risk` scores the fix 0–100 (always heuristic).
- **Reflect:** decide to auto-apply or send to human review.

If enabled, Gemini only does analyze + fix. Planning, JSON fallback, and the risk decision are always heuristic.

---

## 3) Inputs and outputs

**Inputs:**

- Small Python snippets from `sample_code/` (clean code, a `try/except`, mixed issues, `print` spam).
- Shape: single functions, `try/except` blocks, or short scripts.

**Outputs:**

- **Issues:** Code Quality (`print`), Reliability (bare `except:`), Maintainability (`TODO`).
- **Fixes:** logging instead of `print`; specific exceptions instead of bare `except:`.
- **Risk report:** `score`, `level`, `reasons`, and `should_autofix`. Big or too-short fixes get vetoed and sent to review.

---

## 4) Reliability and safety rules

**Rule 1 — Blast-radius guardrail**

- **Checks:** how much of the file changed (churn) vs. how much the issues justify, and vetoes very short snippets.
- **Why it matters:** stops a fix for one small issue from quietly rewriting the whole file.
- **False positive:** blocks a legitimate large refactor that was actually needed.
- **False negative:** a small but behavior-changing edit stays under budget and slips through.

**Rule 2 — Missing `return`**

- **Checks:** the original had `return` but the fixed code doesn't.
- **Why it matters:** dropping a return silently changes what a function outputs.
- **False positive:** flags an intentional refactor that moved or removed the return on purpose.
- **False negative:** misses a return that was kept but now returns the wrong value.

---

## 5) Observed failure modes

**Example 1 — a risky/unnecessary fix**

On `cleanish.py` (a simple `add(a, b)` that logs and returns `a + b`), BugHound
added type hints (e.g. `def add(a: int, b: int) -> int:`) even though the rest of
the file had no type hints. It "fixed" a style choice without checking the
codebase's own convention, changing code that was already fine.

---

## 6) Heuristic vs Gemini comparison

- **Gemini detected more:** it flagged issues beyond the fixed patterns, like
  logic/correctness problems and style concerns, that the heuristics have no rule for.
- **Heuristics caught consistently:** the small, defined set — `print`, bare
  `except:`, and `TODO` — every time, with no surprises.
- **Fixes differed:** heuristics made minimal, mechanical edits; Gemini rewrote
  more of the code.
- **Risk scorer:** it stayed the same in both modes (`assess_risk` is always
  heuristic), so Gemini's larger rewrites tended to score higher risk — which
  matched my intuition that bigger changes deserve more caution.

---

## 7) Human-in-the-loop decision

**Scenario:** the fix changes a large share of the file (big blast radius) —
far more than a small issue justifies. That should go to human review.

- **Trigger:** churn above the allowed budget (`churn > max_churn`), which
  already sets `blast_radius_ok = False`.
- **Where:** in `risk_assessor` (`assess_risk`), so the decision is deterministic
  and both modes share it; the agent workflow just honors `should_autofix`.
- **Message:** "This fix changes too much of the file to apply automatically.
  Please review it before applying."

---

## 8) Improvement idea

**Convention-preserving guardrail.** Before applying, block fixes that introduce
a style the original file doesn't already use — for example, adding type hints
when the file has none. `assess_risk` would compare a few simple features between
the original and the fixed code (e.g. "did the original have type hints?") and, if
the fix adds one that wasn't there, lower the score or veto auto-apply.

This is a small, deterministic check that fits the existing guardrail pattern, and
it directly prevents the Example 1 failure where BugHound added type hints to
`cleanish.py` against the file's own convention.

---
name: verification-before-completion
description: "Use before claiming a mutation is complete or correct. Select fresh evidence proportional to the claim: affected tests for executable code; parser, schema, or smoke checks for configuration; syntax, reference, and diff checks for docs, prompts, skills, or deletions. Run the full project suite only for cross-cutting code changes or final integration."
---

# Verification Before Completion

## Overview

Claiming work is complete without verification is dishonesty, not efficiency.

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## Verification Routing

Choose the smallest complete verification set that proves the exact claim.

| Change type | Required evidence |
|-------------|-------------------|
| Executable behavior | Focused behavior/regression test, then the affected suite |
| Cross-cutting code or final integration | Affected suites plus the full project verification command |
| Runtime/build configuration | Parser or schema validation and a relevant smoke/build check |
| Docs, prompts, skills, or `AGENTS.md` | Syntax/frontmatter validation, reference scan, and diff check |
| File deletion or cleanup | Absence check, dangling-reference scan, and diff check |
| Read-only analysis | Directly inspected source evidence; no mutation test |

Do not manufacture a RED test for a non-code artifact. Do not run an unrelated full
suite merely because a mutation occurred.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. CLASSIFY: What kind of artifact or behavior changed?
2. IDENTIFY: What smallest complete command set proves this exact claim?
3. RUN: Execute every selected command fully (fresh, complete, not truncated)
4. READ: Full output, check exit code, count failures
5. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
6. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Config valid | Parser/schema check and relevant smoke check | Unrelated unit suite |
| Docs/skills valid | Syntax/frontmatter and reference checks | Full application test suite |
| Deletion complete | Path absent and no dangling references | `git status` alone |
| Agent completed | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags - STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting agent success reports
- Stopping a selected verification command early or ignoring part of its output
- Thinking "just this once"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "An unrelated full suite is safer" | Verification must prove the exact claim, not consume time |
| "Part of the selected check is enough" | Run the selected check completely |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Tests:**
```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Regression tests (TDD Red-Green):**
```
✅ Write test → Run (expected fail) → Implement → Run (pass)
❌ "I've written a regression test" (without red-green verification)
```

**Build:**
```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**
```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**
```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Why This Matters

From 24 failure memories:
- your human partner said "I don't believe you" - trust broken
- Undefined functions shipped - would crash
- Missing requirements shipped - incomplete features
- Time wasted on false completion → redirect → rework
- Violates: "Honesty is a core value. If you lie, you'll be replaced."

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Handing off a completed task or crossing an integration boundary

**Rule applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

## The Bottom Line

**No shortcuts for verification.**

Run the command. Read the output. THEN claim the result.

This is non-negotiable.

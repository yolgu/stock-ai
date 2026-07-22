# University Mathematics Practice Skill Implementation Plan

> **For implementation:** Use executing-plans inline in the current session to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install a personal Codex skill that generates an exactly 20-item, source-grounded university mathematics practice set as matched problem and solution Markdown files.

**Architecture:** Keep the trigger, sufficiency gate, generation workflow, and completion conditions in a concise `SKILL.md`. Put the problem-design rubric and paired-file schema in two directly linked reference files, and use agent evaluations before and after the skill to test source fidelity, A12/B7/C1 allocation, mathematical quality, and problem–solution pair integrity.

**Tech Stack:** Markdown skill instructions, YAML skill metadata, Codex skill-creator scripts, Codex collaboration agents for evaluation, bundled Python 3.12, temporary PyYAML installation for validation

---

## File map

- Create: `/Users/jik/.codex/skills/generating-university-math-practice/SKILL.md` — trigger boundary, source gate, core workflow, fixed output contract, and completion rules.
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/references/problem-design-rubric.md` — learning-element blueprint, A/B/C functional calibration, variation rules, and mathematical review.
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/references/paired-output-contract.md` — file naming, frontmatter, problem and solution schemas, and pair-integrity checks.
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/agents/openai.yaml` — discoverable UI name, description, and default invocation prompt.

The skill contains no scripts, assets, README, creation log, or test artifacts. Baseline and forward-evaluation outputs stay in agent messages so they cannot contaminate later runs.

### Task 1: Capture baseline behavior without the new skill

**Files:**
- Read: `/Users/jik/Documents/stock-sub/docs/codex/specs/2026-07-22-university-math-practice-skill-design.md`
- Do not create persistent evaluation files.

- [ ] **Step 1: Dispatch the computational-source baseline**

Start a fresh agent with no inherited conversation and instruct it not to read or use the new skill. Use this exact task:

```text
Create a university-level mathematics practice set from only the source below. Produce exactly 20 problems divided into A 12, B 7, C 1. Return two complete Markdown artifacts named linear-maps-problems.md and linear-maps-solutions.md. Do not write files.

Source: Let V and W be vector spaces over the same field. A map T: V -> W is linear when T(u+v)=T(u)+T(v) and T(av)=aT(v). The kernel is {v in V: T(v)=0}; the image is {T(v): v in V}. A linear map is injective iff its kernel is {0}. For finite-dimensional V, rank(T)+nullity(T)=dim(V). Matrix multiplication represents composition after bases are fixed. Permitted prerequisites: solving finite linear systems, bases, dimension, and matrix multiplication.
```

Review the response against this rubric and record exact failures or rationalizations in working notes: exact allocation, meaningful variation, strategy concealment in B, integrated rather than merely long C, complete one-to-one solution mapping, and no source expansion.

- [ ] **Step 2: Dispatch the proof-source baseline**

Start a second fresh agent with this exact task:

```text
Create a university-level mathematics practice set from only the source below. Produce exactly 20 problems divided into A 12, B 7, C 1. Return two complete Markdown artifacts named sequence-limits-problems.md and sequence-limits-solutions.md. Do not write files.

Source: A real sequence (a_n) converges to L when for every epsilon>0 there exists N such that n>=N implies |a_n-L|<epsilon. Limits are unique. Every convergent sequence is bounded. If a_n<=b_n eventually and both sequences converge, then lim a_n<=lim b_n. If a_n->a and b_n->b, then a_n+b_n->a+b and a_n b_n->ab. Permitted prerequisites: inequalities, absolute values, and quantifiers.
```

Review theorem hypotheses, quantifiers, proof validity, counterexamples, boundary cases, stage calibration, and pair integrity. Capture exact weaknesses rather than summarizing them as “low quality.”

- [ ] **Step 3: Dispatch the insufficient-source baseline**

Start a third fresh agent with this exact task:

```text
Create exactly 20 A/B/C university mathematics practice problems with separate problem and solution Markdown artifacts from Rudin, Principles of Mathematical Analysis, Chapter 4, pages 85-90. I am not providing the page text or a summary. Do not browse or use outside knowledge.
```

The required behavior is to request the actual excerpt, notes, or a sufficient concept list and not fabricate a complete set. Record whether the baseline invents source content, silently uses remembered material, or fills the quota with generic continuity questions.

- [ ] **Step 4: Identify the minimal instruction gaps**

Compare the three raw outputs and list only observed gaps that the new skill must prevent. At minimum inspect:

```text
source boundary
source sufficiency decision
exact A12/B7/C1 allocation
functional rather than length-based stage assignment
controlled mathematical variation rather than cosmetic cloning
one integrated C problem
paired names, matching metadata, and one-to-one IDs
answers, assumptions, proofs, and counterexamples
```

Do not write the skill until at least one concrete baseline failure or inconsistency has been observed. If all three outputs satisfy the rubric, rerun the insufficient-source case with the narrower source “the definition of an even integer” and the same 20-problem demand.

### Task 2: Initialize the personal skill scaffold

**Files:**
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/SKILL.md`
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/agents/openai.yaml`
- Create directory: `/Users/jik/.codex/skills/generating-university-math-practice/references`

- [ ] **Step 1: Confirm the target does not already exist**

Run:

```bash
test ! -e /Users/jik/.codex/skills/generating-university-math-practice
```

Expected: exit code 0. If the path exists, inspect it and stop before overwriting any user-owned content.

- [ ] **Step 2: Run the official initializer with the bundled Python**

Run:

```bash
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/jik/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  generating-university-math-practice \
  --path /Users/jik/.codex/skills \
  --resources references \
  --interface 'display_name=University Math Practice' \
  --interface 'short_description=교재 기반 전공 수학 문제·해설 세트를 만듭니다' \
  --interface 'default_prompt=Use $generating-university-math-practice to create a source-grounded 20-problem A/B/C university mathematics set as matched problem and solution Markdown files.'
```

Expected: the skill directory, `SKILL.md`, `agents/openai.yaml`, and empty `references/` directory are created. No example placeholder files are requested.

- [ ] **Step 3: Inspect the scaffold before editing**

Run:

```bash
find /Users/jik/.codex/skills/generating-university-math-practice -maxdepth 2 -type f -print | sort
sed -n '1,220p' /Users/jik/.codex/skills/generating-university-math-practice/SKILL.md
sed -n '1,120p' /Users/jik/.codex/skills/generating-university-math-practice/agents/openai.yaml
```

Expected: only the required scaffold files exist and every generated placeholder is visible before replacement.

### Task 3: Write the minimal skill that addresses baseline failures

**Files:**
- Modify: `/Users/jik/.codex/skills/generating-university-math-practice/SKILL.md`
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/references/problem-design-rubric.md`
- Create: `/Users/jik/.codex/skills/generating-university-math-practice/references/paired-output-contract.md`
- Modify if needed: `/Users/jik/.codex/skills/generating-university-math-practice/agents/openai.yaml`

- [ ] **Step 1: Replace `SKILL.md` with the core prompt contract**

Write a concise imperative document with this exact frontmatter:

```yaml
---
name: generating-university-math-practice
description: Use when the user asks for a source-grounded university-level mathematics drill set, an A/B/C staged problem set, or a 20-problem practice set from a supplied textbook chapter, lecture note, theorem list, excerpt, or detailed study range.
---
```

The body must include these concrete rules:

```text
Overview:
- Generate one source-grounded university mathematics practice set as a matched problem–solution Markdown pair.
- Treat A12/B7/C1 as a fixed set contract, not proof of learner mastery.

Source gate:
- Use the supplied source and explicitly permitted prerequisites only.
- Require enough detail to recover scope, definitions or procedures, assumptions, notation, and at least 20 meaningfully distinct mathematical actions.
- If source content is missing or too narrow, request the minimum additional excerpt, notes, or concept list and create neither file.
- Never satisfy the quota with remembered textbook content or cosmetic clones.

Required references:
- Read references/problem-design-rubric.md completely before creating the blueprint or problems.
- Read references/paired-output-contract.md completely before choosing names or writing files.

Workflow:
1. Establish the exact source boundary and output location.
2. Build the learning-element map and 20-row blueprint.
3. Pass the source sufficiency and diversity gate.
4. Draft the problem file without answers or method-revealing cues.
5. Solve every problem independently and draft the solution file.
6. Audit mathematics, allocation, diversity, and pair integrity.
7. Write both files only when the pair is complete; otherwise write neither as a completed pair.

Fixed allocation:
- A01-A12, B01-B07, C01 exactly once in each file.
- A = direct use, controlled variation, discrimination, and boundary cases.
- B = representative variation, strategy selection, and source-bounded mixing.
- C = one integrated task; at most three dependent subparts sharing one situation.

Output behavior:
- Use the user’s requested language; otherwise match the user’s language and default to Korean when unclear.
- Use a user-provided safe base name or derive a descriptive kebab-case name.
- Create {base}-problems.md and {base}-solutions.md in the requested directory, or the current working directory when none is supplied.
- Keep answers, hints, strategies, and solutions out of the problem file.

Completion:
- Report both absolute paths and a compact verification summary.
- Do not claim completion if mathematical correctness or pair integrity remains uncertain.
```

Include one compact example showing only the pair naming and ID mapping, not a full generated set.

- [ ] **Step 2: Write the problem-design rubric**

Create `references/problem-design-rubric.md` with these sections and enforceable contents:

```text
Learning-element map fields:
- element ID, source anchor, learner action, prerequisites, permitted result or procedure, representations, boundary cases, and common confusions.

Blueprint fields:
- problem ID, stage, element IDs, mathematical action, transformation axis, expected strategy, answer form, and difficulty rationale.

Allocation:
- A standard 4, A controlled variation 4, A discrimination/boundary 4.
- B representative variation 3, B strategy selection 2, B mixed/cumulative 2.
- C integration 1.

Difficulty axes:
- number of necessary concepts, strategy visibility, essential decisions, representation change, structural distance from a source example, and construction/proof/counterexample demand.
- Solution length and arithmetic volume are not difficulty measures.

Variation rules:
- Cosmetic coefficient, symbol, or order changes alone are duplicates.
- A variants must change at least one meaningful assumption, domain, representation, boundary case, reasoning direction, or adjacent-concept decision.
- B wording and headings must not disclose the method.
- Mixing may use only current elements or prior material included in the supplied source.
- C must integrate the supplied scope and may not be several unrelated questions hidden as subparts.

Mathematical audit:
- Re-solve calculations through an independent route when practical.
- Check definitions, domains, hypotheses, quantifiers, degenerate cases, and boundary cases.
- Verify proof prompts are provable and counterexamples actually falsify the stated claim.
- Replace uncertain or structurally duplicate items rather than weakening the rubric.
```

End with a compact pass/fail checklist the agent can apply to all 20 blueprint rows.

- [ ] **Step 3: Write the paired-output contract**

Create `references/paired-output-contract.md` with exact filename and frontmatter schemas:

```text
{base}-problems.md
{base}-solutions.md
```

Require both files to quote string values and use matching metadata:

```yaml
---
set_id: "{base}"
title: "{set title}"
source_scope: "{exact supplied range}"
problem_count: 20
allocation:
  A: 12
  B: 7
  C: 1
pair_file: "{other paired filename}"
---
```

Define the problem entry as:

```markdown
### A01

[Problem statement only]
```

Define the solution entry as:

```markdown
### A01

- 정답 또는 결론:
- 핵심 전략:
- 풀이:
- 사용한 조건:
- 흔한 오류:
```

For B and C, add progressive hints before the full solution. For C, add an evaluation rubric when more than one proof or construction can be valid. Permit an optional `X00` worked example before the solution entries; exclude it from allocation and pair-ID checks.

Require a transactional write: draft both complete contents first, then create or replace the two intended files. If either path would overwrite an existing file and the user did not request replacement, stop and ask before writing.

Include these mechanical checks, substituting the actual two paths:

```bash
test "$(rg -c '^### A[0-9]{2}$' path/to/problems.md)" -eq 12
test "$(rg -c '^### B[0-9]{2}$' path/to/problems.md)" -eq 7
test "$(rg -c '^### C[0-9]{2}$' path/to/problems.md)" -eq 1
diff <(rg -o '^### [ABC][0-9]{2}$' path/to/problems.md) \
     <(rg -o '^### [ABC][0-9]{2}$' path/to/solutions.md)
```

Also require matching `set_id`, title, source scope, counts, allocation, base name, and opposite `pair_file` values.

- [ ] **Step 4: Verify UI metadata still matches the completed skill**

Ensure `agents/openai.yaml` contains exactly:

```yaml
interface:
  display_name: "University Math Practice"
  short_description: "교재 기반 전공 수학 문제·해설 세트를 만듭니다"
  default_prompt: "Use $generating-university-math-practice to create a source-grounded 20-problem A/B/C university mathematics set as matched problem and solution Markdown files."
```

Do not add icons, colors, dependencies, or policy fields that the user did not request.

### Task 4: Validate the skill structure and instruction quality

**Files:**
- Validate: `/Users/jik/.codex/skills/generating-university-math-practice/SKILL.md`
- Validate: `/Users/jik/.codex/skills/generating-university-math-practice/agents/openai.yaml`
- Validate: `/Users/jik/.codex/skills/generating-university-math-practice/references/problem-design-rubric.md`
- Validate: `/Users/jik/.codex/skills/generating-university-math-practice/references/paired-output-contract.md`

- [ ] **Step 1: Run static artifact checks**

Run:

```bash
rg -n 'TODO|TBD|FIXME|\[TODO' /Users/jik/.codex/skills/generating-university-math-practice
find /Users/jik/.codex/skills/generating-university-math-practice -maxdepth 2 -type f -print | sort
wc -l -w /Users/jik/.codex/skills/generating-university-math-practice/SKILL.md
```

Expected: the placeholder search returns no matches; exactly four intended files exist; `SKILL.md` remains below 500 lines and is concise enough to load as core guidance.

- [ ] **Step 2: Run the official validator with a temporary dependency target**

The default pyenv shims are broken and the bundled Python lacks PyYAML. Do not change the user’s global Python installation. Run:

```bash
skill_yaml_site="$(mktemp -d)"
/Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m pip install --quiet --target "$skill_yaml_site" PyYAML
PYTHONPATH="$skill_yaml_site" \
  /Users/jik/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/jik/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/jik/.codex/skills/generating-university-math-practice
```

Expected: `Skill is valid!`. Leave global Python and site-packages unchanged.

- [ ] **Step 3: Review the prompt contract silently**

Check that the completed skill:

```text
preserves A12/B7/C1 and C exactly one
separates fixed instructions from source input
defines observable completion and stop conditions
does not request hidden chain-of-thought
does not invent citations or outside mathematics
does not force one mathematical task form across all fields
does not duplicate detailed reference content in SKILL.md
links every required reference directly from SKILL.md
```

Revise before forward testing if any item fails.

### Task 5: Forward-test and refactor the skill

**Files:**
- Read all files under `/Users/jik/.codex/skills/generating-university-math-practice/`.
- Modify only the skill file or direct references when an observed failure requires it.

- [ ] **Step 1: Re-run the computational evaluation with the skill**

Start a fresh agent with no inherited conversation. Give it the same linear-map source and output request from Task 1, plus:

```text
Use $generating-university-math-practice at /Users/jik/.codex/skills/generating-university-math-practice. Return the two requested artifacts in your response and do not write files.
```

Verify exact allocation, meaningful variation, B strategy choice, integrated C, correct mathematics, paired names, metadata, and one-to-one IDs.

- [ ] **Step 2: Re-run the proof evaluation with the skill**

Start a second fresh agent with the same sequence-limit source and output request from Task 1 plus the skill invocation. Verify quantifiers, theorem hypotheses, proof validity, counterexamples, boundary cases, progressive hints, and pair mapping.

- [ ] **Step 3: Re-run the insufficient-source evaluation with the skill**

Start a third fresh agent with the same unavailable Rudin range request plus the skill invocation. It must request actual content and produce neither a fake problem file nor a fake solution file.

- [ ] **Step 4: Refactor only against observed failures**

For each forward-test failure:

```text
1. Quote the failing behavior.
2. Identify the missing or ambiguous instruction.
3. Patch the smallest responsible skill section.
4. Re-run only the affected evaluation in a fresh agent.
5. Stop when the evaluation passes without a new workaround or contradiction.
```

Do not add hypothetical rules that no baseline or forward evaluation needed.

### Task 6: Perform final verification and handoff

**Files:**
- Verify all four files under `/Users/jik/.codex/skills/generating-university-math-practice/`.

- [ ] **Step 1: Re-run structural validation after any refactor**

Repeat the static checks and official validator command from Task 4. Expected: no placeholders, exactly four files, direct references resolve, and `Skill is valid!`.

- [ ] **Step 2: Inspect final contents and metadata together**

Run:

```bash
sed -n '1,260p' /Users/jik/.codex/skills/generating-university-math-practice/SKILL.md
sed -n '1,320p' /Users/jik/.codex/skills/generating-university-math-practice/references/problem-design-rubric.md
sed -n '1,320p' /Users/jik/.codex/skills/generating-university-math-practice/references/paired-output-contract.md
sed -n '1,120p' /Users/jik/.codex/skills/generating-university-math-practice/agents/openai.yaml
```

Expected: the final files agree on naming, allocation, source gate, workflow, and completion criteria without duplicated or contradictory rules.

- [ ] **Step 3: Report the installed artifact and evidence**

Report:

```text
installed skill path
four created files
baseline failures that shaped the minimal instructions
forward-evaluation outcomes
official validator result
the broken pyenv/PyYAML environment note without claiming to repair the user’s Python
```

Do not claim mathematical universality, learner mastery, or an empirically optimal 12:7:1 ratio.

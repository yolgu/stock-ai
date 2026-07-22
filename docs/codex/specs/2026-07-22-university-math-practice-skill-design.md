# University Mathematics Practice Skill Design

## Objective

Create a reusable personal Codex skill that turns a sufficiently detailed
university-level mathematics source range into one source-grounded practice
set. Each set contains exactly 20 problems arranged as A 12, B 7, and C 1,
with the student-facing problems and instructor-facing solutions written as a
matched pair of Markdown files.

The skill is installed at
`/Users/jik/.codex/skills/generating-university-math-practice` and is distinct
from the general-purpose `generate-study-questions` skill. It targets repeated
practice of mathematical definitions, procedures, strategy selection, proof,
counterexample construction, and transfer rather than generic quizzes or
recall questions.

## Evidence and interpretation

- The A/B/C labels are a production and learning interface, not a validated
  universal difficulty scale. The fixed 12:7:1 allocation is a user-selected
  practice-set contract, not evidence that 20 items establish mastery.
- The useful part of the Ssen model is type-based organization and repeated
  practice. Good Books Sinsago describes Ssen B as preserving type
  classification and providing one-to-one similar problems for focused
  repetition: <https://truebook.sinsago.co.kr/book/bookRead.aspx?book_idx=6019&school_div=E&subject=C>.
- Interleaving is not treated as universally superior. A preregistered
  classroom trial reported a delayed-test benefit, while a later year-long
  field experiment reported short-term gains but no average cumulative
  end-of-year effect: <https://eric.ed.gov/?id=EJ1237752> and
  <https://www.nber.org/papers/w31853>.
- Worked examples are kept outside the 20-problem count. A mathematics
  meta-analysis found a medium average benefit, but the design still fades
  guidance as problems require more independent strategy selection:
  <https://eric.ed.gov/?id=EJ1364058>.

These findings justify controlled repetition, limited mixing, and optional
guidance. They do not justify claiming that the fixed allocation is optimal
for every learner or every mathematical field.

## Considered approaches

### One self-contained instruction file

Place the workflow, difficulty rules, output template, and validation rubric in
one `SKILL.md`. This is easy to install but makes the frequently loaded file
long and increases the chance that an agent scans past important validation
rules.

### Core workflow with focused references

Keep trigger boundaries, workflow, and completion conditions in `SKILL.md`.
Move the detailed problem-design rubric and paired-file contract into direct
reference files. This is selected because it keeps the core instructions
compact while preserving explicit and reusable quality criteria.

### Script-enforced generation schema

Add a validator for file names, counts, and identifiers. This can verify
mechanical structure but cannot establish mathematical correctness or
pedagogical distinctness. It adds maintenance cost without addressing the main
risks, so the initial skill will use an explicit review checklist rather than
an executable validator.

## Selected skill structure

```text
generating-university-math-practice/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── references/
    ├── problem-design-rubric.md
    └── paired-output-contract.md
```

`SKILL.md` links directly to both reference files and states when each must be
read. No nested references or auxiliary README files are created.

## Trigger boundary

Use the skill when the user requests a university-level or major-mathematics
drill set, an A/B/C staged set, a 20-problem set, or repeated mathematical
practice grounded in a supplied textbook chapter, lecture note, theorem list,
excerpt, or detailed study range.

Do not use it for generic quizzes, school-level worksheet requests without the
university-mathematics intent, solving an existing problem, explaining a
concept without generating a set, or generating questions from a title or page
number whose actual content is unavailable.

## Input contract

Required input is source material detailed enough to determine all of the
following:

- the learning scope;
- the definitions, theorems, procedures, or representations in scope;
- the assumptions and notation needed to state correct problems; and
- enough distinct learning operations to support 20 non-trivial items.

The user may additionally provide a target learner, desired emphasis,
permitted prerequisites, output directory, and base file name. If the source
does not support 20 meaningfully distinct problems, the skill stops and asks
for a broader excerpt, notes, or a concept list. It does not invent missing
content or fill the quota with cosmetic clones.

## Generation workflow

1. Read the supplied source and establish the exact source boundary.
2. Extract a learning-element map before writing any problem. Each element
   records the mathematical action to practice, prerequisites, permitted
   theorem or procedure, representations, and likely boundary cases.
3. Decide whether the scope can support the fixed allocation without outside
   knowledge or excessive duplication. Stop with a focused request when it
   cannot.
4. Create a 20-row blueprint containing identifier, stage, learning element,
   mathematical action, transformation axis, expected strategy, and
   difficulty rationale.
5. Draft the problem file without answers, solution cues, or stage commentary
   that reveals the intended method.
6. Solve every problem independently and draft the matched solution file.
7. Review source fidelity, mathematical correctness, stage calibration,
   structural diversity, identifier parity, and file-name parity.
8. Write both files only after the complete pair passes review. If one file
   cannot be completed, do not present the pair as complete.

## Fixed 20-problem allocation

| Stage | Count | Learning function |
|---|---:|---|
| A — standard | 4 | Directly exercise the central definition, procedure, or proof component |
| A — controlled variation | 4 | Change one meaningful condition, object, parameter, or representation at a time |
| A — discrimination and boundary | 4 | Distinguish adjacent concepts, special cases, edge cases, or simple reverse directions |
| B — representative variation | 3 | Preserve the main structure while hiding or altering surface cues |
| B — strategy selection | 2 | Require the learner to choose the applicable definition, theorem, construction, or algorithm |
| B — mixed or cumulative | 2 | Mix nearby learning elements or prior material explicitly available in the source |
| C — integration | 1 | Integrate the scope through proof, construction, counterexample, interpretation, or transfer |

If no prior material is supplied, the two mixed B problems discriminate among
nearby elements inside the current source. They must not import unprovided
prerequisites.

C is the most integrative problem, not necessarily the longest or most
computationally tedious. It may contain at most three dependent subparts when
they analyze one shared mathematical situation. Independent questions may not
be disguised as subparts to evade the one-problem constraint.

## Difficulty and variation rules

Stage assignment is based on the combination of:

- number of necessary concepts or results;
- visibility of the intended strategy;
- number of essential logical decisions;
- representation change;
- distance from a representative source example; and
- need to construct an auxiliary object, proof, counterexample, or model.

Solution length and arithmetic volume are not difficulty proxies. A long
routine calculation may remain A, while a short counterexample may be B or C.

Cosmetic changes alone do not create a distinct problem. Across A, repeated
items must vary at least one mathematically meaningful feature such as an
assumption, domain, representation, boundary case, direction of reasoning, or
choice among adjacent concepts. Across B and C, the intended strategy must not
be disclosed by the heading or wording.

## Paired Markdown output contract

The two files share one sanitized `kebab-case` base name unless the user
provides a safe base name:

```text
[set-name]-problems.md
[set-name]-solutions.md
```

For example:

```text
real-analysis-continuity-problems.md
real-analysis-continuity-solutions.md
```

Both files contain matching metadata for set title, source scope, set ID,
problem count, and A/B/C allocation. The base name and `set_id` form the pair
identity.

The problem file contains only learning objectives, permitted shared notation,
general instructions, and problems `A01` through `C01`. It contains no answers,
solution outlines, theorem-selection hints, or difficulty rationales.

The solution file contains exactly one matching entry for every problem ID and
no orphan entries. Each entry includes the answer or conclusion, the key
strategy, a complete derivation or proof, assumptions used, and a targeted
common-error note. B and C entries also provide progressive hints. C includes
an evaluation rubric when multiple valid constructions or proofs are possible.

A worked example may appear before the solution entries when the learner is a
novice or the user requests it. It is labeled as an example, uses a different
identifier, and does not count toward the 20 problems.

## Mathematical and pair-integrity review

Before completion, verify:

- every statement is meaningful under the declared assumptions and notation;
- every answer and proof follows from the supplied source and permitted
  prerequisites;
- theorem hypotheses, domains, quantifiers, degenerate cases, and boundary
  cases are handled explicitly;
- computational answers are recomputed or checked through an independent
  route when practical;
- false statements have valid counterexamples and proof prompts are actually
  provable;
- no problem reveals its answer through wording, metadata, ordering comments,
  or a solution accidentally copied into the problem file;
- all 20 identifiers occur once in each file and map one-to-one;
- titles, set IDs, source scopes, counts, and allocation metadata match; and
- the files have the same base name and the required distinct suffixes.

When correctness remains uncertain, revise or replace the item. Do not label an
unverified item as correct merely to preserve the quota.

## Evaluation plan

Use baseline and forward evaluations on at least these cases:

1. A computational source such as a supplied linear-algebra subsection. Check
   exact count, controlled variation, absence of cosmetic cloning, and paired
   identifiers.
2. A proof-oriented source such as a supplied real-analysis definition and
   theorem set. Check hypothesis handling, proof validity, counterexample
   validity, and C integration.
3. An insufficient input containing only a book title and page range. Check
   that the skill requests actual content instead of inventing questions.
4. A narrow source that cannot sustain 20 distinct items. Check that the skill
   refuses quota-filling duplication and asks to widen the scope.
5. A requested custom base name and output directory. Check safe naming and
   exact problem–solution pair creation.

Baseline runs occur without the new skill. Forward runs use the completed
skill on equivalent fresh prompts. Evaluation compares source fidelity,
mathematical correctness, stage function, diversity, problem–solution
separation, and pair integrity.

## Acceptance criteria

- The skill is discoverable for staged university-mathematics practice and
  does not replace the generic study-question skill.
- A sufficient source produces exactly two Markdown files with the required
  paired names.
- The problem file has exactly A 12, B 7, and C 1; the solution file maps to all
  20 identifiers exactly once.
- The set is generated from a learning-element blueprint rather than direct
  quota filling.
- Difficulty labels follow cognitive function rather than length or visual
  complexity.
- Insufficient or overly narrow sources produce a focused input request and no
  fabricated complete set.
- Independent baseline and forward evaluations show that the skill improves
  structural compliance and avoids the identified failure modes.
- Skill metadata and directory structure pass the official skill validator.

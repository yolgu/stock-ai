---
name: using-superpowers
description: Use when starting any conversation or repository task, before choosing project skills or answering implementation requests.
---

# Using Project Skills

## First Line Contract

Every user-facing response must begin with exactly:

```text
Using: using-superpowers
```

If the line is missing, stop the answer and retry internally before continuing.

## Rule

Before responding or acting, check whether a project skill applies. If a skill applies, read it before doing the work.

## Recall Loop

Long conversations make the first instruction easy to forget. Treat this skill as the recurring 복기 point for the whole repository.

- At the start of every response, re-read the nearest `AGENTS.md` first section mentally: GLOBAL SKILL GATE.
- On resume, context compaction, interruption, or a new user message after long work, restart from this skill route before acting.
- Before switching between planning, implementation, testing, review, and final reporting, confirm the applicable route again.
- If you catch yourself about to answer without the required first line, stop and restart the response.
- This rule is active even for small questions, status updates, and final summaries.

## Priority

1. User instructions
2. Nearest `AGENTS.md`
3. Project skills
4. General assistant behavior

## Skill Route

### Planning And Workflow

- `brainstorming`: app design, feature design, behavior changes, UI exploration
- `writing-plans`: multi-step implementation plans
- `executing-plans`: executing an approved written plan
- `rules-governance`: any repository code, config, docs, or skill change
- `test-driven-development`: feature, bugfix, refactor, or behavior change
- `verification-before-completion`: before claiming complete, fixed, passing, or ready
- `systematic-debugging`: bug, failing test, unexpected behavior, flaky behavior
- `git-collaboration`: staging, committing, pushing, pulling, branching, PR prep
- `using-git-worktrees`: isolated feature work or plan execution when the repo supports worktrees

### Neutralino Desktop App

- Use `react-desktop-ui-rules` for renderer UI, hooks, and accessibility.
- Use `technical-research-and-comparison` when changing Neutralino runtime, extension, packaging, or native integration decisions.
- Use `rules-governance` and `test-driven-development` for Neutralino extension contracts, KIS data boundaries, and desktop runtime behavior.

### React Renderer

- `react-desktop-ui-rules`: React/TypeScript renderer UI, hooks, component state, keyboard access, desktop layout, accessibility

### Product Domain

- Use a domain-specific skill only when the user explicitly asks for that product domain or the repository code already establishes it.
- Do not infer a product domain from this base desktop-app setup.

### Review And Support

- `requesting-code-review`: completing implementation work and needing review before merge or handoff
- `receiving-code-review`: evaluating review feedback
- `refactoring-safely`: preserving behavior while improving structure
- `technical-research-and-comparison`: choosing libraries, patterns, or external approaches
- `writing-skills`: creating or editing skills

## Defaults

- Prefer `pnpm` for future Neutralino + React scaffolding unless the repo already chooses another package manager.
- Keep renderer/domain/native-shell boundaries explicit.
- Do not ask the user for facts that can be discovered from the repo or official documentation.
- Preserve high-density project instructions in `AGENTS.md`; do not compress them into a short summary.

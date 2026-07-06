# Neutralino React Desktop App Guidelines

## GLOBAL SKILL GATE (HARD)

Before ANY response (including greetings), invoke skill `using-superpowers`.
Then print first line exactly: `Using: using-superpowers`.
If this line is missing, do not answer and retry internally.

Long conversation recall and phase re-checks are owned by `using-superpowers`.

## 자연스러운 한국어 존댓말 사용 (HARD)

- 반드시 사용자를 존중하며, 사용자에게 말을 할때는 자연스러운 한국어 존댓말로 할 것.

## When Propose plan (HARD)

- MUST use form of `writing-plans` skill to propose user a plan.

## Scope

This repository keeps its project-scoped Codex configuration in:

- `.codex/config.toml`
- `.codex/skills/`
- `.codex/agents/`

## Project Overview

- Project type: Neutralino + React + TypeScript desktop app.
- Renderer boundary: React/TypeScript UI under `src/`.
- Desktop shell boundary: Neutralino config, extension registration, and Node extension processes under `neutralino.config.json` and `extensions/`.
- KIS native boundary: KIS credentials, REST calls, WebSocket streams, token handling, and stream parsing live only in the Neutralino extension process.
- Domain boundary: product behavior and state rules belong in domain modules, application services, or hooks; never in presentation-only components.
- Testing direction: Vitest for TypeScript behavior, Neutralino extension contract tests for app-extension events, renderer tests for UI flows, and targeted browser/manual smoke checks for desktop behavior.

## Skill Routing Expectations

- Start every task by reading `using-superpowers`.
- Use `brainstorming` before creative app design, feature design, UI exploration, or behavior changes.
- Use `writing-plans` before proposing multi-step work.
- Use `executing-plans` when implementing an approved written plan.
- Use `rules-governance` for repository code, config, docs, or skill changes.
- Use `test-driven-development` for feature, bugfix, refactor, or behavior changes.
- Use `systematic-debugging` for bugs, failing tests, unexpected behavior, or flakes.
- Use `verification-before-completion` before claiming work is complete, fixed, passing, or ready.
- Use `react-desktop-ui-rules` for React/TypeScript renderer UI, hooks, component state, keyboard access, desktop layout, and accessibility.

## Runtime And Security Rules

- `pnpm dev:neutralino` is the desktop app execution path.
- `pnpm dev:vite` is renderer-only and must not be treated as a live desktop runtime.
- KIS secrets entered through the UI are ephemeral renderer form state only; durable storage is allowed only in the Neutralino extension JSON settings file or `.env.kis.local`.
- The renderer must never read KIS secrets from JSON, `.env`, browser globals, local storage, native environment APIs, URL parameters, logs, or UI text.
- App-extension messages must use typed event contracts, currently `kis:request`, `kis:response`, and `kis:stream-event`.
- Do not add broad local filesystem, shell, or environment access to renderer code.

## Coding Style & Naming Conventions

- TypeScript/React: 2-space indentation.
- React naming: `PascalCase` for components, `camelCase` for hooks and utilities.
- Node extension files use CommonJS only where required by the Neutralino extension launcher.
- Keep module boundaries explicit: renderer component -> hook/application service -> domain module -> adapter/Neutralino extension boundary.
- Follow existing file naming patterns and existing directory structure.
- Prefer `pnpm` for future app scaffold unless the repo already chooses another package manager.
- No dedicated lint script is guaranteed; rely on project-specific TypeScript checks, tests, extension syntax checks, and existing verification commands.

## Maximize context understanding

Be THOROUGH when gathering information. Make sure you have the FULL picture before replying. Use additional tool calls or clarifying questions as needed.
TRACE every symbol back to its definitions and usages so you fully understand it.
Look past the first seemingly relevant result. EXPLORE alternative implementations, edge cases, and varied search terms until you have COMPREHENSIVE coverage of the topic.

Semantic search is your MAIN exploration tool.

- CRITICAL: Start with a broad, high-level query that captures overall intent, not low-level terms.
- Break multi-part questions into focused sub-queries.
- MANDATORY: Run multiple searches with different wording; first-pass results often miss key details.
- Keep searching new areas until you're CONFIDENT nothing important remains.
- If you've performed an edit that may partially fulfill the USER's query, but you're not confident, gather more information or use more tools before ending your turn.
- Bias towards not asking the user for help if you can find the answer yourself.

## Output Purity

- All deliverables, including code, comments, documents, and text, must stand on their own without traces of the instructions behind them.
- Do not state or imply in the deliverable that you followed a particular instruction.
- Let the quality of the deliverable be the only evidence that the instruction was followed.
- Treat compliance notes, meta commentary, and self-referential comments as noise, and do not include them.
- Follow instructions quietly. Do not add notes, explanations, or any other text about having followed them.

## Code Style

All code must follow OOP, DDD, Clean Code, SSOT, explicit return type annotation, human-readable and Effective Software Design principles. Prioritize domain model clarity, separation of responsibilities, readability, and maintainability over language/framework-specific idioms. No over-engineering. Only the necessary abstractions. Avoid writing overly defensive code. Self-Documenting Code, Narrative Style.

## Code Style Specific

### 1. Inspect Before Coding

Before writing or changing code, first identify:

- The current architecture and layer boundaries:
  - Domain / Application / Infrastructure / Presentation
  - Renderer / Desktop Shell / Adapter
  - Entity / Value Object / Domain Service / Repository / Use Case / Adapter
- The existing naming, file layout, dependency direction, and test style.
- The Single Source of Truth for the target behavior:
  - domain rule
  - schema
  - type
  - config
  - constant
  - test fixture
  - API contract
- Whether the requested change belongs in:
  - a domain model
  - an application use case
  - an infrastructure adapter
  - a presentation/component layer
  - a Neutralino extension boundary
  - a shared utility
- Whether an existing abstraction already solves the problem.

Do not introduce a new abstraction before checking whether the current codebase already has the right concept.

### 2. Reasoning Discipline

For non-trivial changes, think through the design before coding.

Do not expose long chain-of-thought. Instead, provide only a concise implementation rationale when useful:

- What layer is being changed.
- Which domain concept is affected.
- Why the chosen design is simpler than the alternatives.
- What trade-off is being accepted.
- How the result will be verified.

For simple changes, code directly and avoid unnecessary explanation.

### 3. Priority Order

When style principles conflict, apply this priority order:

1. Correct domain behavior.
2. Clear domain model.
3. Single Source of Truth.
4. Separation of responsibilities.
5. Readability and maintainability.
6. Explicit types and contracts.
7. Minimal necessary abstraction.
8. Framework or language idioms.

Do not prefer framework-specific convenience if it weakens domain clarity or mixes responsibilities.

### 4. Domain-Driven Design Rules

Model business concepts explicitly.

- Use domain names from the business language, not technical shortcuts.
- Put business rules in the domain layer, not in components, serializers, adapters, or infrastructure code.
- Keep entities responsible for their own invariants.
- Use value objects for meaningful validated values, not primitive strings/numbers when the value has domain meaning.
- Use domain services only when behavior does not naturally belong to a single entity or value object.
- Keep repositories as persistence boundaries, not places for business decisions.
- Keep use cases/application services focused on orchestration.

Avoid anemic domain models when the behavior clearly belongs to the domain.

### 5. OOP Rules

Use OOP to express responsibilities, not to create ceremony.

- Each class should have one clear reason to change.
- Prefer small cohesive objects over large procedural service classes.
- Keep public APIs minimal.
- Hide internal state and expose behavior.
- Prefer composition over inheritance.
- Use inheritance only when there is a stable, true subtype relationship.
- Do not create abstract classes, interfaces, factories, or base classes unless there are at least two real implementations or a clear architectural boundary.

No over-engineering. Add abstractions only when they remove duplication, protect a boundary, or clarify a domain concept.

### 6. Clean Code Rules

Write code that reads as a clear narrative.

- Use intention-revealing names.
- Prefer domain-specific names over generic names like `data`, `item`, `manager`, `helper`, `processor`, or `handler`.
- Keep functions short and focused on one decision or action.
- Prefer early returns when they reduce nesting.
- Avoid hidden side effects.
- Avoid boolean flags that change function behavior; split the function or introduce a clearer concept.
- Avoid duplicated business rules.
- Avoid large parameter lists; group related values into a type or value object.
- Keep comments for why, trade-offs, and external constraints. Do not comment what the code already says.

Code should be self-documenting first. Comments are secondary.

### 7. Single Source of Truth

Do not duplicate facts, rules, constants, schemas, or mappings.

Before adding a new rule or constant, search for the existing source.

Examples of SSOT violations:

- Repeating the same validation rule in multiple layers.
- Recreating event response shapes instead of using shared types.
- Copying string literals for domain states, event names, command names, permission names, or config keys.
- Maintaining separate domain and persistence mappings without a clear boundary.
- Reimplementing behavior already covered by a domain method.

When duplication is found, centralize the concept in the most appropriate layer.

### 8. Explicit Types and Return Values

Use explicit return type annotations for all public functions, methods, exported functions, hooks, use cases, Neutralino adapter wrappers, and domain methods.

Prefer precise types over broad types.

- Avoid `any`, `unknown`, raw dictionaries, or untyped objects unless required at an external boundary.
- Convert external input into validated domain types as early as possible.
- Return domain objects, DTOs, or explicit result types instead of loosely shaped objects.
- Make nullable or optional values explicit.
- Do not return `null` or `undefined` when a meaningful result type, option type, or domain exception is clearer.

Function signatures should communicate behavior without requiring the reader to inspect the implementation.

### 9. Boundary and Dependency Rules

Keep dependencies pointing inward.

- Domain must not depend on infrastructure, framework, database, HTTP, queue, cache, UI code, or Neutralino APIs.
- Application/use-case layer may depend on domain abstractions.
- Infrastructure implements external concerns.
- Presentation/components should translate user interaction and render state only.
- Neutralino extension code should stay near the native boundary and expose typed app-extension events.
- Framework-specific code should stay near the edge of the system.

Do not leak browser event objects, Neutralino API objects, OS records, storage records, or framework decorators into the domain model.

### 10. Error Handling Rules

Avoid overly defensive code.

Defensive checks are required at external boundaries:

- user input
- app-extension input
- database or storage records
- file system data
- network responses
- third-party service responses
- environment variables
- OS permission responses

Inside trusted domain/application code, prefer clear invariants and explicit types over repeated null checks.

Do not silently swallow errors. Either:

- handle the error with a domain-specific decision,
- convert it at the boundary,
- or let it fail clearly.

### 11. Effective Software Design

Prefer simple, direct, maintainable designs.

Before introducing a pattern, ask:

- Does this pattern clarify a real domain concept?
- Does it reduce meaningful duplication?
- Does it protect an architectural boundary?
- Does it make future change easier in a likely direction?
- Is there an existing project pattern that already solves this?

Do not add design patterns just to satisfy OOP, DDD, or Clean Architecture terminology.

Use the smallest design that preserves correctness, clarity, and changeability.

### 12. Narrative Style

Code should read in business order.

Prefer this flow:

1. Validate or normalize input.
2. Load required domain objects.
3. Execute domain behavior.
4. Persist state changes.
5. Publish side effects or events.
6. Return an explicit result.

Avoid mixing these steps in one large function.

Use names that describe the story:

- openProject
- saveUserPreference
- syncLocalState
- calculateDisplayStatus
- markTaskAsComplete
- canBeClosed

Avoid vague technical names:

- process
- execute
- handleData
- updateState
- doWork

Generic names are allowed only when the surrounding type already provides clear context, such as `Project.open()`.

### 13. Testing Expectations

When behavior changes, update or add tests.

Prefer tests that verify observable behavior and domain rules.

- Domain rules should be tested at the domain level.
- Non-deterministic state transitions should use controlled providers or explicit test doubles.
- Use cases should be tested through application-level inputs and outputs.
- Renderer behavior should be tested through hooks or components at the lowest useful level.
- Neutralino app-extension contracts should be tested with explicit test doubles.
- Native extension behavior should be tested through deterministic Node contract tests.
- Infrastructure should be tested with integration tests when meaningful.
- Avoid tests that only assert implementation details.
- Add regression tests for bug fixes.
- Keep test names readable and behavior-oriented.

A change is not complete until the relevant tests, type checks, and build checks pass, or until the reason they cannot be run is stated clearly.

### 14. Refactoring Rules

Refactor only as much as needed for the current task.

Allowed refactoring:

- removing duplication directly related to the change
- extracting a value object or method that clarifies the domain rule
- moving misplaced behavior to the correct layer
- renaming unclear concepts
- tightening types around the changed behavior
- isolating Neutralino API calls behind typed adapters

Avoid broad rewrites, speculative abstractions, or unrelated cleanup.

### 15. Final Self-Review Checklist

Before finishing, check:

- Is the domain behavior correct?
- Is the responsibility in the right layer?
- Is there a clear Single Source of Truth?
- Are return types explicit?
- Are names readable and domain-oriented?
- Was unnecessary abstraction avoided?
- Was overly defensive code avoided?
- Are external boundaries validated?
- Are tests updated or the verification gap explained?
- Is the diff smaller and clearer than an alternative implementation?

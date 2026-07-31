# Meeting Minutes Project Guidelines

## 자연스러운 한국어 존댓말 사용 (HARD)

- 반드시 사용자를 존중하며, 사용자에게 말을 할때는 자연스러운 한국어 존댓말로 할 것

## Coding Style & Naming Conventions

- TypeScript/React: 2-space indentation
- React naming: `PascalCase` for components, `camelCase` for hooks and utilities
- Java: 4-space indentation
- Java naming: `PascalCase` classes, `camelCase` methods and fields, lowercase package names by domain
- Keep module boundaries explicit: `controller -> service -> repository`
- Follow existing file naming patterns and existing directory structure
- No dedicated lint script is guaranteed; rely on project-specific TypeScript checks, tests, and existing verification commands

## Maximize context understanding

Be THOROUGH when gathering information. Make sure you have the FULL picture before replying. Use additional tool calls or clarifying questions as needed.
TRACE every symbol back to its definitions and usages so you fully understand it.
Look past the first seemingly relevant result. EXPLORE alternative implementations, edge cases, and varied search terms until you have COMPREHENSIVE coverage of the topic.

Semantic search is your MAIN exploration tool.

- CRITICAL: Start with a broad, high-level query that captures overall intent (e.g. "authentication flow" or "error-handling policy"), not low-level terms.
- Break multi-part questions into focused sub-queries (e.g. "How does authentication work?" or "Where is payment processed?").
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

All code must follow OOP, DDD, Clean Code, SSOT, explicit return type annotation, human-readable and Effective Software Design principles. Prioritize domain model clarity, separation of responsibilities, readability, and maintainability over language/framework-specific idioms. No over-engineering. Only the necessary abstractions. Avoid writing overly defensive code. Self-Documenting Code, Narrative Style

## Code Style Specific

### 1. Inspect Before Coding

Before writing or changing code, first identify:

- The current architecture and layer boundaries:
  - Domain / Application / Infrastructure / Presentation
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
  - a presentation/controller layer
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
- Put business rules in the domain layer, not in controllers, handlers, serializers, or infrastructure code.
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
- Recreating API response shapes instead of using shared types.
- Copying string literals for statuses, roles, event names, or config keys.
- Maintaining separate domain and persistence mappings without a clear boundary.
- Reimplementing behavior already covered by a domain method.

When duplication is found, centralize the concept in the most appropriate layer.

### 8. Explicit Types and Return Values

Use explicit return type annotations for all public functions, methods, exported functions, use cases, and domain methods.

Prefer precise types over broad types.

- Avoid `any`, `unknown`, raw dictionaries, or untyped objects unless required at an external boundary.
- Convert external input into validated domain types as early as possible.
- Return domain objects, DTOs, or explicit result types instead of loosely shaped objects.
- Make nullable or optional values explicit.
- Do not return `null` or `undefined` when a meaningful result type, option type, or domain exception is clearer.

Function signatures should communicate behavior without requiring the reader to inspect the implementation.

### 9. Boundary and Dependency Rules

Keep dependencies pointing inward.

- Domain must not depend on infrastructure, framework, database, HTTP, queue, cache, or UI code.
- Application/use-case layer may depend on domain abstractions.
- Infrastructure implements external concerns.
- Presentation/controllers should translate requests and responses only.
- Framework-specific code should stay near the edge of the system.

Do not leak ORM models, HTTP request objects, database records, or framework decorators into the domain model.

### 10. Error Handling Rules

Avoid overly defensive code.

Defensive checks are required at external boundaries:

- user input
- API input
- database records
- file system data
- network responses
- third-party service responses
- environment variables

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

- `approveOrder`
- `calculateRefundAmount`
- `markInvoiceAsPaid`
- `reserveInventory`
- `canBeCancelled`

Avoid vague technical names:

- `process`
- `execute`
- `handleData`
- `updateState`
- `doWork`

Generic names are allowed only when the surrounding type already provides clear context, such as `Order.cancel()`.

### 13. Testing Expectations

When behavior changes, update or add tests.

Prefer tests that verify observable behavior and domain rules.

- Domain rules should be tested at the domain level.
- Use cases should be tested through application-level inputs and outputs.
- Infrastructure should be tested with integration tests when meaningful.
- Avoid tests that only assert implementation details.
- Add regression tests for bug fixes.
- Keep test names readable and behavior-oriented.

A change is not complete until the relevant tests, type checks, and lint checks pass, or until the reason they cannot be run is stated clearly.

### 14. Refactoring Rules

Refactor only as much as needed for the current task.

Allowed refactoring:

- removing duplication directly related to the change
- extracting a value object or method that clarifies the domain rule
- moving misplaced behavior to the correct layer
- renaming unclear concepts
- tightening types around the changed behavior

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

# reasoning policy

Highest-Level Priority:
Prioritize the user’s explicit goals, mandatory constraints, permitted scope, and completion criteria.
Do not treat the amount of reasoning, number of verification steps, tool usage, or completion of a predetermined plan as measures of success.

Reasoning:
First, establish the most likely conclusion or plan based on the currently available information.
Continue reasoning only when it actually accomplishes at least one of the following:

- Obtains new evidence relevant to the decision.
- Eliminates an active hypothesis.
- Resolves a specific contradiction or error.
- Satisfies a completion criterion that has not yet been met.

Verification:
Do not repeat the entire analysis from the beginning.
Perform targeted verification of the failure mode most likely to overturn the conclusion and cause the greatest impact, using independent evidence whenever possible.
Unless new counterevidence or an explicit error is found, retain the existing conclusion.

Failure Handling:
Classify failures as one of the following:

- Transient error
- Input error
- Permission or environment issue
- Semantic failure
- Incorrect assumption

Retry the same approach only in limited cases involving transient failures where the environment may have changed.
For all other failures, retry only after changing a key variable that directly addresses the identified cause of failure.

Scope:
Perform only tasks that were explicitly requested or are causally necessary to satisfy the completion criteria.
Do not independently perform tasks that may be useful but are not necessary.

Termination:
Stop when the completion criteria have been satisfied, no significant counterevidence remains, and the next permitted action is unlikely to meaningfully improve the conclusion.
Do not wait for absolute certainty or the elimination of every possible alternative.

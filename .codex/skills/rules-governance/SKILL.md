---
name: rules-governance
description: Repository-wide engineering governance. Use first for any task to enforce TDD-first flow, evidence-based completion reporting, and strict layer boundaries.
---

# Rules Governance

## Overview

Apply repository-wide engineering governance.

## Dependency Order

- None

## Team Conventions

- Follow TDD in strict order (RED -> GREEN -> REFACTOR) for every task.
- Prove completion/success claims with verification command output in the same turn.
- Block layer-boundary violations immediately.

## Mandatory Workflow

1. Define the behavior change and verification commands first.
2. Write a failing test first (RED).
3. Implement the minimum change to reach GREEN.
4. Refactor, then run full verification.
5. Report results with command-output evidence.

## Prohibited

- Do not claim completion without verification.
- Do not allow layer violations as "exceptions".

## Embedded Rule Sources (Full Text)

### `code-principles.md`
- Scope (globs): `**/*`
- alwaysApply: `true`

````md
---
description: General code principles — OOP, DDD, DRY, Clean Code, TDD; no blind tests; layer separation; explicit types
globs: "**/*"
alwaysApply: true
---

# Code Principles (General)

## OOP

- **Encapsulation**: Hide internal state; expose only necessary interfaces.
- **Single Responsibility**: One reason to change per class/function.
- **Dependency Inversion**: Depend on abstractions (interfaces, contracts), not concretions.

## DDD

- **Bounded Context**: Clear domain boundaries; avoid one Big Model.
- **Aggregate**: Consistency boundary; load/save as a unit.
- **Ubiquitous Language**: Names in code match domain terms.
- **Domain-first**: Domain logic stays in domain layer; keep infrastructure (DB, HTTP) out.

## DRY

- Extract duplicated logic to shared modules/functions.
- Reference other rules or shared types instead of copying.

## Clean Code

- **Naming**: Clear, searchable; avoid abbreviations unless well-known.
- **Functions**: Small, one level of abstraction; prefer under 20 lines.
- **Nesting**: Prefer shallow (max 2–3 levels); early return / extract.
- **Explicit over clever**: Readable first; no tricks.

## TDD

- Red → Green → Refactor. Write a failing test first, then minimal code to pass, then refine.
- Test behavior and contracts, not implementation details.

## 눈가림 테스트 방지 (No Blind/Meaningless Tests)

- **금지**: `expect(true).toBe(true)`, `expect(1).toBe(1)`, asserts that always pass.
- **금지**: Over-mocking that makes the test never run real logic (테스트가 실제 로직을 검증하지 않음).
- **필수**: 테스트는 **실패할 수 있어야** 함. 요구사항·로직 변경 시 실패로 드러나야 함.
- **필수**: Given–When–Then: 입력·상황을 주고, 동작 후, 기대 결과를 구체적으로 assert.

## Layer 분할

- **경계**: Controller/View → Service/UseCase → Repository/API. 상위는 하위만 호출; 역방향·건너뛰기 금지.
- **책임**: Controller/View — 입력·출력·라우팅. Service — 비즈니스·오케스트레이션. Repository/API — 영속·외부 I/O.
- 도메인 규칙·엔티티는 Service·Domain; View/Controller에 비즈니스 로직 두지 말 것.

## 타입 명시

- 함수·변수·반환값에 **명시적 타입**. `any`, `@ts-ignore`, 암시적 타입 우회 등 최소화.
- 제네릭·API 응답 등 추론이 애매한 곳은 반드시 타입 명시. 컴파일/정적 분석으로 오류 조기 발견.
````

### `general/alwayscheck.md`
- Scope (globs): `-`
- alwaysApply: `false`

````md
---
trigger: always_on
---

always check the skills and workflows.
never override
````

### `general/code-principles.mdc`
- Scope (globs): `**/*`
- alwaysApply: `true`

````md
---
description: General code principles — OOP, DDD, DRY, Clean Code, TDD; no blind tests; layer separation; explicit types
globs: "**/*"
alwaysApply: true
---

# Code Principles (General)

## OOP

- **Encapsulation**: Hide internal state; expose only necessary interfaces.
- **Single Responsibility**: One reason to change per class/function.
- **Dependency Inversion**: Depend on abstractions (interfaces, contracts), not concretions.

## DDD

- **Bounded Context**: Clear domain boundaries; avoid one Big Model.
- **Aggregate**: Consistency boundary; load/save as a unit.
- **Ubiquitous Language**: Names in code match domain terms.
- **Domain-first**: Domain logic stays in domain layer; keep infrastructure (DB, HTTP) out.

## DRY

- Extract duplicated logic to shared modules/functions.
- Reference other rules or shared types instead of copying.

## Clean Code

- **Naming**: Clear, searchable; avoid abbreviations unless well-known.
- **Functions**: Small, one level of abstraction; prefer under 20 lines.
- **Nesting**: Prefer shallow (max 2–3 levels); early return / extract.
- **Explicit over clever**: Readable first; no tricks.

## TDD

- Red → Green → Refactor. Write a failing test first, then minimal code to pass, then refine.
- Test behavior and contracts, not implementation details.

## 눈가림 테스트 방지 (No Blind/Meaningless Tests)

- **금지**: `expect(true).toBe(true)`, `expect(1).toBe(1)`, asserts that always pass.
- **금지**: Over-mocking that makes the test never run real logic (테스트가 실제 로직을 검증하지 않음).
- **필수**: 테스트는 **실패할 수 있어야** 함. 요구사항·로직 변경 시 실패로 드러나야 함.
- **필수**: Given–When–Then: 입력·상황을 주고, 동작 후, 기대 결과를 구체적으로 assert.

## Layer 분할

- **경계**: Controller/View → Service/UseCase → Repository/API. 상위는 하위만 호출; 역방향·건너뛰기 금지.
- **책임**: Controller/View — 입력·출력·라우팅. Service — 비즈니스·오케스트레이션. Repository/API — 영속·외부 I/O.
- 도메인 규칙·엔티티는 Service·Domain; View/Controller에 비즈니스 로직 두지 말 것.

## 타입 명시

- 함수·변수·반환값에 **명시적 타입**. `any`, `@ts-ignore`, 암시적 타입 우회 등 최소화.
- 제네릭·API 응답 등 추론이 애매한 곳은 반드시 타입 명시. 컴파일/정적 분석으로 오류 조기 발견.
````

### `general/continuous-improvement.mdc`
- Scope (globs): `**/*`
- alwaysApply: `false`

````md
---
description: Evidence-driven rule and code improvement — TDD, pattern capture in 3+ files, security/perf regression tests
globs: "**/*"
trigger: always_on
---

## Continuous Improvement (TDD Evidence)

- **Evidence-driven**: Propose improvements backed by failing tests or perf metrics.
- **Pattern capture**: When a pattern appears in 3+ files, add/update rules.
- **Security/perf**: Create tests that prevent regression (headers, query counts).

### Process

1) Detect issue or opportunity with data/tests
2) Write failing tests capturing the gap
3) Implement minimal change → green
4) Communicate summary with impact and risks
````

### `general/cursor_rules.mdc`
- Scope (globs): `rules/**/*.mdc`
- alwaysApply: `true`

````md
---
description: Cursor rule authoring — structure, frontmatter, DO/DON'T examples, file references
globs: rules/**/*.mdc
alwaysApply: true
---

- **Required Rule Structure:**
  ```markdown
  ---
  description: Clear, one-line description of what the rule enforces
  globs: path/to/files/*.ext, other/path/**/*
  alwaysApply: boolean
  ---

  - **Main Points in Bold**
    - Sub-points with details
    - Examples and explanations
  ```

- **File References:**
  - Use `[filename](mdc:path/to/file)` ([filename](mdc:filename)) to reference files
  - Example: [prisma.mdc](mdc:.cursor/rules/prisma.mdc) for rule references
  - Example: [schema.prisma](mdc:prisma/schema.prisma) for code references

- **Code Examples:**
  - Use language-specific code blocks
  ```typescript
  // ✅ DO: Show good examples
  const goodExample = true;

  // ❌ DON'T: Show anti-patterns
  const badExample = false;
  ```

- **Rule Content Guidelines:**
  - Start with high-level overview
  - Include specific, actionable requirements
  - Show examples of correct implementation
  - Reference existing code when possible
  - Keep rules DRY by referencing other rules

- **Rule Maintenance:**
  - Update rules when new patterns emerge
  - Add examples from actual codebase
  - Remove outdated patterns
  - Cross-reference related rules

- **Best Practices:**
  - Use bullet points for clarity
  - Keep descriptions concise
  - Include both DO and DON'T examples
  - Reference actual code over theoretical examples
  - Use consistent formatting across rules
````

### `general/self-improve.mdc`
- Scope (globs): `**/*`
- alwaysApply: `true`

````md
---
description: Continuously improve Cursor rules from code patterns — triggers, analysis, add/modify/deprecate; follow cursor_rules for format
globs: "**/*"
alwaysApply: true
---

- **Rule Improvement Triggers:**
  - New code patterns not covered by existing rules
  - Repeated similar implementations across files
  - Common error patterns that could be prevented
  - New libraries or tools being used consistently
  - Emerging best practices in the codebase

- **Analysis Process:**
  - Compare new code with existing rules
  - Identify patterns that should be standardized
  - Look for references to external documentation
  - Check for consistent error handling patterns
  - Monitor test patterns and coverage

- **Rule Updates:**
  - **Add New Rules When:**
    - A new technology/pattern is used in 3+ files
    - Common bugs could be prevented by a rule
    - Code reviews repeatedly mention the same feedback
    - New security or performance patterns emerge

  - **Modify Existing Rules When:**
    - Better examples exist in the codebase
    - Additional edge cases are discovered
    - Related rules have been updated
    - Implementation details have changed

- **Example Pattern Recognition:**
  ```typescript
  // If you see repeated patterns like:
  const data = await prisma.user.findMany({
    select: { id: true, email: true },
    where: { status: 'ACTIVE' }
  });

  // Consider adding to the relevant rule; follow [cursor_rules.mdc](mdc:rules/general/cursor_rules.mdc) for structure.
  // - Standard select fields, common where conditions, performance patterns
  ```

- **Rule Quality Checks:**
  - Rules should be actionable and specific
  - Examples should come from actual code
  - References should be up to date
  - Patterns should be consistently enforced

- **Continuous Improvement:**
  - Monitor code review comments
  - Track common development questions
  - Update rules after major refactors
  - Add links to relevant documentation
  - Cross-reference related rules

- **Rule Deprecation:**
  - Mark outdated patterns as deprecated
  - Remove rules that no longer apply
  - Update references to deprecated rules
  - Document migration paths for old patterns

- **Documentation Updates:**
  - Keep examples synchronized with code
  - Update references to external docs
  - Maintain links between related rules
  - Document breaking changes

Follow [cursor_rules.mdc](mdc:rules/general/cursor_rules.mdc) for proper rule formatting and structure.
````

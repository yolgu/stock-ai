---
name: refactoring-safely
description: Refactor legacy or messy code without breaking functionality. Focuses on creating a safety net (tests) first, then applying small, verifiable structural changes.
---

# Refactoring Safely

## Overview
This skill guides you through improving code structure **without changing its behavior**.
- **Rule #1**: Never refactor without tests.
- **Rule #2**: Do not mix refactoring and feature development. Do them in separate commits.

## Phase 1: Create a Safety Net (The Harness)
Before touching any code, you must ensure that the current behavior is locked in.

1.  **Check Coverage**: Run current tests.
    - If tests pass and cover the code: Proceed to Phase 2.
    - If no tests exist: Go to step 2.
2.  **Write Characterization Tests**:
    - Write tests that capture the *current* output of the code, even if it seems wrong.
    - *Goal*: "The code currently returns X for input Y. I will write a test asserting X."
    - Do NOT try to fix bugs yet. Just pin down the behavior.

## Phase 2: Refactoring Loop (Small Steps)
Perform these steps in a tight loop. If any step fails, **REVERT** and try a smaller step.

1.  **Identify Smell**: Long function, duplicated logic, confusing naming, magic numbers.
2.  **Apply Tactic**:
    - **Rename**: Change variable/function name to reveal intent.
    - **Extract Method**: Move a block of code into a new function.
    - **Inline**: Remove a useless intermediary function.
    - **Move**: Move a class or function to a more appropriate file.
3.  **Compile/Lint**: Ensure no syntax errors.
4.  **Test**: Run the *Safety Net* tests.
    - 🔴 **FAIL**: **Undo immediately**. Do not try to debug the refactoring. Start over with a smaller change.
    - 🟢 **PASS**: **Commit immediately**. (e.g., `refactor: extract validation logic`).
5.  **Repeat**: Go back to Step 1.

## Phase 3: Cleanup
Once the structure is clean:
1.  **Review Tests**: Are the Characterization Tests still relevant? Can they be cleaned up?
2.  **Sanity Check**: Does the code look like the rest of the project?

## Common Techniques

### Extract Method (The Bread and Butter)
**Before:**
```typescript
function processOrder() {
  // validation
  if (x) ...
  if (y) ...
  // calculation
  let total = 0;
  ...
}
```

**After:**
```typescript
function processOrder() {
  validate();
  const total = calculateTotal();
}
```

### Rename
- Don't settle for `d`, `temp`, `data`.
- Rename `d` -> `daysSinceLastLogin`.
- Rename `temp` -> `cacheEntry`.

## When to Stop
- When the code is "Good Enough" to implement the next feature easily.
- Do not refactor for the sake of perfection.

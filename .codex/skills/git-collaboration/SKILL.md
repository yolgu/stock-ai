---
name: git-collaboration
description: Standardizes git usage for the agent. Enforces Conventional Commits, safe push/pull workflows, and proper branch management to prevent errors and ensure a clean history.
---

# Git Collaboration & Standards

## Overview
This skill acts as the "Git Governance" layer. It ensures that every interaction with version control is safe, semantic, and standardized.

## 1. Commit Convention (Conventional Commits)
All commit messages **MUST** follow this format:
`type(scope): description`

### Allowed Types
- **feat**: A new feature (correlates with MINOR in SemVer).
- **fix**: A bug fix (correlates with PATCH in SemVer).
- **docs**: Documentation only changes.
- **style**: Changes that do not affect the meaning of the code (white-space, formatting).
- **refactor**: A code change that neither fixes a bug nor adds a feature.
- **perf**: A code change that improves performance.
- **test**: Adding missing tests or correcting existing tests.
- **chore**: Changes to the build process or auxiliary tools.

### Rules
- **Imperative Mood**: "Add feature" not "Added feature".
- **No Period**: Do not end the subject line with a period.
- **Scope is Optional**: `feat(auth):` is good, `feat:` is also fine.

## 2. Safe Push Workflow
Before pushing code, ALWAYS follow this sequence:

1.  **Check Status**: `git status` - Ensure you are not committing unwanted files.
2.  **Verify Branch**: `git branch --show-current` - Know exactly where you are pushing.
    - *Safety*: If the branch is `main` or `master`, ask for confirmation unless it's a `docs` change.
3.  **Check Upstream**:
    - If it's a new branch: Use `git push -u origin <branch_name>`.
    - If it exists: `git push`.
4.  **Handle Errors**:
    - If `push` fails due to "refspec", double-check the branch name.
    - If `push` fails due to "non-fast-forward", **DO NOT FORCE PUSH** unless explicitly instructed. Suggest a `pull --rebase`.

## 3. Pull & Sync
- **Rebase Preferred**: When pulling updates, prefer `git pull --rebase` to keep history linear.
- **Conflict Handling**:
  - If a conflict occurs during pull/merge:
    1.  **Stop**: Do not try to blindly fix it.
    2.  **Report**: Tell the user which files have conflicts.
    3.  **Wait**: Ask the user if they want the agent to resolve it or if they will do it manually.

## 4. Repository Cleanliness
- **Ignore Garbage**: If you see system files (`.DS_Store`, `Thumbs.db`, `.env`) in `git status`, add them to `.gitignore` BEFORE adding files.
- **Atomic Commits**: Do not bundle a "Typography Fix" and a "Database Migration" in one commit. Split them.

## Example Scenario
**User**: "I added the login page. Push it."

**Agent**:
1. `git status` -> sees `src/LoginPage.tsx` and `.env`.
2. Adds `.env` to `.gitignore`.
3. `git add src/LoginPage.tsx .gitignore`.
4. `git commit -m "feat(auth): implement login page UI"`.
5. `git push origin feature/login`.

---
name: technical-research-and-comparison
description: Systematically research and compare technical solutions to make informed decisions.
---

# Technical Research and Comparison

## Overview
This skill guides you through selecting the right tool, library, or architectural pattern. It prevents "Hype Driven Development" by forcing a comparison based on **User Requirements** vs **Trade-offs**.

## Process

### 1. Define Criteria (The "Why")
Before searching, define what matters for *this specific project*.
- **Must-haves**: (e.g., "Must support React 18", "Must be open source", "Must handle offline mode").
- **Nice-to-haves**: (e.g., "Small bundle size", "Written in TypeScript").
- **Constraints**: (e.g., "Budget $0", "Team only knows TypeScript and Node").

### 2. Candidate Selection (The "What")
Identify 2-3 viable options. Do not pick 10.
- **Option A**: The Industry Standard (Safe bet).
- **Option B**: The Modern Challenger (Features/Performance).
- **Option C**: The Lightweight/Specialized Alternative.

### 3. Investigation (Data Gathering)
For each candidate, check:
- **Popularity**: NPM downloads, GitHub stars (Proxy for community support).
- **Maintenance**: Last commit date, open issues count.
- **Documentation**: Is it readable? Are there examples?
- **Bundle Size**: `bundlephobia.com` check.
- **Integration**: Does it play nice with the current stack?

### 4. Comparison Matrix
Present the data in a table.

| Feature | Option A | Option B | Option C |
| :--- | :--- | :--- | :--- |
| **Size** | 10kb | 50kb | 2kb |
| **API Style** | Hooks | HOC | Class |
| **Community** | Huge | Growing | Niche |
| **Pros** | Well tested | Fast dev | Simple |
| **Cons** | Bloated | Buggy | Minimal functionality |

### 5. Recommendation (The Decision)
End with a clear opinion.
- "I recommend **Option B** because..."
- "Although Option A is popular, it is overkill for our needs."

## Example Output

```markdown
# 🔍 Tech Research: State Management

## Candidates
1. **Redux Toolkit** (Standard)
2. **Zustand** (Minimalist)
3. **Recoil** (Atomic)

## Recommendation: Zustand 🐻
For our current dashboard project, I recommend **Zustand**.

### Reasoning
- **Simplicity**: We don't have complex state interactions requiring Redux.
- **Boilerplate**: Redux requires too much setup; Zustand is almost zero-config.
- **Performance**: It handles transient updates well without re-renders.
```

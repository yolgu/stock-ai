---
name: react-desktop-ui-rules
description: Use when building, reviewing, testing, or refactoring React TypeScript renderer UI for a desktop app, including components, hooks, layout, keyboard access, and client state.
---

# React Desktop UI Rules

## Overview

Renderer UI should be predictable, typed, keyboard-friendly, and separate from domain and native shell concerns.

## Layer Rules

| Layer | Responsibility |
| --- | --- |
| Component | Render props/state, expose accessible controls, call hooks |
| Hook | Orchestrate UI state, domain calls, and adapters |
| Domain module | Pure product calculations and state transitions |
| Adapter | Persistence, Neutralino extension events, notification/window wrappers |
| Utils | Pure formatting and small reusable calculations |

## React State Rules

- Use derived values in render instead of sync `useEffect`.
- Use `useReducer` for related state transitions.
- Use semantic handlers instead of exposing raw setters.
- Keep intervals and subscriptions in hooks with cleanup.
- Do not use component state as the source of truth for durable domain state.

## Desktop UX Rules

- Keyboard operation is required for primary controls.
- Buttons must have clear accessible names.
- Layouts should work in small desktop windows and resizable windows.
- Avoid mobile-only assumptions such as touch-first controls.
- Preserve focus behavior after dialogs, menus, and window visibility changes.

## TypeScript Rules

- Exported functions, hooks, and components have explicit return types.
- Prefer interfaces for object props and DTOs.
- Avoid `any`; add a short boundary comment only when unavoidable.
- Keep Neutralino extension event payload types in one source of truth shared by adapters/tests.

## Common Mistakes

- One large component holding domain logic, rendering, persistence, and notifications.
- `useEffect` chains for derived state.
- Icon-only controls with no accessible labels.
- Direct Neutralino native API calls from presentational components.

# Step 09 PRD: Beginner Explanation Popover UI

## Goal

Teach indicator meaning at the exact row where the user needs it, without adding a separate beginner tab or large learning panel.

## User Value

The user can hover or focus a checklist help button and immediately see what the indicator means, how the current value was calculated, and what limitations apply.

## Scope

- A single `상세보기` detail panel.
- Checklist row help buttons that open explanation popovers on hover and keyboard focus.
- Popover sections for meaning, usage, original formula, substituted formula, result, judgment, caution, and limitation.
- Escape close, blur close, and mouse leave close behavior.
- Bounded popover width and height with internal scrolling.

## Non-Goals

- No LLM refresh.
- No news timeline UI.
- No backtest report UI.
- No order UI.
- No separate beginner explanation tab or roadmap panel in the main detail layout.

## Object-Oriented Design

### Presentation Components

- `IndicatorExplanationPopover`
- `QuantChecklistView`
- `ExplanationBlock`
- `MarketContextStrip`

### View Models

- `BeginnerExplanationSectionViewModel`
- `MarketContextViewModel`

## UI Behavior

- The detail panel has no tab list.
- The detail panel shows current price coordinate, checklist, conditional zones, data quality, AI placeholder, and card editing.
- Each checklist `?` opens the matching deterministic explanation popover.
- Popovers do not shift the detail panel layout.
- CVD and supply-pressure explanations clearly mark estimated values and limitations.
- Small windows keep text readable and avoid overlapping button labels.

## Acceptance Criteria

- The detail panel does not show `초보자 설명` as a separate tab.
- Formula, substituted values, and result appear only inside the active popover.
- Hover and focus open the popover.
- Mouse leave, blur, and Escape close the popover.
- Escape on a popover closes only the popover, not the whole detail panel.
- CVD explanation visibly says the value is estimated.
- Raw volume, orderbook rows, and charts remain hidden.

## Verification

- Renderer tests validate the absence of the beginner tab.
- Renderer tests validate hover, focus, blur, and Escape popover behavior.
- Renderer tests validate price coordinate display and raw-data non-exposure.
- Manual Neutralino smoke check validates the UI in the desktop shell.

## Dependencies

- Step 06 watchlist dashboard and detail UI.
- Step 08 indicator explanation model.

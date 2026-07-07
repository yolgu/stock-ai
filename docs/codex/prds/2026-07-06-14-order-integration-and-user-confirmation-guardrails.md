# Step 14 PRD: Order Integration And User Confirmation Guardrails

## Goal

Integrate Toss order-related APIs as a guarded user-confirmed workflow, keeping LLM and deterministic analysis separate from actual order submission.

## User Value

The user can review buying power, sellable quantity, commissions, stop distance, expected fees, and order constraints before deciding whether to place an order.

## Scope

- Account selection through extension boundary.
- Buying power, sellable quantity, and commission lookup.
- Order preview.
- User confirmation gate.
- Order create, modify, cancel, list, and detail integration.
- Guardrails against LLM-initiated orders.
- Audit trail for order preview and submission attempts.

## Non-Goals

- No autonomous trading.
- No hidden order placement.
- No renderer-side secrets.
- No LLM tool that can submit orders.

## Object-Oriented Design

### Entities

- `OrderDraft`: user-intended order before submission.
- `OrderPreview`: calculated order feasibility and risk summary.
- `OrderSubmission`: confirmed submitted order record.
- `OrderAuditRecord`: immutable record of preview and submission decisions.

### Value Objects

- `AccountSequence`
- `OrderSide`
- `OrderQuantity`
- `OrderPrice`
- `OrderType`
- `ExpectedCommission`
- `ExpectedSlippage`
- `OrderRiskSummary`

### Domain Policies

- `OrderConfirmationPolicy`: requires explicit user confirmation.
- `LlmOrderIsolationPolicy`: prevents LLM output from becoming an executable order command.
- `HighRiskOrderPolicy`: blocks or escalates orders with excessive stop distance, insufficient risk/reward, restricted stock status, or missing market session.

### Application Use Cases

- `CreateOrderDraft`
- `PreviewOrder`
- `ConfirmAndSubmitOrder`
- `CancelOrder`
- `ModifyOrder`
- `ListOrdersForCard`

### Adapters

- `TossOrderInfoAdapter`
- `TossOrderAdapter`
- `TossOrderHistoryAdapter`
- `OrderAuditRepository`

## Acceptance Criteria

- User must manually create or edit an order draft.
- Order preview displays buying power, sellable quantity, estimated commissions, market session, and risk warnings.
- Submission requires a separate confirmation action.
- LLM reports cannot submit, modify, or cancel orders.
- Every submitted order stores an audit record with timestamp, card ID, order draft, preview, and confirmation result.
- Toss API errors are shown with actionable messages.

## Verification

- Policy tests prove LLM-originated order commands are rejected.
- Use case tests verify preview before submit.
- Adapter contract tests mock Toss order info and order submission responses.
- Audit tests verify immutable order records.

## Dependencies

- Step 05 quant indicator engine.
- Step 12 LLM insight isolation policy.

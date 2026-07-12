# Scientific evidence contract

Scientific Gates accept raw observations, never model-authored pass/fail receipts.
The controller reads canonical `scientific-evidence.json` and its SHA-256
sidecar from the current `allowedWriteDirectory`, recomputes the Gate, and
commits a controller-owned validation record bound to the action ID, validator
version, evidence digest, and previous ledger record.

The common root is:

```json
{"schemaVersion":"quant-scientific-evidence.v2"}
```

Action-specific fields are:

- `PREREGISTER`: canonical `cycleSpec`, `developmentAlpha`, `cvarAlpha`,
  `maximumLossCvar`, `maximumRepairableFraction`, `nullAccuracy`, and numeric
  tolerance. The immutable CampaignSpec supplies these defaults; the model
  cannot choose them. Later evidence must match them exactly.
- `DERIVE_FORMULA`: canonical `formulaVersion`. Its implementation must be a
  real hashed file in the same ActionContract directory. A child version may
  change exactly one registered axis.
- `VERIFY_MATHEMATICS` and `VERIFY_EQUIVALENCE`: the development dataset digest
  and preregistered tolerance. The controller evaluates the frozen formula and
  separately hashed declarative implementation over registered rows; submitted
  comparison pairs are not accepted.
- `DEVELOPMENT_OOF`: the registered development dataset digest, preregistered
  embargo and alpha, and null accuracy. Folds, predictions, and totals are read
  from the immutable point-in-time dataset and recomputed from the frozen
  formula expression.
- `FALSIFICATION`: the development dataset digest and preregistered maximum
  repairable fraction. Protected primary and independent postfix evaluators
  generate registered-row and extreme-value stress cases, then derive
  `passed`, `repairable`, or `refuted`; model-authored cases are ignored.
- `CONFIRM_ONCE`: the registered sealed-dataset digest, null accuracy, and the
  campaign's geometrically allocated alpha. Correct/total counts are derived
  from that dataset; model-authored counts are ignored.
- `ECONOMIC_RISK`: the sealed-dataset digest plus preregistered CVaR parameters.
  Formula-directed gross returns, costs, mean net return, and empirical loss
  CVaR are derived from immutable records.
- `INDEPENDENT_REPRODUCTION`: the sealed-dataset digest, frozen primary
  expression, a distinct reproduction expression, and tolerance. A restricted
  recursive evaluator and a separately implemented postfix machine execute the
  frozen formula and hashed declarative implementation over registered rows.
- `ADVERSARIAL_REVIEW`: the sealed dataset digest. Protected validator code
  derives reviewer identity and runs extreme-value/equivalence probes itself;
  model-authored reviewer digests and findings are ignored.
- `INCREMENTAL_INTEGRATION`: the sealed-dataset digest and preregistered minimum
  effect. Champion/baseline and Challenger metrics are derived from registered
  data. Terminal callers cannot supply the improvement.

Development and confirmation datasets use `quant-research-dataset.v2`. Each
record closes over `availableAt`, `signalAt`, numeric features, binary label,
gross return, and cost. The controller rejects future availability, malformed
folds, noncanonical bytes, digest mismatch, or post-commit mutation.

Any mutation of committed evidence, its sidecar, implementation, controller
validation record, or ledger-tail binding makes replay fail closed.

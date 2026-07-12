# Goal-only Quantitative Research V2

V2 adds a bounded Campaign above the immutable RP-001 V1 program runtime. A
Campaign accepts one exact natural-language Goal, freezes a research question
and point-in-time data contract, and advances through finite
Champion–Challenger ProgramVersions.

## User interface

Start a new thread with only:

```text
[QUANT_RESEARCH_GOAL]

Develop a direction-neutral market-state formula from point-in-time data.
```

The project hook preserves the exact prompt, commits the deterministic Campaign
bootstrap, atomically exposes the session binding, and requests Codex Goal
activation. No `$autonomous-research` command is needed.

## Runtime sequence

```text
Goal ingress
→ create_goal
→ bootstrap-campaign
→ question contract
→ data contract
→ DataRequest
→ bounded ProgramVersion workflow
→ Champion evaluation
→ next ResearchFrontier
→ next ProgramVersion
→ registered Campaign terminal
```

Each Goal continuation turn executes at most one CampaignActionContract. The
verified append-only ledger, not chat history, determines the next action.
Scientific actions follow
[`scientific-evidence-contract.md`](scientific-evidence-contract.md): the model
submits raw observations and protected controller code recomputes every
promotion-relevant Gate.

## Boundaries

- V1 artifacts and ledgers remain read-only and use their original schemas.
- Public data collection is not automatic. Missing development or confirmation
  data produces a DataRequest.
- Confirmation data is single-use and formula-version bound.
- Orders, accounts, positions, and assets remain forbidden.
- Campaigns use at most 16 ProgramVersions and geometric alpha spending whose
  total does not exceed 0.05.
- A failed Gate cannot be compensated by performance at another Gate.
- Effect size, temporal guards, development alpha, repair budget, cost, and
  CVaR thresholds are frozen at preregistration and cannot be changed later.
- Champion improvement is controller-derived from committed integration
  evidence; it is not accepted as a terminal command argument.
- Three identical failure fingerprints force stagnation diagnosis.

## Internal CLI

The Goal runtime, not the user, calls:

```text
research/rp-001/quant_autonomous_research.py bootstrap-campaign
research/rp-001/quant_autonomous_research.py status
research/rp-001/quant_autonomous_research.py next
research/rp-001/quant_autonomous_research.py commit-action
research/rp-001/quant_autonomous_research.py register-development-release
research/rp-001/quant_autonomous_research.py register-confirmation-release
research/rp-001/quant_autonomous_research.py record-action-failure
research/rp-001/quant_autonomous_research.py record-program-version-terminal
```

`commit-action` accepts only `--result <canonical-action-result.json>` from the
current ActionContract directory. Every JSON input file must use canonical JSON bytes. Runtime state is stored
under ignored `.codex/state/` and `research/rp-001/autonomy-v2/campaigns/`
directories.

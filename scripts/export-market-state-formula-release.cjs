const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "..");
const historicalAuditPath = path.join(
  projectRoot,
  ".storage/rp-001-data/causal-gated-challenger-historical-audit-v3",
  "causal-gated-challenger-historical-audit-v3.json"
);
const currentUptrendPath = path.join(
  projectRoot,
  ".storage/rp-001-data/uptrend-confirmation-results-v1",
  "uptrend-2025-cross-sectional-registered-detail.json"
);
const outputPath = path.join(
  projectRoot,
  "extensions/app/market-state/formula-release.json"
);
const featureResearchPaths = [
  path.join(
    projectRoot,
    ".storage/rp-001-data/confirmation-freeze-v6/source",
    "analyze_v4_minute_strict_precursor.py"
  ),
  path.join(
    projectRoot,
    ".storage/rp-001-data/confirmation-freeze-v6/source",
    "analyze_v4_minute_pre_confirmation.py"
  ),
  path.join(
    projectRoot,
    ".storage/rp-001-data/confirmation-freeze-v6/source",
    "develop_v4_portable_challengers.py"
  )
];
const lifecycleResearchPath = path.join(
  projectRoot,
  ".storage/rp-001-data/confirmation-freeze-v6/source/rp001",
  "autonomy_v4_minute/reference_episode.py"
);
const engineSourcePaths = [
  "completed-five-minute-bar.cjs",
  "market-state-evaluator.cjs",
  "market-state-features.cjs",
  "market-state-formula.cjs",
  "market-state-normalization.cjs",
  "observed-market-state.cjs",
  "market-state-service.cjs"
].map((fileName) =>
  path.join(projectRoot, "extensions/app/market-state", fileName)
);

const formulaVersion =
  "2ce9e3f48c8437f8f3e218ce39028b81f2279f16fe17bc68111682f7c070e842";
const stateOrder = [
  "FOMO_LIKE",
  "PANIC_LIKE",
  "PROFIT_TAKING_PROXY",
  "PERSISTENT_RECOVERY"
];
const targetInstrumentIds = [
  "AAPL",
  "AMD",
  "AMZN",
  "AVGO",
  "BA",
  "CAT",
  "COST",
  "CVX",
  "DIS",
  "GE",
  "GS",
  "HD",
  "IBM",
  "JNJ",
  "JPM",
  "KO",
  "LOW",
  "MCD",
  "META",
  "MRK",
  "MSFT",
  "MU",
  "NFLX",
  "NKE",
  "NVDA",
  "ORCL",
  "PEP",
  "QCOM",
  "SBUX",
  "TSLA",
  "UPS",
  "WMT",
  "XOM"
];

const historicalAudit = readJson(historicalAuditPath);
const currentUptrend = readJson(currentUptrendPath);
const historicalStates = historicalAudit.audits[0].states;
const firstFourSignals = stateOrder.map((stateId) => {
  const state = historicalStates.find((candidate) => candidate.stateId === stateId);

  if (state === undefined) {
    throw new Error(`formula_state_missing:${stateId}`);
  }

  return selectSignalFormula(state);
});
const uptrendSignal = selectSignalFormula(currentUptrend.state);

if (
  uptrendSignal.stateId !== "EFFICIENT_UPTREND" ||
  uptrendSignal.candidateId !== "PORTABLE_TREND_QUALITY_SCORE" ||
  uptrendSignal.fixedFormula.transportTailSafetyFactor !== 1 ||
  uptrendSignal.fixedFormula.causalGateId !== "POSITIVE_RELATIVE_VOLUME"
) {
  throw new Error("current_uptrend_formula_invalid");
}

const releaseBody = {
  schemaVersion: "stock-sub.market-state-formula-release.v1",
  formulaVersion,
  featureDefinitionVersion:
    "rp001.v4-minute-strict-precursor.v1",
  lifecycleDefinitionVersion:
    "rp001.v4-reference-episode.v1",
  engineVersion: "stock-sub.market-state-engine.v1",
  marketProxyId: "SPY",
  targetInstrumentIds,
  targetRosterSha256: sha256(canonicalJson(targetInstrumentIds)),
  sourceBindings: [
    createSourceBinding(historicalAuditPath, "formula"),
    createSourceBinding(currentUptrendPath, "formula"),
    ...featureResearchPaths.map((filePath) =>
      createSourceBinding(filePath, "feature-research")
    ),
    createSourceBinding(
      lifecycleResearchPath,
      "lifecycle-research"
    ),
    ...engineSourcePaths.map((filePath) =>
      createSourceBinding(filePath, "engine")
    )
  ],
  signals: [...firstFourSignals, uptrendSignal]
};
const release = {
  ...releaseBody,
  contentSha256: sha256(canonicalJson(releaseBody))
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(release, null, 2)}\n`, {
  encoding: "utf8",
  mode: 0o644
});

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function selectSignalFormula(state) {
  return {
    stateId: state.stateId,
    candidateId: state.candidateId,
    cause: state.cause,
    phenotypeTag: state.phenotypeTag,
    riskState: state.riskState,
    horizonBars: state.horizonBars,
    fixedFormula: state.fixedFormula
  };
}

function createSourceBinding(filePath, role) {
  const bytes = fs.readFileSync(filePath);

  return {
    role,
    path: path.relative(projectRoot, filePath),
    sha256: sha256(bytes)
  };
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }

  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }

  return JSON.stringify(value);
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

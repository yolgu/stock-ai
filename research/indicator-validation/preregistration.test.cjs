const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const test = require("node:test");

const RESEARCH_DIRECTORY = __dirname;
const ACTIVE_PREREGISTRATION_RAW_SHA256 = "7f4f940c71027999bf73715a0ff25219c9a213b9a68f1c43cc810e63427fcb7f";
const ACTIVE_PREREGISTRATION_CANONICAL_SHA256 = "ec6198a64cc8f0d811261e8521973ced073b41a03dcb269a651cd20bcc942efb";
const ACTIVE_LEDGER_RAW_SHA256 = "fa2b417323c36170fc1321ffa6cf905537e0b04b485daa54f8bcf61a7181d1fa";
const ACTIVE_LEDGER_CANONICAL_SHA256 = "a13823f871585d5efde2a867e96664b862cb8a16e0051e99009e7316a4cd9806";
const CANDIDATE_DEFINITIONS_SHA256 = "39e7d06ec45f06e0719157a8f0b1a5effc8515f715eb928d341a2381490460c6";
const CANDIDATE_IDS_SHA256 = "1bf7a0685c83eebeb346a4d89f451f1bb65ecc985f1082807547ac3bed08ca70";
const HYPOTHESIS_REGISTRY_ENTRIES_SHA256 = "e7d1f24fa7b83e2d9182f7180c08ce608354a305612226b0f818c2943bfc24f3";
const TRIAL_IDS_SHA256 = "1d56a3025fbbec04a273a26a4009b6b85a20dbc036a09d3f2d6441c23d30a265";
const TRIAL_ROWS_SHA256 = "cb00d0f13ea10f797569794fc4ecb6332077b8523de8e89589455069a55f8ae6";
const IDENTIFIABILITY_SHA256 = "7b6d8d99badd75e9af365d3fdfb0ec9caf02d656ac6e043cd11cae78fc8a4600";
const CHANGE_LOG_HEAD_SHA256 = "bd1b85a72e2c0856c0889c09408f999fd6e1886e6f0aa84994dccb1048c86ece";

const EXPECTED_CANDIDATE_IDS = [
  "fomo.baseline.breakout20",
  "fomo.baseline.momentum5",
  "fomo.baseline.volume20",
  "fomo.deduplicated",
  "fomo.documented",
  "fomo.equal",
  "panic.baseline.drawdown3",
  "panic.baseline.lowBreak20",
  "panic.baseline.volume20",
  "panic.deduplicated",
  "panic.documented",
  "panic.equal",
  "potentialPtp.baseline.runup20",
  "potentialPtp.baseline.vwapExtension",
  "potentialPtp.breadth",
  "potentialPtp.documented",
  "potentialPtp.equal",
  "relief.originalProxy",
  "relief.persistenceGated"
];
const EXPECTED_HOLM_HYPOTHESES = [
  "fomo.deduplicated::fomoContinuation@5",
  "panic.deduplicated::panicContinuation@5",
  "potentialPtp.breadth::profitTakingLike@5",
  "relief.persistenceGated::reliefConfirmed@5"
];
const PREREGISTRATION_VERSION_CHAIN = [
  { file: "preregistration.v1.0.0.json", version: "1.0.0", supersedes: null, rawSha256: "9d1b09d68d911198117a78f3c7709484f3edcdc7025889cd030e64af2513b3fa" },
  { file: "preregistration.v1.1.0.json", version: "1.1.0", supersedes: "1.0.0", rawSha256: "8265d1d2dedb6149b8ec9ff5ffbc44554e8e5d041c43280f88717a4884661e2d" },
  { file: "preregistration.v1.2.0.json", version: "1.2.0", supersedes: "1.1.0", rawSha256: "5d18f668d952940bf760ca235d10075847329ef7442eacbe767f67f66911e889" },
  { file: "preregistration.v1.3.0.json", version: "1.3.0", supersedes: "1.2.0", rawSha256: "67058c444d93b03e4d23bde17d6a6c19dba2658b771e997f972ab5f831c6e853" },
  { file: "preregistration.json", version: "1.4.0", supersedes: "1.3.0", rawSha256: ACTIVE_PREREGISTRATION_RAW_SHA256 }
];
const LEDGER_ARCHIVES = [
  { file: "trial-ledger.v1.0.0.json", version: "1.0.0", rawSha256: "99594ba306b0214936abda13a8794d852c7517b2946cf4c1463c128fcb42af95" },
  { file: "trial-ledger.v1.1.0.json", version: "1.1.0", rawSha256: "67ec28c517247a63a09596a2a6a0f7e83ac41eef01fffc4e3dfff788d8647c69" }
];

function compareCodePoints(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }
  if (value !== null && typeof value === "object") {
    return "{" + Object.keys(value)
      .sort(compareCodePoints)
      .map((key) => JSON.stringify(key) + ":" + canonicalize(value[key]))
      .join(",") + "}";
  }
  return JSON.stringify(value);
}

function sha256Utf8(value) {
  return crypto.createHash("sha256").update(value, "utf8").digest("hex");
}

function sha256Canonical(value) {
  return sha256Utf8(canonicalize(value));
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

async function readResearchText(fileName) {
  return fs.readFile(path.join(RESEARCH_DIRECTORY, fileName), "utf8");
}

async function readResearchJson(fileName) {
  return JSON.parse(await readResearchText(fileName));
}

function readCandidateDefinitions(preregistration) {
  return preregistration.candidateFamilies
    .flatMap((family) => family.candidates.map((candidate) => ({
      familyId: family.id,
      components: family.components,
      ...candidate
    })))
    .sort((left, right) => compareCodePoints(left.id, right.id));
}

function readHypothesisEntries(preregistration) {
  if (preregistration.protocol?.hypothesisRegistry?.entries) {
    return preregistration.protocol.hypothesisRegistry.entries;
  }
  const entries = [];
  const horizons = preregistration.protocol.horizons;
  for (const family of preregistration.candidateFamilies) {
    for (const candidate of family.candidates) {
      for (const outcomeDefinitionId of candidate.outcomeDefinitionIds) {
        const candidateOutcomeHorizons =
          candidate.outcomeApplicableHorizons?.[outcomeDefinitionId] ??
          candidate.applicableHorizons;
        const outcomeHorizons =
          preregistration.outcomeDefinitions[outcomeDefinitionId]?.applicableHorizons ??
          horizons;
        for (const horizon of horizons) {
          if (
            candidate.applicableHorizons.includes(horizon) &&
            candidateOutcomeHorizons.includes(horizon) &&
            outcomeHorizons.includes(horizon)
          ) {
            entries.push({
              hypothesisId: candidate.id + "::" + outcomeDefinitionId + "@" + horizon,
              familyId: family.id,
              candidateId: candidate.id,
              candidateKind: candidate.kind,
              outcomeDefinitionId,
              horizon
            });
          }
        }
      }
    }
  }
  return entries.sort((left, right) =>
    compareCodePoints(left.hypothesisId, right.hypothesisId)
  );
}

function transitionSnapshot(preregistration, rawText) {
  const candidates = readCandidateDefinitions(preregistration);
  const candidateIds = candidates.map(({ id }) => id);
  const hypotheses = readHypothesisEntries(preregistration);
  const trialIds = hypotheses.map(({ hypothesisId }) => hypothesisId);
  return {
    preregistrationVersion: preregistration.research.version,
    preregistrationRawSha256: sha256Utf8(rawText),
    preregistrationCanonicalSha256: sha256Canonical(preregistration),
    candidateCount: candidateIds.length,
    candidateIdsSha256: sha256Canonical(candidateIds),
    candidateDefinitionsSha256: sha256Canonical(candidates),
    hypothesisCount: hypotheses.length,
    hypothesisRegistryEntriesSha256: sha256Canonical(hypotheses),
    trialSetSha256: sha256Canonical(trialIds)
  };
}

function assertFrozenPreregistration(preregistration) {
  assert.equal(
    sha256Canonical(preregistration),
    ACTIVE_PREREGISTRATION_CANONICAL_SHA256
  );
}

function assertFrozenCandidateDefinitions(preregistration) {
  assert.equal(
    sha256Canonical(readCandidateDefinitions(preregistration)),
    CANDIDATE_DEFINITIONS_SHA256
  );
}

test("freezes the active preregistration and rejects execution-contract mutations", async () => {
  const [text, preregistration] = await Promise.all([
    readResearchText("preregistration.json"),
    readResearchJson("preregistration.json")
  ]);

  assert.equal(sha256Utf8(text), ACTIVE_PREREGISTRATION_RAW_SHA256);
  assertFrozenPreregistration(preregistration);
  assert.deepEqual(preregistration.research, {
    id: "mania-indicator-validation",
    version: "1.4.0",
    supersedes: "1.3.0",
    status: "frozen",
    frozenAt: "2026-07-10",
    dataCutoff: "2026-07-09",
    seed: 20260710,
    noMarketDataAnalyzed: true,
    changeReason: "pre_data_execution_and_inference_contract_completion"
  });

  const mutations = [
    ["fold boundary", (draft) => { draft.protocol.windows.anchored.blocks[0].endOrdinalInclusive = 118; }],
    ["calibration", (draft) => { draft.protocol.probabilityCalibration.quantileBins.binCount = 4; }],
    ["outcome horizon", (draft) => { draft.outcomeDefinitions.fakeRelief.applicableHorizons.push(3); }],
    ["hypothesis entry", (draft) => { draft.protocol.hypothesisRegistry.entries.pop(); }],
    ["missing policy", (draft) => { draft.identifiability.missingPolicy = "zero_imputation"; }]
  ];
  for (const [name, mutate] of mutations) {
    const draft = cloneJson(preregistration);
    mutate(draft);
    assert.throws(
      () => assertFrozenPreregistration(draft),
      { code: "ERR_ASSERTION" },
      name
    );
  }
});

test("freezes candidate formulas, weights, outcomes, registry, and Holm hypotheses", async () => {
  const preregistration = await readResearchJson("preregistration.json");
  const candidates = readCandidateDefinitions(preregistration);
  const candidateIds = candidates.map(({ id }) => id);
  const registry = preregistration.protocol.hypothesisRegistry;

  assert.deepEqual(candidateIds, EXPECTED_CANDIDATE_IDS);
  assert.equal(candidateIds.length, 19);
  assert.equal(sha256Canonical(candidateIds), CANDIDATE_IDS_SHA256);
  assertFrozenCandidateDefinitions(preregistration);
  assert.equal(registry.expectedCount, 130);
  assert.equal(registry.entries.length, 130);
  assert.equal(registry.hashTarget, "protocol.hypothesisRegistry.entries");
  assert.equal(sha256Canonical(registry.entries), HYPOTHESIS_REGISTRY_ENTRIES_SHA256);
  assert.equal(registry.sha256, HYPOTHESIS_REGISTRY_ENTRIES_SHA256);
  assert.deepEqual(
    preregistration.protocol.significance.primaryConclusions.hypotheses,
    EXPECTED_HOLM_HYPOTHESES
  );

  const reliefOriginal = preregistration.candidateFamilies
    .find(({ id }) => id === "relief")
    .candidates.find(({ id }) => id === "relief.originalProxy");
  const reliefRepaired = preregistration.candidateFamilies
    .find(({ id }) => id === "relief")
    .candidates.find(({ id }) => id === "relief.persistenceGated");
  assert.deepEqual(reliefOriginal.outcomeApplicableHorizons, {
    reliefFirstRebound: [1, 3, 5, 10],
    fakeRelief: [5, 10],
    reliefConfirmed: [3, 5, 10]
  });
  assert.deepEqual(reliefRepaired.outcomeApplicableHorizons, {
    reliefConfirmed: [3, 5, 10],
    fakeRelief: [5, 10]
  });

  const candidateMutations = [
    ["weight", (draft) => { draft.candidateFamilies[0].candidates[0].weights.returnImpulse = 0.23; }],
    ["formula", (draft) => { draft.candidateFamilies[0].candidates[3].formula = "momentum4"; }],
    ["outcomes", (draft) => { draft.candidateFamilies[1].candidates[0].outcomeDefinitionIds.pop(); }],
    ["outcome applicability", (draft) => { draft.candidateFamilies[3].candidates[0].outcomeApplicableHorizons.fakeRelief.push(3); }]
  ];
  for (const [name, mutate] of candidateMutations) {
    const draft = cloneJson(preregistration);
    mutate(draft);
    assert.throws(
      () => assertFrozenCandidateDefinitions(draft),
      { code: "ERR_ASSERTION" },
      name
    );
  }
});

test("binds all 130 full outcome-specific trials to the v1.4 preregistration", async () => {
  const [preregistration, ledger, ledgerText] = await Promise.all([
    readResearchJson("preregistration.json"),
    readResearchJson("trial-ledger.json"),
    readResearchText("trial-ledger.json")
  ]);
  const candidates = readCandidateDefinitions(preregistration);
  const candidateById = new Map(candidates.map((candidate) => [candidate.id, candidate]));
  const expectedTrials = preregistration.protocol.hypothesisRegistry.entries.map((hypothesis) => ({
    trialId: hypothesis.hypothesisId,
    candidateId: hypothesis.candidateId,
    familyId: hypothesis.familyId,
    kind: hypothesis.candidateKind,
    outcomeDefinitionId: hypothesis.outcomeDefinitionId,
    horizon: hypothesis.horizon,
    status: "preregistered",
    candidateDefinitionSha256: sha256Canonical(candidateById.get(hypothesis.candidateId)),
    outcomeDefinitionSha256: sha256Canonical(
      preregistration.outcomeDefinitions[hypothesis.outcomeDefinitionId]
    ),
    protocolVersion: "1.4.0",
    applicable: true
  }));
  const expectedTrialIds = expectedTrials.map(({ trialId }) => trialId);
  const expectedRowHashes = expectedTrials.map((trial) => ({
    trialId: trial.trialId,
    sha256: sha256Canonical(trial)
  }));

  assert.equal(sha256Utf8(ledgerText), ACTIVE_LEDGER_RAW_SHA256);
  assert.equal(sha256Canonical(ledger), ACTIVE_LEDGER_CANONICAL_SHA256);
  assert.deepEqual(
    {
      researchId: ledger.researchId,
      version: ledger.version,
      protocolVersion: ledger.protocolVersion,
      frozenAt: ledger.frozenAt,
      dataCutoff: ledger.dataCutoff,
      noMarketDataAnalyzed: ledger.noMarketDataAnalyzed
    },
    {
      researchId: "mania-indicator-validation",
      version: "1.4.0",
      protocolVersion: "1.4.0",
      frozenAt: "2026-07-10",
      dataCutoff: "2026-07-09",
      noMarketDataAnalyzed: true
    }
  );
  assert.deepEqual(ledger.policy, {
    appendOnly: true,
    deleteFailedTrials: false,
    retainAllOutcomes: true
  });
  assert.deepEqual(ledger.snapshot.preregistration, {
    file: "preregistration.json",
    version: "1.4.0",
    rawSha256: ACTIVE_PREREGISTRATION_RAW_SHA256,
    canonicalSha256: ACTIVE_PREREGISTRATION_CANONICAL_SHA256
  });
  assert.deepEqual(ledger.snapshot.candidateDefinitions.candidateIds, EXPECTED_CANDIDATE_IDS);
  assert.equal(ledger.snapshot.candidateDefinitions.count, 19);
  assert.equal(ledger.snapshot.candidateDefinitions.candidateIdsSha256, CANDIDATE_IDS_SHA256);
  assert.equal(ledger.snapshot.candidateDefinitions.canonicalSha256, CANDIDATE_DEFINITIONS_SHA256);
  assert.deepEqual(ledger.snapshot.hypothesisRegistry, {
    count: 130,
    entriesSha256: HYPOTHESIS_REGISTRY_ENTRIES_SHA256
  });
  assert.equal(ledger.trials.length, 130);
  assert.deepEqual(ledger.trials, expectedTrials);
  assert.deepEqual(ledger.snapshot.trialDefinitions.trialIds, expectedTrialIds);
  assert.equal(ledger.snapshot.trialDefinitions.trialIdsSha256, TRIAL_IDS_SHA256);
  assert.equal(ledger.snapshot.trialDefinitions.rowsCanonicalSha256, TRIAL_ROWS_SHA256);
  assert.deepEqual(ledger.snapshot.trialDefinitions.rowCanonicalSha256, expectedRowHashes);
  assert.equal(sha256Canonical(expectedTrialIds), TRIAL_IDS_SHA256);
  assert.equal(sha256Canonical(expectedTrials), TRIAL_ROWS_SHA256);

  const identifiability = {
    missingPolicy: preregistration.identifiability.missingPolicy,
    exactFlowCandidates: preregistration.identifiability.exactFlowCandidates
  };
  assert.deepEqual(
    {
      missingPolicy: ledger.snapshot.identifiability.missingPolicy,
      exactFlowCandidates: ledger.snapshot.identifiability.exactFlowCandidates
    },
    identifiability
  );
  assert.equal(ledger.snapshot.identifiability.canonicalSha256, IDENTIFIABILITY_SHA256);
  const exactFlowIds = new Set(identifiability.exactFlowCandidates.map(({ id }) => id));
  assert.equal(ledger.trials.some(({ candidateId }) => exactFlowIds.has(candidateId)), false);
  assert.equal(ledger.trials.every(({ applicable }) => applicable === true), true);
});

test("preserves legacy change-log semantics and externally anchors the v1.4 head", async () => {
  const [ledger, archivedLedger, versions] = await Promise.all([
    readResearchJson("trial-ledger.json"),
    readResearchJson("trial-ledger.v1.1.0.json"),
    Promise.all(PREREGISTRATION_VERSION_CHAIN.slice(1).map(async ({ file }) => ({
      preregistration: await readResearchJson(file),
      text: await readResearchText(file)
    })))
  ]);

  assert.deepEqual(ledger.changeLog.slice(0, 2), archivedLedger.changeLog);
  assert.deepEqual(
    ledger.changeLog.map(({ sequence, type }) => ({ sequence, type })),
    [
      { sequence: 1, type: "initial_freeze" },
      { sequence: 2, type: "pre_data_spec_completion" },
      { sequence: 3, type: "pre_data_formula_contract_completion" },
      { sequence: 4, type: "pre_data_probability_and_numeric_contract_completion" },
      { sequence: 5, type: "pre_data_execution_and_inference_contract_completion" }
    ]
  );

  for (const [index, entry] of ledger.changeLog.entries()) {
    const { entrySha256, ...hashInput } = entry;
    assert.equal(entrySha256, sha256Canonical(hashInput), "change-log " + entry.sequence);
    assert.equal(entry.noMarketDataAnalyzed, true);
    assert.equal(
      entry.previousEntrySha256,
      index === 0 ? null : ledger.changeLog[index - 1].entrySha256
    );
  }

  const transitionVersions = versions.map(({ preregistration, text }) =>
    transitionSnapshot(preregistration, text)
  );
  const transitions = ledger.changeLog.slice(2);
  assert.deepEqual(
    transitions.map(({ fromVersion, toVersion }) => ({ fromVersion, toVersion })),
    [
      { fromVersion: "1.1.0", toVersion: "1.2.0" },
      { fromVersion: "1.2.0", toVersion: "1.3.0" },
      { fromVersion: "1.3.0", toVersion: "1.4.0" }
    ]
  );
  for (let index = 0; index < transitions.length; index += 1) {
    assert.deepEqual(transitions[index].before, transitionVersions[index]);
    assert.deepEqual(transitions[index].after, transitionVersions[index + 1]);
    assert.equal(transitions[index].ledgerSnapshotCreated, index === 2);
  }
  assert.equal(ledger.changeLogHeadSha256, CHANGE_LOG_HEAD_SHA256);
  assert.equal(ledger.changeLog.at(-1).entrySha256, CHANGE_LOG_HEAD_SHA256);
});

test("preserves every preregistration archive and only the real ledger archives", async () => {
  for (const expected of PREREGISTRATION_VERSION_CHAIN) {
    const [text, preregistration] = await Promise.all([
      readResearchText(expected.file),
      readResearchJson(expected.file)
    ]);
    assert.equal(sha256Utf8(text), expected.rawSha256, expected.file);
    assert.equal(preregistration.research.version, expected.version, expected.file);
    assert.equal(preregistration.research.supersedes ?? null, expected.supersedes, expected.file);
  }

  for (const expected of LEDGER_ARCHIVES) {
    const [text, ledger] = await Promise.all([
      readResearchText(expected.file),
      readResearchJson(expected.file)
    ]);
    assert.equal(sha256Utf8(text), expected.rawSha256, expected.file);
    assert.equal(ledger.version, expected.version, expected.file);
  }

  await assert.rejects(
    fs.access(path.join(RESEARCH_DIRECTORY, "trial-ledger.v1.2.0.json")),
    { code: "ENOENT" }
  );
  await assert.rejects(
    fs.access(path.join(RESEARCH_DIRECTORY, "trial-ledger.v1.3.0.json")),
    { code: "ENOENT" }
  );
  const source = await readResearchText("preregistration.test.cjs");
  const forbiddenComparatorName = ["locale", "Compare"].join("");
  assert.equal(source.includes(forbiddenComparatorName), false);
});

test("retains the no-market-data declaration across the active freeze", async () => {
  const [preregistration, ledger, archivedLedger] = await Promise.all([
    readResearchJson("preregistration.json"),
    readResearchJson("trial-ledger.json"),
    readResearchJson("trial-ledger.v1.1.0.json")
  ]);

  assert.equal(preregistration.research.noMarketDataAnalyzed, true);
  assert.equal(ledger.noMarketDataAnalyzed, true);
  assert.equal(ledger.changeLog.every(({ noMarketDataAnalyzed }) => noMarketDataAnalyzed), true);
  assert.equal(
    archivedLedger.changeLog.every(({ noMarketDataAnalyzed }) => noMarketDataAnalyzed),
    true
  );
});

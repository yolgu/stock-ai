const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");

const fileOperationQueues = new Map();

class StorageError extends Error {
  constructor(code, message, recoverable) {
    super(message);
    this.name = "StorageError";
    this.code = code;
    this.recoverable = recoverable;
  }
}

class JsonFileStore {
  constructor(filePath, defaultValue) {
    this.filePath = filePath;
    this.defaultValue = defaultValue;
  }

  async read() {
    return this.readUnlocked();
  }

  async readUnlocked() {
    try {
      const text = await fs.readFile(this.filePath, "utf8");

      return JSON.parse(text);
    } catch (error) {
      if (error && error.code === "ENOENT") {
        return cloneJson(this.defaultValue);
      }

      if (error instanceof SyntaxError) {
        throw new StorageError(
          "storage_corrupted",
          `${path.basename(this.filePath)} is not valid JSON`,
          true
        );
      }

      throw error;
    }
  }

  async write(value) {
    return enqueueFileOperation(this.filePath, () => this.writeUnlocked(value));
  }

  async update(updater) {
    return enqueueFileOperation(this.filePath, async () => {
      const currentValue = await this.readUnlocked();
      const nextValue = await updater(currentValue);
      await this.writeUnlocked(nextValue);

      return nextValue;
    });
  }

  async writeUnlocked(value) {
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });

    const temporaryPath = `${this.filePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
    await fs.writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, {
      encoding: "utf8",
      mode: 0o600
    });
    await fs.chmod(temporaryPath, 0o600);
    await fs.rename(temporaryPath, this.filePath);
    await fs.chmod(this.filePath, 0o600);
  }
}

async function enqueueFileOperation(filePath, operation) {
  const queueKey = path.resolve(filePath);
  const previousOperation = fileOperationQueues.get(queueKey) || Promise.resolve();
  const currentOperation = previousOperation
    .catch(() => undefined)
    .then(operation);
  const queueTail = currentOperation.catch(() => undefined);
  fileOperationQueues.set(queueKey, queueTail);

  try {
    return await currentOperation;
  } finally {
    if (fileOperationQueues.get(queueKey) === queueTail) {
      fileOperationQueues.delete(queueKey);
    }
  }
}

class StoredWatchlistRepository {
  constructor(filePath) {
    this.store = new JsonFileStore(filePath, {
      cards: [],
      groups: []
    });
  }

  async list() {
    const snapshot = await this.readSnapshot();

    return createListPayload(snapshot.cards);
  }

  async create(input, now) {
    const snapshot = await this.readSnapshot();
    const normalizedMarket = normalizeMarket(input.market);
    const normalizedSymbol = normalizeSymbol(input.symbol);
    const existingCard = snapshot.cards.find(
      (card) => card.market === normalizedMarket && card.symbol === normalizedSymbol
    );

    if (existingCard && existingCard.lifecycleStatus === "archived") {
      return {
        type: "restore-available",
        archivedCardId: existingCard.id,
        watchlist: createListPayload(snapshot.cards)
      };
    }

    if (existingCard) {
      return {
        type: "duplicate-card",
        existingCardId: existingCard.id,
        watchlist: createListPayload(snapshot.cards)
      };
    }

    const card = {
      id: typeof input.id === "string" && input.id.trim() !== "" ? input.id : crypto.randomUUID(),
      market: normalizedMarket,
      symbol: normalizedSymbol,
      displayName: normalizeDisplayName(input.displayName),
      groupId: typeof input.groupId === "string" ? input.groupId : null,
      tags: normalizeTags(input.tags),
      memo: typeof input.memo === "string" ? input.memo : "",
      sortOrder: nextSortOrder(snapshot.cards),
      lifecycleStatus: "active",
      createdAt: now,
      updatedAt: now
    };

    snapshot.cards.push(card);
    await this.writeSnapshot(snapshot);

    return {
      type: "created",
      card,
      watchlist: createListPayload(snapshot.cards)
    };
  }

  async update(cardId, input, now) {
    const snapshot = await this.readSnapshot();
    const card = findCard(snapshot.cards, cardId);

    if (!card) {
      return undefined;
    }

    if (typeof input.displayName === "string") {
      card.displayName = normalizeDisplayName(input.displayName);
    }

    if ("groupId" in input) {
      card.groupId = typeof input.groupId === "string" ? input.groupId : null;
    }

    if (Array.isArray(input.tags)) {
      card.tags = normalizeTags(input.tags);
    }

    if (typeof input.memo === "string") {
      card.memo = input.memo;
    }

    card.updatedAt = now;
    await this.writeSnapshot(snapshot);

    return {
      card,
      watchlist: createListPayload(snapshot.cards)
    };
  }

  async hide(cardId, now) {
    return this.changeLifecycleStatus(cardId, "hidden", now);
  }

  async archive(cardId, now) {
    return this.changeLifecycleStatus(cardId, "archived", now);
  }

  async restore(cardId, now) {
    return this.changeLifecycleStatus(cardId, "active", now);
  }

  async delete(cardId) {
    const snapshot = await this.readSnapshot();
    snapshot.cards = snapshot.cards.filter((card) => card.id !== cardId);
    await this.writeSnapshot(snapshot);

    return createListPayload(snapshot.cards);
  }

  async reorder(cardIds, now) {
    const snapshot = await this.readSnapshot();
    const activeCardsById = new Map(
      snapshot.cards
        .filter((card) => card.lifecycleStatus === "active")
        .map((card) => [card.id, card])
    );

    cardIds.forEach((cardId, index) => {
      const card = activeCardsById.get(cardId);

      if (card) {
        card.sortOrder = index + 1;
        card.updatedAt = now;
      }
    });

    await this.writeSnapshot(snapshot);

    return createListPayload(snapshot.cards);
  }

  async changeLifecycleStatus(cardId, lifecycleStatus, now) {
    const snapshot = await this.readSnapshot();
    const card = findCard(snapshot.cards, cardId);

    if (!card) {
      return undefined;
    }

    card.lifecycleStatus = lifecycleStatus;
    card.updatedAt = now;
    await this.writeSnapshot(snapshot);

    return {
      card,
      watchlist: createListPayload(snapshot.cards)
    };
  }

  async readSnapshot() {
    const snapshot = await this.store.read();

    return {
      cards: Array.isArray(snapshot.cards) ? snapshot.cards : [],
      groups: Array.isArray(snapshot.groups) ? snapshot.groups : []
    };
  }

  async writeSnapshot(snapshot) {
    await this.store.write({
      cards: snapshot.cards,
      groups: snapshot.groups
    });
  }
}

function createListPayload(cards) {
  return {
    activeCards: cards
      .filter((card) => card.lifecycleStatus === "active")
      .sort(compareBySortOrder),
    hiddenCards: cards
      .filter((card) => card.lifecycleStatus === "hidden")
      .sort(compareBySortOrder),
    archivedCards: cards
      .filter((card) => card.lifecycleStatus === "archived")
      .sort(compareBySortOrder)
  };
}

function normalizeMarket(value) {
  const market = String(value ?? "").trim().toUpperCase();

  if (market === "") {
    throw new Error("market is required");
  }

  return market;
}

function normalizeSymbol(value) {
  const symbol = String(value ?? "").trim().toUpperCase();

  if (!/^[A-Z0-9.-]+$/.test(symbol)) {
    throw new Error("symbol supports letters, numbers, '.', and '-' only");
  }

  return symbol;
}

function normalizeDisplayName(value) {
  const displayName = String(value ?? "").trim();

  if (displayName === "") {
    throw new Error("displayName is required");
  }

  return displayName;
}

function normalizeTags(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  return values
    .map((value) => String(value).trim())
    .filter((value) => value !== "");
}

function findCard(cards, cardId) {
  return cards.find((card) => card.id === cardId);
}

function nextSortOrder(cards) {
  return cards.reduce((maxSortOrder, card) => Math.max(maxSortOrder, card.sortOrder), 0) + 1;
}

function compareBySortOrder(left, right) {
  return left.sortOrder - right.sortOrder;
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

module.exports = {
  JsonFileStore,
  StorageError,
  StoredWatchlistRepository
};

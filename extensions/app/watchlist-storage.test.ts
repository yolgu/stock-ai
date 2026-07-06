import { mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const { JsonFileStore, StoredWatchlistRepository } = require("./storage.cjs") as {
  JsonFileStore: new (filePath: string, defaultValue: unknown) => {
    read(): Promise<unknown>;
    write(value: unknown): Promise<void>;
  };
  StoredWatchlistRepository: new (filePath: string) => {
    list(): Promise<unknown>;
    create(input: Record<string, unknown>, now: string): Promise<unknown>;
    hide(cardId: string, now: string): Promise<unknown>;
    archive(cardId: string, now: string): Promise<unknown>;
    restore(cardId: string, now: string): Promise<unknown>;
    delete(cardId: string): Promise<unknown>;
    reorder(cardIds: string[], now: string): Promise<unknown>;
  };
};

let tempDirectory: string | undefined;

async function createTempPath(fileName: string): Promise<string> {
  tempDirectory = await mkdtemp(join(tmpdir(), "stock-sub-"));

  return join(tempDirectory, fileName);
}

afterEach(async () => {
  if (tempDirectory !== undefined) {
    await rm(tempDirectory, { recursive: true, force: true });
    tempDirectory = undefined;
  }
});

describe("extension JSON persistence", () => {
  it("round-trips JSON with owner-only permissions", async () => {
    const filePath = await createTempPath("settings.json");
    const store = new JsonFileStore(filePath, { cards: [] });

    await store.write({ cards: [{ id: "card-1" }] });

    expect(await store.read()).toEqual({ cards: [{ id: "card-1" }] });
    expect((await stat(filePath)).mode & 0o777).toBe(0o600);
  });

  it("returns a recoverable storage error for corrupted JSON", async () => {
    const filePath = await createTempPath("watchlist.json");
    await writeFile(filePath, "{", { mode: 0o600 });
    const store = new JsonFileStore(filePath, { cards: [] });

    await expect(store.read()).rejects.toMatchObject({
      code: "storage_corrupted",
      recoverable: true
    });
  });

  it("persists watchlist CRUD results without deleted cards", async () => {
    const filePath = await createTempPath("watchlist.json");
    const repository = new StoredWatchlistRepository(filePath);

    await repository.create(
      {
        id: "card-1",
        market: "NASDAQ",
        symbol: "MU",
        displayName: "MU 마이크론",
        groupId: null,
        tags: ["반도체"],
        memo: ""
      },
      "2026-07-06T09:00:00.000Z"
    );
    await repository.create(
      {
        id: "card-2",
        market: "NYSE",
        symbol: "IBM",
        displayName: "IBM",
        groupId: null,
        tags: [],
        memo: ""
      },
      "2026-07-06T09:01:00.000Z"
    );
    await repository.hide("card-2", "2026-07-06T09:02:00.000Z");
    await repository.archive("card-1", "2026-07-06T09:03:00.000Z");
    await repository.restore("card-1", "2026-07-06T09:04:00.000Z");
    await repository.reorder(["card-1"], "2026-07-06T09:05:00.000Z");
    await repository.delete("card-2");

    expect(await repository.list()).toEqual({
      activeCards: [
        expect.objectContaining({
          id: "card-1",
          symbol: "MU",
          sortOrder: 1,
          lifecycleStatus: "active"
        })
      ],
      hiddenCards: [],
      archivedCards: []
    });
    expect(await readFile(filePath, "utf8")).not.toContain("card-2");
  });
});

import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);

const {
  StoredTossCredentialRepository,
  TossOAuthClient
} = require("./toss-credentials.cjs") as {
  StoredTossCredentialRepository: new (filePath: string) => {
    readStatus(): Promise<unknown>;
    save(input: { clientId: string; clientSecret: string }, now: string): Promise<unknown>;
    delete(): Promise<unknown>;
    markValidated(now: string): Promise<unknown>;
  };
  TossOAuthClient: new (fetcher: typeof fetch) => {
    testConnection(credentials: {
      clientId: string;
      clientSecret: string;
    }): Promise<unknown>;
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

describe("Toss credential settings", () => {
  it("stores credentials locally but returns only masked status", async () => {
    const filePath = await createTempPath("toss-credentials.json");
    const repository = new StoredTossCredentialRepository(filePath);

    const status = await repository.save(
      {
        clientId: "client_fixture_1234567890",
        clientSecret: "secret_fixture_super_secret"
      },
      "2026-07-06T09:00:00.000Z"
    );

    expect(status).toEqual({
      configured: true,
      maskedClientId: "clie…7890",
      lastValidatedAt: null,
      connectionStatus: "saved"
    });
    expect(JSON.stringify(status)).not.toContain("super_secret");
    expect(await readFile(filePath, "utf8")).toContain("secret_fixture_super_secret");
  });

  it("does not persist access tokens after OAuth connection tests", async () => {
    const requests: Array<{ url: string; body: string; contentType: string | null }> = [];
    const fetcher = async (url: string | URL | Request, init?: RequestInit): Promise<Response> => {
      requests.push({
        url: String(url),
        body: String(init?.body),
        contentType: new Headers(init?.headers).get("Content-Type")
      });

      return new Response(
        JSON.stringify({
          access_token: "access-token-that-must-not-be-stored",
          token_type: "Bearer",
          expires_in: 86400
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    };
    const client = new TossOAuthClient(fetcher);

    await expect(
      client.testConnection({
        clientId: "client_fixture_1234567890",
        clientSecret: "secret_fixture_super_secret"
      })
    ).resolves.toEqual({ ok: true });

    expect(requests).toEqual([
      {
        url: "https://openapi.tossinvest.com/oauth2/token",
        body: "grant_type=client_credentials&client_id=client_fixture_1234567890&client_secret=secret_fixture_super_secret",
        contentType: "application/x-www-form-urlencoded"
      }
    ]);
  });

  it("maps Toss invalid client responses to a recoverable credential error", async () => {
    const fetcher = async (): Promise<Response> =>
      new Response(
        JSON.stringify({
          error: "invalid_client",
          error_description: "Client authentication failed."
        }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
    const client = new TossOAuthClient(fetcher);

    await expect(
      client.testConnection({
        clientId: "client_fixture_invalid",
        clientSecret: "secret_fixture_invalid"
      })
    ).rejects.toMatchObject({
      code: "invalid_toss_credentials",
      recoverable: true
    });
  });
});

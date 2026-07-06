const { JsonFileStore } = require("./storage.cjs");

class TossCredentialError extends Error {
  constructor(code, message, recoverable) {
    super(message);
    this.name = "TossCredentialError";
    this.code = code;
    this.recoverable = recoverable;
  }
}

class StoredTossCredentialRepository {
  constructor(filePath) {
    this.store = new JsonFileStore(filePath, {
      clientId: null,
      clientSecret: null,
      savedAt: null,
      lastValidatedAt: null,
      connectionStatus: "notConfigured"
    });
  }

  async readStatus() {
    const credentials = await this.readCredentials();

    return createCredentialStatus(credentials);
  }

  async readCredentials() {
    return this.store.read();
  }

  async save(input, now) {
    const credentials = {
      clientId: normalizeCredentialField(input.clientId, "clientId"),
      clientSecret: normalizeCredentialField(input.clientSecret, "clientSecret"),
      savedAt: now,
      lastValidatedAt: null,
      connectionStatus: "saved"
    };

    await this.store.write(credentials);

    return createCredentialStatus(credentials);
  }

  async delete() {
    const credentials = {
      clientId: null,
      clientSecret: null,
      savedAt: null,
      lastValidatedAt: null,
      connectionStatus: "notConfigured"
    };

    await this.store.write(credentials);

    return createCredentialStatus(credentials);
  }

  async markValidated(now) {
    const credentials = await this.readCredentials();
    credentials.lastValidatedAt = now;
    credentials.connectionStatus = "valid";
    await this.store.write(credentials);

    return createCredentialStatus(credentials);
  }

  async markInvalid() {
    const credentials = await this.readCredentials();
    credentials.connectionStatus = "invalid";
    await this.store.write(credentials);

    return createCredentialStatus(credentials);
  }
}

class TossOAuthClient {
  constructor(fetcher) {
    this.fetcher = fetcher;
  }

  async testConnection(credentials) {
    await this.issueAccessToken(credentials);

    return { ok: true };
  }

  async issueAccessToken(credentials) {
    const body = new URLSearchParams();
    body.set("grant_type", "client_credentials");
    body.set("client_id", credentials.clientId);
    body.set("client_secret", credentials.clientSecret);

    let response;

    try {
      response = await this.fetcher("https://openapi.tossinvest.com/oauth2/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: body.toString()
      });
    } catch (error) {
      throw new TossCredentialError(
        "toss_connection_failed",
        error instanceof Error ? error.message : "Toss token request failed",
        true
      );
    }

    if (!response.ok) {
      await mapTossAuthFailure(response);
    }

    let payload;

    try {
      payload = await response.json();
    } catch {
      throw new TossCredentialError(
        "toss_connection_failed",
        "Toss token response was not valid JSON",
        true
      );
    }

    if (typeof payload.access_token !== "string") {
      throw new TossCredentialError(
        "toss_connection_failed",
        "Toss token response did not include access_token",
        true
      );
    }

    return {
      accessToken: payload.access_token,
      expiresIn: typeof payload.expires_in === "number" ? payload.expires_in : 3600
    };
  }
}

function createCredentialStatus(credentials) {
  const configured = typeof credentials.clientId === "string" &&
    credentials.clientId !== "" &&
    typeof credentials.clientSecret === "string" &&
    credentials.clientSecret !== "";

  return {
    configured,
    maskedClientId: configured ? maskClientId(credentials.clientId) : null,
    lastValidatedAt: typeof credentials.lastValidatedAt === "string"
      ? credentials.lastValidatedAt
      : null,
    connectionStatus: configured
      ? credentials.connectionStatus ?? "saved"
      : "notConfigured"
  };
}

async function mapTossAuthFailure(response) {
  let payload = {};

  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (response.status === 401 || payload.error === "invalid_client") {
    throw new TossCredentialError(
      "invalid_toss_credentials",
      "Toss client id or secret is invalid",
      true
    );
  }

  throw new TossCredentialError(
    "toss_connection_failed",
    "Toss connection test failed",
    true
  );
}

function normalizeCredentialField(value, name) {
  const normalized = String(value ?? "").trim();

  if (normalized === "") {
    throw new TossCredentialError(
      "invalid_request",
      `${name} is required`,
      true
    );
  }

  return normalized;
}

function maskClientId(clientId) {
  if (clientId.length <= 8) {
    return "****";
  }

  return `${clientId.slice(0, 4)}…${clientId.slice(-4)}`;
}

module.exports = {
  StoredTossCredentialRepository,
  TossCredentialError,
  TossOAuthClient,
  createCredentialStatus
};

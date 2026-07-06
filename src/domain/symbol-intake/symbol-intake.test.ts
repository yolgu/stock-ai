import { describe, expect, it } from "vitest";

import {
  StockIdentityValidator,
  SymbolInputParser,
  VerifiedStockIdentity
} from "./SymbolIntake";

function createVerifiedIdentity(
  overrides: Partial<Parameters<typeof VerifiedStockIdentity.fromStockInfo>[0]> = {}
): VerifiedStockIdentity {
  return VerifiedStockIdentity.fromStockInfo({
    symbol: "MU",
    name: "마이크론 테크놀로지",
    englishName: "Micron Technology",
    market: "NASDAQ",
    securityType: "STOCK",
    status: "ACTIVE",
    currency: "USD",
    koreanMarketDetail: null,
    ...overrides
  });
}

describe("SymbolInputParser", () => {
  it("normalizes pasted US and Korean stock symbols", () => {
    const parser = new SymbolInputParser();

    expect(parser.parse("mu").candidates).toEqual([
      { symbol: "MU", expectedMarket: null, sourceText: "mu" }
    ]);
    expect(parser.parse("NASDAQ: MU").candidates).toEqual([
      { symbol: "MU", expectedMarket: "NASDAQ", sourceText: "NASDAQ: MU" }
    ]);
    expect(parser.parse("MU.US").candidates).toEqual([
      { symbol: "MU", expectedMarket: "US", sourceText: "MU.US" }
    ]);
    expect(parser.parse("005930 삼성전자").candidates).toEqual([
      { symbol: "005930", expectedMarket: null, sourceText: "005930 삼성전자" }
    ]);
    expect(parser.parse("마이크론 테크놀로지 MU").candidates).toEqual([
      { symbol: "MU", expectedMarket: null, sourceText: "마이크론 테크놀로지 MU" }
    ]);
  });

  it("parses comma separated input and removes duplicate symbols in first-seen order", () => {
    const parser = new SymbolInputParser();

    const result = parser.parse("AAPL, MSFT, mu, NASDAQ:MU");

    expect(result.candidates).toEqual([
      { symbol: "AAPL", expectedMarket: null, sourceText: "AAPL" },
      { symbol: "MSFT", expectedMarket: null, sourceText: "MSFT" },
      { symbol: "MU", expectedMarket: null, sourceText: "mu" }
    ]);
    expect(result.invalidInputs).toEqual([]);
  });

  it("reports pure Korean text as invalid symbol input", () => {
    const parser = new SymbolInputParser();

    expect(parser.parse("삼성전자").invalidInputs).toEqual(["삼성전자"]);
  });
});

describe("StockIdentityValidator", () => {
  it("accepts active tradable stock identities", () => {
    const validator = new StockIdentityValidator();

    expect(validator.validate(createVerifiedIdentity())).toEqual({
      type: "accepted",
      reasons: []
    });
  });

  it("requires confirmation for delisted, suspended, or liquidation stocks", () => {
    const validator = new StockIdentityValidator();

    expect(
      validator.validate(
        createVerifiedIdentity({
          status: "DELISTED"
        })
      )
    ).toEqual({
      type: "confirmation-required",
      reasons: ["delisted"]
    });
    expect(
      validator.validate(
        createVerifiedIdentity({
          market: "KOSPI",
          currency: "KRW",
          koreanMarketDetail: {
            liquidationTrading: true,
            nxtSupported: true,
            krxTradingSuspended: true,
            nxtTradingSuspended: false
          }
        })
      )
    ).toEqual({
      type: "confirmation-required",
      reasons: ["liquidation_trading", "trading_suspended"]
    });
  });
});

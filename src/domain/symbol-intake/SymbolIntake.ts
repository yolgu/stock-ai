export interface NormalizedSymbolDto {
  symbol: string;
  expectedMarket: string | null;
  sourceText: string;
}

export interface SymbolInputParseResult {
  candidates: NormalizedSymbolDto[];
  invalidInputs: string[];
}

export interface TossStockInfo {
  symbol: string;
  name: string;
  englishName: string;
  market: string;
  securityType: string;
  status: string;
  currency: string;
  koreanMarketDetail: KoreanMarketDetail | null;
}

export interface KoreanMarketDetail {
  liquidationTrading: boolean;
  nxtSupported: boolean;
  krxTradingSuspended: boolean;
  nxtTradingSuspended?: boolean | null;
}

export type StockIdentityConfirmationReason =
  | "delisted"
  | "inactive"
  | "liquidation_trading"
  | "trading_suspended";

export interface VerifiedStockIdentityDto {
  symbol: string;
  market: string;
  displayName: string;
  englishName: string;
  currency: string;
  status: string;
  securityType: string;
  tradingSuspended: boolean;
  liquidationTrading: boolean;
}

export type StockIdentityValidationResult =
  | {
      type: "accepted";
      reasons: [];
    }
  | {
      type: "confirmation-required";
      reasons: StockIdentityConfirmationReason[];
    };

export class SymbolInputParser {
  public parse(rawInput: string): SymbolInputParseResult {
    const segments = splitRawInput(rawInput);
    const candidates: NormalizedSymbolDto[] = [];
    const invalidInputs: string[] = [];
    const seenSymbols = new Set<string>();

    segments.forEach((segment) => {
      const parsedSymbols = parseSegment(segment);

      if (parsedSymbols.length === 0) {
        invalidInputs.push(segment);
        return;
      }

      parsedSymbols.forEach((candidate) => {
        if (!seenSymbols.has(candidate.symbol)) {
          candidates.push(candidate);
          seenSymbols.add(candidate.symbol);
        }
      });
    });

    return {
      candidates,
      invalidInputs
    };
  }
}

export class VerifiedStockIdentity {
  private constructor(private readonly state: VerifiedStockIdentityDto) {}

  public static fromStockInfo(stockInfo: TossStockInfo): VerifiedStockIdentity {
    const koreanMarketDetail = stockInfo.koreanMarketDetail;

    return new VerifiedStockIdentity({
      symbol: normalizeSymbol(stockInfo.symbol),
      market: normalizeMarket(stockInfo.market),
      displayName: stockInfo.name.trim(),
      englishName: stockInfo.englishName.trim(),
      currency: stockInfo.currency.trim().toUpperCase(),
      status: stockInfo.status.trim().toUpperCase(),
      securityType: stockInfo.securityType.trim().toUpperCase(),
      tradingSuspended: Boolean(
        koreanMarketDetail?.krxTradingSuspended ||
          koreanMarketDetail?.nxtTradingSuspended
      ),
      liquidationTrading: Boolean(koreanMarketDetail?.liquidationTrading)
    });
  }

  public status(): string {
    return this.state.status;
  }

  public isTradingSuspended(): boolean {
    return this.state.tradingSuspended;
  }

  public isLiquidationTrading(): boolean {
    return this.state.liquidationTrading;
  }

  public toDto(): VerifiedStockIdentityDto {
    return { ...this.state };
  }
}

export class StockIdentityValidator {
  public validate(identity: VerifiedStockIdentity): StockIdentityValidationResult {
    const reasons: StockIdentityConfirmationReason[] = [];

    if (identity.status() === "DELISTED") {
      reasons.push("delisted");
    } else if (identity.status() !== "ACTIVE") {
      reasons.push("inactive");
    }

    if (identity.isLiquidationTrading()) {
      reasons.push("liquidation_trading");
    }

    if (identity.isTradingSuspended()) {
      reasons.push("trading_suspended");
    }

    if (reasons.length === 0) {
      return {
        type: "accepted",
        reasons: []
      };
    }

    return {
      type: "confirmation-required",
      reasons
    };
  }
}

function splitRawInput(rawInput: string): string[] {
  return rawInput
    .split(/[,;\n]+/)
    .map((segment) => segment.trim())
    .filter((segment) => segment !== "");
}

function parseSegment(segment: string): NormalizedSymbolDto[] {
  const prefixed = segment.match(/^([A-Za-z_]+)\s*:\s*([A-Za-z0-9.-]+)$/);

  if (prefixed !== null && prefixed[1] !== undefined && prefixed[2] !== undefined) {
    return [
      {
        symbol: normalizeSymbol(prefixed[2]),
        expectedMarket: normalizeMarket(prefixed[1]),
        sourceText: segment
      }
    ];
  }

  const suffixed = segment.match(/^([A-Za-z0-9-]+)\.([A-Za-z]{2,})$/);

  if (suffixed !== null && suffixed[1] !== undefined && suffixed[2] !== undefined) {
    return [
      {
        symbol: normalizeSymbol(suffixed[1]),
        expectedMarket: normalizeMarket(suffixed[2]),
        sourceText: segment
      }
    ];
  }

  return extractPlainSymbols(segment).map((symbol) => ({
    symbol,
    expectedMarket: null,
    sourceText: segment
  }));
}

function extractPlainSymbols(segment: string): string[] {
  const candidates = new Set<string>();
  const numericMatches = segment.match(/\b\d{6}\b/g) ?? [];
  const tickerMatches = segment.match(/\b[A-Za-z][A-Za-z0-9.-]{0,31}\b/g) ?? [];

  numericMatches.forEach((value) => candidates.add(normalizeSymbol(value)));
  tickerMatches.forEach((value) => candidates.add(normalizeSymbol(value)));

  return [...candidates];
}

function normalizeSymbol(value: string): string {
  return value.trim().toUpperCase();
}

function normalizeMarket(value: string): string {
  return value.trim().toUpperCase();
}

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SensitiveValueCategory(str, Enum):
    ACCOUNT_NUMBER = "account_number"
    AWS_ACCESS_KEY = "aws_access_key"
    AUTHORIZATION_ASSIGNMENT = "authorization_assignment"
    BEARER_TOKEN = "bearer_token"
    CANO_ACCOUNT_NUMBER = "cano_account_number"
    DATABASE_URL_CREDENTIALS = "database_url_credentials"
    GENERIC_SECRET_ASSIGNMENT = "generic_secret_assignment"
    GITHUB_PERSONAL_ACCESS_TOKEN = "github_personal_access_token"
    GOOGLE_API_KEY = "google_api_key"
    KIS_API_CREDENTIAL = "kis_api_credential"
    OPENAI_API_KEY = "openai_api_key"
    PEM_PRIVATE_KEY = "pem_private_key"
    SLACK_TOKEN = "slack_token"
    TOSS_API_CREDENTIAL = "toss_api_credential"


@dataclass(frozen=True)
class SensitiveValueMatch:
    category: SensitiveValueCategory
    start_index: int
    end_index: int


@dataclass(frozen=True)
class _SensitiveValuePattern:
    category: SensitiveValueCategory
    expression: re.Pattern[str]


_TOKEN_CHARACTERS = r"A-Za-z0-9_./+=:@-"
_PATTERNS = (
    _SensitiveValuePattern(
        SensitiveValueCategory.KIS_API_CREDENTIAL,
        re.compile(
            rf"(?<![A-Za-z0-9_])[\"']?app[ _-]?(?:key|secret)"
            rf"[\"']?(?![A-Za-z0-9_])[ \t]*[:=][ \t]*[\"']?"
            r"(?!(?:redacted|example|placeholder|none|null|not[ _-]?set|unset)\b)"
            rf"[{_TOKEN_CHARACTERS}]{{8,}}",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.CANO_ACCOUNT_NUMBER,
        re.compile(
            r"(?<![A-Za-z0-9_])[\"']?cano[\"']?(?![A-Za-z0-9_])"
            r"[ \t]*[:=][ \t]*[\"']?[0-9]{8,}",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.AUTHORIZATION_ASSIGNMENT,
        re.compile(
            r"(?<![A-Za-z0-9_])[\"']?authorization"
            r"[\"']?(?![A-Za-z0-9_])[ \t]*[:=][ \t]*[\"']?"
            r"(?!(?:redacted|example|placeholder|none|null|not[ _-]?set|unset)\b)"
            rf"[{_TOKEN_CHARACTERS}]{{16,}}",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.TOSS_API_CREDENTIAL,
        re.compile(
            r"\bts(?:ck|sk)_(?:live|test|sandbox)_[A-Za-z0-9_-]{8,}\b",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.OPENAI_API_KEY,
        re.compile(r"\bsk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.AWS_ACCESS_KEY,
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.GITHUB_PERSONAL_ACCESS_TOKEN,
        re.compile(
            r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.GOOGLE_API_KEY,
        re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.SLACK_TOKEN,
        re.compile(
            r"\b(?:xox[baprs]-|xapp-|xwfp-)[A-Za-z0-9-]{20,}\b",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.BEARER_TOKEN,
        re.compile(
            r"\bbearer[ \t]+[A-Za-z0-9._~+/=-]{16,}"
            r"(?![A-Za-z0-9._~+/=-])",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.PEM_PRIVATE_KEY,
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.DATABASE_URL_CREDENTIALS,
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?)://"
            r"[^\s/:@]*:[^\s/@]+@[^\s]+",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.GENERIC_SECRET_ASSIGNMENT,
        re.compile(
            rf"(?<![A-Za-z0-9_])(?<!app-)(?<!app )[\"']?"
            r"(?:api[ _-]?key|client[ _-]?secret|secret[ _-]?key|"
            r"access[ _-]?token|refresh[ _-]?token|auth[ _-]?token|"
            r"private[ _-]?key|password|passwd|secret|token|key)"
            rf"[\"']?(?![A-Za-z0-9_])[ \t]*[:=][ \t]*[\"']?"
            r"(?!(?:redacted|example|placeholder|none|null|not[ _-]?set|unset)\b)"
            rf"[{_TOKEN_CHARACTERS}]{{8,}}",
            re.IGNORECASE,
        ),
    ),
    _SensitiveValuePattern(
        SensitiveValueCategory.ACCOUNT_NUMBER,
        re.compile(
            r"(?<![A-Za-z0-9_])[\"']?"
            r"(?:account(?:[ _-]?number)?|계좌번호)"
            r"[\"']?(?![A-Za-z0-9_])[ \t]*[:=][ \t]*[\"']?"
            r"[0-9][0-9 -]{6,22}[0-9]",
            re.IGNORECASE,
        ),
    ),
)


def find_sensitive_values(source: str) -> tuple[SensitiveValueMatch, ...]:
    matches = [
        SensitiveValueMatch(
            category=pattern.category,
            start_index=match.start(),
            end_index=match.end(),
        )
        for pattern in _PATTERNS
        for match in pattern.expression.finditer(source)
    ]
    return tuple(
        sorted(
            matches,
            key=lambda match: (
                match.start_index,
                match.end_index,
                match.category.value,
            ),
        )
    )

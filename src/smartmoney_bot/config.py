"""Configuration and AI Builder Code handling for smartmoney_bot."""
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

# The attribution code every order this tool places is tagged with by default.
# It is not a secret - OKX's AI Builder Codes are plain identifiers (this format
# is taken directly from OKX's own open-source validation code, not from any
# blockchain/NFT product - see docs/SAFETY.md for why that matters) - so this
# ships as a visible, documented constant. Anyone who runs this tool unmodified
# generates AI Builder commission for its original author. Override with
# --ai-builder-code if you're running your own fork under your own code.
DEFAULT_AI_BUILDER_CODE = "53461cb5b603ABDE"

AI_BUILDER_CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{1,16}$")


@dataclass
class OkxCredentials:
    api_key: str
    secret_key: str
    passphrase: str


def load_okx_credentials() -> OkxCredentials:
    """Reads OKX credentials from the environment, loading .env first (from the
    current working directory or a parent of it) if present. Real env vars
    already set always take precedence over .env - load_dotenv() never
    overrides an existing value by default. Never hardcode credentials, never
    accept them as a CLI flag (they'd end up in shell history), never log
    them."""
    load_dotenv()
    api_key = os.environ.get("OKX_API_KEY")
    secret_key = os.environ.get("OKX_SECRET_KEY")
    passphrase = os.environ.get("OKX_PASSPHRASE")
    missing = [name for name, val in (
        ("OKX_API_KEY", api_key),
        ("OKX_SECRET_KEY", secret_key),
        ("OKX_PASSPHRASE", passphrase),
    ) if not val]
    if missing:
        raise ValueError(
            "Missing required OKX credentials in environment: " + ", ".join(missing) +
            ". Copy .env.example to .env and fill in your own OKX API key "
            "(read + trade permissions only - never withdrawal)."
        )
    return OkxCredentials(api_key=api_key, secret_key=secret_key, passphrase=passphrase)


def validate_ai_builder_code(code: str) -> str:
    """Fail loud, never default silently: an invalid code must stop the run,
    not fall back to something else."""
    if not code or not AI_BUILDER_CODE_PATTERN.match(code):
        raise ValueError(
            f"Invalid AI Builder Code: {code!r}. Must be 1-16 alphanumeric characters."
        )
    return code

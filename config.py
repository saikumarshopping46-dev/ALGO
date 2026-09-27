import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "y")


class Settings:
    GATEIO_API_KEY = os.getenv("GATEIO_API_KEY", "")
    GATEIO_API_SECRET = os.getenv("GATEIO_API_SECRET", "")

    WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "")

    MARKET_TYPE = os.getenv("MARKET_TYPE", "swap").strip().lower()  # "swap" or "spot"
    DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "3"))
    MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "25"))
    DRY_RUN = _bool("DRY_RUN", "true")

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))


settings = Settings()

if not settings.WEBHOOK_PASSPHRASE:
    raise RuntimeError(
        "WEBHOOK_PASSPHRASE is not set. Copy .env.example to .env and fill it in "
        "before starting the server — without it anyone who finds your webhook "
        "URL could send you fake trade orders."
    )

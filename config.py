import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    """Мини-парсер .env, чтобы не тащить python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    token: str
    tz: ZoneInfo
    db_path: str
    tg_proxy: str | None
    ruz_proxy: str | None
    ruz_verify_ssl: bool
    allowed_users: frozenset[int]


def _load() -> Settings:
    _load_env(BASE_DIR / ".env")
    users = os.getenv("ALLOWED_USERS", "")
    return Settings(
        token=os.getenv("BOT_TOKEN", ""),
        tz=ZoneInfo(os.getenv("TZ_NAME", "Europe/Moscow")),
        db_path=os.getenv("DB_PATH", str(BASE_DIR / "diary.db")),
        tg_proxy=os.getenv("TG_PROXY") or None,
        ruz_proxy=os.getenv("RUZ_PROXY") or None,
        ruz_verify_ssl=os.getenv("RUZ_VERIFY_SSL", "1") != "0",
        allowed_users=frozenset(int(u) for u in users.replace(" ", "").split(",") if u),
    )


settings = _load()
TZ = settings.tz

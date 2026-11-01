import os
from dataclasses import dataclass

from dotenv import load_dotenv

from logic import ALLOWED_OFFER_HOURS

load_dotenv()


def _opt_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    session_name: str
    accept_min_stars: int | None     # None = never auto-accept incoming offers
    decline_below_stars: int | None  # None = never auto-decline incoming offers
    offer_codeword: str              # empty = offer command disabled
    offer_max_stars: int             # hard cap for any single offer
    offer_duration_sec: int


def load_settings() -> Settings:
    api_id = _opt_int("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise SystemExit("TG_API_ID and TG_API_HASH are required (create them at https://my.telegram.org).")

    accept_min = _opt_int("OFFER_ACCEPT_MIN_STARS")
    decline_below = _opt_int("OFFER_DECLINE_BELOW_STARS")
    if accept_min is not None and decline_below is not None and decline_below > accept_min:
        raise SystemExit("OFFER_DECLINE_BELOW_STARS must not be greater than OFFER_ACCEPT_MIN_STARS")

    offer_hours = int(os.getenv("OFFER_DURATION_HOURS", "6").strip() or "6")
    if offer_hours not in ALLOWED_OFFER_HOURS:
        raise SystemExit(f"OFFER_DURATION_HOURS must be one of {ALLOWED_OFFER_HOURS}")

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        session_name=os.getenv("TG_SESSION", "owner").strip() or "owner",
        accept_min_stars=accept_min,
        decline_below_stars=decline_below,
        offer_codeword=os.getenv("OFFER_CODEWORD", "").strip(),
        offer_max_stars=int(os.getenv("OFFER_MAX_STARS", "1000").strip() or "1000"),
        offer_duration_sec=offer_hours * 3600,
    )

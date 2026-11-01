"""Pure logic: command parsing and offer rules. No network access, so it's unit-testable."""

import re
from dataclasses import dataclass

# https://t.me/nft/SignetRing-4557  ->  "SignetRing-4557"  (scheme is optional)
NFT_LINK_RE = re.compile(r"(?:https?://)?t\.me/nft/([A-Za-z0-9][A-Za-z0-9_-]*)", re.IGNORECASE)

# Offer durations Telegram accepts, in hours.
ALLOWED_OFFER_HOURS = (6, 12, 24, 36, 48, 72)


def has_codeword(text: str | None, codeword: str) -> bool:
    """True if the codeword appears as a separate word in the text."""
    if not text or not codeword:
        return False
    target = codeword.casefold()
    return any(word.casefold() == target for word in text.split())


@dataclass(frozen=True)
class OfferCommand:
    slug: str
    price: int


def parse_offer_command(text: str | None, codeword: str) -> OfferCommand | None:
    """Parse "<codeword> <gift link> <price in Stars>", in any order.

    Returns None unless the codeword is present, exactly one NFT link is present
    and exactly one positive integer (the price) is present.
    """
    if not has_codeword(text, codeword):
        return None
    link = NFT_LINK_RE.search(text)
    if link is None:
        return None
    words = [w for w in text.split() if w.casefold() != codeword.casefold()]
    rest = " ".join(words).replace(link.group(0), " ")
    numbers = re.findall(r"\d{1,9}", rest)
    if len(numbers) != 1:
        return None
    price = int(numbers[0])
    if price <= 0:
        return None
    return OfferCommand(slug=link.group(1), price=price)


def validate_offer(price: int, max_stars: int, gift_min_stars: int | None) -> str | None:
    """Return an error message if the offer must not be sent, otherwise None."""
    if price > max_stars:
        return f"сумма {price} ⭐ больше лимита OFFER_MAX_STARS ({max_stars} ⭐)"
    if gift_min_stars is not None and price < gift_min_stars:
        return f"сумма {price} ⭐ ниже минимума для этого подарка ({gift_min_stars} ⭐)"
    return None


@dataclass(frozen=True)
class Decision:
    action: str  # "accept" | "decline" | "notify"
    reason: str


def decide_offer(price_stars: int, accept_min: int | None, decline_below: int | None) -> Decision:
    """Decide what to do with an incoming gift offer.

    - accept_min is None    -> never auto-accept
    - decline_below is None -> never auto-decline
    - anything else         -> "notify": the owner decides in the Telegram client
    """
    if accept_min is not None and price_stars >= accept_min:
        return Decision("accept", f"{price_stars} >= {accept_min} Stars")
    if decline_below is not None and price_stars < decline_below:
        return Decision("decline", f"{price_stars} < {decline_below} Stars")
    return Decision("notify", "outside auto rules, owner decides")

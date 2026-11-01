"""Runs on your own Telegram account (MTProto via Telethon). It sends nothing to clients or to a bot.

Two things happen here:
1. Offer command. In a private chat with someone, you type "<codeword> <t.me/nft link> <price>".
   The message is deleted, then a purchase offer is sent for that gift, but only if the gift
   belongs to the person you're chatting with.
2. Incoming offers. Telegram's offer message is handled by the thresholds in .env
   (accept, decline, or leave it to you).

Why there is no bot: only user accounts can send or resolve gift offers
(payments.sendStarGiftOffer, payments.resolveStarGiftOffer). The Bot API has neither.

Security: the session file is a full login to your account. Keep it private.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from telethon import TelegramClient, events, types
from telethon.tl.functions.payments import (
    GetUniqueStarGiftRequest,
    ResolveStarGiftOfferRequest,
    SendStarGiftOfferRequest,
)

from config import Settings, load_settings
from logic import decide_offer, has_codeword, parse_offer_command, validate_offer

log = logging.getLogger("owner_session")


def _gift_label(gift: Any) -> str:
    title = getattr(gift, "title", None) or "подарок"
    num = getattr(gift, "num", None)
    return f"{title} #{num}" if num else title


def _peer_user_id(peer: Any) -> int:
    return getattr(peer, "user_id", None) or getattr(peer, "chat_id", None) or getattr(peer, "channel_id", 0)


def _private_text(update: Any) -> tuple[int, int, str, bool] | None:
    """(message id, other party's user id, text, is_outgoing) for private text messages."""
    if isinstance(update, types.UpdateShortMessage):
        # For outgoing short messages Telethon treats user_id as the recipient, which is the chat partner.
        return update.id, update.user_id, update.message or "", bool(update.out)
    msg = getattr(update, "message", None)
    if isinstance(msg, types.Message) and isinstance(msg.peer_id, types.PeerUser):
        return msg.id, msg.peer_id.user_id, msg.message or "", bool(msg.out)
    return None


async def _sender_label(client: Any, peer: Any) -> str:
    try:
        entity = await client.get_entity(peer)
        name = " ".join(p for p in (getattr(entity, "first_name", None), getattr(entity, "last_name", None)) if p)
        return name or getattr(entity, "username", None) or str(_peer_user_id(peer))
    except Exception:
        return str(_peer_user_id(peer))


def _done(outcome: str) -> str:
    log.info(outcome)
    return outcome


async def handle_update(
    update: Any,
    *,
    client: Any,
    settings: Settings,
    handled: set[tuple[int, int]],
    now: datetime | None = None,
) -> str | None:
    """Handle an incoming gift offer. Returns the outcome, or None if it's not an open offer to us."""
    msg = getattr(update, "message", None)
    if not isinstance(msg, types.MessageService):
        return None
    action = msg.action
    if not isinstance(action, types.MessageActionStarGiftPurchaseOffer):
        return None
    if msg.out or action.accepted or action.declined:
        return None

    now = now or datetime.now(timezone.utc)
    if action.expires_at is not None and action.expires_at <= now:
        return None
    # Message ids are only unique inside one chat, so the key includes the peer.
    key = (_peer_user_id(msg.peer_id), msg.id)
    if key in handled:
        return None
    handled.add(key)

    # Decisions use the price from Telegram's service message, never text a client typed.
    price = int(action.price.amount)
    gift = _gift_label(action.gift)
    sender = await _sender_label(client, msg.peer_id)

    decision = decide_offer(price, settings.accept_min_stars, settings.decline_below_stars)
    outcome = "ждёт вашего решения до истечения срока"
    if decision.action in ("accept", "decline"):
        decline = decision.action == "decline"
        try:
            await client(ResolveStarGiftOfferRequest(offer_msg_id=msg.id, decline=decline))
            outcome = "отклонено автоматически" if decline else "принято автоматически"
        except Exception as exc:
            log.exception("failed to resolve offer %s", msg.id)
            outcome = f"автоматически не удалось ({type(exc).__name__}: {exc}), решите вручную"
    return _done(f"предложение от {sender}: {gift} за {price} ⭐, правило: {decision.reason}, {outcome}")


async def handle_command(
    update: Any,
    *,
    client: Any,
    settings: Settings,
    me_id: int,
    handled: set[tuple[int, int]],
) -> str | None:
    """Type "<codeword> <gift link> <price>" in a private chat. The message is deleted and an offer is sent."""
    if not settings.offer_codeword:
        return None
    parsed = _private_text(update)
    if parsed is None:
        return None
    msg_id, chat_user_id, text, outgoing = parsed
    # Only messages you wrote, in a private chat with someone other than yourself.
    if not outgoing or chat_user_id == me_id or not has_codeword(text, settings.offer_codeword):
        return None
    key = (chat_user_id, msg_id)
    if key in handled:
        return None
    handled.add(key)

    # Remove the command first, so the other person doesn't keep seeing it.
    try:
        chat = await client.get_input_entity(chat_user_id)
        await client.delete_messages(chat, [msg_id], revoke=True)
    except Exception as exc:
        log.warning("не удалось удалить сообщение %s: %s", msg_id, exc)

    cmd = parse_offer_command(text, settings.offer_codeword)
    if cmd is None:
        return _done("неверный формат команды, оффер не отправлен")

    try:
        info = await client(GetUniqueStarGiftRequest(slug=cmd.slug))
    except Exception as exc:
        return _done(f"подарок {cmd.slug} не найден: {type(exc).__name__}: {exc}")

    gift = info.gift
    label = _gift_label(gift)
    owner_id = getattr(gift.owner_id, "user_id", None)
    if owner_id is None:
        return _done(f"{label}: владелец не пользователь, оффер не отправлен")
    if owner_id != chat_user_id:
        return _done(f"{label} принадлежит не собеседнику из этого чата, оффер не отправлен")

    error = validate_offer(cmd.price, settings.offer_max_stars, getattr(gift, "offer_min_stars", None))
    if error:
        return _done(f"{label}: оффер не отправлен, {error}")

    try:
        peer = await client.get_input_entity(owner_id)
        await client(
            SendStarGiftOfferRequest(
                peer=peer,
                slug=cmd.slug,
                price=types.StarsAmount(amount=cmd.price, nanos=0),
                duration=settings.offer_duration_sec,
            )
        )
    except Exception as exc:
        log.exception("failed to send offer for %s", cmd.slug)
        return _done(f"{label}: оффер не отправлен: {type(exc).__name__}: {exc}")

    hours = settings.offer_duration_sec // 3600
    return _done(f"оффер отправлен: {label} за {cmd.price} ⭐, срок {hours} ч")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    offers_handled: set[tuple[int, int]] = set()
    commands_handled: set[tuple[int, int]] = set()

    # First run asks for the phone number, login code and 2FA password, then saves the session.
    await client.start()
    me = await client.get_me()
    # Load the dialog list so chats can be addressed by user id (needed to delete and offer).
    await client.get_dialogs(limit=None)
    log.info("вошли как %s (id %s), жду команды и предложения", me.first_name, me.id)

    async def on_update(update: Any) -> None:
        try:
            await handle_update(update, client=client, settings=settings, handled=offers_handled)
            await handle_command(
                update,
                client=client,
                settings=settings,
                me_id=me.id,
                handled=commands_handled,
            )
        except Exception:
            log.exception("unexpected error while handling update")

    client.add_event_handler(
        on_update,
        events.Raw(types=(types.UpdateNewMessage, types.UpdateShortMessage)),
    )
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

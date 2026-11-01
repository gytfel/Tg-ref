import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from telethon import types  # noqa: E402
from telethon.tl.functions.payments import (  # noqa: E402
    GetUniqueStarGiftRequest,
    ResolveStarGiftOfferRequest,
    SendStarGiftOfferRequest,
)

from config import Settings  # noqa: E402
from owner_session import handle_command, handle_update  # noqa: E402

FUTURE = datetime.now(timezone.utc) + timedelta(hours=5)
ME_ID = 1
CHAT_USER = 42  # the person you are chatting with
CODEWORD = "апельсин"
CMD = f"{CODEWORD} https://t.me/nft/SignetRing-4557 500"


def settings(accept_min=None, decline_below=None, codeword=CODEWORD, max_stars=1000) -> Settings:
    return Settings(
        api_id=1,
        api_hash="x",
        session_name="test",
        accept_min_stars=accept_min,
        decline_below_stars=decline_below,
        offer_codeword=codeword,
        offer_max_stars=max_stars,
        offer_duration_sec=6 * 3600,
    )


def command_update(text, out=True, peer_id=CHAT_USER, msg_id=500):
    message = types.Message(
        id=msg_id,
        peer_id=types.PeerUser(user_id=peer_id),
        date=datetime.now(timezone.utc),
        message=text,
        out=out,
    )
    return types.UpdateNewMessage(message=message, pts=1, pts_count=1)


def short_command_update(text, msg_id=501):
    # Telegram sends some private text messages as updateShortMessage.
    return types.UpdateShortMessage(
        out=True, id=msg_id, user_id=CHAT_USER, message=text, pts=1, pts_count=1, date=datetime.now(timezone.utc)
    )


def offer_update(msg_id=100, price=999, expires_at=FUTURE, out=False, accepted=None, declined=None, peer_id=CHAT_USER):
    action = types.MessageActionStarGiftPurchaseOffer(
        gift=SimpleNamespace(title="Signet Ring", num=4557),
        price=types.StarsAmount(amount=price, nanos=0),
        expires_at=expires_at,
        accepted=accepted,
        declined=declined,
    )
    service = types.MessageService(
        id=msg_id,
        peer_id=types.PeerUser(user_id=peer_id),
        date=datetime.now(timezone.utc),
        action=action,
        out=out,
    )
    return types.UpdateNewMessage(message=service, pts=1, pts_count=1)


class FakeClient:
    """Stands in for TelegramClient. Records what would have been sent to Telegram."""

    def __init__(self, owner_id=CHAT_USER, offer_min=None, send_error=None, delete_error=None, resolve_error=None):
        self.owner_peer = types.PeerUser(user_id=owner_id) if owner_id is not None else types.PeerChannel(channel_id=5)
        self.offer_min = offer_min
        self.send_error = send_error
        self.delete_error = delete_error
        self.resolve_error = resolve_error
        self.sent = []
        self.resolved = []
        self.deleted = []

    async def __call__(self, request):
        if isinstance(request, GetUniqueStarGiftRequest):
            gift = SimpleNamespace(title="Signet Ring", num=4557, owner_id=self.owner_peer, offer_min_stars=self.offer_min)
            return SimpleNamespace(gift=gift, users=[], chats=[])
        if isinstance(request, SendStarGiftOfferRequest):
            if self.send_error:
                raise self.send_error
            self.sent.append(request)
            return None
        if isinstance(request, ResolveStarGiftOfferRequest):
            if self.resolve_error:
                raise self.resolve_error
            self.resolved.append(request)
            return None
        raise AssertionError(f"unexpected request {request!r}")

    async def delete_messages(self, entity, message_ids, revoke=True):
        if self.delete_error:
            raise self.delete_error
        self.deleted.append((entity, list(message_ids), revoke))

    async def get_input_entity(self, user_id):
        return types.InputPeerUser(user_id=user_id, access_hash=0)

    async def get_entity(self, peer):
        return SimpleNamespace(first_name="Buyer", last_name=None, username="buyer")


def run_command(update, s=None, client=None, handled=None):
    client = client or FakeClient()
    outcome = asyncio.run(
        handle_command(
            update,
            client=client,
            settings=s or settings(),
            me_id=ME_ID,
            handled=handled if handled is not None else set(),
        )
    )
    return outcome, client


def run_incoming(update, s=None, client=None, handled=None):
    client = client or FakeClient()
    outcome = asyncio.run(
        handle_update(
            update,
            client=client,
            settings=s or settings(),
            handled=handled if handled is not None else set(),
        )
    )
    return outcome, client


class OfferCommandTests(unittest.TestCase):
    def test_sends_offer_and_deletes_command(self):
        outcome, client = run_command(command_update(CMD))
        self.assertIn("оффер отправлен", outcome)
        self.assertEqual(len(client.sent), 1)
        req = client.sent[0]
        self.assertEqual(req.slug, "SignetRing-4557")
        self.assertEqual(req.price.amount, 500)
        self.assertEqual(req.duration, 6 * 3600)
        self.assertEqual(req.peer.user_id, CHAT_USER)
        self.assertEqual(len(client.deleted), 1)
        _, ids, revoke = client.deleted[0]
        self.assertEqual(ids, [500])
        self.assertTrue(revoke)

    def test_short_message_form_also_works(self):
        outcome, client = run_command(short_command_update(CMD))
        self.assertIn("оффер отправлен", outcome)
        self.assertEqual(client.deleted[0][1], [501])

    def test_codeword_is_case_insensitive(self):
        _, client = run_command(command_update("АПЕЛЬСИН https://t.me/nft/SignetRing-4557 100"))
        self.assertEqual(len(client.sent), 1)

    def test_wrong_codeword_is_ignored_and_not_deleted(self):
        outcome, client = run_command(command_update("неверно https://t.me/nft/SignetRing-4557 500"))
        self.assertIsNone(outcome)
        self.assertEqual(client.sent, [])
        self.assertEqual(client.deleted, [])

    def test_message_from_other_person_is_ignored(self):
        outcome, client = run_command(command_update(CMD, out=False))
        self.assertIsNone(outcome)
        self.assertEqual(client.sent, [])
        self.assertEqual(client.deleted, [])

    def test_message_to_yourself_is_ignored(self):
        outcome, client = run_command(command_update(CMD, peer_id=ME_ID))
        self.assertIsNone(outcome)
        self.assertEqual(client.deleted, [])

    def test_disabled_when_no_codeword(self):
        outcome, client = run_command(command_update(CMD), s=settings(codeword=""))
        self.assertIsNone(outcome)
        self.assertEqual(client.sent, [])
        self.assertEqual(client.deleted, [])

    def test_gift_owned_by_someone_else_is_refused_but_command_deleted(self):
        outcome, client = run_command(command_update(CMD), client=FakeClient(owner_id=99))
        self.assertIn("не собеседнику", outcome)
        self.assertEqual(client.sent, [])
        self.assertEqual(len(client.deleted), 1)

    def test_gift_not_owned_by_user_is_refused(self):
        outcome, client = run_command(command_update(CMD), client=FakeClient(owner_id=None))
        self.assertIn("не пользователь", outcome)
        self.assertEqual(client.sent, [])

    def test_bad_format_is_deleted_and_not_sent(self):
        outcome, client = run_command(command_update(f"{CODEWORD} https://t.me/nft/SignetRing-4557"))
        self.assertIn("неверный формат", outcome)
        self.assertEqual(client.sent, [])
        self.assertEqual(len(client.deleted), 1)

    def test_refuses_above_cap(self):
        outcome, client = run_command(
            command_update(f"{CODEWORD} https://t.me/nft/SignetRing-4557 5000"), s=settings(max_stars=1000)
        )
        self.assertIn("больше лимита", outcome)
        self.assertEqual(client.sent, [])

    def test_refuses_below_gift_minimum(self):
        outcome, client = run_command(command_update(f"{CODEWORD} https://t.me/nft/SignetRing-4557 50"),
                                      client=FakeClient(offer_min=100))
        self.assertIn("ниже минимума", outcome)
        self.assertEqual(client.sent, [])

    def test_reports_telegram_error(self):
        outcome, _ = run_command(command_update(CMD), client=FakeClient(send_error=ValueError("STARGIFT_OFFER_NOT_ALLOWED")))
        self.assertIn("не отправлен", outcome)
        self.assertIn("STARGIFT_OFFER_NOT_ALLOWED", outcome)

    def test_offer_still_sent_if_delete_fails(self):
        outcome, client = run_command(command_update(CMD), client=FakeClient(delete_error=RuntimeError("no rights")))
        self.assertIn("оффер отправлен", outcome)
        self.assertEqual(len(client.sent), 1)

    def test_same_message_is_not_processed_twice(self):
        handled = set()
        cmd = command_update(CMD)
        run_command(cmd, handled=handled)
        outcome, client = run_command(cmd, handled=handled)
        self.assertIsNone(outcome)
        self.assertEqual(client.sent, [])


class IncomingOfferTests(unittest.TestCase):
    def test_accepts_when_price_meets_minimum(self):
        outcome, client = run_incoming(offer_update(price=999), settings(accept_min=500))
        self.assertEqual(outcome.split(", ")[-1], "принято автоматически")
        self.assertEqual(len(client.resolved), 1)
        self.assertEqual(client.resolved[0].offer_msg_id, 100)
        self.assertFalse(client.resolved[0].decline)

    def test_declines_below_threshold(self):
        outcome, client = run_incoming(offer_update(price=50), settings(accept_min=500, decline_below=100))
        self.assertIn("отклонено автоматически", outcome)
        self.assertTrue(client.resolved[0].decline)

    def test_no_rules_only_logs(self):
        outcome, client = run_incoming(offer_update(price=999), settings())
        self.assertIn("ждёт вашего решения", outcome)
        self.assertEqual(client.resolved, [])

    def test_ignores_offers_made_by_owner(self):
        outcome, client = run_incoming(offer_update(out=True), settings(accept_min=1))
        self.assertIsNone(outcome)
        self.assertEqual(client.resolved, [])

    def test_ignores_already_resolved_offers(self):
        self.assertIsNone(run_incoming(offer_update(accepted=True), settings(accept_min=1))[0])
        self.assertIsNone(run_incoming(offer_update(declined=True), settings(accept_min=1))[0])

    def test_ignores_expired_offers(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.assertIsNone(run_incoming(offer_update(expires_at=past), settings(accept_min=1))[0])

    def test_handles_each_offer_once(self):
        handled = set()
        first = run_incoming(offer_update(), settings(accept_min=1), handled=handled)
        second = run_incoming(offer_update(), settings(accept_min=1), handled=handled)
        self.assertIsNotNone(first[0])
        self.assertIsNone(second[0])

    def test_same_message_id_in_two_chats_are_both_handled(self):
        handled = set()
        first = run_incoming(offer_update(msg_id=100), settings(accept_min=1), handled=handled)
        second = run_incoming(offer_update(msg_id=100, peer_id=43), settings(accept_min=1), handled=handled)
        self.assertIsNotNone(first[0])
        self.assertIsNotNone(second[0])

    def test_ignores_plain_messages(self):
        plain = types.UpdateNewMessage(
            message=types.Message(id=5, peer_id=types.PeerUser(user_id=CHAT_USER), date=datetime.now(timezone.utc), message="hi"),
            pts=1,
            pts_count=1,
        )
        self.assertIsNone(run_incoming(plain, settings(accept_min=1))[0])


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from logic import (  # noqa: E402
    decide_offer,
    has_codeword,
    parse_offer_command,
    validate_offer,
)


class ParseOfferCommandTests(unittest.TestCase):
    def test_basic_command(self):
        cmd = parse_offer_command("апельсин https://t.me/nft/SignetRing-4557 500", "апельсин")
        self.assertEqual((cmd.slug, cmd.price), ("SignetRing-4557", 500))

    def test_order_does_not_matter_and_stars_word_is_fine(self):
        cmd = parse_offer_command("300 stars t.me/nft/Plush-Pepe-12 апельсин", "апельсин")
        self.assertEqual((cmd.slug, cmd.price), ("Plush-Pepe-12", 300))

    def test_codeword_with_digits_is_not_a_price(self):
        cmd = parse_offer_command("code7 https://t.me/nft/SignetRing-4557 250", "code7")
        self.assertEqual(cmd.price, 250)

    def test_missing_codeword(self):
        self.assertIsNone(parse_offer_command("https://t.me/nft/SignetRing-4557 500", "апельсин"))

    def test_codeword_inside_other_word_does_not_count(self):
        self.assertIsNone(parse_offer_command("апельсиновый https://t.me/nft/SignetRing-4557 500", "апельсин"))

    def test_missing_link_or_price(self):
        self.assertIsNone(parse_offer_command("апельсин 500", "апельсин"))
        self.assertIsNone(parse_offer_command("апельсин https://t.me/nft/SignetRing-4557", "апельсин"))

    def test_two_numbers_is_ambiguous(self):
        self.assertIsNone(parse_offer_command("апельсин https://t.me/nft/SignetRing-4557 500 600", "апельсин"))

    def test_zero_price_rejected(self):
        self.assertIsNone(parse_offer_command("апельсин https://t.me/nft/SignetRing-4557 0", "апельсин"))

    def test_empty_codeword_disables(self):
        self.assertIsNone(parse_offer_command("https://t.me/nft/SignetRing-4557 500", ""))

    def test_has_codeword(self):
        self.assertTrue(has_codeword("привет АПЕЛЬСИН", "апельсин"))
        self.assertFalse(has_codeword("привет", "апельсин"))


class ValidateOfferTests(unittest.TestCase):
    def test_ok(self):
        self.assertIsNone(validate_offer(500, 1000, None))
        self.assertIsNone(validate_offer(500, 1000, 400))

    def test_over_cap(self):
        self.assertIn("больше лимита", validate_offer(1001, 1000, None))

    def test_below_gift_minimum(self):
        self.assertIn("ниже минимума", validate_offer(99, 1000, 100))


class DecideOfferTests(unittest.TestCase):
    def test_accept_at_or_above_minimum(self):
        self.assertEqual(decide_offer(500, 500, None).action, "accept")
        self.assertEqual(decide_offer(999, 500, None).action, "accept")

    def test_decline_below_threshold(self):
        self.assertEqual(decide_offer(100, 500, 200).action, "decline")

    def test_between_thresholds_is_notify(self):
        self.assertEqual(decide_offer(300, 500, 200).action, "notify")

    def test_no_rules_always_notify(self):
        self.assertEqual(decide_offer(10_000, None, None).action, "notify")
        self.assertEqual(decide_offer(1, None, None).action, "notify")


if __name__ == "__main__":
    unittest.main()

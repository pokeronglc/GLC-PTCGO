import unittest

from spirit.game.attributes import AttrID
from spirit.packets.handlers.auth import currency_caps_packet


class CurrencyCapsTests(unittest.TestCase):
    """Without a cap the client warns 'maximum of 0 Trainer Tokens' before Versus."""

    def test_every_wallet_currency_has_a_high_cap(self):
        packet = currency_caps_packet()
        self.assertEqual(packet["messageName"], "CurrencyCaps")
        caps = {c["name"]: c["value"] for c in packet["currencies"]}
        for attr in (AttrID.TRAINER_TOKENS, AttrID.GEMS, AttrID.EVENT_TICKETS):
            self.assertGreaterEqual(caps[attr.value], 25_000)
            # Client: Convert.ToInt16(cap * 0.8) -- larger caps throw OverflowException.
            self.assertLessEqual(int(caps[attr.value] * 0.8), 32767)


if __name__ == "__main__":
    unittest.main()

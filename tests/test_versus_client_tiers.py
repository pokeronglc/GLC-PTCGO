import json
import os
import unittest

from spirit.game.models.versus import (CLIENT_TIER_COUNT, VersusSeason,
                                       client_tiers)


def _tok(n):
    return {"name": f"{n} Tokens", "rewardType": "Tokens", "rewardAmount": n,
            "rewardCurrency": "prizeTrainerCoin"}


def _season(tiers):
    return VersusSeason.from_dict({"seasonID": "S", "startTime": 1, "endTime": 2,
                                   "tiers": tiers})


class ClientTierTests(unittest.TestCase):
    """The Versus screen indexes Tiers[0..2] and Last() of each unguarded."""

    def _assert_safe(self, tiers):
        self.assertEqual(len(tiers), CLIENT_TIER_COUNT)
        for t in tiers:
            self.assertTrue(t["rewards"])
        last = [max(int(k) for k in t["rewards"]) for t in tiers]
        self.assertEqual(last, sorted(last))

    def test_single_tier_single_milestone(self):
        s = _season([{"rewards": {"10000": [_tok(10)]}}])
        out = s.to_client_dict()["tiers"]
        self._assert_safe(out)
        self.assertEqual(len(s.tiers), 1)          # real season untouched

    def test_single_tier_many_milestones_spread(self):
        s = _season([{"rewards": {str(p): [_tok(1)] for p in (10, 20, 30, 40, 50, 60)}}])
        out = s.to_client_dict()["tiers"]
        self._assert_safe(out)
        self.assertEqual([sorted(map(int, t["rewards"])) for t in out],
                         [[10, 20], [30, 40], [50, 60]])

    def test_empty_tier_is_filled(self):
        s = _season([{"rewards": {"10": [_tok(1)]}}, {"rewards": {}},
                     {"rewards": {"30": [_tok(1)]}}])
        self._assert_safe(s.to_client_dict()["tiers"])

    def test_three_full_tiers_kept_as_is(self):
        tiers = [{"rewards": {str(p): [_tok(1)]}} for p in (10, 50, 100)]
        s = _season(tiers)
        self.assertEqual(s.to_client_dict()["tiers"], [t.to_dict() for t in s.tiers])

    def test_no_season_fallback(self):
        self._assert_safe(client_tiers([]))

    def test_shipped_season_file(self):
        path = os.path.join(os.path.dirname(__file__), "..", "spirit", "database",
                            "json_data", "versus_seasons.json")
        for raw in json.load(open(path)):
            self._assert_safe(VersusSeason.from_dict(raw).to_client_dict()["tiers"])


if __name__ == "__main__":
    unittest.main()

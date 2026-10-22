"""Versus screen pop-ups: ladder reset and first-visit tips shouldn't repeat."""
import json
import os
import unittest
from unittest.mock import patch

from spirit.game import account_attributes as aa


def client_long(high, low):
    # K.L.GetLongAccountSetting: (high << 32) + (low & 0xFFFFFFFF)
    return (high << 32) + (low & 0xFFFFFFFF)


class VersusPopupTests(unittest.TestCase):
    def test_season_times_round_trip_through_client_halves(self):
        for value in (1767225600000, 4102444800000, 1):
            high, low = aa._long_halves(value)
            self.assertTrue(-2**31 <= high < 2**31 and -2**31 <= low < 2**31)
            self.assertEqual(client_long(high, low), value)

    def test_login_seeds_the_last_seen_season(self):
        season = type('S', (), {'season_id': 'Season1', 'start_time': 1767225600000,
                                'end_time': 4102444800000})()
        saved = {}
        with patch.object(aa.VersusSeasonManager, 'get_active_season', return_value=season), \
                patch.object(aa.versus_data, 'get_progress', return_value=(0, 0)), \
                patch.object(aa, 'merge_account_settings',
                             side_effect=lambda account, s: saved.update(s)):
            aa.anchor_versus_animation('acct')
        self.assertEqual(saved[108], 1)
        self.assertEqual(client_long(saved[111], saved[112]), season.start_time)
        self.assertEqual(client_long(saved[113], saved[114]), season.end_time)

    def test_season_start_is_not_zero(self):
        path = os.path.join(os.path.dirname(aa.__file__), '..', 'database',
                            'json_data', 'versus_seasons.json')
        for season in json.load(open(path)):
            self.assertTrue(season['startTime'])

    def test_every_intro_scene_is_reported_visited(self):
        with patch.object(aa.VersusSeasonManager, 'get_active_season', return_value=None), \
                patch.object(aa.versus_data, 'get_progress', return_value=(0, 0)), \
                patch.object(aa, 'get_account_settings', return_value={}), \
                patch.object(aa, 'get_screen_name', return_value='x'):
            attributes = aa.build_account_attributes('acct')
        visited = next(a['value'] for a in attributes if a['name'] == 202101)
        self.assertIn('VersusUpdate', visited)
        self.assertIn('Versus', visited)


if __name__ == "__main__":
    unittest.main()

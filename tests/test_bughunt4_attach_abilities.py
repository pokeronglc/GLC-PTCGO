"""Bug hunt 4c (Oct 15): live-deck Abilities that attach Energy with a
restriction -- which Energy, which Pokémon, and where the Ability's owner
must be (pattern behind the Larry's Komala report)."""
import unittest

from tests.test_untested_trainers import Base
from tests.untested_trainer_kit import plain, C, G, R, W, L, P, F, D, M, N
from tests.bughunt_table import Table
from spirit.tools.effect_smoke import P1, P2


class AttachAbilities(Base):
    async def go(self, ref, title, *, holder_zone, zone, good, bad, targets_ok, targets_bad,
                  active=None):
        """holder in holder_zone; Energy `good`/`bad` (types) in `zone`;
        Pokémon of types targets_ok / targets_bad on the Bench (plus the
        Active `active`).  Returns (energy offered, Pokémon offered, ok/bad
        Pokémon, energies)."""
        t = Table(self)
        act = t.put(active or plain(C), P1, 'active')
        holder = t.put(ref, P1, holder_zone) if holder_zone != 'active' else None
        if holder_zone == 'active':
            t.board.find_player_area(P1, 'activePokemonArea').children.remove(act)
            holder = t.put(ref, P1, 'active')
            act = holder
        t.put(plain(C), P2, 'active')
        ok = [t.put(plain(k), P1, 'bench') for k in targets_ok]
        bad_mons = [t.put(plain(k), P1, 'bench') for k in targets_bad]
        e_good = t.put(t.basic_energy(good), P1, zone)
        e_bad = t.put(t.basic_energy(bad), P1, zone)
        seen_cards, seen_mons = [], []

        def picks(cards, count, prompt, shown):
            seen_cards.append(list(cards))
            return [c for c in cards if c is e_good][:count] or list(cards)[:count]

        def pokemon(cands, prompt):
            seen_mons.append(list(cands))
            return next((c for c in cands if c in ok), cands[0] if cands else None)
        t.picks, t.pokemon = picks, pokemon
        entry = t.ability_offer(holder, title)
        if entry is not None:
            await t.do(entry)
        return t, entry, seen_cards, seen_mons, act, ok, bad_mons, e_good, e_bad

    def check(self, res, *, active_allowed):
        t, entry, cards, mons, act, ok, bad, e_good, e_bad = res
        self.assertIsNotNone(entry, 'ability offered')
        flat_cards = [c for s in cards for c in s]
        flat_mons = [c for s in mons for c in s]
        self.assertNotIn(e_bad, flat_cards, 'wrong Energy offered')
        for b in bad:
            self.assertNotIn(b, flat_mons, 'wrong Pokémon offered')
        if not active_allowed:
            self.assertNotIn(act, flat_mons, 'Active offered for a Benched-only Ability')
        self.assertTrue(any(e_good in t.attached(p) for p in ok), 'Energy attached')

    async def test_malamar_psychic_recharge(self):
        self.check(await self.go('SM6.Malamar_51', 'Psychic Recharge', holder_zone='bench',
                                  zone='discard', good=P, bad=D, targets_ok=[C], targets_bad=[]),
                   active_allowed=False)

    async def test_flaaffy_dynamotor(self):
        self.check(await self.go('SWSH7.Flaaffy_55', 'Dynamotor', holder_zone='bench',
                                  zone='discard', good=L, bad=F, targets_ok=[C], targets_bad=[]),
                   active_allowed=False)

    async def test_bronzong_metal_links(self):
        self.check(await self.go('XY4.Bronzong_61', 'Metal Links', holder_zone='bench',
                                  zone='discard', good=M, bad=F, targets_ok=[C], targets_bad=[]),
                   active_allowed=False)

    async def test_xatu_clairvoyant_sense(self):
        self.check(await self.go('SV4.Xatu_72', 'Clairvoyant Sense', holder_zone='bench',
                                  zone='hand', good=P, bad=D, targets_ok=[C], targets_bad=[]),
                   active_allowed=False)

    async def test_eelektrik_dynamotor(self):
        self.check(await self.go('ME2PT5.Eelektrik_60', 'Dynamotor', holder_zone='bench',
                                  zone='discard', good=L, bad=F, targets_ok=[C], targets_bad=[]),
                   active_allowed=False)

    async def test_barbaracle_stone_arms_fighting_only(self):
        self.check(await self.go('ME3.Barbaracle_43', 'Stone Arms', holder_zone='bench',
                                  zone='hand', good=F, bad=W, targets_ok=[F], targets_bad=[W]),
                   active_allowed=True)

    async def test_frosmoth_ice_dance_benched_water_only(self):
        self.check(await self.go('SWSH45.Frosmoth_30', 'Ice Dance', holder_zone='bench',
                                  zone='hand', good=W, bad=F, targets_ok=[W], targets_bad=[F],
                                  active=plain(W)),
                   active_allowed=False)

    async def test_reshiram_turboblaze_active_only_dragon_targets(self):
        res = await self.go('XY6.Reshiram_63', 'Turboblaze', holder_zone='active',
                             zone='hand', good=R, bad=W, targets_ok=[N], targets_bad=[C])
        self.check(res, active_allowed=True)
        res = await self.go('XY6.Reshiram_63', 'Turboblaze', holder_zone='bench',
                             zone='hand', good=R, bad=W, targets_ok=[N], targets_bad=[C])
        self.assertIsNone(res[1], 'Turboblaze only while Reshiram is Active')


if __name__ == '__main__':
    unittest.main()

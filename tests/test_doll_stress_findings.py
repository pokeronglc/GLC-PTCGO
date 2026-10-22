"""Findings of the Poké Doll / Robo Substitute x Ability-lock stress run
(spirit/tools/stress_dolls.py, 2026-10-12).

Guards (must pass): the rule-action buttons stay usable under every Ability
lock, a KO'd doll gives no Prize, put-away/discard leave no damaged doll and
promote correctly.

Client-facing wire findings (fixed 2026-10-12: PokemonEntity.client_card_type
is location-aware, fossil/doll CARD_TYPE updates ride the move brackets, the
reconnect resume re-syncs types before replaying offers):
  * the CARD_TYPE "back to Trainer" AttributeModified for a doll that left
    play is broadcast after the card is already in a hidden zone (the deck
    after "Put Lillie's Poké Doll Away", the opponent's hand after Scoop Up
    Net) -- the only routine AttributeModified on a hidden card;
  * a doll put into play by Clefairy CEC 144 Doll Swap stays CARD_TYPE
    Trainer on both clients until the next main-phase offer (after the
    between-turns checkup), so prompts in that window (prize pick, KO
    promotion) show a Trainer card in the Active Spot.
"""
import unittest

from tests import test_bughunt7_chunk36 as _c36
from spirit.game.attributes import PokemonTypes
from spirit.game.attributes import AttrID, CardType
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

DOLL = 'SM12.LilliesPokDoll_197'
DOLL_267 = 'SM12.LilliesPokDoll_267'
ROBO = 'XY4.RoboSubstituteTeamFlareGear_102'
CLEFAIRY = 'SM12.Clefairy_144'
HEX = 'XY7.HexManiac_75'
SILENT_LAB = 'XY5.SilentLab_140'
PATH = 'SWSH6.PathtothePeak_148'
SCOOP = 'SWSH2.ScoopUpNet_165'

PUT_AWAY = "Put Lillie's Poké Doll Away"
ROBO_DISCARD = "Discard Robo Substitute"


class Wire:
    """Records every AttributeModified CARD_TYPE the session broadcasts,
    with the server zone of the card at send time."""

    def __init__(self, t):
        self.t = t
        self.card_type_msgs = []
        session = t.session
        orig_broadcast = session.broadcast_packet
        orig_sequence = session.send_game_sequence

        def note(msg):
            if not isinstance(msg, dict) or msg.get('name') != 'AttributeModified':
                return
            value = msg.get('value') or {}
            attr = value.get('attribute') or {}
            if attr.get('name') != AttrID.CARD_TYPE.value:
                return
            ent = t.board.get_entity(value.get('entityID'))
            zone = ent._containing_area_name() if ent is not None else None
            self.card_type_msgs.append((value.get('entityID'), attr.get('value'), zone))

        async def broadcast(name, value, flags=0):
            note((value or {}).get('msg'))
            return await orig_broadcast(name, value, flags)

        async def sequence(players, name, inner):
            for m in inner or []:
                note(m)
            return await orig_sequence(players, name, inner)

        session.broadcast_packet = broadcast
        session.send_game_sequence = sequence

    def for_card(self, card):
        return [(v, z) for eid, v, z in self.card_type_msgs if eid == card.entity_id]


class DollStressFindings(_c36.Chunk36):

    async def bench_doll(self, t, spec=DOLL, active=False):
        doll = t.put(spec, P1, 'hand')
        await t.play(doll)
        self.assertIn(doll, t.board.pokemon_in_play(P1))
        if active:
            await t._run(lambda: EffectContext(t.session, P1, doll, None).switch_active(P1, doll))
            self.assertIs(t.active(P1), doll)
        return doll

    # ------------------------------------------------------------------
    # Guards: these held in all 1650 stress games.

    async def test_put_away_offered_under_every_ability_lock(self):
        for lock in (None, HEX, SILENT_LAB, PATH):
            with self.subTest(lock=lock):
                t = self.table()
                self.mine(t, self.filler, zone='active')
                self.mine(t, self.filler, zone='bench')
                doll = await self.bench_doll(t, active=True)
                robo = await self.bench_doll(t, ROBO)
                if lock == HEX:
                    await t.play(t.put(HEX, P1, 'hand'))
                elif lock is not None:
                    t.stadium(lock, P2)
                self.assertIsNotNone(t.ability_offer(doll, PUT_AWAY), lock)
                self.assertIsNotNone(t.ability_offer(robo, ROBO_DISCARD), lock)

    async def test_put_away_not_offered_from_bench_and_no_retreat(self):
        t = self.table()
        self.mine(t, self.filler, zone='active')
        doll = await self.bench_doll(t)
        self.assertIsNone(t.ability_offer(doll, PUT_AWAY))
        await t._run(lambda: EffectContext(t.session, P1, doll, None).switch_active(P1, doll))
        self.assertFalse(t.offers(doll, 'BaseRetreat'))

    async def test_put_away_clears_damage_and_promotes(self):
        for spec in (DOLL, DOLL_267):
            with self.subTest(spec=spec):
                t = self.table()
                bench = self.mine(t, self.filler, zone='active')
                doll = await self.bench_doll(t, spec, active=True)
                doll.set_attribute(AttrID.HP, 10)
                await t.use(doll, PUT_AWAY)
                deck = t.zone(P1, 'deck')
                self.assertIs(deck[0], doll)          # bottom of the deck
                self.assertEqual(doll.get_attribute(AttrID.HP), 30)
                self.assertIs(t.active(P1), bench)     # lone benched Pokémon promoted

    async def test_knocked_out_doll_gives_no_prize(self):
        t = self.table()
        self.mine(t, self.filler, zone='active')
        doll = await self.bench_doll(t, active=True)
        prizes = len(t.zone(P2, 'prizes'))
        ctx = EffectContext(t.session, P2, self.opp, None)
        doll.set_attribute(AttrID.HP, 0)
        ctx.knockouts.append(doll)
        await t.knockouts(ctx)
        self.assertIn(doll, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), prizes)

    # ------------------------------------------------------------------
    # Open findings (client-facing wire).

    async def test_card_type_revert_not_sent_while_doll_in_deck(self):
        """Put Away moves the doll into the hidden deck; the next offer's
        _sync_fossil_card_types then sends AttributeModified CARD_TYPE=Trainer
        for a card the client holds face-down in the deck.  The revert should
        ride the leave-play bracket (card still public) or be skipped (the
        re-draw EntityIntroduced already carries CARD_TYPE Trainer)."""
        t = self.table()
        self.mine(t, self.filler, zone='active')
        doll = await self.bench_doll(t, active=True)
        wire = Wire(t)
        await t.session._sync_fossil_card_types()
        self.assertIn((CardType.POKEMON.value, 'activePokemonArea'), wire.for_card(doll))
        await t.use(doll, PUT_AWAY)
        await t.session._sync_fossil_card_types()
        hidden = [m for m in wire.for_card(doll) if m[1] in ('deck', 'prizePile')]
        self.assertEqual(hidden, [], f"CARD_TYPE sent for a doll in a hidden zone: {hidden}")

    async def test_doll_swap_types_doll_as_pokemon_before_turn_ends(self):
        """Clefairy CEC 144 Doll Swap puts the doll into the Active Spot during
        the attack; the attack ends the turn, and the CARD_TYPE=Pokemon update
        only goes out at the opponent's first main offer.  Stress seed 3100018
        (pool doll_pool.txt, decks 5046 vs 5145) prompts P2 for a Prize with the
        doll still typed Trainer on its client."""
        t = self.table()
        clef = self.mine(t, CLEFAIRY, PokemonTypes.FIRE, 3)
        self.mine(t, self.filler, zone='bench')
        doll = t.put(DOLL, P1, 'hand')
        t.yes = True
        wire = Wire(t)
        await t.attack(clef, 'Doll Swap')
        self.assertIs(t.active(P1), doll)
        self.assertIn((CardType.POKEMON.value, 'activePokemonArea'), wire.for_card(doll))

    async def test_reconnect_snapshot_types_doll_in_play_as_pokemon(self):
        """reconnect_player clears _fossil_type_sent and the client rebuilds
        from SerializedGameState, where an in-play doll (or fossil) carries
        its printed CARD_TYPE Trainer.  _resume_reconnect_cycle then replays
        the pending main offer without running _sync_fossil_card_types, so the
        returning player is offered "Put Lillie's Poké Doll Away" on a card
        its client now holds as a Trainer in the Active Spot (stress tool:
        simulate_reconnect, 10/20 games with a doll in play)."""
        t = self.table()
        self.mine(t, self.filler, zone='active')
        doll = await self.bench_doll(t, active=True)
        robo = await self.bench_doll(t, ROBO)
        snap = t.board.serialize(P1)

        def find(node, eid):
            if node.get('entityID') == eid:
                return node
            for ch in node.get('children') or []:
                hit = find(ch, eid)
                if hit is not None:
                    return hit
            return None

        for card in (doll, robo):
            node = find(snap['entities'], card.entity_id)
            ctype = next(a['value'] for a in node['attributes']
                         if a['name'] == AttrID.CARD_TYPE.value)
            self.assertEqual(ctype, CardType.POKEMON.value)

    # ------------------------------------------------------------------
    # Per-viewer wire order (what each client actually receives).

    def capture(self, t):
        """Per-player list of (name, value) of every SequenceMessage."""
        got = {P1: [], P2: []}
        for pid, player in t.session.players.items():
            orig = player.send_packet

            async def send(name, value, flags=0, _pid=pid, _orig=orig):
                if name == 'SequenceMessage':
                    msg = (value or {}).get('msg') or {}
                    got[_pid].append((msg.get('name'), msg.get('value') or {}))
                return await _orig(name, value, flags)
            player.send_packet = send
        return got

    @staticmethod
    def card_type_of(name, value, eid):
        if name == 'AttributeModified' and value.get('entityID') == eid:
            attr = value.get('attribute') or {}
            if attr.get('name') == AttrID.CARD_TYPE.value:
                return attr.get('value')
        if name == 'EntityIntroduced' and value.get('entityID') == eid:
            return next((a['value'] for a in value.get('attributeMap') or []
                         if a['name'] == AttrID.CARD_TYPE.value), None)
        return None

    def client_type_when_moved(self, msgs, eid):
        """CARD_TYPE the viewer holds for `eid` at each of its EntityMoved,
        plus the name of the bracket carrying that move."""
        ctype, bracket, out = None, [], []
        for name, value in msgs:
            if name == 'StartSequence':
                bracket.append(value.get('name'))
            elif name == 'StopSequence' and bracket:
                bracket.pop()
            seen = self.card_type_of(name, value, eid)
            if seen is not None:
                ctype = seen
            if name == 'EntityMoved' and value.get('entityID') == eid:
                out.append((bracket[0] if bracket else None, ctype))
        return out, ctype

    async def test_bench_play_presents_doll_as_pokemon_before_play_bracket(self):
        """The PlayCard executor picks its animation from CARD_TYPE before
        its bracket runs: both clients must already hold the doll as a
        Pokemon. Owner: it is typed Pokemon in the hand (EntityIntroduced /
        snapshot), and NO retype is sent around the play (Oct 13: retyping
        the dragged card mid-play stranded it beside the Active Spot).
        Opponent: EntityIntroduced carries Pokemon."""
        for spec in (DOLL, ROBO, 'SWSH10.UnidentifiedFossil_157'):
            with self.subTest(spec=spec):
                t = self.table()
                self.mine(t, self.filler, zone='active')
                doll = t.put(spec, P1, 'hand')
                self.assertEqual(doll.client_card_type(), CardType.POKEMON.value)
                intro = t.session._entity_introduced_msg(doll)
                self.assertEqual(self.card_type_of(intro['name'], intro['value'], doll.entity_id),
                                 CardType.POKEMON.value)
                got = self.capture(t)
                await t.play(doll)
                self.assertIn(doll, t.board.pokemon_in_play(P1))
                moves, final = self.client_type_when_moved(got[P1], doll.entity_id)
                self.assertEqual(moves, [('PlayCard', None)])     # no retype sent
                moves, final = self.client_type_when_moved(got[P2], doll.entity_id)
                self.assertEqual(moves, [('PlayCard', CardType.POKEMON.value)])
                self.assertEqual(final, CardType.POKEMON.value)
                # The rules side keeps the printed Item type.
                self.assertEqual(doll.get_attribute(AttrID.CARD_TYPE), CardType.TRAINER.value)

    async def test_leave_play_revert_rides_move_bracket_and_skips_hidden(self):
        t = self.table()
        self.mine(t, self.filler, zone='active')
        robo = await self.bench_doll(t, ROBO)
        doll = await self.bench_doll(t, active=True)
        await t.session._sync_fossil_card_types()
        got = self.capture(t)
        await t.use(robo, ROBO_DISCARD)
        self.assertIn(robo, t.zone(P1, 'discard'))
        for pid in (P1, P2):
            moves, final = self.client_type_when_moved(got[pid], robo.entity_id)
            self.assertEqual(final, CardType.TRAINER.value, pid)
            # the revert is inside the bracket that moved it to the discard
            names = [n for n, _ in got[pid]]
            mv = next(i for i, (n, v) in enumerate(got[pid])
                      if n == 'EntityMoved' and v.get('entityID') == robo.entity_id)
            rv = next(i for i, (n, v) in enumerate(got[pid])
                      if n == 'AttributeModified'
                      and self.card_type_of(n, v, robo.entity_id) == CardType.TRAINER.value)
            self.assertGreater(rv, mv)
            self.assertNotIn('StopSequence', names[mv:rv])
        for pid in (P1, P2):
            got[pid].clear()
        await t.use(doll, PUT_AWAY)
        await t.session._sync_fossil_card_types()
        for pid in (P1, P2):
            self.assertFalse([1 for n, v in got[pid]
                              if self.card_type_of(n, v, doll.entity_id) is not None
                              and n == 'AttributeModified'],
                             f"CARD_TYPE sent to {pid} for a doll put into the deck")

    async def test_scoop_up_net_revert_only_to_owner(self):
        """Scooped back to hand: the owner's copy stays a Pokemon (that is
        how it is played from the hand); the opponent holds it face down and
        gets nothing (its next EntityIntroduced carries the right type)."""
        t = self.table()
        self.mine(t, self.filler, zone='active')
        doll = await self.bench_doll(t)
        await t.session._sync_fossil_card_types()
        got = self.capture(t)
        t.pokemon = lambda candidates, prompt: doll
        t.picks = lambda cards, count, *a, **k: [doll] if doll in cards else list(cards)[:count]
        await t.play(t.put(SCOOP, P1, 'hand'), targets=[doll.entity_id])
        self.assertIn(doll, t.zone(P1, 'hand'))
        await t.session._sync_fossil_card_types()
        _, mine = self.client_type_when_moved(got[P1], doll.entity_id)
        self.assertIn(mine, (None, CardType.POKEMON.value))
        self.assertFalse([1 for n, v in got[P2] if n == 'AttributeModified'
                          and self.card_type_of(n, v, doll.entity_id) is not None])


for _n in [n for n in vars(_c36.Chunk36) if n.startswith('test_')]:
    setattr(DollStressFindings, _n, None)


if __name__ == '__main__':
    unittest.main()

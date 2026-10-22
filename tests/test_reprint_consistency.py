"""Reprint consistency: every printing of the same card runs the same code.

Printings that share a name and rules text (reprints, full arts, secret
rares, promos) must behave identically.  The catalog-wide test groups the
loaded catalog by printed identity (name, card class, HP, Stage, types,
Weakness/Resistance, Retreat, Trainer type and every Ability/attack title,
cost, damage and text) and compares the behaviour-relevant code of each
printing: effect/condition/passive callables (structurally: same library
function and closure arguments, or the same card-script code), triggers,
activation flags, attach rules, subtypes and evolves-from keys.  Cosmetic
fields (GUID, key, set, number, rarity, art, search tags) are ignored.

Near-identical rules text (a typo in one printing: similarity >= 0.9 with
otherwise identical stats/costs/damage) is grouped too, and the normalized
text is compared as behaviour because the generic text interpreters
(standard_attack, bw_legacy_*) read it at runtime.

Run: PYTHONPATH=. python3 -m unittest tests.test_reprint_consistency
"""
import collections
import difflib
import enum
import functools
import re
import types
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonCardDef
from spirit.game.scripts.cards import loader
from spirit.game.session.passives import energy_provided_options
from spirit.tools.effect_smoke import P1, P2


# ----------------------------------------------------------------------
# Printed identity
# ----------------------------------------------------------------------

def norm(text):
    text = re.sub(r"\[\s*\[\s*(\w+)\s*\]\s*\]", r"\1", text or "")   # "[ [Fire] ]" icon markup
    for a, b in (("é", "e"), ("É", "E"), ("’", "'"), ("‘", "'"), ("“", '"'),
                 ("”", '"'), ("—", "-"), ("–", "-")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().casefold()


def attr(definition, attr_id):
    spec = definition.extra_attributes.get(str(attr_id.value))
    return spec.get("value") if isinstance(spec, dict) else spec


TEXT_ATTRS = [AttrID.HP, AttrID.STAGE, AttrID.POKEMON_TYPES, AttrID.WEAKNESS_TYPES,
              AttrID.WEAKNESS_AMOUNT, AttrID.WEAKNESS_OPERATOR, AttrID.RESISTANCE_TYPES,
              AttrID.RESISTANCE_AMOUNT, AttrID.RESISTANCE_OPERATOR, AttrID.RETREAT_COST,
              AttrID.TRAINER_TYPE, AttrID.IS_SPECIAL_ENERGY]


def ability_text(ability):
    cost = getattr(ability, "cost", None) or {}
    return (type(ability).__name__, norm(ability.title), str(ability.ability_type),
            norm(ability.game_text), tuple(sorted((str(k), v) for k, v in cost.items())),
            getattr(ability, "damage", None), getattr(ability, "damage_operator", None))


def text_key(definition):
    return (type(definition).__name__, norm(definition.display_name),
            tuple(repr(attr(definition, a)) for a in TEXT_ATTRS),
            tuple(ability_text(a) for a in (definition.abilities or [])))


def _loose_key(key):
    return key[:3] + (tuple(a[:3] + a[4:] for a in key[3]),)


def _texts_close(k1, k2, threshold=0.9):
    return all(a[3] == b[3] or difflib.SequenceMatcher(None, a[3], b[3]).ratio() >= threshold
               for a, b in zip(k1[3], k2[3]))


def catalog():
    out = []
    for guid, path in loader.script_by_guid.items():
        definition = CARD_DEFS_BY_GUID.get(guid.lower())
        if definition is not None:
            out.append((path.split("/scripts/cards/")[-1], definition))
    return out


def build_groups(defs):
    """{representative text key: [(script path, definition), ...]}."""
    exact = collections.defaultdict(list)
    for rel, definition in defs:
        exact[text_key(definition)].append((rel, definition))
    by_loose = collections.defaultdict(list)
    for key in exact:
        by_loose[_loose_key(key)].append(key)
    groups = {}
    for keys in by_loose.values():
        clusters = []
        for key in keys:
            for cluster in clusters:
                if all(_texts_close(key, other) for other in cluster):
                    cluster.append(key)
                    break
            else:
                clusters.append([key])
        for cluster in clusters:
            groups[cluster[0]] = [item for key in cluster for item in exact[key]]
    return groups


# ----------------------------------------------------------------------
# Behaviour signature
# ----------------------------------------------------------------------

COSMETIC_CARD = {"guid", "key", "collector_number", "set_code", "rarity", "regulation_mark",
                 "foil", "extra_attributes", "display_name", "name", "searchable_by"}
COSMETIC_ABILITY = {"ability_id", "printed_pokemon_name", "printed_set_code", "game_text", "title"}
BEHAVIOUR_ATTRS = [AttrID.EVOLVES_FROM, AttrID.EVOLUTION_LOGIC_NAME,
                   AttrID.EVOLUTION_LOGIC_FROM, AttrID.CARD_TYPE, AttrID.ENERGY_INFO]
_SKIP_CLASS_KEYS = {"__module__", "__dict__", "__weakref__", "__doc__", "__qualname__",
                    "__firstlineno__", "__static_attributes__"}


def _card_module(mod):
    # Card scripts load under the loader's names, their package path, or
    # sibling_card()'s private module names: all are "card code".
    return (mod or "").startswith(("card_script_", "spirit.game.scripts.cards", "_sibling_card_"))


def sig(value, depth=0, seen=frozenset()):
    if value is None or isinstance(value, (bool, int, float, str, bytes, enum.Enum)):
        return repr(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [sig(x, depth, seen) for x in value]
        if isinstance(value, (set, frozenset)):
            items.sort()
        return f"{type(value).__name__}[{', '.join(items)}]"
    if isinstance(value, dict):
        return "{" + ", ".join(sorted(f"{sig(k, depth, seen)}: {sig(v, depth, seen)}"
                                      for k, v in value.items())) + "}"
    if isinstance(value, types.ModuleType):
        return f"module {value.__name__}"
    if isinstance(value, types.MethodType):
        return f"method({sig(value.__func__, depth, seen)})"
    if isinstance(value, functools.partial):
        return f"partial({sig(value.func, depth, seen)}, {sig(value.args, depth, seen)}, {sig(value.keywords, depth, seen)})"
    if isinstance(value, types.FunctionType):
        return func_sig(value, depth, seen)
    if isinstance(value, type):
        return class_sig(value, depth, seen)
    if isinstance(value, types.BuiltinFunctionType):
        return f"{getattr(value, '__module__', '')}.{value.__qualname__}"
    if isinstance(value, types.CodeType):
        return repr(code_sig(value))
    if id(value) in seen or depth > 6:
        return f"<{type(value).__name__}>"
    seen = seen | {id(value)}
    if hasattr(value, "__dict__"):
        return f"{class_sig(type(value), depth + 1, seen)}({sig(vars(value), depth + 1, seen)})"
    return re.sub(r" at 0x[0-9a-f]+", "", repr(value))


def code_sig(code):
    consts = tuple(code_sig(c) if isinstance(c, types.CodeType) else repr(c)
                   for c in code.co_consts
                   if not (isinstance(c, str) and c is code.co_consts[0] and len(c) > 40))  # docstrings
    return (code.co_code.hex(), consts, code.co_names, code.co_varnames, code.co_freevars)


def class_sig(cls, depth, seen):
    mod = getattr(cls, "__module__", "") or ""
    if not _card_module(mod):
        return f"{mod}.{cls.__qualname__}"
    if id(cls) in seen or depth > 6:
        return f"class* {cls.__qualname__}"
    seen = seen | {id(cls)}
    body = []
    for k, v in sorted(vars(cls).items()):
        if k in _SKIP_CLASS_KEYS:
            continue
        if isinstance(v, (staticmethod, classmethod)):
            v = v.__func__
        body.append(f"{k}={sig(v, depth + 1, seen)}")
    bases = ",".join(class_sig(b, depth + 1, seen) for b in cls.__bases__)
    return f"class {cls.__qualname__}({bases}){{{'; '.join(body)}}}"


def lib_sig(fn, depth, seen):
    """A library function is identified by name plus its closure/defaults."""
    name = f"fn {fn.__module__}.{fn.__qualname__}"
    if id(fn) in seen or depth > 8:
        return name
    seen = seen | {id(fn)}
    extra = []
    for cell in fn.__closure__ or ():
        try:
            extra.append(sig(cell.cell_contents, depth + 1, seen))
        except ValueError:
            extra.append("<empty>")
    if fn.__defaults__:
        extra.append(sig(fn.__defaults__, depth + 1, seen))
    if fn.__kwdefaults__:
        extra.append(sig(fn.__kwdefaults__, depth + 1, seen))
    return name + ("(" + " | ".join(extra) + ")" if extra else "")


def func_sig(fn, depth, seen):
    """Card-script functions compare by code, closure and referenced globals."""
    if not _card_module(fn.__module__):
        return lib_sig(fn, depth, seen)
    if id(fn) in seen or depth > 6:
        return f"fn* {fn.__qualname__}"
    seen = seen | {id(fn)}
    parts = [repr(code_sig(fn.__code__))]
    for cell in fn.__closure__ or ():
        try:
            parts.append(sig(cell.cell_contents, depth + 1, seen))
        except ValueError:
            parts.append("<empty>")
    parts.append(sig(fn.__defaults__, depth + 1, seen))
    parts.append(sig(fn.__kwdefaults__, depth + 1, seen))
    names = set(fn.__code__.co_names)
    for const in fn.__code__.co_consts:
        if isinstance(const, types.CodeType):
            names |= set(const.co_names)
    for name in sorted(names):
        if name in fn.__globals__ and not isinstance(fn.__globals__[name], types.ModuleType):
            parts.append(f"{name}={sig(fn.__globals__[name], depth + 1, seen)}")
    return "fn(" + " | ".join(parts) + ")"


def _ability_code(ability):
    out = {"text": norm(ability.game_text)}
    for k, v in sorted(vars(ability).items()):
        if k not in COSMETIC_ABILITY:
            out[k] = sig(v)
    return out


def behaviour(definition):
    """Flat {field: signature} of everything that affects how a card plays."""
    flat = {}
    for k, v in sorted(vars(definition).items()):
        if k in COSMETIC_CARD:
            continue
        if k in ("abilities", "granted_abilities"):
            flat[f"{k}#len"] = str(len(v or []))
            for i, ability in enumerate(v or []):
                for kk, vv in _ability_code(ability).items():
                    flat[f"{k}[{i}].{kk}"] = vv
        elif k == "ability" and v is not None:
            for kk, vv in _ability_code(v).items():
                flat[f"ability.{kk}"] = vv
        elif k == "subtypes":
            flat[k] = repr(sorted(v or []))
        else:
            flat[k] = sig(v)
    for a in BEHAVIOUR_ATTRS:
        flat["attr_" + a.name] = repr(attr(definition, a))
    return flat


def differing_groups(groups):
    out = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        flats = [(rel, behaviour(d)) for rel, d in items]
        fields = set().union(*(f.keys() for _, f in flats))
        diff = sorted(x for x in fields if len({f.get(x) for _, f in flats}) > 1)
        if diff:
            variants = collections.defaultdict(list)
            for rel, f in flats:
                variants[tuple(f.get(x) for x in diff)].append(rel)
            out.append((key[1], tuple(diff), sorted(sorted(v) for v in variants.values())))
    return out


# Genuinely intentional differences: (normalized name, differing fields).
ALLOWED = {
    # NVI Virizion 13/97 print "Leaf Wallop attack does 40 more damage"; the
    # PLB/LTR reprints use the newer "Leaf Wallop does ..." wording.  Same
    # card, and every printing already runs the same bespoke effects
    # (draw_attack(2) / bw10.leaf_wallop), which do not read the text.
    ("virizion", ("abilities[1].text",)),
}


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------

class ReprintConsistencyCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HgssRulesTests.setUpClass.__func__(cls)
        cls.groups = build_groups(catalog())

    def test_same_text_printings_share_behaviour(self):
        multi = [g for g in self.groups.values() if len(g) > 1]
        self.assertGreater(len(multi), 1000)   # the sweep actually saw the reprints
        bad = [d for d in differing_groups(self.groups) if (d[0], d[1]) not in ALLOWED]
        self.assertEqual(bad, [], "printings with the same text run different code:\n" +
                         "\n".join(f"{n}: {f} {v}" for n, f, v in bad))

    def test_allowlist_is_not_stale(self):
        live = {(d[0], d[1]) for d in differing_groups(self.groups)}
        self.assertEqual(ALLOWED - live, set())

    def test_signature_sees_closure_arguments_and_card_code(self):
        from spirit.game.card_effects.attacks_common import damage_per, count_energy
        a = damage_per(count_energy("self"), 30)
        b = damage_per(count_energy("self"), 30, base=30)
        self.assertNotEqual(sig(a), sig(b))
        self.assertEqual(sig(a), sig(damage_per(count_energy("self"), 30)))
        g1, g2 = {"__name__": "card_script_X"}, {"__name__": "card_script_Y"}
        exec("async def eff(ctx):\n    await ctx.draw_cards(2)\n", g1)
        exec("async def eff(ctx):\n    await ctx.draw_cards(3)\n", g2)
        self.assertNotEqual(sig(g1["eff"]), sig(g2["eff"]))

    def test_evolves_from_keys_match_across_printings(self):
        # A misspelled evolves-from key (RSV10PT5 Archen "AntiuqePlumeFossil")
        # splits a group on attr_EVOLVES_FROM; it is covered above, and this
        # pins the Archen fix explicitly.
        archens = [d for rel, d in catalog() if rel.startswith("RSV10PT5/Archen_")]
        self.assertTrue(archens)
        self.assertEqual({attr(d, AttrID.EVOLUTION_LOGIC_FROM) for d in archens},
                         {"AntiquePlumeFossil"})


class ReprintBehaviourTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def defender(self, t):
        target = t.put(self.filler, P2, 'active')
        target.set_attribute(AttrID.WEAKNESS_TYPES, [])
        target.set_attribute(AttrID.RESISTANCE_TYPES, [])
        target.set_attribute(AttrID.HP, 400)
        return target

    async def test_lunatone_moon_kinesis_keeps_base_damage_on_every_printing(self):
        # "30+: 30 more damage for each Psychic Energy attached."
        for path in ('PGO.Lunatone_34', 'CZ.Lunatone_62', 'CZ.Lunatone_171'):
            with self.subTest(path=path):
                t = Table(self)
                me = t.put(path, P1, 'active')
                t.energy(me, PokemonTypes.PSYCHIC, 3)
                target = self.defender(t)
                await t.attack(me, 'Moon Kinesis')
                self.assertEqual(400 - t.hp(target), 120)

    async def test_passimian_team_play_counts_base_damage_on_both_printings(self):
        # "10+: 30 more damage for each of your Benched Passimian."
        for path in ('Promo_SM.Passimian_12', 'SM1.Passimian_73'):
            with self.subTest(path=path):
                t = Table(self)
                me = t.put(path, P1, 'active')
                t.energy(me, PokemonTypes.FIGHTING, 2)
                t.put(path, P1, 'bench')
                t.put(path, P1, 'bench')
                target = self.defender(t)
                await t.attack(me, 'Team Play')
                self.assertEqual(400 - t.hp(target), 70)

    async def test_prism_energy_every_printing_basic_only(self):
        for path in ('BW4.PrismEnergy_93', 'ZSV10PT5.PrismEnergy_86', 'ME2PT5.PrismEnergy_216'):
            with self.subTest(path=path):
                t = Table(self)
                basic = t.put(self.filler, P1, 'active')
                evolved = t.put('BW4.Vanilluxe_33', P1, 'bench')
                on_basic = t.attach(path, basic)
                on_evolved = t.attach(path, evolved)
                options = energy_provided_options(t.board, on_basic)
                self.assertIn([PokemonTypes.GRASS.value], options)
                self.assertIn([PokemonTypes.DARKNESS.value], options)
                self.assertTrue(all(len(o) == 1 for o in options))
                self.assertEqual(energy_provided_options(t.board, on_evolved),
                                 [[PokemonTypes.COLORLESS.value]])

    async def test_deck_look_items_need_a_deck_on_every_printing(self):
        for path in ('SWSH11.ColresssExperiment_155', 'SWSH11.ColresssExperiment_190',
                     'SWSH11.ColresssExperiment_205', 'CZ.ColresssExperiment_219',
                     'SWSH10.TrekkingShoes_156', 'SWSH10.TrekkingShoes_215',
                     'CZ.TrekkingShoes_145'):
            with self.subTest(path=path):
                t = Table(self)
                t.put(self.filler, P1, 'active')
                card = t.put(path, P1, 'hand')
                self.assertTrue(t.can(card, 'UseTrainerCard'))
                for c in t.zone(P1, 'deck'):
                    t.board.find_player_area(P1, 'deck').remove_child(c)
                self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_level_ball_every_printing_finds_only_90_hp_or_less(self):
        small = next(d for d in CARD_DEFS_BY_GUID.values()
                     if isinstance(d, PokemonCardDef) and attr(d, AttrID.HP) == 60
                     and d.guid.lower() in loader.cards_by_guid)
        for path in ('SWSH5.LevelBall_129', 'SWSH5.LevelBall_181', 'BW4.LevelBall_89',
                     'XY7.LevelBall_76'):
            with self.subTest(path=path):
                t = Table(self)
                t.put(self.filler, P1, 'active')
                self.defender(t)
                t.deck(P1, [small, self.filler])
                offered = []
                t.picks = lambda cards, count, prompt, display: offered.extend(cards) or cards[:1]
                await t.play(t.put(path, P1, 'hand'))
                names = {c.archetype_id for c in offered}
                self.assertIn(small.guid.lower(), {n.lower() for n in names})
                self.assertNotIn(self.filler.guid.lower(), {n.lower() for n in names})

    async def test_dark_patch_bw5_matches_asr(self):
        dark = next(d for d in CARD_DEFS_BY_GUID.values()
                    if isinstance(d, PokemonCardDef) and attr(d, AttrID.STAGE) == 0
                    and attr(d, AttrID.POKEMON_TYPES) == f'[{PokemonTypes.DARKNESS.value}]'
                    and d.guid.lower() in loader.cards_by_guid)
        for path in ('BW5.DarkPatch_93', 'SWSH10.DarkPatch_139', 'SWSH11.DarkPatch_216'):
            with self.subTest(path=path):
                t = Table(self)
                t.put(self.filler, P1, 'active')
                self.defender(t)
                energy = t.put(t.basic_energy(PokemonTypes.DARKNESS), P1, 'discard')
                card = t.put(path, P1, 'hand')
                self.assertFalse(t.can(card, 'UseTrainerCard'))   # no Benched Darkness Pokémon
                bench = t.put(dark, P1, 'bench')
                self.assertTrue(t.can(card, 'UseTrainerCard'))
                await t.play(card)
                self.assertIn(energy, list(bench.children))

    async def test_empoleon_diving_draw_needs_a_card_to_discard(self):
        for path in ('BW5.Empoleon_29', 'BW9.Empoleon_117'):
            with self.subTest(path=path):
                t = Table(self)
                me = t.put(path, P1, 'active')
                self.defender(t)
                self.assertIsNone(t.ability_offer(me, 'Diving Draw'))
                t.put(self.item, P1, 'hand')
                self.assertIsNotNone(t.ability_offer(me, 'Diving Draw'))
                await t.use(me, 'Diving Draw')
                self.assertEqual(len(t.zone(P1, 'hand')), 2)
                self.assertEqual(len(t.zone(P1, 'discard')), 1)

    def test_shared_effects_are_imported_from_the_fixed_printing(self):
        from importlib import import_module
        mod = lambda p: import_module('spirit.game.scripts.cards.' + p)
        avery = mod('SWSH6.Avery_130').avery
        for p in ('SWSH6.Avery_187', 'SWSH6.Avery_211'):
            self.assertIs(mod(p).card.effect, avery)
        caitlin = mod('SWSH6.Caitlin_132').caitlin
        for p in ('SWSH6.Caitlin_189', 'SWSH6.Caitlin_213', 'BW10.Caitlin_78'):
            self.assertIs(mod(p).card.effect, caitlin)
        self.assertIs(mod('SWSH1.Pokgear30_174').card.effect,
                      mod('SV1.Pokgear30_186').pokegear_3_0)
        self.assertIn('Rapid Strike', mod('SWSH5.KorrinasFocus_160').card.subtypes)
        self.assertNotIn('Single Strike', mod('SWSH5.KorrinasFocus_160').card.subtypes)


if __name__ == '__main__':
    unittest.main()

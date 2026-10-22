from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import Rarities
from spirit.game.card_effects.trainers import is_basic_energy_card, is_water_energy_card
from spirit.game.session.effects import is_water_pokemon
from spirit.game.card_effects.support_common import requires_discard


def _is_basic_water_energy(card):
    return is_basic_energy_card(card) and is_water_energy_card(card)


async def great_haul_net(ctx):
    """Choose 1 or both: shuffle up to 3 Water Pokemon and/or up to 3 Basic
    Water Energy cards from your discard pile into your deck.

    The player picks which option(s) first, so choosing only Pokemon never
    forces an Energy pick (and vice versa); each chosen option takes 1-3."""
    pokemon = [c for c in ctx.discard_pile() if is_water_pokemon(c)]
    energy = [c for c in ctx.discard_pile() if _is_basic_water_energy(c)]
    want_p, want_e = bool(pokemon), bool(energy)
    if pokemon and energy:
        pick = await ctx.choose(
            "Great Haul Net: choose 1 or both.",
            ["Water Pokémon", "Basic Water Energy", "Both"],
            use_panel=False,
        )
        want_p, want_e = pick in (0, 2), pick in (1, 2)
    picks = []
    if want_p:
        picks += await ctx.choose_cards(
            pokemon, min(3, len(pokemon)), minimum=1,
            prompt="Choose up to 3 Water Pokémon to shuffle into your deck.",
        )
    if want_e:
        picks += await ctx.choose_cards(
            energy, min(3, len(energy)), minimum=1,
            prompt="Choose up to 3 Basic Water Energy cards to shuffle into your deck.",
        )
    if picks:
        await ctx.shuffle_into_deck(picks)


card = ItemCardDef(
    guid="bbbbda91-40aa-5f8f-9ee0-f3eb1bcb6e14",
    key="ME4",
    name="com.direwolfdigital.cake.data.archetypes.trainer.GreatHaulNet.Name",
    display_name="Great Haul Net",
    searchable_by=["Great Haul Net","Item","GreatHaulNet"],
    subtypes=["Item"],
    collector_number=78,
    set_code="ME4",
    regulation_mark="J",
    rarity=Rarities.Uncommon,
    condition=requires_discard(
        lambda card: is_water_pokemon(card) or _is_basic_water_energy(card)
    ),
    effect=great_haul_net,
)

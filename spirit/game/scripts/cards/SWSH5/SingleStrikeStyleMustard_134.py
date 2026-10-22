from spirit.game.data_utils import SupporterCardDef, subtypes_for
from spirit.game.attributes import Rarities
from spirit.game.session.effects import is_pokemon_card
from spirit.game.card_effects.support_common import search_to_bench


def _last_card_in_hand(board, player_id):
    hand = board.find_player_area(player_id, "hand")
    return hand is not None and len(hand.children) == 1


def _is_single_strike_pokemon(card):
    return is_pokemon_card(card) and "Single Strike" in subtypes_for(card.archetype_id)


async def _draw_five(ctx, benched):
    await ctx.draw_cards(5)


# "If you searched your deck in this way, draw 5 cards": the draw follows
# any search, even one that finds no Single Strike Pokémon.
_EFFECT = search_to_bench(
    _is_single_strike_pokemon, count=1, then=_draw_five, then_if_searched=True,
    prompt="Choose a Single Strike Pokémon to put onto your Bench.",
)


def _mustard_playable(board, player_id):
    """Last card in hand, AND the search can happen: with a full Bench (or an
    empty deck) there is no searching "in this way", so no draw either."""
    return _last_card_in_hand(board, player_id) and _EFFECT.play_condition(board, player_id)


card = SupporterCardDef(
    guid="33b83541-71ea-58f9-803e-e6143d51e6c2",
    key="SWSH5",
    name="com.direwolfdigital.cake.data.archetypes.trainer.SingleStrikeStyleMustard.Name",
    display_name="Single Strike Style Mustard",
    searchable_by=["Single Strike Style Mustard", "Supporter", "Single Strike"],
    subtypes=["Supporter", "Single Strike"],
    collector_number=134,
    set_code="SWSH5",
    rarity=Rarities.Uncommon,
    condition=_mustard_playable,
    effect=_EFFECT,
)

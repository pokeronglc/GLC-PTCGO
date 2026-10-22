from spirit.game.data_utils import ItemCardDef
from spirit.game.attributes import Rarities
from spirit.game.card_effects.passives_common import ability_lock_passive


async def canceling_cologne(ctx):
    """Until the end of your turn, your opponent's Active Pokemon has no
    Abilities (including one that comes into play this turn).

    Side-wide: whichever Pokemon is the opponent's Active is covered, so a
    replacement promoted after a Knock Out (Archeops) has no Abilities either."""
    opponent = ctx.opponent_id
    if ctx.opponent_active() is None:
        return

    def is_opponents_active(pokemon, carrier):
        return getattr(pokemon, "owning_player_id", None) == opponent \
            and pokemon._containing_area_name() == "activePokemonArea"

    ctx.add_temporary_player_passive(
        opponent, ability_lock_passive(is_opponents_active),
        expires_after_turn=ctx.session.turn_state.turn_number,
    )

card = ItemCardDef(
    guid="6dfa3e30-4350-5602-8ff0-83f57687e48d",
    key="SWSH10",
    name="com.direwolfdigital.cake.data.archetypes.trainer.CancelingCologne.Name",
    display_name="Canceling Cologne",
    searchable_by=["Canceling Cologne", "Item"],
    subtypes=["Item"],
    collector_number=136,
    set_code="SWSH10",
    rarity=Rarities.Uncommon,
    effect=canceling_cologne
)

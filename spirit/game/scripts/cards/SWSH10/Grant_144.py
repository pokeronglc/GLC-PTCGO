from spirit.game.data_utils import SupporterCardDef, Ability, Activations
from spirit.game.attributes import AttrID, PokemonTypes, Rarities
from spirit.game.session.passives import TurnDamageModifier


async def grant(ctx):
    """This turn, your Fighting Pokemon's attacks do 30 more damage to the
    opponent's Active Pokemon (before W/R)."""
    ctx.add_turn_damage_modifier(TurnDamageModifier(
        30, ctx.player_id,
        source_predicate=lambda p: PokemonTypes.FIGHTING.value in (
            p.get_attribute(AttrID.POKEMON_TYPES) or []),
    ))



def _is_grant(card):
    from spirit.game.data_utils import def_for
    return getattr(def_for(card.archetype_id), "display_name", None) == "Grant"


def _cost_cards(board, player_id):
    hand = board.find_player_area(player_id, "hand")
    return [c for c in (hand.children if hand else []) if not _is_grant(c)]


def grant_recovery_condition(board, player_id, source=None):
    return len(_cost_cards(board, player_id)) >= 2


async def grant_recovery(ctx):
    """From the discard pile: discard 2 cards (not Grant) from your hand to put
    this Grant into your hand. Doesn't use up your Supporter for the turn."""
    cost = _cost_cards(ctx.board, ctx.player_id)
    if len(cost) < 2:
        return
    paid = await ctx.choose_cards(cost, 2, minimum=2,
                                  prompt="Choose 2 cards to discard (not Grant)")
    if len(paid) != 2:
        return
    await ctx.discard_cards(list(paid))
    await ctx.put_in_hand([ctx.source], reveal=True)


GRANT_TEXT = ("During your turn, if this card is in your discard pile, you may "
              "discard 2 cards, except any Grant, from your hand. If you do, put "
              "this card into your hand. (This effect doesn't use up your Supporter "
              "card for the turn.)")

card = SupporterCardDef(
    guid="a8f1995e-7be2-502c-a816-33872a499b32",
    key="SWSH10",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Grant.Name",
    display_name="Grant",
    searchable_by=["Grant", "Supporter"],
    subtypes=["Supporter"],
    collector_number=144,
    set_code="SWSH10",
    rarity=Rarities.Uncommon,
    effect=grant,
    abilities=[
        Ability(
            title="Grant",
            game_text=GRANT_TEXT,
            activation=Activations.UNLIMITED,
            usable_from="discard",
            condition=grant_recovery_condition,
            effect=grant_recovery,
        ),
    ],
)

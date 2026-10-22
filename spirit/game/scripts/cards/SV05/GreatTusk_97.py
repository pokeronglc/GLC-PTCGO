from spirit.game.data_utils import Attack, PokemonCardDef, subtypes_for
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities, TrainerType


def _ancient_supporter_played(ctx):
    return ctx.played_trainer_this_turn(
        lambda r: r[2] == TrainerType.SUPPORTER.value
        and "Ancient" in subtypes_for(r[0])
    ) > 0


async def land_collapse(ctx):
    """Discard the top card of the opponent's deck; 3 more if an Ancient
    Supporter was played from hand this turn."""
    count = 4 if _ancient_supporter_played(ctx) else 1
    cards = ctx.deck_top(count, ctx.opponent_id)
    if cards:
        await ctx.discard_cards(cards)


card = PokemonCardDef(
    guid="4c20eddf-46bf-5cb5-8ec3-b92536675d7b",
    key="SV05",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.GreatTusk.Name",
    display_name="Great Tusk",
    searchable_by=["Great Tusk", "Basic", "Ancient", "GreatTusk"],
    subtypes=["Basic", "Ancient"],
    collector_number=97,
    set_code="SV05",
    regulation_mark="H",
    rarity=Rarities.Uncommon,
    hp=140,
    elements=[PokemonTypes.FIGHTING],
    stage=PokemonStage.BASIC,
    retreat_cost=3,
    weakness_type=PokemonTypes.PSYCHIC,
    weakness_amount=2,
    family_id=984,
    abilities=[
        Attack(
            title="Land Collapse",
            game_text="Discard the top card of your opponent's deck. If you played an Ancient Supporter card from your hand during this turn, discard 3 more cards in this way.",
            cost={PokemonTypes.COLORLESS: 2},
            effect=land_collapse,
        ),
        Attack(
            title="Giant Tusk",
            cost={PokemonTypes.FIGHTING: 2, PokemonTypes.COLORLESS: 2},
            damage=160,
        ),
    ],
)

from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)


async def alluring_light(ctx):
    """Once during your turn: each player draws a card (you, then your opponent)."""
    await ctx.draw_cards(1)
    await ctx.draw_cards(1, player_id=ctx.opponent_id)


card = PokemonCardDef(
    guid="d9cd2eb4-ad7d-56fb-b3ac-6e047e8471cb",
    key="SV06",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Chandelure.Name",
    display_name="Chandelure",
    searchable_by=["Chandelure", "Stage 2", "Chandelure"],
    subtypes=["Stage 2"],
    collector_number=38,
    set_code="SV06",
    regulation_mark="H",
    rarity=Rarities.Rare,
    hp=130,
    elements=[PokemonTypes.FIRE],
    stage=PokemonStage.STAGE2,
    retreat_cost=2,
    weakness_type=PokemonTypes.WATER,
    weakness_amount=2,
    evolves_from="com.direwolfdigital.cake.data.archetypes.pokemon.Lampent.Name",
    family_id=607,
    abilities=[
        Ability(
            title="Alluring Light",
            game_text="Once during your turn, you may have each player draw a card.",
            effect=alluring_light,
            activation=Activations.ONCE_PER_TURN,
        ),
        Attack(
            title="Mind Ruler",
            game_text="This attack does 30 damage for each card in your opponent's hand.",
            cost={PokemonTypes.FIRE: 1},
            damage=30,
            damage_operator="x",
            effect=standard_attack,
        ),
    ],
)

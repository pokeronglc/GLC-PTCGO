from spirit.game.data_utils import PokemonCardDef, Attack, Ability
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities, AttrID
from spirit.game.card_effects.attacks_common import damage_per, count_in_play, bonus_if, defender_is_v


async def acidic_mucus(ctx):
    """50 damage for each of your opponent's Pokémon that has an Ability
    (rule buttons on dolls/fossils aren't Abilities; locked ones don't count)."""
    from spirit.game.card_effects.bw_era import _has_working_ability, has_real_ability
    n = sum(1 for p in ctx.opponent_pokemon_in_play()
            if _has_working_ability(ctx.board, p, has_real_ability))
    await ctx.deal_damage(50 * n)


card = PokemonCardDef(
    guid="b37d682c-193f-5d1d-b36a-06a5eae44cc8",
    key="SWSH7",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Flapple.Name",
    display_name="Flapple",
    searchable_by=["Flapple", "Stage 1", "Flapple"],
    subtypes=["Stage 1"],
    collector_number=120,
    set_code="SWSH7",
    rarity=Rarities.Rare,
    hp=80,
    elements=[PokemonTypes.DRAGON],
    stage=PokemonStage.STAGE1,
    retreat_cost=1,
    evolves_from="com.direwolfdigital.cake.data.archetypes.pokemon.Applin.Name",
    family_id=840,
    abilities=[
        Attack(
            title="Acidic Mucus",
            game_text="This attack does 50 damage for each of your opponent's Pok\u00e9mon in play that has an Ability.",
            cost={PokemonTypes.COLORLESS: 1},
            damage=50,
            damage_operator="x",
            effect=acidic_mucus,
        ),
        Attack(
            title="Fighting Tackle",
            game_text="If your opponent's Active Pok\u00e9mon is a Pok\u00e9mon V, this attack does 80 more damage.",
            cost={PokemonTypes.GRASS: 1, PokemonTypes.FIRE: 1},
            damage=80,
            damage_operator="+",
            effect=bonus_if(defender_is_v, 80),
        ),
    ],
)
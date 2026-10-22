from spirit.game.data_utils import PokemonCardDef, Attack, Ability
from spirit.game.card_effects.attacks_common import lock_chosen_defender_attack
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage, Rarities


async def memory_skip(ctx):
    """Choose 1 of the opponent's Active Pokemon's attacks; it can't be used
    during their next turn."""
    await ctx.deal_damage()
    await lock_chosen_defender_attack(ctx, prompt='Choose an attack to lock')


card = PokemonCardDef(
    guid="a573590e-327b-5e02-a35d-623c2e59cbe4",
    key="SWSH12",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Ralts.Name",
    display_name="Ralts",
    searchable_by=["Ralts", "Basic", "Ralts"],
    subtypes=["Basic"],
    collector_number=67,
    set_code="SWSH12",
    rarity=Rarities.Common,
    hp=60,
    elements=[PokemonTypes.PSYCHIC],
    stage=PokemonStage.BASIC,
    retreat_cost=1,
    weakness_type=PokemonTypes.METAL,
    family_id=280,
    abilities=[
        Attack(
            title="Memory Skip",
            game_text="Choose 1 of your opponent's Active Pok\u00e9mon's attacks. During your opponent's next turn, that Pok\u00e9mon can't use that attack.",
            cost={PokemonTypes.PSYCHIC: 1},
            damage=10,
            effect=memory_skip,
        ),
    ],
)
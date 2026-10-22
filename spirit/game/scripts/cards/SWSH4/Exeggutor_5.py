from spirit.game.data_utils import PokemonCardDef, Attack, Ability
from spirit.game.card_effects.attacks_common import lock_chosen_defender_attack
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage, Rarities


async def head_crack(ctx):
    """Choose 1 of the opponent's Active Pokemon's attacks; it can't be used
    during their next turn."""
    await ctx.deal_damage()
    await lock_chosen_defender_attack(ctx, prompt='Choose an attack to lock')


card = PokemonCardDef(
    guid="143bdca5-77c6-5544-a0b5-bb646905f463",
    key="SWSH4",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Exeggutor.Name",
    display_name="Exeggutor",
    searchable_by=["Exeggutor", "Stage 1", "Exeggutor"],
    subtypes=["Stage 1"],
    collector_number=5,
    set_code="SWSH4",
    rarity=Rarities.Rare,
    hp=140,
    elements=[PokemonTypes.GRASS],
    stage=PokemonStage.STAGE1,
    retreat_cost=3,
    weakness_type=PokemonTypes.FIRE,
    evolves_from="com.direwolfdigital.cake.data.archetypes.pokemon.Exeggcute.Name",
    family_id=102,
    abilities=[
        Attack(
            title="Head Crack",
            game_text="Choose 1 of your opponent's Active Pok\u00e9mon's attacks. During your opponent's next turn, that Pok\u00e9mon can't use that attack.",
            cost={PokemonTypes.GRASS: 1},
            damage=30,
            effect=head_crack,
        ),
        Attack(
            title="Solar Beam",
            cost={PokemonTypes.GRASS: 1, PokemonTypes.COLORLESS: 2},
            damage=90,
        ),
    ],
)
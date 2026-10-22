from spirit.game.data_utils import PokemonCardDef, Attack, Ability
from spirit.game.card_effects.attacks_common import lock_chosen_defender_attack
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.support_common import draw_attack


async def torment(ctx):
    """30 damage. Choose 1 of the opponent's Active Pokemon's attacks; it
    can't be used during their next turn."""
    await ctx.deal_damage()
    await lock_chosen_defender_attack(ctx, prompt='Choose an attack to lock')


card = PokemonCardDef(
    guid="52861551-aac3-5659-a5f6-df39484b10d8",
    key="SWSH4",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Sableye.Name",
    display_name="Sableye",
    searchable_by=["Sableye", "Basic", "Sableye"],
    subtypes=["Basic"],
    collector_number=105,
    set_code="SWSH4",
    rarity=Rarities.Uncommon,
    hp=70,
    elements=[PokemonTypes.DARKNESS],
    stage=PokemonStage.BASIC,
    retreat_cost=1,
    weakness_type=PokemonTypes.GRASS,
    family_id=302,
    abilities=[
        Attack(
            title="Filch",
            game_text="Draw a card.",
            cost={PokemonTypes.COLORLESS: 1},
            effect=draw_attack(1),
        ),
        Attack(
            title="Torment",
            game_text="Choose 1 of your opponent's Active Pok\u00e9mon's attacks. During your opponent's next turn, that Pok\u00e9mon can't use that attack.",
            cost={PokemonTypes.COLORLESS: 2},
            damage=30,
            effect=torment,
        ),
    ],
)
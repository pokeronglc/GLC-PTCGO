from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = FossilItemCardDef(
    guid="4d2f3e05-3346-5374-a3c6-2f2c7effa7d5",
    key="SV07",
    name="com.direwolfdigital.cake.data.archetypes.trainer.AntiqueRootFossil.Name",
    display_name="Antique Root Fossil",
    searchable_by=["Antique Root Fossil", "Item", "AntiqueRootFossil"],
    subtypes=["Item"],
    collector_number=130,
    set_code="SV07",
    regulation_mark="H",
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Primal Root",
            game_text="As long as this Pokémon is in the Active Spot, attacks used by your opponent's Basic Pokémon cost Colorless more.",
            passive=standard_passive("As long as this Pokémon is in the Active Spot, attacks used by your opponent's Basic Pokémon cost Colorless more."),
        ),
    ],
)

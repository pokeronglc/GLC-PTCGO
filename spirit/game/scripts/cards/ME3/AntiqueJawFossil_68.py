from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = FossilItemCardDef(
    guid="fa34c662-3f2c-513c-b977-69f0dbad66e4",
    key="ME3",
    name="com.direwolfdigital.cake.data.archetypes.trainer.AntiqueJawFossil.Name",
    display_name="Antique Jaw Fossil",
    searchable_by=["Antique Jaw Fossil", "Item", "AntiqueJawFossil"],
    subtypes=["Item"],
    collector_number=68,
    set_code="ME3",
    regulation_mark="J",
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Intimidating Jaw",
            game_text="As long as this Pokémon is in the Active Spot, attacks used by your opponent's Active Pokémon do 30 less damage (before applying Weakness and Resistance).",
            passive=standard_passive("As long as this Pokémon is in the Active Spot, attacks used by your opponent's Active Pokémon do 30 less damage (before applying Weakness and Resistance)."),
        ),
    ],
)

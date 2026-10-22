from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_effect,
)


card = FossilItemCardDef(
    guid="ea6326a0-4192-5ef2-a996-423bd0e31cf7",
    key="ME3",
    name="com.direwolfdigital.cake.data.archetypes.trainer.AntiqueSailFossil.Name",
    display_name="Antique Sail Fossil",
    searchable_by=["Antique Sail Fossil", "Item", "AntiqueSailFossil"],
    subtypes=["Item"],
    collector_number=69,
    set_code="ME3",
    regulation_mark="J",
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Protective Sail",
            game_text="Whenever your opponent plays a Supporter card from their hand, prevent all effects of that card done to this Pokémon.",
            passive=standard_passive("Whenever your opponent plays a Supporter card from their hand, prevent all effects of that card done to this Pokémon."),
        ),
    ],
)

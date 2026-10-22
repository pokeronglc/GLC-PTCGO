from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_condition, standard_trainer_effect,
)


card = FossilItemCardDef(
    guid='7a9a3cf8-041b-53a4-b40f-57efa201c75c',
    key='SV035',
    name='com.direwolfdigital.cake.data.archetypes.trainer.AntiqueDomeFossil.Name',
    display_name='Antique Dome Fossil',
    searchable_by=['Antique Dome Fossil', 'Item', 'AntiqueDomeFossil'],
    subtypes=['Item'],
    collector_number=152,
    set_code='SV035',
    regulation_mark='G',
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Domed Armor",
            game_text="This Pokémon takes 30 less damage from attacks (after applying Weakness and Resistance).",
            passive=standard_passive("This Pokémon takes 30 less damage from attacks (after applying Weakness and Resistance)."),
        ),
    ],
)

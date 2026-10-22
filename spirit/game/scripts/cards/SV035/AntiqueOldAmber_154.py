from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_condition, standard_trainer_effect,
)


card = FossilItemCardDef(
    guid='d36a5bb1-24f7-529b-8484-86a8d577d7f0',
    key='SV035',
    name='com.direwolfdigital.cake.data.archetypes.trainer.AntiqueOldAmber.Name',
    display_name='Antique Old Amber',
    searchable_by=['Antique Old Amber', 'Item', 'AntiqueOldAmber'],
    subtypes=['Item'],
    collector_number=154,
    set_code='SV035',
    regulation_mark='G',
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Amber Protection",
            game_text="Prevent all effects of your opponent's Pokémon's Abilities done to this Pokémon.",
            passive=standard_passive("Prevent all effects of your opponent's Pokémon's Abilities done to this Pokémon."),
        ),
    ],
)

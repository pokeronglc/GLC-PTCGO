from spirit.game.data_utils import FossilItemCardDef, Ability, Triggers
from spirit.game.card_effects.trainers import FossilBodyPassive, fossil_discard_ability
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive, standard_stadium_ability,
    standard_trainer_condition, standard_trainer_effect,
)


card = FossilItemCardDef(
    guid='b500d3cb-ce10-5632-a8aa-325059584f49',
    key='SV035',
    name='com.direwolfdigital.cake.data.archetypes.trainer.AntiqueHelixFossil.Name',
    display_name='Antique Helix Fossil',
    searchable_by=['Antique Helix Fossil', 'Item', 'AntiqueHelixFossil'],
    subtypes=['Item'],
    collector_number=153,
    set_code='SV035',
    regulation_mark='G',
    rarity=Rarities.Common,
    hp=60,
    passive=FossilBodyPassive(blocks_conditions=True),
    abilities=[
        fossil_discard_ability(),
        Ability(
            title="Helical Swell",
            game_text="As long as this Pokémon is in the Active Spot, your opponent can't play any Stadium cards from their hand.",
            passive=standard_passive("As long as this Pokémon is in the Active Spot, your opponent can't play any Stadium cards from their hand."),
        ),
    ],
)

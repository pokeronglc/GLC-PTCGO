from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import PokemonTypes, Rarities
from spirit.game.card_effects.standard_era import standard_trainer_condition
from spirit.game.card_effects.bw10 import is_basic_energy_of_type

TEXT = ('Search your deck for up to 4 Fire Energy cards and attach them to 1 of your '
        'Pokémon. Then, shuffle your deck. Your turn ends.')


async def kiawe(ctx):
    """Up to 4 Fire Energy from the deck, all onto ONE chosen Pokémon."""
    picks = await ctx.search_deck(
        lambda c: is_basic_energy_of_type(c, PokemonTypes.FIRE), count=4, minimum=0,
        prompt="Choose up to 4 Fire Energy cards to attach to 1 of your Pokémon.",
    )
    if picks:
        target = await ctx.choose_pokemon(
            ctx.my_pokemon_in_play(), "Choose a Pokémon to attach the Fire Energy to")
        if target is not None:
            ctx.visual_targets = [target.entity_id]
            for energy in picks:
                await ctx.attach_energy(energy, target)
    await ctx.shuffle_deck()


kiawe.printed_ends_turn = True


card = SupporterCardDef(
    guid='be3ca5ba-43d8-5792-9d4c-6d4ea7da4d07',
    key='SM3',
    name='com.direwolfdigital.cake.data.archetypes.trainer.Kiawe.Name',
    display_name='Kiawe',
    searchable_by=['Kiawe', 'Supporter', 'Kiawe'],
    subtypes=['Supporter'],
    collector_number=116,
    set_code='SM3',
    regulation_mark=None,
    rarity=Rarities.Uncommon,
    effect=kiawe,
    condition=standard_trainer_condition(TEXT),
)

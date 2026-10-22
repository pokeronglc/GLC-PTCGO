from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)
from spirit.game.session.effects import is_supporter_card


async def hearsay(ctx):
    """Choose 1: a Supporter from the discard pile, or search the deck for one."""
    discarded = [c for c in ctx.discard_pile() if is_supporter_card(c)]
    options, labels = [], []
    if discarded:
        options.append("discard")
        labels.append("Supporter from discard pile")
    if ctx.deck():
        options.append("deck")
        labels.append("Search your deck for a Supporter")
    if not options:
        return
    pick = await ctx.choose("Hearsay", labels + ["Don't use"])
    if pick >= len(options):
        return
    if options[pick] == "discard":
        chosen = await ctx.choose_cards(discarded, 1, minimum=1, prompt="Choose a Supporter card")
        await ctx.put_in_hand(chosen, reveal=True)
        return
    picks = await ctx.search_deck(is_supporter_card, count=1, minimum=0,
                                  reveal_result=True, prompt="Choose a Supporter card")
    await ctx.put_in_hand(picks, reveal=True)
    await ctx.shuffle_deck()


card = PokemonCardDef(
    guid='a0903616-808b-56d7-b0e0-eac0b13c46e0',
    key='SV2',
    name='com.direwolfdigital.cake.data.archetypes.pokemon.Pelipper.Name',
    display_name='Pelipper',
    searchable_by=['Pelipper', 'Stage 1', 'Pelipper'],
    subtypes=['Stage 1'],
    collector_number=159,
    set_code='SV2',
    regulation_mark='G',
    rarity=Rarities.Uncommon,
    hp=120,
    elements=[PokemonTypes.COLORLESS],
    stage=PokemonStage.STAGE1,
    retreat_cost=2,
    weakness_type=PokemonTypes.LIGHTNING,
    weakness_amount=2,
    resistance_type=PokemonTypes.FIGHTING,
    resistance_amount=30,
    evolves_from='com.direwolfdigital.cake.data.archetypes.pokemon.Wingull.Name',
    family_id=278,
    abilities=[
        Ability(
            title='Hearsay',
            game_text='When you play this Pokémon from your hand to evolve 1 of your Pokémon during your turn, you may choose 1: put a Supporter card from your discard pile into your hand; or search your deck for a Supporter card, reveal it, put it into your hand, and then shuffle your deck.',
            effect=hearsay,
            trigger=Triggers.ON_EVOLVE,
        ),
        Attack(
            title='Wing Attack',
            cost={PokemonTypes.COLORLESS: 3},
            damage=90,
        ),
    ],
)

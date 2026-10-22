from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)
from spirit.game.session.passives import Passive


class LeapThroughTimePassive(Passive):
    """The coin is flipped while the Prize count is worked out, so heads can
    stop the Prize and send the whole stack to the deck instead of the
    discard pile."""

    async def extra_prizes_for_knockout(self, pokemon, ctx, count, carrier):
        if pokemon is not carrier:
            return 0
        heads = (await ctx.flip_coins(1, "Leap Through Time", source=carrier,
                                      player_id=carrier.owning_player_id))[0]
        carrier._leap_through_time = bool(heads)
        return -count if heads else 0

    def knockout_destination_for(self, pokemon, ctx, carrier):
        return "deck" if pokemon is carrier and getattr(carrier, "_leap_through_time", False) else None

    def knockout_attachment_destination(self, pokemon, ctx, carrier):
        return self.knockout_destination_for(pokemon, ctx, carrier)


async def leap_through_time(ctx):
    """Heads: the stack is already in the deck (moved by the Knock Out); shuffle it."""
    celebi = ctx.source
    if getattr(celebi, "_leap_through_time", False):
        celebi._leap_through_time = False
        await ctx.shuffle_deck()


card = PokemonCardDef(
    guid='3fe533d2-cbc3-5384-b0be-eba42cb313c4',
    key='Promo_XY',
    name='com.direwolfdigital.cake.data.archetypes.pokemon.Celebi.Name',
    display_name='Celebi',
    searchable_by=['Celebi', 'Basic', 'Celebi'],
    subtypes=['Basic'],
    collector_number=93,
    set_code='Promo_XY',
    regulation_mark=None,
    rarity=Rarities.RarePromo,
    hp=70,
    elements=[PokemonTypes.GRASS],
    stage=PokemonStage.BASIC,
    retreat_cost=1,
    weakness_type=PokemonTypes.FIRE,
    weakness_amount=2,
    family_id=251,
    abilities=[
        Ability(
            title='Leap Through Time',
            game_text="When this Pokémon is Knocked Out, flip a coin. If heads, shuffle this Pokémon and all cards attached to it into your deck, and your opponent can't take any Prize cards for it.",
            effect=leap_through_time,
            trigger=Triggers.ON_KNOCKED_OUT,
            passive=LeapThroughTimePassive(),
        ),
        Attack(
            title='Sparkle Motion',
            game_text="Put 1 damage counter on each of your opponent's Pokémon.",
            cost={PokemonTypes.GRASS: 1},
            effect=standard_attack,
        ),
    ],
    passive=standard_passive("Prevent all effects of your opponent's Pokémon's Abilities done to this Pokémon."),
)

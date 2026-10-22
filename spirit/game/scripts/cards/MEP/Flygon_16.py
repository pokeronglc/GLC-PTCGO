from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)


async def sandy_flapping(ctx):
    """ON_EVOLVE via the generic interpreter; the KO clause only when this
    Pokemon was Active and Knocked Out by damage from an opponent's attack."""
    if getattr(ctx, "knocked_out_pokemon", None) is None:
        await standard_ability(ctx)
        return
    if not (ctx.ko_from_attack and ctx.was_active_at_ko):
        return
    top = ctx.deck_top(2, ctx.opponent_id)
    if not top or not await ctx.ask_yes_no("Use Sandy Flapping?"):
        return
    await ctx.discard_cards(top)


card = PokemonCardDef(
    guid="c52cef67-07be-5b4d-a6b5-85228d69e1d6",
    key="MEP",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Flygon.Name",
    display_name="Flygon",
    searchable_by=["Flygon", "Stage 2", "Flygon"],
    subtypes=["Stage 2"],
    collector_number=16,
    set_code="MEP",
    regulation_mark="I",
    rarity=Rarities.Rare,
    hp=150,
    elements=[PokemonTypes.FIGHTING],
    stage=PokemonStage.STAGE2,
    retreat_cost=1,
    weakness_type=PokemonTypes.GRASS,
    weakness_amount=2,
    evolves_from="com.direwolfdigital.cake.data.archetypes.pokemon.Vibrava.Name",
    abilities=[
        Ability(
            title="Sandy Flapping",
            game_text="Once during your turn, when you play this Pokémon from your hand to evolve 1 of your Pokémon, you may use this Ability. You may also use this Ability if this Pokémon is in the Active Spot and is Knocked Out by damage from an attack from your opponent's Pokémon. Discard the top 2 cards of your opponent's deck.",
            effect=sandy_flapping,
            # Event-only (never click-usable), like the shared normalizer.
            trigger=(Triggers.ON_EVOLVE, Triggers.ON_KNOCKED_OUT),
        ),
        Attack(
            title="Cutting Wind",
            cost={PokemonTypes.FIGHTING: 2},
            damage=130,
        ),
    ],
)

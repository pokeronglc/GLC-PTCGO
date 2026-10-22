from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)



def _is_larrys(pokemon) -> bool:
    from spirit.game.data_utils import def_for
    return (getattr(def_for(pokemon.archetype_id), "display_name", "") or "").startswith("Larry's ")


def lethargic_charge_condition(board, player_id, pokemon):
    """Benched, your Active is a Larry's Pokémon, and you have an Energy card in hand."""
    from spirit.game.session.effects import is_energy_card
    active = board.active_pokemon(player_id)
    hand = board.find_player_area(player_id, "hand")
    return (pokemon is not active and active is not None and _is_larrys(active)
            and any(is_energy_card(c) for c in (hand.children if hand else [])))


async def lethargic_charge(ctx):
    """Attach an Energy card from your hand to your Active Larry's Pokémon
    (owner report Oct 15: it attached to any Pokémon)."""
    from spirit.game.session.effects import is_energy_card
    active = ctx.my_active()
    if active is None or not _is_larrys(active):
        return
    pool = [c for c in ctx.hand() if is_energy_card(c)]
    if not pool:
        return
    picks = await ctx.choose_cards(
        pool, 1, prompt="Choose an Energy card to attach to your Active Larry's Pokémon")
    if picks:
        await ctx.attach_energy(picks[0], active)


card = PokemonCardDef(
    guid="e3c812a5-fb90-5a1a-ae70-a6fce31a6a1f",
    key="ME2PT5",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.LarrysKomala.Name",
    display_name="Larry's Komala",
    searchable_by=["Larry's Komala", "Basic", "LarrysKomala"],
    subtypes=["Basic"],
    collector_number=175,
    set_code="ME2PT5",
    regulation_mark="J",
    rarity=Rarities.Common,
    hp=90,
    elements=[PokemonTypes.COLORLESS],
    stage=PokemonStage.BASIC,
    retreat_cost=2,
    weakness_type=PokemonTypes.FIGHTING,
    weakness_amount=2,
    family_id=775,
    abilities=[
        Ability(
            title="Lethargic Charge",
            game_text="Once during your turn, if this Pokémon is on your Bench, you may use this Ability. Attach an Energy card from your hand to your Active Larry's Pokémon.",
            effect=lethargic_charge,
            condition=lethargic_charge_condition,
            activation=Activations.ONCE_PER_TURN,
        ),
        Attack(
            title="Dozing Draw",
            game_text="This Pokémon is now Asleep. Draw 2 cards.",
            cost={PokemonTypes.COLORLESS: 1},
            effect=standard_attack,
        ),
    ],
)

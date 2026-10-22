from spirit.game.data_utils import Attack, Ability, PokemonCardDef, Activations, Triggers
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.card_effects.standard_era import (
    standard_ability, standard_attack, standard_passive,
)
from spirit.game.session.passives import Passive, effective_pokemon_types


class _SpitefulSwirl(Passive):
    """"If your Active Darkness Pokémon is damaged by an attack from your
    opponent's Pokémon (even if it is Knocked Out), place 1 damage counter on
    the Attacking Pokémon." Spiritomb watches the Active from anywhere in
    play, so this is an after-attack observer (like Wishiwashi's
    Counterattack Grouping), not a trigger on Spiritomb itself."""

    async def after_attack_damage(self, ctx, carrier):
        owner = carrier.owning_player_id
        attacker = ctx.attacker
        if attacker is None or attacker.owning_player_id == owner:
            return
        board = ctx.board
        hit = [board.get_entity(eid) for eid in ctx.attack_damage_active]
        if not any(p is not None and p.owning_player_id == owner
                   and PokemonTypes.DARKNESS.value in effective_pokemon_types(board, p)
                   for p in hit):
            return
        from spirit.game.session.effects import EffectContext
        from spirit.game.data_utils import def_for
        ability = next(a for a in def_for(carrier.archetype_id).abilities
                       if a.title == "Spiteful Swirl")
        reaction = EffectContext(ctx.session, owner, carrier, ability)
        await reaction.deal_damage(10, attacker, as_counters=True)
        ctx.knockouts.extend(p for p in reaction.knockouts if p not in ctx.knockouts)
        await ctx.session._flush_effect_runs(reaction)


card = PokemonCardDef(
    guid="3d412a02-a6f7-53d5-acd4-970e747fdb4e",
    key="ME1",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Spiritomb.Name",
    display_name="Spiritomb",
    searchable_by=["Spiritomb", "Basic", "Spiritomb"],
    subtypes=["Basic"],
    collector_number=87,
    set_code="ME1",
    regulation_mark="I",
    rarity=Rarities.Uncommon,
    hp=80,
    elements=[PokemonTypes.DARKNESS],
    stage=PokemonStage.BASIC,
    retreat_cost=1,
    weakness_type=PokemonTypes.GRASS,
    weakness_amount=2,
    family_id=442,
    abilities=[
        Ability(
            title="Spiteful Swirl",
            game_text="If your Active Darkness Pokémon is damaged by an attack from your opponent's Pokémon (even if your Active Darkness Pokémon is Knocked Out), place 1 damage counter on the Attacking Pokémon.",
            passive=_SpitefulSwirl(),
        ),
        Attack(
            title="Mountain Breaker",
            game_text="Discard the top card of your opponent's deck.",
            cost={PokemonTypes.DARKNESS: 1},
            damage=10,
            effect=standard_attack,
        ),
    ],
)

from spirit.game.data_utils import PokemonCardDef, Attack, Ability
from spirit.game.attributes import PokemonTypes, PokemonStage, Rarities
from spirit.game.session.passives import Passive, carrier_pokemon


class _TemptingTrapVulnerability(Passive):
    def modify_damage_taken(self, calc, carrier):
        # Only the marked Pokemon, only attack damage (it used to add 90 to
        # every hit on the board, the attacker's own Pokemon included).
        if calc.is_attack and carrier_pokemon(carrier) is calc.target:
            calc.amount += 90


async def tempting_trap(ctx):
    """Defender can't retreat next turn; takes 90 more (after W/R) during your next turn."""
    target = ctx.defender
    if target is None or ctx.effects_blocked(target):
        return
    ctx.lock_retreat(target)
    # Owner ruling Oct 13: +90 only during the attacker's own next turn.
    ctx.add_passive_through_own_next_turn(target, _TemptingTrapVulnerability(),
                                          only_own_turn=True)


card = PokemonCardDef(
    guid="b5dc5855-de8b-5ac6-b805-6d911440ade7",
    key="SWSH11",
    name="com.direwolfdigital.cake.data.archetypes.pokemon.Mawile.Name",
    display_name="Mawile",
    searchable_by=["Mawile", "Basic", "Mawile"],
    subtypes=["Basic"],
    collector_number=71,
    set_code="SWSH11",
    rarity=Rarities.Common,
    hp=90,
    elements=[PokemonTypes.PSYCHIC],
    stage=PokemonStage.BASIC,
    retreat_cost=1,
    weakness_type=PokemonTypes.METAL,
    family_id=303,
    abilities=[
        Attack(
            title="Tempting Trap",
            game_text="During your opponent's next turn, the Defending Pok\u00e9mon can't retreat. During your next turn, the Defending Pok\u00e9mon takes 90 more damage from attacks (after applying Weakness and Resistance).",
            cost={PokemonTypes.COLORLESS: 1},
            effect=tempting_trap,
        ),
        Attack(
            title="Bite",
            cost={PokemonTypes.PSYCHIC: 1, PokemonTypes.COLORLESS: 2},
            damage=90,
        ),
    ],
)
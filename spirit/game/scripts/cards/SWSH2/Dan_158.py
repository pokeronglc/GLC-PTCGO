import logging
from spirit.game.data_utils import SupporterCardDef
from spirit.game.attributes import Rarities

log = logging.getLogger(__name__)


RPS = ["Rock", "Paper", "Scissors"]
_BEATS = {0: 2, 1: 0, 2: 1}       # rock > scissors, paper > rock, scissors > paper
_MAX_ROUNDS = 10                   # ties replay; stop a stalled game eventually


async def dan(ctx):
    """Draw 2 cards. Play Rock-Paper-Scissors with your opponent. If you win,
    draw 2 more cards.

    Each player picks privately: Dan's player picks first, then the opponent
    is asked without seeing that pick. A tie is replayed."""
    await ctx.draw_cards(2)
    prompt_note = ""
    for _ in range(_MAX_ROUNDS):
        mine = await ctx.choose(
            prompt_note + "Dan: Rock-Paper-Scissors! Pick one.", RPS, use_panel=False)
        theirs = await ctx.choose(
            prompt_note + "Dan: your opponent is playing Rock-Paper-Scissors. Pick one.",
            RPS, player_id=ctx.opponent_id, use_panel=False)
        log.info("[Dan] %s picked %s, %s picked %s", ctx.player_id, RPS[mine],
                 ctx.opponent_id, RPS[theirs])
        if mine == theirs:
            prompt_note = f"Tie ({RPS[mine]})! Go again. "
            continue
        if _BEATS[mine] == theirs:
            await ctx.draw_cards(2)
        return


card = SupporterCardDef(
    guid="eef4c1b0-77f4-5523-a0c4-c1749b53d1a8",
    key="SWSH2",
    name="com.direwolfdigital.cake.data.archetypes.trainer.Dan.Name",
    display_name="Dan",
    searchable_by=["Dan", "Supporter"],
    subtypes=["Supporter"],
    collector_number=158,
    set_code="SWSH2",
    rarity=Rarities.Uncommon,
    effect=dan
)

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from spirit.database.base import Base


class PlayerStats(Base):
    """Lifetime totals behind the client's Profile > Game Stats tab."""
    __tablename__ = 'player_stats'

    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.account_id'), primary_key=True)
    cards_drawn: Mapped[int] = mapped_column(default=0)
    damage_dealt: Mapped[int] = mapped_column(default=0)
    damage_taken: Mapped[int] = mapped_column(default=0)
    games_played: Mapped[int] = mapped_column(default=0)
    seconds_played: Mapped[int] = mapped_column(default=0)
    upset_wins: Mapped[int] = mapped_column(default=0)

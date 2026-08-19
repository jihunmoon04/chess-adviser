from typing import Optional
from pydantic import BaseModel, Field


class MoveAnalysisRequest(BaseModel):
    before_fen: str = Field(
        ...,
        description="FEN string of the board state before the move was played",
        json_schema_extra={"example": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"},
    )
    after_fen: str = Field(
        ...,
        description="FEN string of the board state after the move was played",
        json_schema_extra={"example": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"},
    )
    move_san: str = Field(
        ...,
        description="Standard Algebraic Notation of the played move",
        json_schema_extra={"example": "e5"},
    )
    move_uci: Optional[str] = Field(
        default=None,
        description="UCI coordinate notation of the played move (e.g., e7e5)",
        json_schema_extra={"example": "e7e5"},
    )
    time_control: Optional[str] = Field(
        default=None,
        description="Time control category (bullet, blitz, rapid, classical)",
        json_schema_extra={"example": "rapid"},
    )
    move_history_san: Optional[list[str]] = Field(
        default_factory=list,
        description="Full move history up to this move in SAN format (e.g. ['e4', 'c5', 'Nf3'])",
    )

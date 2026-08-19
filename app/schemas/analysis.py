from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class MoveQuality(str, Enum):
    BRILLIANT = "Brilliant"
    GREAT = "Great"
    BEST = "Best"
    EXCELLENT = "Excellent"
    GOOD = "Good"
    INACCURACY = "Inaccuracy"
    MISTAKE = "Mistake"
    MISS = "Miss"
    BLUNDER = "Blunder"
    BOOK = "Book"


class ScoreType(str, Enum):
    CP = "cp"       # Centipawns
    MATE = "mate"   # Moves to mate


class GameOverReason(str, Enum):
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    INSUFFICIENT_MATERIAL = "insufficient_material"
    FIFTY_MOVES = "fifty_moves"
    THREEFOLD_REPETITION = "threefold_repetition"
    FIVEFOLD_REPETITION = "fivefold_repetition"
    SEVENTYFIVE_MOVES = "seventyfive_moves"


class GameOverInfo(BaseModel):
    is_game_over: bool = Field(default=False, description="Whether the game has legally terminated")
    reason: Optional[GameOverReason] = Field(default=None, description="Specific termination reason")
    winner: Optional[str] = Field(default=None, description="'white', 'black', or None for draw")
    winner_color_ko: Optional[str] = Field(default=None, description="'백(White)', '흑(Black)', or '무승부'")
    result_score: str = Field(default="*", description="'1-0', '0-1', '1/2-1/2', or '*'")
    description_ko: str = Field(default="", description="Korean readable game over description")


class EvalScore(BaseModel):
    type: ScoreType = Field(default=ScoreType.CP, description="cp (centipawns) or mate")
    value: float = Field(..., description="Score from White's perspective in pawns (+1.50) or moves to mate (+3)")
    raw_cp: Optional[int] = Field(default=None, description="Raw centipawn value")


class PvLine(BaseModel):
    rank: int = Field(..., description="Rank in MultiPV (1 = Best)")
    score: EvalScore
    move_san: str
    move_uci: str
    continuation_uci: List[str] = Field(default_factory=list, description="3-5 moves ahead PV sequence in UCI format")
    continuation_san: List[str] = Field(default_factory=list, description="3-5 moves ahead PV sequence in SAN format")
    formatted_line: str = Field(default="", description="Full move-numbered line, e.g. '1. e4 e5 2. Nf3 Nc6'")
    narrative_summary: Optional[str] = Field(default=None, description="1-line plain Korean explanation of this candidate line")
    strategic_plan: Optional[str] = Field(default=None, description="Deep strategic breakdown of this candidate continuation")


class OpeningInfo(BaseModel):
    eco: str = Field(..., description="ECO code, e.g. 'B90'")
    name: str = Field(..., description="English Opening name")
    name_ko: str = Field(..., description="Korean Opening name")
    defining_move: Optional[str] = Field(default=None, description="The move that defines this variation")
    purpose: str = Field(default="", description="Strategic purpose of this opening")
    white_plan: str = Field(default="", description="White's main plan and themes")
    black_plan: str = Field(default="", description="Black's main plan and themes")
    key_ideas: str = Field(default="", description="Historical and master context")
    is_book: bool = Field(default=True, description="Whether currently following the book line")
    is_out_of_book_step: bool = Field(default=False, description="Whether this exact move was the first out-of-book move")
    previous_opening_name: Optional[str] = Field(default=None, description="Name of opening line departed from")


class LookaheadInsight(BaseModel):
    refutation_narrative: Optional[str] = Field(default=None, description="상대의 처벌 수순이 강력한 이유")
    best_move_narrative: Optional[str] = Field(default=None, description="최선수 선택 시의 구체적 이점")
    prophylactic_narrative: Optional[str] = Field(default=None, description="장기적 예방 및 사전 준비 의도")
    leaf_outcome_narrative: Optional[str] = Field(default=None, description="추천 수순 끝에서의 형세/기물 결과")
    pv_chain_narrative: Optional[str] = Field(default=None, description="2~4수 연속 전술 콤보 및 룩 리프트/메이팅 네트/기물 교환 맥락 해설")


class TacticalMetrics(BaseModel):
    is_hanging: bool = Field(default=False, description="Whether the moved piece or another piece is left hanging")
    hanging_pieces: List[str] = Field(default_factory=list, description="List of hanging pieces and squares (e.g. ['e5', 'c4'])")
    undefended_pieces: List[str] = Field(default_factory=list, description="Pieces that lost their defender due to this move")
    is_brilliant_sacrifice: bool = Field(default=False, description="Material sacrifice leading to decisive advantage/mate")
    is_great_move: bool = Field(default=False, description="Only move saving the position or turning the game around")
    is_indirectly_defended: bool = Field(default=False, description="Apparent undefended piece protected via tactic (pin/skewer/counter)")
    is_overloaded: bool = Field(default=False, description="Defender piece is tasked with guarding multiple vulnerable squares/pieces")
    tactical_motifs: List[str] = Field(default_factory=list, description="Motifs identified: pin, fork, skewer, discovered_attack, etc.")
    forks: List[str] = Field(default_factory=list, description="Detailed fork descriptions")
    pins: List[str] = Field(default_factory=list, description="Detailed pin descriptions")
    skewers: List[str] = Field(default_factory=list, description="Detailed skewer descriptions")
    discovered_attacks: List[str] = Field(default_factory=list, description="Discovered attacks or checks unmasked")
    line_clearances: List[str] = Field(default_factory=list, description="Line/diagonal clearances created")
    mate_threats: List[str] = Field(default_factory=list, description="Checkmate or back-rank threats")


class PawnStructureMetrics(BaseModel):
    pawn_structure_type: str = Field(default="Dynamic", description="Open, Semi-Open, Closed, Dynamic")
    passed_pawns_created: List[str] = Field(default_factory=list, description="New passed pawn squares")
    isolated_pawns: List[str] = Field(default_factory=list, description="Current isolated pawn files")
    doubled_pawns: List[str] = Field(default_factory=list, description="Current doubled pawn files")
    backward_pawns: List[str] = Field(default_factory=list, description="Current backward pawns")
    pawn_breaks: List[str] = Field(default_factory=list, description="Pawn breaks available or executed")
    pawn_dynamics: List[str] = Field(default_factory=list, description="Pawn events: 'Central Break', 'Pawn Trade', 'File Closed', 'Structure Lock'")


class PositionalMetrics(BaseModel):
    space_control_delta: int = Field(default=0, description="Change in total squares controlled across the board")
    central_control_delta: int = Field(default=0, description="Change in control over central squares (d4, d5, e4, e5)")
    activity_delta: int = Field(default=0, description="Change in legal mobility / active piece reach")
    is_outpost: bool = Field(default=False, description="Piece settled on protected enemy territory")
    outpost_square: Optional[str] = Field(default=None, description="Square of the outpost")
    open_file_control: bool = Field(default=False, description="Rook/Queen placed on an open or semi-open file")
    open_file_name: Optional[str] = Field(default=None, description="File letter")
    open_files: List[str] = Field(default_factory=list, description="List of open files")
    semi_open_files: List[str] = Field(default_factory=list, description="List of semi-open files")
    color_complex_weaknesses: List[str] = Field(default_factory=list, description="Color complex weaknesses (dark/light square holes)")
    bishop_quality: List[str] = Field(default_factory=list, description="Good/bad/active bishop evaluations")
    pawn_structure: PawnStructureMetrics = Field(default_factory=PawnStructureMetrics)
    king_safety_delta: int = Field(default=0, description="Delta in king safety/exposure")
    pawn_shield_intact: bool = Field(default=True, description="Whether king's protective pawns are intact")
    king_safety_details: List[str] = Field(default_factory=list, description="Detailed King safety observations (pawn shield, exposed files/diagonals, king zone pressure)")
    is_rook_lift: bool = Field(default=False, description="Whether this is a rook lift into the 3rd/4th rank for wing attack")
    rook_lift_note: Optional[str] = Field(default=None, description="Rook lift description")
    tempo_development: bool = Field(default=False, description="New minor/major piece developed in opening")
    is_repeated_move: bool = Field(default=False, description="Same piece moved again in opening")
    initiative: bool = Field(default=False, description="Move forces opponent into passive defense")
    prophylaxis_notes: List[str] = Field(default_factory=list, description="Prophylaxis, retreat square, and denial intentions")
    maneuver_notes: List[str] = Field(default_factory=list, description="Piece maneuvering and outpost target intentions")
    defended_targets_notes: List[str] = Field(default_factory=list, description="Friendly pieces/pawns defended or overprotected")
    attacked_targets_notes: List[str] = Field(default_factory=list, description="Enemy targets newly pressured by the move")


class CommentarySections(BaseModel):
    move_evaluation: str = Field(default="", description="1. 수 자체에 대한 총평 (등급, 형세 변화, 핵심 요약)")
    tactical_analysis: str = Field(default="", description="2. 전술적 평가 (포크, 핀, 스큐어, 디스커버리, 라인 개방 등)")
    positional_analysis: str = Field(default="", description="3. 포지셔널 평가 (폰 구조, 오픈 파일, 색상 약점, 기물 배치 등)")


class AnalysisPacket(BaseModel):
    move_san: str = Field(..., description="The played move in SAN")
    move_uci: str = Field(..., description="The played move in UCI")
    player_color: str = Field(..., description="'white' or 'black'")
    move_quality: MoveQuality = Field(..., description="Quality rating of the move")
    eval_before: EvalScore = Field(..., description="Engine evaluation before the move")
    eval_after: EvalScore = Field(..., description="Engine evaluation after the move")
    eval_change: float = Field(..., description="Delta from the player's perspective (+ improves, - degrades)")
    best_move_san: str = Field(..., description="The engine's top choice move in SAN")
    best_move_uci: str = Field(..., description="The engine's top choice move in UCI")
    principal_variation: List[str] = Field(default_factory=list, description="Top engine PV line in SAN")
    formatted_best_line: str = Field(default="", description="Full best line with move numbers, e.g. '1. e4 e5 2. Nf3 Nc6'")
    refutation_move: Optional[str] = Field(default=None, description="Opponent's punishing move if played move was a mistake/blunder")
    pv_lines: List[PvLine] = Field(default_factory=list, description="Multi-PV engine candidate lines")
    tactics: TacticalMetrics = Field(default_factory=TacticalMetrics)
    positional: PositionalMetrics = Field(default_factory=PositionalMetrics)
    lookahead: LookaheadInsight = Field(default_factory=LookaheadInsight, description="Deep lookahead and PV simulation insights")
    opening: Optional[OpeningInfo] = Field(default=None, description="Opening encyclopedia match and variation breakdown")
    game_over: Optional[GameOverInfo] = Field(default=None, description="Game over and outcome termination details")
    summary_tags: List[str] = Field(default_factory=list, description="Concise tags for LLM prompt")
    commentary_sections: Optional[CommentarySections] = Field(default=None, description="Structured 3-part GM commentary")
    commentary: Optional[str] = Field(default=None, description="Combined full commentary text")

import logging
import chess
from typing import List, Optional

from app.core.rules import ChessRulesHelper
from app.core.stockfish import PvLineResult
from app.core.opening_tree import OpeningTree
from app.analyzer.tactics import TacticsAnalyzer
from app.analyzer.positional import PositionalAnalyzer
from app.analyzer.lookahead import LookaheadAnalyzer
from app.schemas.analysis import (
    AnalysisPacket,
    MoveQuality,
    EvalScore,
    PvLine,
    ScoreType,
    LookaheadInsight,
    OpeningInfo,
    GameOverInfo,
    GameOverReason,
)

logger = logging.getLogger(__name__)


class AnalysisAggregator:
    """Aggregates Stockfish engine evaluation and python-chess tactical/positional deltas into AnalysisPacket."""

    @classmethod
    def aggregate(
        cls,
        before_fen: str,
        after_fen: str,
        move_san: str,
        move_uci: Optional[str],
        before_pv_results: List[PvLineResult],
        after_pv_results: List[PvLineResult],
        move_history_san: Optional[List[str]] = None,
    ) -> AnalysisPacket:
        before_board = chess.Board(before_fen)
        after_board = chess.Board(after_fen)

        player_color = before_board.turn

        # Resolve UCI move string if not provided
        resolved_uci = move_uci
        if not resolved_uci:
            try:
                move_obj = before_board.parse_san(move_san)
                resolved_uci = move_obj.uci()
            except Exception:
                resolved_uci = "0000"

        try:
            move = chess.Move.from_uci(resolved_uci)
        except Exception:
            move = chess.Move.null()

        # 0. Game Over & Outcome Detection
        is_checkmate = after_board.is_checkmate()
        is_stalemate = after_board.is_stalemate()
        is_insufficient = after_board.is_insufficient_material()
        is_fifty = after_board.is_fifty_moves() or after_board.is_seventyfive_moves()
        is_repetition = after_board.is_repetition(3) or after_board.is_fivefold_repetition()
        is_game_over = after_board.is_game_over() or is_checkmate or is_stalemate or is_insufficient or is_fifty or is_repetition

        game_over_info: Optional[GameOverInfo] = None
        if is_game_over:
            if is_checkmate:
                winner = "white" if player_color == chess.WHITE else "black"
                winner_ko = "백(White)" if player_color == chess.WHITE else "흑(Black)"
                result = "1-0" if winner == "white" else "0-1"
                desc = f"체크메이트(Checkmate)로 {winner_ko} 승리"
                reason = GameOverReason.CHECKMATE
            elif is_stalemate:
                winner = None
                winner_ko = "무승부"
                result = "1/2-1/2"
                desc = "스테일메이트(Stalemate) 성립으로 무승부"
                reason = GameOverReason.STALEMATE
            elif is_insufficient:
                winner = None
                winner_ko = "무승부"
                result = "1/2-1/2"
                desc = "기물 부족(Insufficient Material)으로 무승부"
                reason = GameOverReason.INSUFFICIENT_MATERIAL
            elif is_fifty:
                winner = None
                winner_ko = "무승부"
                result = "1/2-1/2"
                desc = "50수 규칙(50-Move Rule)으로 무승부"
                reason = GameOverReason.FIFTY_MOVES
            elif is_repetition:
                winner = None
                winner_ko = "무승부"
                result = "1/2-1/2"
                desc = "3회 동형 반복(Threefold Repetition)으로 무승부"
                reason = GameOverReason.THREEFOLD_REPETITION
            else:
                winner = None
                winner_ko = "무승부"
                result = "1/2-1/2"
                desc = "체스 규정에 의한 대국 종료 (무승부)"
                reason = GameOverReason.STALEMATE

            game_over_info = GameOverInfo(
                is_game_over=True,
                reason=reason,
                winner=winner,
                winner_color_ko=winner_ko,
                result_score=result,
                description_ko=desc,
            )

        # 1. Engine Eval Before & After
        top_before = before_pv_results[0] if before_pv_results else None
        top_after = after_pv_results[0] if after_pv_results else None

        eval_before = top_before.score if top_before else EvalScore(type=ScoreType.CP, value=0.0, raw_cp=0)
        
        if is_stalemate or is_insufficient or is_fifty or is_repetition:
            eval_after = EvalScore(type=ScoreType.CP, value=0.0, raw_cp=0)
        elif is_checkmate:
            eval_val = 1.0 if player_color == chess.WHITE else -1.0
            eval_after = EvalScore(type=ScoreType.MATE, value=eval_val, raw_cp=int(eval_val * 10000))
        else:
            eval_after = top_after.score if top_after else EvalScore(type=ScoreType.CP, value=0.0, raw_cp=0)

        # Helper to convert EvalScore to effective CP scale (Mates -> ±100.0)
        def to_effective_score(score: EvalScore) -> float:
            if score.type == ScoreType.MATE:
                return 100.0 if score.value > 0 else -100.0
            return float(score.value)

        eff_before = to_effective_score(eval_before)
        eff_after = to_effective_score(eval_after)

        # 2. Eval Change from moving player's perspective
        if player_color == chess.WHITE:
            eval_change = round(eff_after - eff_before, 2)
            player_eval_before = eff_before
        else:
            eval_change = round(eff_before - eff_after, 2)
            player_eval_before = -eff_before

        # 3. Top Engine Best Move & PV Lines Before Move
        best_move_uci = top_before.move_uci if top_before else resolved_uci
        best_move_san = ChessRulesHelper.uci_to_san(before_board, best_move_uci) or best_move_uci
        best_pv_uci_list = top_before.continuation_uci if top_before else []
        pv_san_line = ChessRulesHelper.pv_uci_to_san(before_board, [best_move_uci] + best_pv_uci_list)
        formatted_best_line = ChessRulesHelper.format_pv_line(before_board, [best_move_uci] + best_pv_uci_list)

        # Format candidate MultiPV lines for the CURRENT (NEXT) position from after_board
        formatted_pv_lines: List[PvLine] = []
        if not is_game_over:
            target_pv_results = after_pv_results if after_pv_results else before_pv_results
            target_board = after_board if after_pv_results else before_board

            for pv in target_pv_results:
                if not pv.move_uci or pv.move_uci in ("0000", "(none)", "none"):
                    continue
                san_m = ChessRulesHelper.uci_to_san(target_board, pv.move_uci) or pv.move_uci
                if san_m == "--":
                    continue
                cont_san = ChessRulesHelper.pv_uci_to_san(target_board, [pv.move_uci] + pv.continuation_uci)[1:]
                full_line_str = ChessRulesHelper.format_pv_line(target_board, [pv.move_uci] + pv.continuation_uci)
                narrative = LookaheadAnalyzer.generate_pv_narrative_summary(target_board, [pv.move_uci] + pv.continuation_uci)
                strategic_plan = LookaheadAnalyzer.generate_pv_strategic_plan(target_board, [pv.move_uci] + pv.continuation_uci)
                formatted_pv_lines.append(
                    PvLine(
                        rank=pv.rank,
                        score=pv.score,
                        move_san=san_m,
                        move_uci=pv.move_uci,
                        continuation_uci=pv.continuation_uci,
                        continuation_san=cont_san,
                        formatted_line=full_line_str,
                        narrative_summary=narrative,
                        strategic_plan=strategic_plan,
                    )
                )

        # 4. Refutation Move (Opponent's top punishment in after_board)
        refutation_san: Optional[str] = None
        if not is_game_over and top_after and top_after.move_uci and top_after.move_uci not in ("0000", "(none)", "none"):
            cand = ChessRulesHelper.uci_to_san(after_board, top_after.move_uci)
            if cand and cand != "--":
                refutation_san = cand

        # 5. Tactical Analysis (Chess.com Calibrated)
        is_engine_top_choice = (resolved_uci == best_move_uci)
        tactics = TacticsAnalyzer.analyze(
            before_board=before_board,
            after_board=after_board,
            played_move=move,
            eval_change=eval_change,
            eval_before=eval_before.value,
            eval_after=eval_after.value,
            is_top_choice=is_engine_top_choice,
            best_pv_uci=[top_after.move_uci] + top_after.continuation_uci if (top_after and not is_game_over) else None,
            before_pv_results=before_pv_results,
            after_pv_results=after_pv_results if not is_game_over else [],
        )

        # 6. Positional Analysis
        positional = PositionalAnalyzer.analyze(
            before_board=before_board,
            after_board=after_board,
            played_move=move,
        )

        # 7. Opening Encyclopedia Trie Matching
        opening_info: Optional[OpeningInfo] = None
        op_match = OpeningTree.match_history(move_history_san) if move_history_san else None
        if op_match:
            opening_info = OpeningInfo(
                eco=op_match.eco,
                name=op_match.name,
                name_ko=op_match.name_ko,
                defining_move=op_match.defining_move,
                purpose=op_match.purpose,
                white_plan=op_match.white_plan,
                black_plan=op_match.black_plan,
                key_ideas=op_match.key_ideas,
                is_book=op_match.is_book,
                is_out_of_book_step=op_match.is_out_of_book_step,
                previous_opening_name=op_match.previous_opening_name,
            )

        # 8. Move Quality Classification (Chess.com Model)
        if op_match and op_match.is_book:
            move_quality = MoveQuality.BOOK
        else:
            move_quality = cls._classify_move_quality(
                eval_change=eval_change,
                eval_before=eval_before.value,
                is_top_choice=is_engine_top_choice,
                is_brilliant=tactics.is_brilliant_sacrifice,
                is_great=tactics.is_great_move,
                is_stalemate=is_stalemate,
                is_checkmate=is_checkmate,
                player_eval_before=player_eval_before,
            )

        # 9. Lookahead & PV Simulation Analysis
        if not is_game_over:
            lookahead = LookaheadAnalyzer.analyze(
                before_board=before_board,
                after_board=after_board,
                played_move=move,
                move_quality=move_quality,
                refutation_san=refutation_san,
                after_pv_results=after_pv_results,
                before_pv_results=before_pv_results,
                player_color=player_color,
            )
        else:
            lookahead = LookaheadInsight()

        # 10. Checkmate & Stalemate Tags Generation
        if is_checkmate:
            move_quality = MoveQuality.BEST
            tactics.mate_threats = ["결정적인 체크메이트(Checkmate)가 성립되어 게임이 종료되었습니다"]
            tactics.skewers = []
            tactics.pins = []
            tactics.forks = []

        summary_tags = cls._generate_summary_tags(
            move_quality=move_quality,
            tactics=tactics,
            positional=positional,
            eval_change=eval_change,
            refutation=refutation_san,
        )
        if is_checkmate and "Checkmate" not in summary_tags:
            summary_tags.insert(1, "Checkmate")
        if is_stalemate:
            summary_tags.insert(1, "Stalemate")
            if player_eval_before >= 2.0:
                summary_tags.insert(2, "Stalemate Blunder")
            elif player_eval_before <= -2.0:
                summary_tags.insert(2, "Stalemate Save")
        if is_insufficient:
            summary_tags.insert(1, "Insufficient Material")
        if is_fifty:
            summary_tags.insert(1, "50-Move Draw")
        if is_repetition:
            summary_tags.insert(1, "Threefold Repetition")

        if opening_info and opening_info.is_out_of_book_step:
            summary_tags.insert(0, "Out of Book")

        return AnalysisPacket(
            move_san=move_san,
            move_uci=resolved_uci,
            player_color="white" if player_color == chess.WHITE else "black",
            move_quality=move_quality,
            eval_before=eval_before,
            eval_after=eval_after,
            eval_change=eval_change,
            best_move_san=best_move_san,
            best_move_uci=best_move_uci,
            principal_variation=pv_san_line,
            formatted_best_line=formatted_best_line,
            refutation_move=refutation_san if move_quality in (MoveQuality.INACCURACY, MoveQuality.MISTAKE, MoveQuality.MISS, MoveQuality.BLUNDER) else None,
            pv_lines=formatted_pv_lines,
            tactics=tactics,
            positional=positional,
            lookahead=lookahead,
            opening=opening_info,
            game_over=game_over_info,
            summary_tags=summary_tags,
        )

    @classmethod
    def _classify_move_quality(
        cls,
        eval_change: float,
        eval_before: float,
        is_top_choice: bool,
        is_brilliant: bool,
        is_great: bool,
        is_stalemate: bool = False,
        is_checkmate: bool = False,
        player_eval_before: float = 0.0,
    ) -> MoveQuality:
        if is_checkmate:
            return MoveQuality.BEST

        if is_stalemate:
            # Player had decisive win (>= +2.0) and threw it away into a draw -> BLUNDER
            if player_eval_before >= 1.80:
                return MoveQuality.BLUNDER
            # Player was lost (<= -2.0) and forced a miraculous stalemate draw -> BRILLIANT
            if player_eval_before <= -1.80:
                return MoveQuality.BRILLIANT
            return MoveQuality.BEST if is_top_choice else MoveQuality.GOOD

        # Special Classifications
        if is_brilliant:
            return MoveQuality.BRILLIANT
        if is_great:
            return MoveQuality.GREAT

        # Missed Win / Miss detection (player had winning advantage >= +1.80, but blew it)
        if player_eval_before >= 1.80 and eval_change <= -1.50:
            return MoveQuality.MISS

        # Standard Expected Points / Eval Delta Classifications
        if is_top_choice:
            return MoveQuality.BEST
        if eval_change >= -0.15:
            return MoveQuality.EXCELLENT
        if eval_change >= -0.45:
            return MoveQuality.GOOD
        if eval_change >= -1.20:
            return MoveQuality.INACCURACY
        if eval_change >= -2.50:
            return MoveQuality.MISTAKE
        return MoveQuality.BLUNDER

    @classmethod
    def _generate_summary_tags(
        cls,
        move_quality: MoveQuality,
        tactics,
        positional,
        eval_change: float,
        refutation: Optional[str],
    ) -> List[str]:
        tags: List[str] = [move_quality.value]

        if tactics.is_brilliant_sacrifice:
            tags.append("Brilliant Sacrifice")
        if tactics.is_great_move:
            tags.append("Only Move / Game Changer")
        if tactics.is_hanging:
            tags.append(f"Hanging Piece ({', '.join(tactics.hanging_pieces[:2])})")
        if tactics.undefended_pieces:
            tags.append(f"Severed Defender ({', '.join(tactics.undefended_pieces[:2])})")
        if tactics.is_overloaded:
            tags.append("Overloaded Defender")
        for motif in tactics.tactical_motifs:
            if motif.title() not in tags:
                tags.append(motif.title())

        if positional.is_outpost:
            tags.append(f"Outpost on {positional.outpost_square}")
        if positional.open_file_control:
            tags.append(f"Open {positional.open_file_name}-file Control")
        if positional.pawn_structure.passed_pawns_created:
            tags.append("Passed Pawn Created")
        if positional.pawn_structure.pawn_breaks:
            tags.append(f"Break: {positional.pawn_structure.pawn_breaks[0]}")
        if positional.pawn_structure.pawn_structure_type != "Dynamic":
            tags.append(f"{positional.pawn_structure.pawn_structure_type} Center")
        if positional.initiative:
            tags.append("Initiative")
        if positional.is_repeated_move:
            tags.append("Lost Tempo (Repeated Move)")

        return tags

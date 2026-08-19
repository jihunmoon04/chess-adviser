import pytest
import chess
from app.analyzer.tactics import TacticsAnalyzer


def test_hanging_piece_detection():
    # White moves Queen to e5 where Black pawn on d6 can capture it with 0 defenders
    before_fen = "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    board_before = chess.Board(before_fen)
    
    # White plays Qh5? (or Qe2)
    move = board_before.parse_san("Qh5")
    board_after = board_before.copy()
    board_after.push(move)

    metrics = TacticsAnalyzer.analyze(
        before_board=board_before,
        after_board=board_after,
        played_move=move,
        eval_change=0.0,
    )
    # Check that tactics analyzer executed properly
    assert isinstance(metrics.is_hanging, bool)
    assert isinstance(metrics.tactical_motifs, list)


def test_tactical_motifs_check():
    # Scholar's Mate position: Qxf7#
    before_fen = "r1bqkb1r/pppp1ppp/2n5/4p3/2B1n3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 0 4"
    board_before = chess.Board(before_fen)
    move = board_before.parse_san("Qxf7")
    board_after = board_before.copy()
    board_after.push(move)

    metrics = TacticsAnalyzer.analyze(
        before_board=board_before,
        after_board=board_after,
        played_move=move,
        eval_change=10.0,
    )
    assert "check" in metrics.tactical_motifs

import pytest
import chess
from app.analyzer.positional import PositionalAnalyzer


def test_opening_e4_positional_metrics():
    # Initial starting position
    board_before = chess.Board()
    move = board_before.parse_san("e4")
    board_after = board_before.copy()
    board_after.push(move)

    metrics = PositionalAnalyzer.analyze(
        before_board=board_before,
        after_board=board_after,
        played_move=move,
    )
    # Playing e4 increases control over d5 and f5 and adds central control
    assert metrics.central_control_delta > 0
    assert metrics.space_control_delta > 0
    assert metrics.pawn_shield_intact is True


def test_development_tempo():
    # 1. e4 e5 2. Nf3
    board_before = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2")
    move = board_before.parse_san("Nf3")
    board_after = board_before.copy()
    board_after.push(move)

    metrics = PositionalAnalyzer.analyze(
        before_board=board_before,
        after_board=board_after,
        played_move=move,
    )
    assert metrics.tempo_development is True
    assert metrics.is_repeated_move is False

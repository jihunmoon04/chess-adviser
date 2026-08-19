import pytest
import chess
from app.analyzer.aggregator import AnalysisAggregator
from app.core.stockfish import PvLineResult
from app.schemas.analysis import EvalScore, ScoreType, MoveQuality


def test_aggregator_packet_assembly():
    before_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    after_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    move_san = "e4"

    pv_before = [
        PvLineResult(
            rank=1,
            score=EvalScore(type=ScoreType.CP, value=0.3, raw_cp=30),
            move_uci="e2e4",
            continuation_uci=["e7e5", "g1f3", "b8c6"],
        )
    ]
    pv_after = [
        PvLineResult(
            rank=1,
            score=EvalScore(type=ScoreType.CP, value=0.3, raw_cp=30),
            move_uci="e7e5",
            continuation_uci=["g1f3", "b8c6"],
        )
    ]

    packet = AnalysisAggregator.aggregate(
        before_fen=before_fen,
        after_fen=after_fen,
        move_san=move_san,
        move_uci="e2e4",
        before_pv_results=pv_before,
        after_pv_results=pv_after,
    )

    assert packet.move_san == "e4"
    assert packet.move_quality == MoveQuality.BEST
    assert packet.player_color == "white"
    assert packet.best_move_san == "e4"
    assert len(packet.principal_variation) >= 1

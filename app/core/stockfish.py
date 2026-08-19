import os
import shutil
import logging
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import chess
import chess.engine
from app.config import settings
from app.schemas.analysis import EvalScore, ScoreType

import threading

logger = logging.getLogger(__name__)


@dataclass
class PvLineResult:
    rank: int
    score: EvalScore
    move_uci: str
    continuation_uci: List[str] = field(default_factory=list)


class StockfishManager:
    """Manages Stockfish engine using python-chess SimpleEngine in a thread-safe worker thread,
    providing 100% compatibility on Windows and Linux without asyncio subprocess limitations."""

    def __init__(self, executable_path: Optional[str] = None):
        self.executable_path = executable_path or settings.STOCKFISH_PATH
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._is_available = False
        self._initialized = False

    def _find_executable(self) -> str:
        candidates = [
            self.executable_path,
            os.path.join(os.getcwd(), "stockfish.exe"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "stockfish.exe"),
            "/usr/games/stockfish",
            "/usr/bin/stockfish",
            "/usr/local/bin/stockfish",
            shutil.which(self.executable_path),
            shutil.which("stockfish"),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)
        return shutil.which(self.executable_path) or self.executable_path

    def _init_sync(self) -> bool:
        with self._lock:
            if self._engine is not None:
                return True
            resolved_path = self._find_executable()
            try:
                self._engine = chess.engine.SimpleEngine.popen_uci(resolved_path)
                self._engine.configure({
                    "Threads": settings.STOCKFISH_THREADS,
                    "Hash": settings.STOCKFISH_HASH_MB,
                })
                self._is_available = True
                self._initialized = True
                logger.info(f"Stockfish 18 engine loaded successfully: {resolved_path}")
                return True
            except Exception as e:
                logger.warning(
                    f"Stockfish engine not initialized at '{resolved_path}': {type(e).__name__} ({e}). "
                    "Running in fallback heuristic mode."
                )
                self._is_available = False
                self._initialized = True
                return False

    async def initialize(self) -> bool:
        return await asyncio.to_thread(self._init_sync)

    def _restart_sync(self) -> bool:
        """Kills any dead engine process and creates a fresh Stockfish SimpleEngine instance."""
        if self._engine:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None
        self._is_available = False
        resolved_path = self._find_executable()
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(resolved_path)
            self._engine.configure({
                "Threads": settings.STOCKFISH_THREADS,
                "Hash": settings.STOCKFISH_HASH_MB,
            })
            self._is_available = True
            logger.info("Stockfish engine restarted successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to restart Stockfish: {e}")
            self._is_available = False
            return False

    def _close_sync(self):
        with self._lock:
            if self._engine:
                try:
                    self._engine.quit()
                except Exception:
                    pass
                self._engine = None
            self._is_available = False

    async def close(self):
        await asyncio.to_thread(self._close_sync)

    def _analyze_sync(
        self,
        fen: str,
        multi_pv: int,
        depth: int,
        timeout_ms: int,
    ) -> List[PvLineResult]:
        with self._lock:
            try:
                board = chess.Board(fen)
            except Exception:
                return self._fallback_analyze(fen, multi_pv)

            # Check fatal FEN status flags that could crash UCI engine (missing king or opposite king in check)
            fatal_flags = (
                chess.STATUS_NO_WHITE_KING |
                chess.STATUS_NO_BLACK_KING |
                chess.STATUS_TOO_MANY_KINGS |
                chess.STATUS_OPPOSITE_CHECK
            )
            if board.status() & fatal_flags:
                logger.warning(f"Fatal FEN status detected ({fen}), status: {board.status()}. Using fallback evaluation.")
                return self._fallback_analyze(fen, multi_pv)

            # If engine is not available, try to initialize or restart
            if not self._engine:
                if not self._restart_sync():
                    return self._fallback_analyze(fen, multi_pv)

            # Run analysis with 1 retry on engine failure
            for attempt in range(2):
                try:
                    limit = chess.engine.Limit(depth=depth, time=timeout_ms / 1000.0)
                    info_list = self._engine.analyse(board, limit, multipv=multi_pv)

                    if isinstance(info_list, dict):
                        info_list = [info_list]

                    results: List[PvLineResult] = []
                    for i, item in enumerate(info_list, 1):
                        score_pov = item.get("score")
                        pv = item.get("pv", [])
                        if not pv:
                            continue

                        white_score = score_pov.white()
                        if white_score.is_mate():
                            score_type = ScoreType.MATE
                            score_val = float(white_score.mate())
                            raw_cp = int(score_val * 10000)
                        else:
                            score_type = ScoreType.CP
                            raw_cp = white_score.score()
                            score_val = round(raw_cp / 100.0, 2)

                        first_move_uci = pv[0].uci()
                        continuation_uci = [m.uci() for m in pv[1:6]]

                        results.append(
                            PvLineResult(
                                rank=item.get("multipv", i),
                                score=EvalScore(type=score_type, value=score_val, raw_cp=raw_cp),
                                move_uci=first_move_uci,
                                continuation_uci=continuation_uci,
                            )
                        )
                    if results:
                        return results
                    return self._fallback_analyze(fen, 1)

                except Exception as e:
                    logger.error(f"Error during Stockfish analysis (attempt {attempt+1}): {e}")
                    if attempt == 0:
                        # Auto-restart engine immediately on first failure
                        logger.info("Attempting auto-recovery restart of Stockfish engine...")
                        self._restart_sync()
                    else:
                        return self._fallback_analyze(fen, multi_pv)

            return self._fallback_analyze(fen, multi_pv)

    async def analyze_position(
        self,
        fen: str,
        multi_pv: int = 3,
        depth: int = 15,
        timeout_ms: int = 300,
    ) -> List[PvLineResult]:
        """Run Multi-PV search on given FEN."""
        if not self._initialized:
            await self.initialize()

        if not self._is_available or not self._engine:
            return self._fallback_analyze(fen, multi_pv)

        async with self._async_lock:
            return await asyncio.to_thread(
                self._analyze_sync, fen, multi_pv, depth, timeout_ms
            )

    def _fallback_analyze(self, fen: str, multi_pv: int) -> List[PvLineResult]:
        """Heuristic evaluation fallback when native Stockfish binary is not active."""
        board = chess.Board(fen)
        val_map = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900}

        mat_white = sum(val_map.get(p.piece_type, 0) for p in board.piece_map().values() if p.color == chess.WHITE)
        mat_black = sum(val_map.get(p.piece_type, 0) for p in board.piece_map().values() if p.color == chess.BLACK)
        raw_diff = mat_white - mat_black
        score_val = round(raw_diff / 100.0, 2)

        legal_moves = list(board.legal_moves)
        results: List[PvLineResult] = []
        for i, move in enumerate(legal_moves[:multi_pv], 1):
            results.append(
                PvLineResult(
                    rank=i,
                    score=EvalScore(type=ScoreType.CP, value=score_val, raw_cp=raw_diff),
                    move_uci=move.uci(),
                    continuation_uci=[],
                )
            )
        if not results:
            results.append(
                PvLineResult(
                    rank=1,
                    score=EvalScore(type=ScoreType.CP, value=0.0, raw_cp=0),
                    move_uci="0000",
                    continuation_uci=[],
                )
            )
        return results


stockfish_manager = StockfishManager()

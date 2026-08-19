import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.core.stockfish import stockfish_manager
from app.core.rules import ChessRulesHelper
from app.services.cache_service import cache_service
from app.services.llm_service import llm_service
from app.analyzer.aggregator import AnalysisAggregator
from app.schemas.request import MoveAnalysisRequest
from app.schemas.analysis import AnalysisPacket, MoveQuality

logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("chess_adviser")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to initialize and cleanup engine and cache resources."""
    logger.info("Initializing Chess Adviser Backend...")
    await stockfish_manager.initialize()
    await cache_service.initialize()
    logger.info("Chess Adviser Backend is ready.")
    yield
    logger.info("Shutting down Chess Adviser Backend...")
    await stockfish_manager.close()
    await cache_service.close()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Chess Adviser Backend API",
    description="Real-time chess tactical evaluation and AI commentary streaming engine.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Mount static folder
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "status": "online",
        "service": "Chess Adviser Backend",
        "version": "1.0.0",
        "stockfish_available": stockfish_manager._is_available,
        "llm_provider": settings.LLM_PROVIDER,
    }


@app.get("/api/info")
async def get_system_info():
    has_gemini = bool(settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"))
    has_openai = bool(settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))
    if settings.LLM_PROVIDER.lower() == "gemini" and has_gemini:
        active_engine = f"Gemini ({settings.GEMINI_MODEL})"
        engine_type = "gemini"
    elif settings.LLM_PROVIDER.lower() == "openai" and has_openai:
        active_engine = f"OpenAI ({settings.OPENAI_MODEL})"
        engine_type = "openai"
    else:
        active_engine = "오프라인 룰 엔진 (Rule Engine)"
        engine_type = "rule_engine"

    return {
        "status": "online",
        "service": "Chess Adviser Backend",
        "version": "1.0.0",
        "stockfish_available": stockfish_manager._is_available,
        "active_engine": active_engine,
        "engine_type": engine_type,
        "llm_provider": settings.LLM_PROVIDER,
        "gemini_model": settings.GEMINI_MODEL,
        "has_key": has_gemini or has_openai,
    }


@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "stockfish": stockfish_manager._is_available}


async def compute_fast_analysis_packet(req: MoveAnalysisRequest) -> Optional[AnalysisPacket]:
    """Runs ultra-fast Stockfish MultiPV (depth 8-10, timeout 40ms) for instant UI response in ~0.05s."""
    try:
        before_pv = await stockfish_manager.analyze_position(
            fen=req.before_fen,
            multi_pv=settings.STOCKFISH_MULTI_PV,
            depth=settings.STOCKFISH_FAST_DEPTH,
            timeout_ms=settings.STOCKFISH_FAST_TIMEOUT_MS,
        )
        after_pv = await stockfish_manager.analyze_position(
            fen=req.after_fen,
            multi_pv=settings.STOCKFISH_MULTI_PV,
            depth=settings.STOCKFISH_FAST_DEPTH,
            timeout_ms=settings.STOCKFISH_FAST_TIMEOUT_MS,
        )
        return AnalysisAggregator.aggregate(
            before_fen=req.before_fen,
            after_fen=req.after_fen,
            move_san=req.move_san,
            move_uci=req.move_uci,
            before_pv_results=before_pv,
            after_pv_results=after_pv,
            move_history_san=req.move_history_san,
        )
    except Exception as e:
        logger.warning(f"Fast stage analysis skipped: {e}")
        return None


async def compute_analysis_packet(req: MoveAnalysisRequest) -> AnalysisPacket:
    """Runs deep Stockfish multi-pv analysis (depth 18, 600ms) on before/after positions."""
    # 1. Validate FENs with python-chess
    try:
        ChessRulesHelper.create_board(req.before_fen)
        ChessRulesHelper.create_board(req.after_fen)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid FEN format: {e}")

    # 2. Run Stockfish MultiPV analysis on both positions
    before_pv = await stockfish_manager.analyze_position(
        fen=req.before_fen,
        multi_pv=settings.STOCKFISH_MULTI_PV,
        depth=settings.STOCKFISH_DEFAULT_DEPTH,
        timeout_ms=settings.STOCKFISH_TIMEOUT_MS,
    )
    after_pv = await stockfish_manager.analyze_position(
        fen=req.after_fen,
        multi_pv=settings.STOCKFISH_MULTI_PV,
        depth=settings.STOCKFISH_DEFAULT_DEPTH,
        timeout_ms=settings.STOCKFISH_TIMEOUT_MS,
    )

    # 3. Aggregate results
    packet = AnalysisAggregator.aggregate(
        before_fen=req.before_fen,
        after_fen=req.after_fen,
        move_san=req.move_san,
        move_uci=req.move_uci,
        before_pv_results=before_pv,
        after_pv_results=after_pv,
        move_history_san=req.move_history_san,
    )
    return packet


@app.post("/api/analyze")
async def analyze_move(req: MoveAnalysisRequest):
    """Synchronous endpoint returning full Analysis JSON and complete commentary."""
    # Check cache
    cached = await cache_service.get(req.before_fen, req.move_san, history_san=req.move_history_san)
    if cached:
        return cached

    packet = await compute_analysis_packet(req)

    # Collect commentary
    is_critical = llm_service.is_critical_moment(packet)
    force_local = (not is_critical) or (packet.move_quality == MoveQuality.BOOK)

    commentary_chunks = []
    async for chunk in llm_service.stream_commentary(packet, force_local=force_local):
        commentary_chunks.append(chunk)
    commentary_text = "".join(commentary_chunks)

    response_data = {
        "analysis": packet.model_dump(),
        "commentary": commentary_text,
    }

    # Save to cache
    await cache_service.set(req.before_fen, req.move_san, response_data, history_san=req.move_history_san)
    return response_data


import io
import chess.pgn
from pydantic import BaseModel


class PgnImportRequest(BaseModel):
    text: str


@app.post("/api/pgn/import")
async def import_pgn(req: PgnImportRequest):
    """Parses full PGN game or single FEN into sequential timeline states."""
    raw = req.text.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty PGN or FEN text")

    # 1. Try single FEN
    try:
        b = chess.Board(raw)
        return {
            "type": "fen",
            "initial_fen": b.fen(),
            "moves": [],
            "final_fen": b.fen(),
        }
    except Exception:
        pass

    # 2. Try PGN / SAN sequence
    try:
        import re
        moves_list = []
        initial_fen = chess.STARTING_FEN
        board = chess.Board()

        # Step A: Try standard PGN reader
        game = chess.pgn.read_game(io.StringIO(raw))
        if game is None or not list(game.mainline_moves()):
            game = chess.pgn.read_game(io.StringIO(f'[Event "Imported"]\n\n{raw}\n*'))

        if game and list(game.mainline_moves()):
            board = game.board()
            initial_fen = board.fen()
            for move in game.mainline_moves():
                before_fen = board.fen()
                move_san = board.san(move)
                move_uci = move.uci()
                board.push(move)
                after_fen = board.fen()
                moves_list.append({
                    "move_san": move_san,
                    "move_uci": move_uci,
                    "before_fen": before_fen,
                    "after_fen": after_fen,
                })

        # Step B: Also run lenient token fallback to recover any moves truncated by ambiguous SAN
        clean_text = re.sub(r'\[.*?\]', '', raw)
        clean_text = re.sub(r'\{.*?\}', '', clean_text)
        clean_text = re.sub(r'\d+\.+', '', clean_text)
        tokens = clean_text.split()

        fb_board = chess.Board()
        fb_initial_fen = fb_board.fen()
        fb_moves_list = []

        for tok in tokens:
            tok = tok.strip()
            if not tok or tok in ('*', '1-0', '0-1', '1/2-1/2'):
                continue
            m = None
            try:
                m = fb_board.parse_san(tok)
            except Exception:
                clean_tok = tok.replace('x', '').replace('+', '').replace('#', '')
                dest_match = re.search(r'[a-h][1-8]', clean_tok)
                if dest_match:
                    dest_sq = chess.parse_square(dest_match.group(0))
                    p_char = clean_tok[0] if clean_tok[0].isupper() else 'P'
                    p_type = chess.PIECE_SYMBOLS.index(p_char.lower())
                    candidates = [
                        lm for lm in fb_board.legal_moves
                        if lm.to_square == dest_sq and fb_board.piece_type_at(lm.from_square) == p_type
                    ]
                    if candidates:
                        if len(candidates) > 1 and len(clean_tok) >= 3:
                            hint = clean_tok[1]
                            matched = [c for c in candidates if chess.square_name(c.from_square).startswith(hint)]
                            if matched:
                                candidates = matched
                        m = candidates[0]

            if m and m in fb_board.legal_moves:
                before_fen = fb_board.fen()
                san = fb_board.san(m)
                uci = m.uci()
                fb_board.push(m)
                fb_moves_list.append({
                    "move_san": san,
                    "move_uci": uci,
                    "before_fen": before_fen,
                    "after_fen": fb_board.fen(),
                })

        # Choose whichever parsed more moves
        if len(fb_moves_list) > len(moves_list):
            moves_list = fb_moves_list
            initial_fen = fb_initial_fen
            final_fen = fb_board.fen()
        else:
            final_fen = board.fen()

        if not moves_list:
            raise HTTPException(status_code=400, detail="Could not parse PGN or FEN format")

        return {
            "type": "pgn",
            "initial_fen": initial_fen,
            "moves": moves_list,
            "final_fen": final_fen,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PGN parsing error: {e}")


@app.post("/api/analyze/stream")
async def stream_analysis(req: MoveAnalysisRequest):
    """SSE endpoint streaming the Analysis JSON metadata first, then streaming LLM commentary tokens."""
    cached = await cache_service.get(req.before_fen, req.move_san, history_san=req.move_history_san)

    async def event_generator() -> AsyncGenerator[str, None]:
        if cached and "analysis" in cached:
            # 1. Yield cached analysis packet immediately
            yield json.dumps({
                "event": "analysis",
                "data": cached["analysis"],
                "engine_info": cached.get("engine_info"),
            }, ensure_ascii=False)

            # 2. Yield cached commentary text
            commentary_text = cached.get("commentary", "")
            if commentary_text:
                import asyncio
                words = commentary_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield json.dumps({
                        "event": "token",
                        "data": chunk,
                    }, ensure_ascii=False)
                    await asyncio.sleep(0.008)

            # 3. Yield done event
            yield json.dumps({
                "event": "done",
                "data": {"status": "complete", "full_commentary": commentary_text},
            }, ensure_ascii=False)
            return

        # Not cached -> Compute 2-stage progressive analysis
        # STAGE 1: Ultra-fast initial analysis for instant UI render (0.04-0.08s)
        try:
            fast_packet = await compute_fast_analysis_packet(req)
            if fast_packet:
                yield json.dumps({
                    "event": "instant_analysis",
                    "data": fast_packet.model_dump(),
                }, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Error in fast stage: {e}")

        # STAGE 2: Full Deep Analysis (depth 18, 0.4-0.6s)
        packet = await compute_analysis_packet(req)

        # Smart Hybrid Engine Selection:
        # Critical turning point (Mistake, Blunder, Tactics, Brilliant, Swing) -> Call Gemini LLM
        # Normal/Routine move -> Zero Latency Local Engine (0s instant)
        is_critical = llm_service.is_critical_moment(packet)
        has_gemini = bool(settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"))
        has_openai = bool(settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))

        if is_critical and settings.LLM_PROVIDER.lower() == "gemini" and has_gemini:
            engine_name = f"✨ Gemini ({settings.GEMINI_MODEL})"
            engine_type = "gemini"
            force_local = False
        elif is_critical and settings.LLM_PROVIDER.lower() == "openai" and has_openai:
            engine_name = f"✨ OpenAI ({settings.OPENAI_MODEL})"
            engine_type = "openai"
            force_local = False
        else:
            engine_name = "⚡ 로컬 자체 엔진"
            engine_type = "rule_engine"
            force_local = True

        engine_info = {
            "engine_name": engine_name,
            "engine_type": engine_type,
            "is_critical": is_critical,
        }

        # Send finalized deep Analysis JSON packet + engine metadata
        yield json.dumps({
            "event": "analysis",
            "data": packet.model_dump(),
            "engine_info": engine_info,
        }, ensure_ascii=False)

        # STAGE 3: Stream commentary text tokens
        full_commentary = []
        fallback_queue = []

        def handle_fallback(fallback_name: str):
            engine_info["engine_name"] = fallback_name
            engine_info["engine_type"] = "rule_engine"
            fallback_queue.append(engine_info.copy())

        async for chunk in llm_service.stream_commentary(packet, force_local=force_local, on_fallback=handle_fallback):
            while fallback_queue:
                fb_info = fallback_queue.pop(0)
                yield json.dumps({
                    "event": "engine_update",
                    "engine_info": fb_info,
                }, ensure_ascii=False)

            full_commentary.append(chunk)
            yield json.dumps({
                "event": "token",
                "data": chunk,
            }, ensure_ascii=False)

        # Send done event & cache completed result
        complete_text = "".join(full_commentary)
        await cache_service.set(
            req.before_fen,
            req.move_san,
            {
                "analysis": packet.model_dump(),
                "commentary": complete_text,
                "engine_info": engine_info,
            },
            history_san=req.move_history_san,
        )

        yield json.dumps({
            "event": "done",
            "data": {
                "status": "complete",
                "full_commentary": complete_text,
                "engine_info": engine_info,
            },
        }, ensure_ascii=False)

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)

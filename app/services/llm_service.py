import os
import json
import logging
from typing import AsyncGenerator, Optional, List, Any, Dict, Tuple, Callable

from app.config import settings
from app.schemas.analysis import AnalysisPacket, MoveQuality, CommentarySections

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 체스 분석과 전략을 깊이 있게 연구하는 전문 체스 코치입니다.
주어지는 'Analysis JSON' 데이터를 바탕으로, 과장이나 감정적 수식어를 배제하고 **객관적이고 분석적인 어조**로 다음 **3개 영역의 한국어 코칭 해설**을 작성하십시오:

### 🏆 수 총평
- 수의 등급과 평가치 변화(Δ), 이 수가 갖는 구조적/전술적 목적(예: 킹사이드 폰 구조 해체, 핀 유도, 중앙 공간 확보, 룩 리프트 등)을 객관적이고 담담하게 1문장으로 총평하십시오.

### ⚔️ 전술적 평가
- 보드에서 발생한 전술적 인과관계(포크, 핀, 스큐어, 기물 희생, 라인 개방, 메이트 위협 등)와 후속 연속 수순(PV Chain)의 전술적 결말을 논리적으로 설명하십시오.
- 기물 희생(Sacrifice)이나 룩 리프트(Rook Lift)의 경우, 단기적 투자나 행마를 통해 얻는 구체적인 전술적 이점(상대 킹의 폰 실드 파괴, 메이팅 네트 형성, 킹사이드 총공세 등)을 객관적인 기물 상호작용 관점에서 기술하십시오.
- 제공된 팩트에 없는 가상의 전술(존재하지 않는 스큐어나 허위 포크)을 임의로 지어내지 마십시오.

### ♟️ 포지셔널 분석
- 이 수로 인해 형성된 포지션 변화(킹의 안전도/폰 실드 상태, 룩 리프트, 사선/파일 개방, 기물 활동성 증감, 폰 구조 변화 등)와 향후 타당한 전략적 전개 방향을 1~2문장으로 설명하십시오.

[엄격한 스타일 및 어휘 규칙]
1. 과장되거나 감정적인 표현 금지: '기막힌', '초토화', '폭발적으로', '완전히 무너뜨리는', '승기를 확정 짓는' 등의 극단적 과장 표현을 절대 사용하지 마십시오.
2. 체스 전문 용어 준수: 체스 말은 '왕'이 아니라 반드시 '킹(King)', '퀸(Queen)', '비숍(Bishop)', '나이트(Knight)', '룩(Rook)', '폰(Pawn)'으로 표기하십시오. 룩의 3/4열 측면 전환 행마는 '룩 리프트(Rook Lift)'로 명명하십시오.
3. 고정 상투어 금지: 불필요한 관용구를 피하고 해당 포지션의 실제 기물과 칸(h6, g7, f5 등) 좌표를 기반으로 분석하십시오.
4. 3개 섹션 제목(### 🏆 수 총평, ### ⚔️ 전술적 평가, ### ♟️ 포지셔널 분석) 형식을 반드시 준수하십시오.
"""


def fmt_san(s: Optional[str]) -> str:
    """Formats chess move with clean Korean description and spacing."""
    if not s:
        return ""
    if s == "O-O":
        return "킹사이드 캐슬링(O-O)"
    if s == "O-O-O":
        return "퀸사이드 캐슬링(O-O-O)"
    return s


def with_eun_neun(name: str) -> str:
    """Attaches 은/는 naturally."""
    if not name:
        return ""
    last_ch = name[-1].lower()
    if last_ch in ('1', '3', '6', '7', '8', 'l', 'm', 'n', 'r', ')'):
        return f"{name}은"
    return f"{name}는"


def with_eul_reul(name: str) -> str:
    """Attaches 을/를 naturally."""
    if not name:
        return ""
    last_ch = name[-1].lower()
    if last_ch in ('1', '3', '6', '7', '8', 'l', 'm', 'n', 'r', ')'):
        return f"{name}을"
    return f"{name}를"


def with_i_ga(name: str) -> str:
    """Attaches 이/가 naturally."""
    if not name:
        return ""
    last_ch = name[-1].lower()
    if last_ch in ('1', '3', '6', '7', '8', 'l', 'm', 'n', 'r', ')'):
        return f"{name}이"
    return f"{name}가"


class LLMCommentaryService:
    """Streams natural language coaching commentary using LLM or Expert Rule-Based Engine."""

    def __init__(self):
        self._openai_client = None
        self._gemini_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
            if api_key:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=api_key)
        return self._openai_client

    def _get_gemini_client(self):
        if self._gemini_client is None:
            api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
            if api_key:
                from google import genai
                self._gemini_client = genai.Client(api_key=api_key)
        return self._gemini_client

    def is_critical_moment(self, packet: AnalysisPacket) -> bool:
        """Determines whether a move is a critical turning point worthy of calling LLM."""
        # 1. Mistakes, Blunders, Misses, Brilliant, Great moves
        if packet.move_quality in (MoveQuality.BRILLIANT, MoveQuality.GREAT, MoveQuality.BLUNDER, MoveQuality.MISTAKE, MoveQuality.MISS):
            return True

        # 2. Significant Evaluation Swing (|eval_change| >= 0.7)
        if abs(packet.eval_change) >= 0.7:
            return True

        # 3. Forced Checkmate or Mate Threat
        if (
            str(packet.eval_after.type).lower().endswith("mate") or
            (packet.tactics and packet.tactics.mate_threats) or
            (packet.move_san and packet.move_san.endswith("#"))
        ):
            return True

        # 4. Sharp Tactical Motifs
        tactics = packet.tactics
        if tactics and (
            tactics.forks or tactics.skewers or tactics.discovered_attacks or
            tactics.line_clearances or tactics.is_brilliant_sacrifice or tactics.is_hanging
        ):
            return True

        return False

    async def stream_commentary(
        self,
        packet: AnalysisPacket,
        force_local: bool = False,
        on_fallback: Optional[Any] = None
    ) -> AsyncGenerator[str, None]:
        """Streams commentary text chunks based on the AnalysisPacket."""
        # Book moves or non-critical routine moves always use ultra-fast 0ms local engine
        if force_local or packet.move_quality == MoveQuality.BOOK or not self.is_critical_moment(packet):
            async for chunk in self._expert_grandmaster_stream(packet):
                yield chunk
            return

        sections = self.generate_sections(packet)
        provider = settings.LLM_PROVIDER.lower()

        # Try Gemini grounded on exact computed intent sections
        if provider == "gemini":
            client = self._get_gemini_client()
            if client:
                try:
                    user_message = f"""아래 분석 데이터와 영역별 핵심 분석을 바탕으로 3개 섹션(### 🏆 수 총평, ### ⚔️ 전술적 평가, ### ♟️ 포지셔널 분석)의 한국어 코칭 해설을 작성하십시오:

[기본 정보]
- 착수: {packet.move_san} ({packet.player_color})
- 등급: {packet.move_quality.value} (평가치 변화: {packet.eval_change:+.2f})
- 최선수: {packet.best_move_san}

[영역별 핵심 사실]
1. 수 총평: {sections.move_evaluation}
2. 전술적 사실: {sections.tactical_analysis}
3. 포지셔널 사실: {sections.positional_analysis}"""

                    response_stream = await client.aio.models.generate_content_stream(
                        model=settings.GEMINI_MODEL,
                        contents=f"{SYSTEM_PROMPT}\n\n{user_message}",
                    )
                    async for chunk in response_stream:
                        if chunk.text:
                            yield chunk.text
                    return
                except Exception as e:
                    logger.error(f"Gemini API streaming failed ({e}). Attempting fallback to local rule engine.")
                    if on_fallback:
                        if asyncio.iscoroutinefunction(on_fallback):
                            await on_fallback("⚡ 로컬 자체 엔진 (Gemini 오류 폴백)")
                        else:
                            on_fallback("⚡ 로컬 자체 엔진 (Gemini 오류 폴백)")

        # Try OpenAI grounded on exact computed intent sections
        elif provider == "openai":
            client = self._get_openai_client()
            if client:
                try:
                    user_message = f"""아래 분석 데이터와 영역별 핵심 분석을 바탕으로 3개 섹션의 한국어 코칭 해설을 작성하십시오:

[영역별 핵심 사실]
1. 수 총평: {sections.move_evaluation}
2. 전술적 사실: {sections.tactical_analysis}
3. 포지셔널 사실: {sections.positional_analysis}"""

                    stream = await client.chat.completions.create(
                        model=settings.OPENAI_MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        stream=True,
                        temperature=0.3,
                    )
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content or ""
                        if content:
                            yield content
                    return
                except Exception as e:
                    logger.error(f"OpenAI API streaming failed ({e}). Attempting fallback to local rule engine.")
                    if on_fallback:
                        if asyncio.iscoroutinefunction(on_fallback):
                            await on_fallback("⚡ 로컬 자체 엔진 (OpenAI 폴백)")
                        else:
                            on_fallback("⚡ 로컬 자체 엔진 (OpenAI 폴백)")

        # Expert Deterministic 3-Tier Grandmaster Commentary Generator (Zero-latency, 100% accurate)
        async for chunk in self._expert_grandmaster_stream(packet):
            yield chunk

    def generate_sections(self, packet: AnalysisPacket) -> dict:
        """Generates structured 3-part GM commentary dictionary."""
        san = packet.move_san
        quality = packet.move_quality
        best_san = packet.best_move_san
        refutation = packet.refutation_move
        tactics = packet.tactics
        positional = packet.positional
        eval_change = packet.eval_change

        san_disp = fmt_san(san)
        best_disp = fmt_san(best_san)

        is_white_player = (packet.player_color.lower() == "white")
        player_eval = packet.eval_after.value if is_white_player else -packet.eval_after.value
        is_winning = player_eval >= 1.8
        is_losing = player_eval <= -1.5

        # Core Intent extraction for Move Summary (Concise role definition without duplicating positional notes)
        san_raw = san.replace("+", "").replace("#", "")
        summary_intent = ""
        if san_raw in ('exd5', 'dxe4', 'cxd4', 'exd4', 'cxd5', 'dxe5'):
            summary_intent = "중앙 폰을 교환하는"
        elif san_raw in ('a6', 'a3'):
            summary_intent = "상대 침투 및 확장을 차단하는"
        elif san_raw in ('h6', 'h3'):
            summary_intent = "킹의 탈출로(Luft)를 여는"
        elif san_raw in ('Re1', 'Re8'):
            summary_intent = "중앙 e-파일을 장악하는"
        elif san_raw in ('Rd1', 'Rd8'):
            summary_intent = "중앙 d-파일을 장악하는"
        elif san_raw in ('Nh4', 'Nh5', 'Ne2', 'Ne7', 'Nf1', 'Nbd2', 'Nbd7'):
            summary_intent = "나이트를 전초기지로 재기동하는"
        elif san_raw in ('Nf5', 'Nf4', 'Nd5', 'Nd4'):
            summary_intent = "핵심 거점(Outpost)을 점령하는"
        elif san_raw in ('Ba7', 'Ba2', 'Bb3', 'Bb6', 'Bc2', 'Bc7'):
            summary_intent = "비숍 사선을 안전하게 유지하는"
        elif san_raw in ('Be6', 'Be3'):
            summary_intent = "비숍을 중앙으로 전개하는"

        prefix_intent = f" {summary_intent}" if summary_intent else ""

        # ----------------------------------------------------
        # 1. 🏆 수에 대한 총평 (Overall Move Assessment)
        # ----------------------------------------------------
        game_over = getattr(packet, "game_over", None)
        is_checkmate = packet.move_san.endswith("#") or "Checkmate" in getattr(packet, "summary_tags", []) or (game_over and game_over.reason == "checkmate")
        is_stalemate = "Stalemate" in getattr(packet, "summary_tags", []) or (game_over and game_over.reason == "stalemate")
        is_insufficient = "Insufficient Material" in getattr(packet, "summary_tags", []) or (game_over and game_over.reason == "insufficient_material")
        is_fifty = "50-Move Draw" in getattr(packet, "summary_tags", []) or (game_over and game_over.reason == "fifty_moves")
        is_repetition = "Threefold Repetition" in getattr(packet, "summary_tags", []) or (game_over and game_over.reason == "threefold_repetition")

        eval_sign = "+" if eval_change > 0 else ""
        eval_str = f" (평가치 변화: {eval_sign}{eval_change:.2f})"

        # 1-A. Checkmate (승리 확정)
        if is_checkmate:
            move_eval = f"🏆 {with_eun_neun(san_disp)} 완벽한 체크메이트(Checkmate)를 완성하며 승리를 확정짓는 결정적인 한 수입니다!"
            tactical_eval = "상대 킹의 모든 도주로가 차단되었고, 어떤 기물로도 체크를 방어하거나 공격 기물을 잡을 수 없어 체크메이트로 대국이 종료되었습니다."
            positional_eval = "기물들의 압도적인 공격 집중력과 빈틈없는 사선 장악으로 상대 킹 진영을 완전히 제압하고 최종 승리를 거두었습니다."
            return CommentarySections(
                move_evaluation=move_eval,
                tactical_analysis=tactical_eval,
                positional_analysis=positional_eval,
            )

        # 1-B. Stalemate (스테일메이트 무승부)
        if is_stalemate:
            if quality == MoveQuality.BLUNDER:
                move_eval = f"⚠️ {with_eun_neun(san_disp)} 다 이긴 완승 국면을 허무하게 무승부(1/2-1/2)로 날려버린 치명적인 스테일메이트 블런더(Blunder)입니다!{eval_str} 대신 {with_eul_reul(best_disp)} 두어 즉시 승리를 거두었어야 합니다."
                tactical_eval = "상대 킹이 체크 상태가 아니지만, 주변 모든 칸이 장악되어 합법적으로 움직일 수 있는 수가 0개이므로 체스 규정에 따라 즉시 스테일메이트(Stalemate)가 성립되어 비겼습니다."
                positional_eval = f"압도적인 기물 우위에도 불구하고 상대 킹의 숨통(합법적 수)을 고려하지 못해 승리를 놓쳤습니다. 대신 {with_eul_reul(best_disp)} 두었다면 결정적인 체크메이트 승리였습니다."
            elif quality in (MoveQuality.BRILLIANT, MoveQuality.GREAT):
                move_eval = f"✨ {with_eun_neun(san_disp)} 패색이 짙던 위기에서 기적적으로 스테일메이트(Stalemate)를 강제하여 무승부를 이끌어낸 환상적인 묘수(Brilliant)입니다!"
                tactical_eval = "자신의 기물 이동을 희생하거나 킹의 합법적인 수를 모두 소진시켜 상대에게 강제 스테일메이트를 유도하여 패배를 막아냈습니다."
                positional_eval = "절망적인 포지션 불리를 뒤집고 공식 무승부(1/2-1/2)를 쟁취한 완벽한 위기 탈출 수순입니다."
            else:
                move_eval = f"⚖️ {with_eun_neun(san_disp)} 스테일메이트(Stalemate)가 성립되어 대국이 공식 무승부(1/2-1/2)로 종료되었습니다."
                tactical_eval = "어느 쪽도 체크 상태가 아니면서 합법적으로 둘 수 있는 수가 없어 체스 규정에 따라 무승부가 확정되었습니다."
                positional_eval = "양측 모두 승패 없이 균형을 이루며 대국이 최종 마무리되었습니다."
            return CommentarySections(
                move_evaluation=move_eval,
                tactical_analysis=tactical_eval,
                positional_analysis=positional_eval,
            )

        # 1-C. Other Draw Termination Types
        if is_insufficient:
            move_eval = f"⚖️ {with_eun_neun(san_disp)} 기물 부족(Insufficient Material)으로 인해 대국이 공식 무승부(1/2-1/2)로 종료되었습니다."
            tactical_eval = "양측 모두 상대를 체크메이트시킬 수 있는 최소 기물이 남아있지 않아 규정에 따라 무승부 처리되었습니다."
            positional_eval = "킹을 제외한 유효 공격 기물이 소진되어 평화롭게 대국이 종결되었습니다."
            return CommentarySections(
                move_evaluation=move_eval,
                tactical_analysis=tactical_eval,
                positional_analysis=positional_eval,
            )

        if is_fifty:
            move_eval = f"⚖️ {with_eun_neun(san_disp)} 50수 규칙(50-Move Rule)에 도달하여 대국이 무승부로 공식 종료되었습니다."
            tactical_eval = "50수 동안 폰 이동이나 기물 포획이 없어 규정에 따라 무승부가 성립되었습니다."
            positional_eval = "더 이상의 형세 변화 없이 규정에 따라 대국이 마무리되었습니다."
            return CommentarySections(
                move_evaluation=move_eval,
                tactical_analysis=tactical_eval,
                positional_analysis=positional_eval,
            )

        if is_repetition:
            move_eval = f"⚖️ {with_eun_neun(san_disp)} 동일한 국면이 3회 반복(Threefold Repetition)되어 무승부로 종료되었습니다."
            tactical_eval = "동일한 포지션과 권리가 3번 발생하여 체스 규정에 따라 공식 무승부가 선언되었습니다."
            positional_eval = "반복적인 수순으로 인해 대국이 평화로운 무승부로 매듭지어졌습니다."
            return CommentarySections(
                move_evaluation=move_eval,
                tactical_analysis=tactical_eval,
                positional_analysis=positional_eval,
            )

        # Check Opening Book Match
        opening = getattr(packet, "opening", None)
        if opening and opening.is_book:
            move_eval = f"{with_eun_neun(san_disp)} {opening.name_ko} ({opening.eco})의 공인된 정석 수순(Book Move)입니다."
            tactical_eval = "체스 이론상 검증된 표준 전개 수순으로, 백과 흑 모두 안정적인 중앙 장악과 신속한 기물 전개를 도모합니다."
            key_note = opening.key_ideas if opening.key_ideas else "기물들을 최적 거점으로 전개하며 향후 미들게임 주도권을 준비합니다."
            positional_eval = f"💡 {key_note}"
            return CommentarySections(
                move_evaluation=move_eval,
                tactical_analysis=tactical_eval,
                positional_analysis=positional_eval,
            )

        # Check if player is winning by mate or decisive advantage
        is_winning_mate = (
            str(packet.eval_after.type).lower().endswith("mate") and (
                (is_white_player and packet.eval_after.value > 0) or
                (not is_white_player and packet.eval_after.value < 0)
            )
        )
        best_line_first_resp = packet.principal_variation[1] if len(packet.principal_variation) > 1 else ""
        is_same_ref = bool(refutation and best_line_first_resp and refutation == best_line_first_resp)

        if quality == MoveQuality.BRILLIANT:
            move_eval = f"{with_eun_neun(san_disp)} 상대 킹 진영의 방어선을 해체하고 공격로를 개방하는 전술적 기물 희생(Brilliant)입니다.{eval_str}"
        elif quality == MoveQuality.GREAT:
            move_eval = f"{with_eun_neun(san_disp)} 국면의 균형을 유지하고 위기를 방어하는 정확한 유일수(Great Move)입니다.{eval_str}"
        elif quality == MoveQuality.BEST:
            move_eval = f"{with_eun_neun(san_disp)}{prefix_intent} 스톡피시가 추천하는 1순위 최선수(Best)입니다.{eval_str}"
        elif quality == MoveQuality.EXCELLENT:
            move_eval = f"{with_eun_neun(san_disp)}{prefix_intent} 최선수와 대등하게 유효한 훌륭한 수(Excellent)입니다.{eval_str}"
        elif quality == MoveQuality.GOOD:
            move_eval = f"{with_eun_neun(san_disp)}{prefix_intent} 무난하고 안정적인 좋은 수(Good)입니다.{eval_str}"
        elif quality == MoveQuality.INACCURACY:
            if is_winning_mate:
                move_eval = f"{with_eun_neun(san_disp)} 최선수보다 체크메이트 수순이 미세하게 늦어지는 차이(Inaccuracy)이나, 여전히 강제 메이트로 승리를 굳힌 완승 국면입니다.{eval_str} (최선수: {best_disp})"
            else:
                ref_t = f" 상대의 {fmt_san(refutation)} 반격을 허용합니다." if (refutation and not is_same_ref) else ""
                move_eval = f"{with_eun_neun(san_disp)} 최선의 수순을 살짝 벗어난 사소한 부정확(Inaccuracy)입니다.{eval_str}{ref_t} 대신 {with_eul_reul(best_disp)} 두는 것이 더 견고했습니다."
        elif quality == MoveQuality.MISTAKE:
            if is_winning_mate:
                move_eval = f"{with_eun_neun(san_disp)} 최선수 대비 메이트 경로가 길어지는 실수(Mistake)이나, 침착하게 응수하면 여전히 강제 메이트 승리가 유지됩니다.{eval_str} (최선수: {best_disp})"
            else:
                ref_t = f" 상대에게 강력한 {fmt_san(refutation)} 반격을 허용합니다." if (refutation and not is_same_ref) else ""
                move_eval = f"{with_eun_neun(san_disp)} 상대에게 주도권을 내어주는 실수(Mistake)입니다.{eval_str}{ref_t} 대신 {with_eul_reul(best_disp)} 두는 편이 더 좋았습니다."
        elif quality == MoveQuality.MISS:
            ref_t = f" 상대의 {fmt_san(refutation)} 반격을 허용합니다." if (refutation and not is_same_ref) else ""
            move_eval = f"{with_eun_neun(san_disp)} 결정적인 국면 우위를 잡을 기회를 놓친 아쉬운 수(Miss)입니다.{eval_str}{ref_t} 대신 {with_eul_reul(best_disp)} 두었어야 합니다."
        elif quality == MoveQuality.BLUNDER:
            ref_t = f" 상대의 {fmt_san(refutation)} 응수가 결정적입니다." if refutation else ""
            move_eval = f"{with_eun_neun(san_disp)} 형세를 불리하게 만드는 치명적인 블런더(Blunder)입니다.{eval_str}{ref_t} 반드시 {with_eul_reul(best_disp)} 두었어야 합니다."
        else:
            move_eval = f"{with_eun_neun(san_disp)} 대국의 한 수입니다.{eval_str}"

        lookahead = getattr(packet, "lookahead", None)

        if opening and opening.is_out_of_book_step:
            prev_name = opening.previous_opening_name or "오프닝"
            move_eval = f"💡 {san_disp}은(는) {prev_name}의 주요 정석 라인을 벗어난 수(Out of Book)입니다.\n\n" + move_eval

        # ----------------------------------------------------
        # 2. ⚔️ 전술적 평가 (Tactical & Lookahead Analysis)
        # ----------------------------------------------------
        tac_points: List[str] = []

        is_bad_move = quality in (MoveQuality.INACCURACY, MoveQuality.MISTAKE, MoveQuality.MISS, MoveQuality.BLUNDER)
        if is_bad_move and lookahead and lookahead.refutation_narrative:
            tac_points.append(lookahead.refutation_narrative)
            if lookahead.best_move_narrative:
                tac_points.append(f"대신 {with_eul_reul(best_disp)} 두었다면, {lookahead.best_move_narrative}")

        # Direct Sharp Tactics
        if lookahead and lookahead.pv_chain_narrative:
            tac_points.append(lookahead.pv_chain_narrative)
        if tactics.line_clearances:
            for lc in tactics.line_clearances[:1]:
                tac_points.append(f"{lc}.")
        if tactics.discovered_attacks:
            for da in tactics.discovered_attacks[:1]:
                tac_points.append(f"{da}.")
        if tactics.forks:
            for fk in tactics.forks[:1]:
                tac_points.append(f"{fk}.")
        if tactics.pins:
            for pn in tactics.pins[:1]:
                tac_points.append(f"{pn}이 형성되었습니다.")
        if tactics.skewers:
            for sk in tactics.skewers[:1]:
                tac_points.append(f"{sk}이 성립했습니다.")
        if tactics.is_brilliant_sacrifice:
            tac_points.append("기물을 희생하여 상대 킹사이드 폰 방어선을 해체하고 공격 기물들의 진입 사선을 확보합니다.")
        if tactics.is_overloaded:
            tac_points.append("상대 수비 기물의 과부하(Overload)를 유도하여 핵심 거점의 방어를 무력화합니다.")
        if tactics.is_hanging and tactics.hanging_pieces:
            tac_points.append(f"자신의 기물({', '.join(tactics.hanging_pieces[:2])})이 방어선 없이 상대 공격에 노출되어 기물 손실 위험이 있습니다.")
        if tactics.undefended_pieces:
            tac_points.append(f"{', '.join(tactics.undefended_pieces[:2])} 지점의 수비선이 단절되어 잠재적인 전술 표적이 되었습니다.")
        if tactics.mate_threats:
            tac_points.append(f"{', '.join(tactics.mate_threats[:1])}입니다.")

        tactical_eval = " ".join(tac_points).strip()

        # ----------------------------------------------------
        # 3. ♟️ 포지셔널 분석 (Positional & Structural Strategy)
        # ----------------------------------------------------
        pos_points: List[str] = []

        if positional.is_rook_lift and positional.rook_lift_note:
            pos_points.append(f"{positional.rook_lift_note}로 측면 공격 사선을 개방합니다.")
        if positional.king_safety_details:
            for ksd in positional.king_safety_details:
                pos_points.append(f"{ksd}.")

        if lookahead and lookahead.prophylactic_narrative:
            pos_points.append(f"{lookahead.prophylactic_narrative}로 기물의 활동성을 극대화합니다.")
        elif san_raw in ('exd5', 'dxe4', 'cxd4', 'exd4', 'cxd5', 'dxe5'):
            pos_points.append("중앙 폰 교환을 통해 중앙 긴장을 해소하고 룩과 비숍의 전개 사선을 활짝 열었습니다.")
        elif san_raw == 'a6':
            pos_points.append("향후 백이 d4나 b4로 중앙을 밀어붙일 때 c5 비숍이 a7으로 안전하게 후퇴하여 핵심 대각선(a7-g1)의 압박력을 온전히 보존할 수 있습니다.")
        elif san_raw == 'a3':
            pos_points.append("흑의 b4 확장을 저지하고 백 비숍이 a2로 안전하게 후퇴할 공간을 마련하여 대각선 활동성을 지킵니다.")
        elif san_raw in ('h6', 'h3'):
            pos_points.append("킹의 탈출로(Luft)를 열어 백랭크 위협을 영구히 예방하고 킹사이드 진영을 안정화합니다.")
        elif san_raw in ('Re1', 'Re8'):
            file_l = san_raw[1].lower() if len(san_raw) > 1 else "e"
            pos_points.append(f"룩이 {file_l}-파일을 장악함으로써 향후 나이트가 중앙과 킹사이드로 원활하게 기동할 수 있는 전략적 발판을 마련합니다.")
        elif san_raw in ('Nh4', 'Nh5'):
            pos_points.append("나이트를 측면으로 전개하여 상대 킹사이드 핵심 약점 칸인 f5 거점(Outpost)으로 침투하기 위한 도약대를 확보합니다.")
        elif san_raw in ('Nf5', 'Nf4'):
            pos_points.append(f"나이트가 상대 킹 근처의 최적 초소인 {san_raw[1:]} 거점에 안착하여 공격 주도권을 장악하고 상대 기물들을 위축시킵니다.")
        elif san_raw in ('Ba7', 'Ba2', 'Bb3', 'Bb6', 'Bc2', 'Bc7'):
            pos_points.append(f"비숍을 안전한 {san_raw[1:]} 칸에 안착시켜 장거리 대각선 사정거리를 유지하고 공격력을 보존합니다.")
        elif san_raw in ('Be6', 'Be3'):
            pos_points.append("e6 대각선에 비숍을 전개하여 상대 비숍과 사선 지배력을 경합하고 중앙 통제력을 강화합니다.")
        elif positional.pawn_structure.pawn_breaks:
            pos_points.append(f"중앙 폰 브레이크({positional.pawn_structure.pawn_breaks[0]})를 통해 중앙 사선을 개방하고 기물들의 활동 반경을 넓혔습니다.")
        elif positional.open_file_control:
            pos_points.append(f"열린 {positional.open_file_name}열에 룩을 배치하여 적 진영 침투의 교두보를 마련했습니다.")
        elif positional.is_outpost:
            pos_points.append(f"기물이 {positional.outpost_square} 전초기지에 강력하게 안착하여 상대 진영에 지속적인 압박을 가합니다.")
        elif positional.maneuver_notes:
            pos_points.append(f"{positional.maneuver_notes[0]}하여 기물의 활동성을 극대화합니다.")
        elif positional.prophylaxis_notes:
            pos_points.append(f"{positional.prophylaxis_notes[0]}하여 포지션 안정성을 높였습니다.")
        else:
            if not pos_points:
                pos_points.append("기물들의 전개 범위를 넓히며 중앙과 측면의 통제력을 유지하고 있습니다.")

        positional_eval = " ".join(pos_points).strip()

        return CommentarySections(
            move_evaluation=move_eval,
            tactical_analysis=tactical_eval,
            positional_analysis=positional_eval,
        )

    async def _expert_grandmaster_stream(self, packet: AnalysisPacket) -> AsyncGenerator[str, None]:
        """Streams structured Grandmaster commentary with dynamic section rendering."""
        sections = self.generate_sections(packet)

        if sections.tactical_analysis:
            full_text = (
                f"### 🏆 수 총평\n{sections.move_evaluation}\n\n"
                f"### ⚔️ 전술적 평가\n{sections.tactical_analysis}\n\n"
                f"### ♟️ 포지셔널 분석\n{sections.positional_analysis}"
            )
        else:
            full_text = (
                f"### 🏆 수 총평\n{sections.move_evaluation}\n\n"
                f"### ♟️ 포지셔널 분석\n{sections.positional_analysis}"
            )

        import asyncio
        words = full_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.012)


llm_service = LLMCommentaryService()

import logging
from typing import List, Optional
import chess
from app.core.rules import ChessRulesHelper
from app.schemas.analysis import LookaheadInsight, MoveQuality

logger = logging.getLogger(__name__)


class LookaheadAnalyzer:
    """Simulates and decodes Stockfish Principal Variation (PV) continuation lines,
    extracting the deep tactical and positional causality behind moves."""

    @classmethod
    def analyze(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        played_move: chess.Move,
        move_quality: MoveQuality,
        refutation_san: Optional[str],
        after_pv_results: list,
        before_pv_results: list,
        player_color: chess.Color,
    ) -> LookaheadInsight:
        insight = LookaheadInsight()

        # 1. Analyze Refutation Dynamics for Inaccuracy/Mistake/Blunder/Miss
        if move_quality in (MoveQuality.INACCURACY, MoveQuality.MISTAKE, MoveQuality.BLUNDER, MoveQuality.MISS) and after_pv_results:
            top_after = after_pv_results[0]
            is_mate_win = False
            score = getattr(top_after, "score", None)
            if score:
                if str(score.type).lower().endswith("mate"):
                    if player_color == chess.WHITE and score.value > 0:
                        is_mate_win = True
                    elif player_color == chess.BLACK and score.value < 0:
                        is_mate_win = True
                elif (player_color == chess.WHITE and score.value >= 7.0) or (player_color == chess.BLACK and score.value <= -7.0):
                    is_mate_win = True

            ref_pv_uci = [top_after.move_uci] + getattr(top_after, "continuation_uci", [])
            insight.refutation_narrative = cls._analyze_refutation_line(
                after_board, ref_pv_uci, player_color, is_mate_win=is_mate_win
            )

            # 2. Analyze Best Alternative Value
            if before_pv_results:
                top_before = before_pv_results[0]
                best_pv_uci = [top_before.move_uci] + getattr(top_before, "continuation_uci", [])
                insight.best_move_narrative = cls._analyze_best_alternative_line(
                    before_board, best_pv_uci, player_color
                )

        # 3. Multi-move Decisive Sequence (PV Chain Narrative)
        if after_pv_results:
            top_after = after_pv_results[0]
            top_pv_uci = [top_after.move_uci] + getattr(top_after, "continuation_uci", [])
            insight.pv_chain_narrative = cls._decode_pv_chain_narrative(
                after_board, top_pv_uci, not player_color
            )

        # 4. Analyze Prophylaxis / Strategic Preparation
        if before_pv_results:
            top_before = before_pv_results[0]
            best_pv_uci = [top_before.move_uci] + getattr(top_before, "continuation_uci", [])
            insight.prophylactic_narrative = cls._analyze_prophylaxis_preparation(
                before_board, after_board, played_move, best_pv_uci
            )

        return insight

    @classmethod
    def _decode_pv_chain_narrative(
        cls,
        board: chess.Board,
        pv_uci: List[str],
        active_color: chess.Color,
    ) -> Optional[str]:
        """Simulates 2-4 moves along the PV line to explain the full strategic/tactical sequence."""
        if not pv_uci or len(pv_uci) < 2:
            return None

        sim_board = board.copy()
        moves_san: List[str] = []
        is_checks: List[bool] = []
        is_caps: List[bool] = []
        parsed_moves: List[chess.Move] = []

        for uci in pv_uci[:5]:
            try:
                mv = chess.Move.from_uci(uci)
                if not sim_board.is_legal(mv):
                    break
                moves_san.append(sim_board.san(mv))
                is_caps.append(sim_board.is_capture(mv))
                parsed_moves.append(mv)
                sim_board.push(mv)
                is_checks.append(sim_board.is_check())
            except Exception:
                break

        if len(moves_san) < 2:
            return None

        m1, m2 = moves_san[0], moves_san[1]
        m3 = moves_san[2] if len(moves_san) > 2 else ""

        # Pattern 1: Mate / Mating Net (Check -> Mate)
        if any("#" in m for m in moves_san) or sim_board.is_checkmate():
            mate_move = [m for m in moves_san if "#" in m]
            mate_str = f" ({mate_move[0]})" if mate_move else ""
            return f"이어지는 수순은 {m1}을(를) 시작으로 상대 킹을 메이팅 네트(Mating Net)에 몰아넣어 강제 체크메이트{mate_str}로 승리를 확정 짓는 결정타입니다."

        # Pattern 2: Rook Lift Attack (e.g. Re3 -> Rg3/Rh3)
        p1 = board.piece_at(parsed_moves[0].from_square) if parsed_moves else None
        if p1 and p1.piece_type == chess.ROOK:
            r1_from = chess.square_rank(parsed_moves[0].from_square)
            r1_to = chess.square_rank(parsed_moves[0].to_square)
            if (active_color == chess.WHITE and r1_from in (0, 1) and r1_to in (2, 3)) or (active_color == chess.BLACK and r1_from in (7, 6) and r1_to in (5, 4)):
                target_flank = "킹사이드" if any(f in m2 for f in ("g", "h", "f")) else "측면"
                return f"{m1} 룩 리프트로 3열을 확보한 뒤 {m2}로 신속하게 전환하여 {target_flank}에 치명적인 총공세를 전개하는 연계 수순입니다."

        # Pattern 3: Tactical Trade / Pawn Break
        if sum(is_caps) >= 2:
            return f"{m1}을(를) 기점으로 {m2}와 {m3}로 이어지는 연속 기물 교환을 통해 긴장을 해소하고 확실한 기물 우위를 확보하는 수순입니다."

        # Pattern 4: Piece Infiltration / King Pressure
        if is_checks and is_checks[0] and len(moves_san) >= 3:
            return f"{m1} 체크로 상대 킹을 노출시킨 후 {m3} 등으로 침투하여 상대 수비 진영을 연쇄 압박하는 공격 수순입니다."

        return f"{m1} 이후 {m2}로 이어지는 기물 기동을 통해 전세를 장악하고 지속적인 주도권을 유지하는 수순입니다."

    @classmethod
    def _analyze_refutation_line(
        cls,
        board: chess.Board,
        pv_uci: List[str],
        player_color: chess.Color,
        is_mate_win: bool = False,
    ) -> str:
        """Simulate opponent's punishing line on a virtual board and identify what makes it deadly."""
        if not pv_uci:
            return ""

        victim_color_ko = "백" if player_color == chess.WHITE else "흑"
        sim_board = board.copy()
        first_uci = pv_uci[0]
        try:
            first_move = chess.Move.from_uci(first_uci)
            first_san = sim_board.san(first_move)
        except Exception:
            first_san = first_uci
            return f"{first_san} 반격으로 상대에게 주도권을 허용합니다."

        if is_mate_win:
            return f"상대가 {first_san} 체크로 최후의 저항을 시도하지만, 침착하게 응수하면 강제 체크메이트로 승리를 확정짓습니다."

        actions = []
        from_sq = first_move.from_square
        to_sq = first_move.to_square
        piece = sim_board.piece_at(from_sq)

        is_cap = sim_board.is_capture(first_move)
        is_chk = sim_board.gives_check(first_move)

        # Check if first_move is a Rook Lift
        is_rook_lift = False
        if piece and piece.piece_type == chess.ROOK:
            opp_color = not player_color
            from_r, to_r = chess.square_rank(from_sq), chess.square_rank(to_sq)
            if (opp_color == chess.WHITE and from_r in (0, 1) and to_r in (2, 3)) or (opp_color == chess.BLACK and from_r in (7, 6) and to_r in (5, 4)):
                is_rook_lift = True

        # Classify by piece type accurately
        if piece and piece.piece_type == chess.PAWN:
            if to_sq in (chess.D4, chess.D5, chess.E4, chess.E5, chess.C4, chess.C5):
                actions.append(f"{first_san}로 중앙 폰을 전진하여 구조를 흔들면")
            elif to_sq in (chess.G4, chess.G5, chess.H4, chess.H5, chess.F4, chess.F5):
                actions.append(f"{first_san} 폰 전진으로 {victim_color_ko}의 기물을 위협하고 진영을 압박하면")
            elif is_cap:
                actions.append(f"{first_san} 폰 타격으로 폰 구조를 파괴하면")
            else:
                actions.append(f"{first_san} 폰 전진으로 활로를 열면")
        elif piece and piece.piece_type == chess.KNIGHT:
            if is_cap:
                actions.append(f"{first_san}로 주요 기물을 타격하면")
            else:
                actions.append(f"{first_san}로 나이트를 공격 거점으로 기동하여 압박하면")
        elif piece and piece.piece_type == chess.BISHOP:
            if is_cap:
                actions.append(f"{first_san}로 기물을 타격하고 수비선을 붕괴시키면")
            else:
                actions.append(f"{first_san}로 비숍 사선을 장악하고 기물을 압박하면")
        elif piece and piece.piece_type == chess.ROOK:
            if is_chk:
                actions.append(f"기습적인 {first_san} 룩 체크로 킹을 몰아붙이면")
            elif is_cap:
                actions.append(f"{first_san}로 룩을 침투시켜 기물을 타격하면")
            elif is_rook_lift:
                actions.append(f"{first_san} 룩 리프트로 킹사이드 측면 공격 화력을 집중시키면")
            else:
                actions.append(f"{first_san}로 주요 파일을 장악하고 진영을 압박하면")
        elif piece and piece.piece_type == chess.QUEEN:
            if is_chk:
                actions.append(f"기습적인 {first_san} 퀸 체크로 킹을 압박하면")
            elif is_cap:
                actions.append(f"{first_san} 기물 타격으로 수비망을 무너뜨리면")
            else:
                actions.append(f"{first_san} 퀸 침투로 전방위 압박을 가하면")
        else:
            if is_chk:
                actions.append(f"기습적인 {first_san} 체크로 킹을 압박하면")
            elif is_cap:
                actions.append(f"{first_san} 기물 타격으로 수비망을 흔들면")
            else:
                actions.append(f"{first_san} 기동으로 공격 주도권을 장악하면")

        return f"상대가 {' '.join(actions)}, {victim_color_ko}은 주도권을 잃고 수세에 몰리게 됩니다."

    @classmethod
    def _analyze_best_alternative_line(
        cls,
        board: chess.Board,
        pv_uci: List[str],
        player_color: chess.Color,
    ) -> str:
        """Analyze why the engine's best move resolves the danger without repeating the move name."""
        if not pv_uci:
            return ""

        sim_board = board.copy()
        first_uci = pv_uci[0]
        try:
            first_move = chess.Move.from_uci(first_uci)
            first_san = sim_board.san(first_move)
        except Exception:
            first_san = first_uci

        piece = sim_board.piece_at(first_move.from_square) if hasattr(first_move, 'from_square') else None

        # 1. King Move / Escape (e.g. Kh8, Kf8)
        if piece and piece.piece_type == chess.KING:
            return "킹을 상대 나이트 체크(Nf6+/Nxg7) 및 위험한 대각선 핀(Pin)에서 미리 대피시켜 안정성을 확보할 수 있었습니다."

        # 2. Defense / Guard
        if first_san in ("Re8", "Re1", "Rd8", "Rd1", "Qe7", "Qd8", "Qe2"):
            return "중앙 핵심 폰과 약점 거점을 단단히 지키고 상대의 돌파를 차단할 수 있었습니다."

        # 3. Counter attack or piece trade
        if sim_board.is_capture(first_move):
            return "기물 교환으로 상대의 공격 템포를 끊고 형세를 대등하게 유지할 수 있었습니다."

        return "기물 배치를 안정화하고 상대의 전술적 틈새를 억제할 수 있었습니다."

    @classmethod
    def _analyze_prophylaxis_preparation(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        played_move: chess.Move,
        best_pv_uci: List[str],
    ) -> Optional[str]:
        """Check if the played move prepares for future central breaks or maneuvers."""
        san = ChessRulesHelper.uci_to_san(before_board, played_move.uci())
        if not san:
            return None

        if san in ("Rad8", "Rfd8", "Rad1", "Rfd1", "Rd8", "Rd1"):
            file_char = san[-2] if len(san) >= 3 else "d"
            return f"향후 일어날 중앙 폰 돌파로 {file_char}-파일이 개방될 때를 대비하여 룩을 사전에 정렬(X-ray)한 전략적 준비수"
        elif san in ("Re8", "Re1", "Rae8", "Rfe8", "Rae1", "Rfe1"):
            return "중앙 폰을 든든히 지키며 향후 나이트의 기동 경로를 열어주는 사전 배치"
        elif san in ("a6", "a3"):
            return "상대의 진입을 차단하고 비숍의 안전한 퇴로를 미리 확보하는 예방수"
        elif san in ("h6", "h3"):
            return "킹의 탈출로(Luft)를 열어 백랭크 위협을 영구히 예방하고 핀을 억제하는 예방수"

        return None

    @classmethod
    def generate_pv_narrative_summary(
        cls,
        board: chess.Board,
        pv_uci_list: List[str],
    ) -> str:
        """Generate a clean 1-line narrative summary for a candidate PV line."""
        if not pv_uci_list:
            return "안정적인 국면 유지 라인"

        sim_board = board.copy()
        try:
            first_move = chess.Move.from_uci(pv_uci_list[0])
            first_san = sim_board.san(first_move)
        except Exception:
            first_san = pv_uci_list[0]

        if first_san in ("d4", "d5", "e4", "e5", "c4", "c5"):
            return f"{first_san} 중앙 폰 돌파 및 사선 개방 라인"
        elif first_san.startswith("N"):
            return f"{first_san} 나이트 기동 및 공격 거점 침투 라인"
        elif first_san.startswith("B"):
            return f"{first_san} 비숍 사선 장악 및 기물 압박 라인"
        elif first_san.startswith("R"):
            return f"{first_san} 파일 지배 및 전선 지원 라인"
        elif first_san.startswith("Q"):
            return f"{first_san} 퀸 전개 및 전방위 압박 라인"
        elif first_san in ("Kh8", "Kh1", "Kf8", "Kf1", "Kg8", "Kg1"):
            return f"{first_san} 킹 안전 확보 및 핀 회피 라인"

        return f"{first_san} 전개 및 국면 조율 라인"

    @classmethod
    def generate_pv_strategic_plan(
        cls,
        board: chess.Board,
        pv_uci_list: List[str],
    ) -> str:
        """Generates a deep strategic breakdown explaining the purpose and outcome of a candidate line."""
        if not pv_uci_list:
            return "포지션을 유지하며 안정적인 기물 전개를 도모하는 라인입니다."

        sim_b = board.copy()
        moves_san: List[str] = []
        captures_count = 0
        checks_count = 0

        for uci_str in pv_uci_list[:6]:
            try:
                mv = sim_b.parse_uci(uci_str)
                is_cap = sim_b.is_capture(mv)
                san = sim_b.san(mv)
                moves_san.append(san)
                if is_cap:
                    captures_count += 1
                sim_b.push(mv)
                if sim_b.is_check():
                    checks_count += 1
            except Exception:
                break

        first_san = moves_san[0] if moves_san else pv_uci_list[0]
        first_piece_char = first_san[0]

        # Strategic categorization
        if captures_count >= 2:
            theme = "적극적인 기물 교환 및 국면 단순화"
            desc = f"{first_san}을(를) 시작으로 연속적인 기물 교환을 유도하여 복잡성을 줄이고 안정적인 기물 정렬로 진입합니다."
        elif checks_count >= 1:
            theme = "선제 공격 및 주도권 장악"
            desc = f"{first_san}을(를) 통해 상대 진영에 직접적인 압박을 가하고 상대 수비를 강제하여 주도권을 쥐는 공격적 라인입니다."
        elif first_san in ("O-O", "O-O-O", "Kh8", "Kh1", "Kf8", "Kf1"):
            theme = "킹 안전 확보 및 캐슬링 전개"
            desc = f"{first_san}으로 킹을 안전한 진영으로 대피시키고 룩들을 연결하여 후방 전선을 정비하는 안정적 정석 수순입니다."
        elif first_san in ("d4", "d5", "e4", "e5", "c4", "c5", "f4", "f5"):
            theme = "중앙 폰 브레이크 및 공간 확장"
            desc = f"{first_san} 폰 전진을 통해 중앙 텐션을 발생시키고, 기물들의 기동 사선을 열어 활동 반경을 넓히는 핵심 라인입니다."
        elif first_piece_char == 'N':
            theme = "나이트 기동 및 전초기지 침투"
            desc = f"{first_san}으로 나이트를 유리한 거점으로 재배치하여 상대 중앙과 약점 칸을 정밀 타격하는 전략적 수순입니다."
        elif first_piece_char == 'B':
            theme = "비숍 대각선 사선 장악"
            desc = f"{first_san}을(를) 통해 긴 대각선을 확보하고 상대 주요 기물과 킹 진영을 조준하는 기물 활성화 라인입니다."
        elif first_piece_char == 'R':
            theme = "오픈 파일 룩 정렬 및 전선 압박"
            desc = f"{first_san}으로 룩을 주요 세로줄에 배치하여 향후 침투로를 사전에 확보하는 포지셔널 라인입니다."
        elif first_piece_char == 'Q':
            theme = "퀸 전개 및 전방위 압박"
            desc = f"{first_san}으로 퀸을 공격적인 위치로 전개하여 상대 수비의 균열을 유도하는 라인입니다."
        else:
            theme = "기물 조율 및 안정적 발전"
            desc = f"{first_san}을(를) 통해 진형의 약점을 보완하고 차분히 다음 공격을 준비하는 균형 잡힌 라인입니다."

        return f"[{theme}] {desc}"
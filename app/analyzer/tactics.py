import chess
from typing import List, Optional, Set, Dict, Tuple, Any
from app.core.rules import ChessRulesHelper, PIECE_VALUES
from app.schemas.analysis import TacticalMetrics


class TacticsAnalyzer:
    """Calculates tactical delta and piece relationships before and after a move."""

    @classmethod
    def analyze(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        played_move: chess.Move,
        eval_change: float,
        eval_before: float = 0.0,
        eval_after: float = 0.0,
        is_top_choice: bool = False,
        best_pv_uci: Optional[List[str]] = None,
        before_pv_results: Optional[List[Any]] = None,
        after_pv_results: Optional[List[Any]] = None,
    ) -> TacticalMetrics:
        player_color = before_board.turn
        opponent_color = not player_color

        from_sq = played_move.from_square
        to_sq = played_move.to_square
        moved_piece = after_board.piece_at(to_sq)

        # 1. Hanging Piece Detection
        is_hanging, hanging_list = cls._detect_hanging_pieces(before_board, after_board, player_color, to_sq, played_move)

        # 2. Defending Line Severed (Undefended Pieces)
        undefended_list = cls._detect_lost_defenders(before_board, after_board, player_color, from_sq)

        # 3. Chess.com Standard Brilliant Move Detection (Genuine Piece/Exchange Sacrifice)
        is_brilliant = cls._detect_brilliant_move(
            before_board=before_board,
            after_board=after_board,
            played_move=played_move,
            eval_change=eval_change,
            eval_before=eval_before,
            best_pv_uci=best_pv_uci,
            after_pv_results=after_pv_results,
        )

        # 4. Chess.com Standard Great Move Detection (Only Move or Critical Game-Changer without sacrifice)
        is_great = cls._detect_great_move(
            eval_before=eval_before,
            eval_after=eval_after,
            eval_change=eval_change,
            is_top_choice=is_top_choice,
            is_brilliant=is_brilliant,
            before_pv_results=before_pv_results,
            player_color=player_color,
        )

        # 5. Indirect Defense Detection
        is_indirect = cls._detect_indirect_defense(after_board, player_color, to_sq, best_pv_uci)

        # 6. Overloaded Piece Detection
        is_overloaded = cls._detect_overloaded_pieces(after_board, player_color)

        # 7. Rich Tactical Motifs Detection (Strict Delta Check)
        forks = cls._detect_forks(before_board, after_board, played_move, player_color)
        pins = cls._detect_pins(before_board, after_board, played_move, player_color)
        skewers = cls._detect_skewers(before_board, after_board, played_move, player_color)
        discovered_attacks = cls._detect_discovered_attacks(before_board, after_board, played_move, player_color)
        line_clearances = cls._detect_line_clearances(before_board, after_board, played_move, player_color)
        mate_threats = cls._detect_mate_threats(after_board, player_color, after_pv_results)

        # Unified motif tags
        motifs: List[str] = []
        if after_board.is_check():
            motifs.append("Check")
        if forks:
            motifs.append("Fork")
        if pins:
            motifs.append("Pin")
        if skewers:
            motifs.append("Skewer")
        if discovered_attacks:
            motifs.append("Discovered Attack")
        if line_clearances:
            motifs.append("Line Clearance")
        if is_overloaded:
            motifs.append("Overload")
        if mate_threats:
            motifs.append("Mate Threat")

        return TacticalMetrics(
            is_hanging=is_hanging,
            hanging_pieces=hanging_list,
            undefended_pieces=undefended_list,
            is_brilliant_sacrifice=is_brilliant,
            is_great_move=is_great,
            is_indirectly_defended=is_indirect,
            is_overloaded=is_overloaded,
            tactical_motifs=motifs,
            forks=forks,
            pins=pins,
            skewers=skewers,
            discovered_attacks=discovered_attacks,
            line_clearances=line_clearances,
            mate_threats=mate_threats,
        )

    @classmethod
    def _detect_forks(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> List[str]:
        """Detects genuine double attacks / forks against 2+ vulnerable targets or King + piece."""
        forks: List[str] = []
        opponent_color = not color
        to_sq = move.to_square
        piece = after_board.piece_at(to_sq)
        if not piece:
            return forks

        # A pawn capturing an enemy pawn in an exchange is NOT a fork
        is_capture = before_board.is_capture(move)
        captured_p = before_board.piece_at(to_sq)
        if piece.piece_type == chess.PAWN and is_capture and captured_p and captured_p.piece_type == chess.PAWN:
            return forks

        attacked_targets: List[str] = []
        attacks = after_board.attacks(to_sq)
        attacker_val = ChessRulesHelper.get_piece_value(piece)

        for sq in attacks:
            p = after_board.piece_at(sq)
            if p and p.color == opponent_color:
                val = ChessRulesHelper.get_piece_value(p)
                p_name = p.piece_type
                is_undefended = len(after_board.attackers(opponent_color, sq)) == 0

                if p_name == chess.KING:
                    attacked_targets.append(f"킹({chess.square_name(sq)})")
                elif is_undefended or val > attacker_val:
                    attacked_targets.append(f"{p.symbol().upper()}({chess.square_name(sq)})")

        if len(attacked_targets) >= 2:
            forks.append(f"{chess.square_name(to_sq)}의 {piece.symbol().upper()}이(가) 상대 {', '.join(attacked_targets)}을(를) 동시 공격(Fork)")
        return forks

    @classmethod
    def _detect_pins(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> List[str]:
        """Detects NEW Absolute Pins (to King) and Relative Pins (to Queen) created by this move."""
        pins: List[str] = []
        opponent_color = not color
        opp_king = after_board.king(opponent_color)

        # 1. NEW Absolute Pins to King
        if opp_king is not None:
            for sq in chess.SQUARES:
                p = after_board.piece_at(sq)
                if p and p.color == opponent_color and p.piece_type != chess.KING:
                    was_pinned = before_board.is_pinned(opponent_color, sq)
                    is_pinned = after_board.is_pinned(opponent_color, sq)
                    if is_pinned and not was_pinned:
                        pinners = after_board.attackers(color, sq)
                        for p_sq in pinners:
                            pinner_piece = after_board.piece_at(p_sq)
                            if pinner_piece and pinner_piece.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                                pins.append(
                                    f"{pinner_piece.symbol().upper()}({chess.square_name(p_sq)})의 상대 킹({chess.square_name(opp_king)})을 향한 절대 핀(Absolute Pin)"
                                )
                                break

        # 2. NEW Relative Pins to Queen
        opp_queens = [sq for sq in chess.SQUARES if after_board.piece_at(sq) == chess.Piece(chess.QUEEN, opponent_color)]
        for q_sq in opp_queens:
            q_f, q_r = chess.square_file(q_sq), chess.square_rank(q_sq)
            for sq in chess.SQUARES:
                p = after_board.piece_at(sq)
                if p and p.color == opponent_color and p.piece_type not in (chess.KING, chess.QUEEN):
                    sq_f, sq_r = chess.square_file(sq), chess.square_rank(sq)
                    df, dr = q_f - sq_f, q_r - sq_r
                    # Check collinearity
                    is_diag = abs(df) == abs(dr) and df != 0
                    is_ortho = (df == 0 and dr != 0) or (dr == 0 and df != 0)
                    if not (is_diag or is_ortho):
                        continue

                    step_f = 0 if df == 0 else (1 if df > 0 else -1)
                    step_r = 0 if dr == 0 else (1 if dr > 0 else -1)

                    # 1. Verify path between sq and q_sq is completely clear (no intermediate pieces)
                    curr_f, curr_r = sq_f + step_f, sq_r + step_r
                    path_clear = True
                    while (curr_f, curr_r) != (q_f, q_r):
                        if after_board.piece_at(chess.square(curr_f, curr_r)) is not None:
                            path_clear = False
                            break
                        curr_f += step_f
                        curr_r += step_r

                    if not path_clear:
                        continue

                    # 2. Check if attacker exists along the opposite direction from sq (stepping backward)
                    back_f, back_r = sq_f - step_f, sq_r - step_r
                    while 0 <= back_f <= 7 and 0 <= back_r <= 7:
                        b_sq = chess.square(back_f, back_r)
                        b_p = after_board.piece_at(b_sq)
                        if b_p is not None:
                            if b_p.color == color:
                                # Must be valid sliding piece along this direction
                                if (is_diag and b_p.piece_type in (chess.BISHOP, chess.QUEEN)) or \
                                   (is_ortho and b_p.piece_type in (chess.ROOK, chess.QUEEN)):
                                    # Was it already pinning before the move?
                                    was_pinning = (
                                        b_sq in before_board.attackers(color, sq) and
                                        before_board.piece_at(q_sq) == chess.Piece(chess.QUEEN, opponent_color)
                                    )
                                    if not was_pinning:
                                        p_name = ChessRulesHelper.get_piece_korean_name(b_p)
                                        pinned_name = ChessRulesHelper.get_piece_korean_name(p)
                                        pins.append(
                                            f"{p_name}({chess.square_name(b_sq)})의 상대 퀸({chess.square_name(q_sq)})을 향한 {pinned_name}({chess.square_name(sq)}) 상대적 핀(Relative Pin)"
                                        )
                            break
                        back_f -= step_f
                        back_r -= step_r
        return pins[:2]

    @classmethod
    def _detect_skewers(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> List[str]:
        """Detects NEW Skewers created by moving piece with strict directional raycast and obstacle checks."""
        skewers: List[str] = []
        to_sq = move.to_square
        piece = after_board.piece_at(to_sq)
        if not piece or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            return skewers

        opponent_color = not color
        to_f, to_r = chess.square_file(to_sq), chess.square_rank(to_sq)
        attacks = after_board.attacks(to_sq)

        for front_sq in attacks:
            front_p = after_board.piece_at(front_sq)
            if not front_p or front_p.color != opponent_color:
                continue

            front_val = ChessRulesHelper.get_piece_value(front_p)
            # Front piece must be high value (King or Queen)
            if front_p.piece_type != chess.KING and front_val < 5:
                continue

            # Calculate single step direction from to_sq to front_sq
            fr_f, fr_r = chess.square_file(front_sq), chess.square_rank(front_sq)
            df = fr_f - to_f
            dr = fr_r - to_r
            step_f = 0 if df == 0 else (1 if df > 0 else -1)
            step_r = 0 if dr == 0 else (1 if dr > 0 else -1)

            # Step strictly forward behind front_sq
            curr_f, curr_r = fr_f + step_f, fr_r + step_r
            while 0 <= curr_f <= 7 and 0 <= curr_r <= 7:
                curr_sq = chess.square(curr_f, curr_r)
                curr_p = after_board.piece_at(curr_sq)
                if curr_p is not None:
                    if curr_p.color == opponent_color:
                        behind_val = ChessRulesHelper.get_piece_value(curr_p)
                        if behind_val <= front_val and behind_val >= 3:
                            skewers.append(
                                f"{piece.symbol().upper()}({chess.square_name(to_sq)})의 스큐어(Skewer) 공격 ({front_p.symbol().upper()}({chess.square_name(front_sq)}) 뒤 {curr_p.symbol().upper()}({chess.square_name(curr_sq)}) 노림)"
                            )
                    # Ray is blocked by any piece
                    break
                curr_f += step_f
                curr_r += step_r

        return skewers[:2]

    @classmethod
    def _detect_discovered_attacks(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> List[str]:
        """Detects Discovered Attacks/Checks unmasked when the moving piece clears the line."""
        discovered: List[str] = []
        from_sq = move.from_square
        opponent_color = not color

        for sq in chess.SQUARES:
            p = after_board.piece_at(sq)
            if p and p.color == color and p.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN) and sq != move.to_square:
                ray = chess.SquareSet.ray(sq, from_sq)
                if ray and from_sq in ray:
                    attacks_after = after_board.attacks(sq)
                    attacks_before = before_board.attacks(sq)
                    new_attacks = attacks_after - attacks_before
                    for t_sq in new_attacks:
                        t_piece = after_board.piece_at(t_sq)
                        if t_piece and t_piece.color == opponent_color:
                            if t_piece.piece_type == chess.KING:
                                discovered.append(f"{p.symbol().upper()}({chess.square_name(sq)})의 상대 킹({chess.square_name(t_sq)})을 향한 디스커버드 체크(Discovered Check)")
                            elif ChessRulesHelper.get_piece_value(t_piece) >= 3:
                                discovered.append(f"{p.symbol().upper()}({chess.square_name(sq)})의 상대 {t_piece.symbol().upper()}({chess.square_name(t_sq)})을 향한 디스커버드 공격(Discovered Attack)")
        return discovered[:2]

    @classmethod
    def _detect_line_clearances(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> List[str]:
        """Detects when moving from_sq genuinely opens a slider's attack ray to a high-value enemy target or king."""
        clearances: List[str] = []
        from_sq = move.from_square
        to_sq = move.to_square
        opponent_color = not color

        for sq in chess.SQUARES:
            slider = after_board.piece_at(sq)
            if not slider or slider.color != color or sq == to_sq or slider.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                continue

            # Check geometric validity: from_sq must be along this slider's natural move direction
            f_from, r_from = chess.square_file(from_sq), chess.square_rank(from_sq)
            f_sq, r_sq = chess.square_file(sq), chess.square_rank(sq)
            df = abs(f_from - f_sq)
            dr = abs(r_from - r_sq)

            is_diagonal = (df == dr and df > 0)
            is_orthogonal = ((df == 0 and dr > 0) or (dr == 0 and df > 0))

            if slider.piece_type == chess.BISHOP and not is_diagonal:
                continue
            if slider.piece_type == chess.ROOK and not is_orthogonal:
                continue
            if slider.piece_type == chess.QUEEN and not is_diagonal and not is_orthogonal:
                continue

            # Must have newly unmasked an attack onto enemy King or piece value >= 3
            attacks_before = before_board.attacks(sq)
            attacks_after = after_board.attacks(sq)
            new_attacks = attacks_after - attacks_before

            for target_sq in new_attacks:
                t_piece = after_board.piece_at(target_sq)
                if t_piece and t_piece.color == opponent_color:
                    if t_piece.piece_type == chess.KING or ChessRulesHelper.get_piece_value(t_piece) >= 3:
                        target_name = "상대 킹" if t_piece.piece_type == chess.KING else f"상대 {t_piece.symbol().upper()}({chess.square_name(target_sq)})"
                        clearances.append(f"기물 이동으로 {chess.square_name(sq)} {slider.symbol().upper()}의 {target_name}을 향한 공격 사선(Line Clearance) 개방")
        return clearances[:2]

    @classmethod
    def _detect_mate_threats(
        cls,
        board: chess.Board,
        color: chess.Color,
        after_pv_results: Optional[List[Any]] = None,
    ) -> List[str]:
        """Detects forced mate threats or strict back-rank traps with zero luft."""
        threats: List[str] = []
        opponent_color = not color
        opp_king = board.king(opponent_color)

        # 1. Multi-PV forced checkmate
        if after_pv_results and len(after_pv_results) > 0:
            top = after_pv_results[0]
            if top.score.type == "mate":
                threats.append(f"{abs(int(top.score.value))}수 강제 체크메이트 위협")
                return threats

        # 2. Strict Back-Rank Checkmate trap (King trapped with no escape squares and major piece attacking)
        if opp_king is not None and board.fullmove_number > 15:
            back_rank = 7 if opponent_color == chess.BLACK else 0
            if chess.square_rank(opp_king) == back_rank:
                king_file = chess.square_file(opp_king)
                king_rank = chess.square_rank(opp_king)
                front_rank = king_rank - 1 if opponent_color == chess.BLACK else king_rank + 1

                escape_squares = [
                    chess.square(f, front_rank)
                    for f in (king_file - 1, king_file, king_file + 1)
                    if 0 <= f <= 7
                ]
                has_luft = False
                for esc_sq in escape_squares:
                    p = board.piece_at(esc_sq)
                    if not p and not board.is_attacked_by(color, esc_sq):
                        has_luft = True
                        break

                if not has_luft:
                    back_rank_attacks = any(
                        board.piece_at(sq) and board.piece_at(sq).piece_type in (chess.ROOK, chess.QUEEN) and board.piece_at(sq).color == color
                        for sq in [chess.square(f, back_rank) for f in range(8)]
                    )
                    if back_rank_attacks:
                        threats.append(f"상대 킹({chess.square_name(opp_king)})의 백랭크(Back-rank) 메이트 위협")

        return threats[:2]

    @classmethod
    def _detect_hanging_pieces(
        cls,
        before_board: chess.Board,
        board: chess.Board,
        color: chess.Color,
        destination_sq: chess.Square,
        move: chess.Move,
    ) -> Tuple[bool, List[str]]:
        """Checks if friendly pieces are truly left hanging (undefended or losing exchange)."""
        hanging_squares: List[str] = []
        opponent_color = not color

        is_capture = before_board.is_capture(move)
        captured_piece = before_board.piece_at(destination_sq)
        captured_val = ChessRulesHelper.get_piece_value(captured_piece) if captured_piece else 0

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.color != color:
                continue

            attackers = list(board.attackers(opponent_color, sq))
            defenders = list(board.attackers(color, sq))

            if not attackers:
                continue

            my_val = ChessRulesHelper.get_piece_value(piece)
            min_attacker_val = min(
                ChessRulesHelper.get_piece_value(board.piece_at(a_sq))
                for a_sq in attackers
            )

            # Exclude legitimate equal/favorable trades on destination square
            if sq == destination_sq and is_capture:
                # If we just captured equal or greater material (e.g. Pawn takes Pawn, Bishop takes Bishop)
                if captured_val >= my_val:
                    continue
                if piece.piece_type == chess.PAWN and captured_val >= 1:
                    continue

            # Case A: Attacked with 0 defenders
            p_name = ChessRulesHelper.get_piece_korean_name(piece)
            sq_label = f"{p_name}({chess.square_name(sq)})"

            if len(defenders) == 0:
                hanging_squares.append(sq_label)
                continue

            # Case B: Attacked by strictly lower value piece (e.g. Pawn attacking Queen/Rook/Minor)
            if min_attacker_val < my_val:
                hanging_squares.append(sq_label)
                continue

            # Case C: Attacked by equal or lower value piece where equal/lower attackers outnumber defenders
            equal_or_lower_attackers = [
                a_sq for a_sq in attackers
                if ChessRulesHelper.get_piece_value(board.piece_at(a_sq)) <= my_val
            ]
            if len(equal_or_lower_attackers) > len(defenders) and min_attacker_val <= my_val:
                hanging_squares.append(sq_label)

        dest_name = chess.square_name(destination_sq)
        is_dest_hanging = any(dest_name in h for h in hanging_squares)
        is_hanging = len(hanging_squares) > 0
        return is_hanging, hanging_squares

    @classmethod
    def _detect_lost_defenders(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        color: chess.Color,
        from_sq: chess.Square,
    ) -> List[str]:
        """Detects friendly pieces that lost protection because the moving piece moved away."""
        opponent_color = not color
        lost_defended: List[str] = []

        # Squares that were attacked/defended by from_sq before the move
        guarded_before = before_board.attacks(from_sq)

        for sq in guarded_before:
            piece_before = before_board.piece_at(sq)
            if not piece_before or piece_before.color != color:
                continue

            # Check if this friendly piece is attacked by opponent
            if after_board.attackers(opponent_color, sq):
                # Check defenders after the move
                defenders_after = after_board.attackers(color, sq)
                if len(defenders_after) == 0:
                    p_name = ChessRulesHelper.get_piece_korean_name(piece_before)
                    lost_defended.append(f"{p_name}({chess.square_name(sq)})")

        return lost_defended

    @classmethod
    def _detect_brilliant_move(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        played_move: chess.Move,
        eval_change: float,
        eval_before: float,
        best_pv_uci: Optional[List[str]],
        after_pv_results: Optional[List[Any]] = None,
    ) -> bool:
        """Chess.com Official Standard Brilliant Move Detector:
        1. Condition 1 (Near-Best Move): Eval loss <= 0.20 cp compared to best.
        2. Condition 2 (Non-Runaway): Game is not already runaway won before move (|eval_before| < 7.0).
        3. Condition 3 (Direct Piece Sacrifice): The MOVED PIECE ITSELF (Knight/Bishop=3, Rook=5, Queen=9)
           must be intentionally placed into an attacked square with fewer defenders than attackers,
           or attacked by lower-value piece (e.g. Queen attacked by pawn/minor), or net material sacrifice.
           (Moving a piece safely while an unrelated pawn is hanging elsewhere is NOT a sacrifice!)
        4. Condition 4 (Tactical Value):
           - Trap Gap >= 2.0 (opponent suffers heavy collapse if taking the piece), OR
           - Multi-ply sequence forces a net material gain >= +1.0 or forced winning attack.
        """
        # Condition 1: Must be near-best (evaluation loss <= 0.20 cp)
        if eval_change < -0.20:
            return False

        # Condition 2: Exclude already runaway winning games
        if abs(eval_before) >= 7.0:
            return False

        to_sq = played_move.to_square
        player_color = before_board.turn
        opponent_color = not player_color

        moved_piece = after_board.piece_at(to_sq)
        if not moved_piece:
            return False

        piece_val = ChessRulesHelper.get_piece_value(moved_piece)
        if piece_val < 3:  # Only Knight, Bishop, Rook, Queen sacrifices count
            return False

        captured_piece = before_board.piece_at(to_sq)
        captured_val = ChessRulesHelper.get_piece_value(captured_piece) if captured_piece else 0

        # Equal or greater material captures (e.g. Bishop takes Bishop, Queen takes Queen)
        # are standard trades/captures, NEVER a sacrifice!
        if captured_val >= piece_val:
            return False

        # Condition 3: Moved piece ITSELF must be under direct attack / sacrificed
        attackers = after_board.attackers(opponent_color, to_sq)
        defenders = after_board.attackers(player_color, to_sq)

        if len(attackers) == 0:
            # Destination square is completely safe -> NOT a piece sacrifice!
            return False

        is_legit_sacrifice = False
        # Case A: Clean undefended piece (1+ attackers, 0 defenders)
        if len(attackers) > 0 and len(defenders) == 0:
            is_legit_sacrifice = True
        # Case B: Under-defended (more enemy attackers than friendly defenders)
        elif len(attackers) > len(defenders):
            is_legit_sacrifice = True
        # Case C: Attacked by strictly lower value enemy piece (e.g. Queen/Rook attacked by pawn/minor)
        else:
            min_attacker_val = min(
                ChessRulesHelper.get_piece_value(after_board.piece_at(a_sq))
                for a_sq in attackers
            )
            # Queen(9) attacked by Rook(5)/Minor(3)/Pawn(1), or Rook(5) attacked by Minor(3)/Pawn(1)
            if min_attacker_val < piece_val:
                is_legit_sacrifice = True

        if not is_legit_sacrifice:
            return False

        # Condition 4: Tactical Justification
        # A. Tactical Punishment Gap (If opponent recapturing on to_sq is heavily punished)
        if after_pv_results and len(after_pv_results) >= 2:
            top_defense = after_pv_results[0]
            for pv_cand in after_pv_results[1:]:
                try:
                    cand_move = after_board.parse_uci(pv_cand.move_uci)
                    if cand_move.to_square == to_sq:
                        best_val = top_defense.score.value
                        cand_val = pv_cand.score.value
                        gap = (best_val - cand_val) if opponent_color == chess.WHITE else (cand_val - best_val)
                        if gap >= 2.0 or abs(best_val - cand_val) >= 2.5:
                            return True
                except Exception:
                    pass

        # B. Multi-ply PV Material Delta Simulation (Simulating 4~6 moves ahead)
        if best_pv_uci and len(best_pv_uci) >= 2:
            try:
                def get_tot_material(b: chess.Board, col: chess.Color) -> int:
                    return sum(
                        ChessRulesHelper.get_piece_value(b.piece_at(s))
                        for s in chess.SQUARES
                        if b.piece_at(s) and b.piece_at(s).color == col
                    )

                start_diff = get_tot_material(before_board, player_color) - get_tot_material(before_board, opponent_color)

                sim_b = before_board.copy()
                sim_b.push(played_move)
                for uci_str in best_pv_uci[:6]:
                    try:
                        mv = sim_b.parse_uci(uci_str)
                        sim_b.push(mv)
                    except Exception:
                        break

                end_diff = get_tot_material(sim_b, player_color) - get_tot_material(sim_b, opponent_color)
                # If sequence forces a net material gain of +1 or more (Pawn up endgame or piece won)
                if end_diff - start_diff >= 1:
                    return True
            except Exception:
                pass

        # C. Pure Upfront Sacrifice (if piece_val - captured_val >= 2 and eval stays non-losing)
        if (piece_val - captured_val >= 2) and len(attackers) > 0 and len(defenders) == 0:
            return True

        return False

    @classmethod
    def _detect_great_move(
        cls,
        eval_before: float,
        eval_after: float,
        eval_change: float,
        is_top_choice: bool,
        is_brilliant: bool,
        before_pv_results: Optional[List[Any]] = None,
        player_color: chess.Color = chess.WHITE,
    ) -> bool:
        """Chess.com Official Standard Great Move Detector:
        1. Must be the Top Move (is_top_choice == True) or near-best (eval loss <= 0.05).
        2. Must NOT already be Brilliant.
        3. Condition A (Only Move): The gap between Rank 1 move and Rank 2 move before the move is >= 1.50 pawns.
        4. Condition B (Game Changer): Turns a losing position (player_eval <= -1.5) into equal (>= -0.3),
           or equal into winning (>= +1.8).
        """
        if is_brilliant:
            return False

        if eval_change < -0.05:
            return False

        # Condition A: Only Move (Rank 1 is significantly better than Rank 2)
        if before_pv_results and len(before_pv_results) >= 2:
            top_eval = before_pv_results[0].score.value
            second_eval = before_pv_results[1].score.value
            gap = (top_eval - second_eval) if player_color == chess.WHITE else (second_eval - top_eval)
            if gap >= 1.50 and is_top_choice:
                return True

        # Condition B: Game Changer
        p_eval_before = eval_before if player_color == chess.WHITE else -eval_before
        p_eval_after = eval_after if player_color == chess.WHITE else -eval_after

        if p_eval_before <= -1.50 and p_eval_after >= -0.30:
            return True
        if -0.50 <= p_eval_before <= 0.50 and p_eval_after >= 1.80:
            return True

        return False

    @classmethod
    def _detect_indirect_defense(
        cls,
        board: chess.Board,
        color: chess.Color,
        to_sq: chess.Square,
        best_pv_uci: Optional[List[str]],
    ) -> bool:
        """Detects if a seemingly undefended piece cannot be captured because the response punishes it."""
        if not best_pv_uci or len(best_pv_uci) < 2:
            return False

        # If opponent's top response does NOT capture the piece on to_sq despite being attacked
        opponent_color = not color
        attackers = board.attackers(opponent_color, to_sq)
        if not attackers:
            return False

        opp_reply_uci = best_pv_uci[0]
        # Check if opp_reply targets to_sq
        try:
            opp_move = board.parse_uci(opp_reply_uci)
            if opp_move.to_square != to_sq:
                # Opponent cannot safely capture the piece!
                return True
        except Exception:
            pass

        return False

    @classmethod
    def _detect_overloaded_pieces(
        cls,
        board: chess.Board,
        color: chess.Color,
    ) -> bool:
        """Detects if any friendly minor/major piece is solely tasked with defending multiple attacked valuable pieces."""
        opponent_color = not color
        defense_map: Dict[chess.Square, List[chess.Square]] = {}

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.color != color:
                continue

            # Only consider minor/major pieces (value >= 3) under real attack
            p_val = ChessRulesHelper.get_piece_value(piece)
            if p_val < 3:
                continue

            attackers = board.attackers(opponent_color, sq)
            if attackers:
                defenders = board.attackers(color, sq)
                # Only if this piece is defended
                for d_sq in defenders:
                    d_piece = board.piece_at(d_sq)
                    # King and Pawns are never considered overloaded tactical defenders
                    if d_piece and d_piece.piece_type not in (chess.KING, chess.PAWN):
                        defense_map.setdefault(d_sq, []).append(sq)

        # Overloaded if a single minor/major defender protects 2 or more currently attacked valuable pieces
        for d_sq, defended_list in defense_map.items():
            if len(defended_list) >= 2:
                return True
        return False

    @classmethod
    def _detect_tactical_motifs(
        cls,
        board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> List[str]:
        """Detects tactical motifs created by the move: check, pin, fork, skewer, etc."""
        motifs: List[str] = []
        opponent_color = not color

        # Check
        if board.is_check():
            motifs.append("check")

        # Fork detection: moved piece attacks 2 or more valuable enemy pieces
        to_sq = move.to_square
        attacks = board.attacks(to_sq)
        attacked_valuable = 0
        for sq in attacks:
            p = board.piece_at(sq)
            if p and p.color == opponent_color and ChessRulesHelper.get_piece_value(p) >= 3:
                attacked_valuable += 1
        if attacked_valuable >= 2:
            motifs.append("fork")

        # Pin detection: any enemy piece pinned to their king
        opp_king_sq = board.king(opponent_color)
        if opp_king_sq is not None:
            for sq in chess.SQUARES:
                p = board.piece_at(sq)
                if p and p.color == opponent_color and board.is_pinned(opponent_color, sq):
                    motifs.append("pin")
                    break

        return list(set(motifs))

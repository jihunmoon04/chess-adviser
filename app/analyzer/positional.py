import chess
from typing import List, Optional, Set, Tuple
from app.core.rules import ChessRulesHelper, CENTER_SQUARES
from app.schemas.analysis import PositionalMetrics, PawnStructureMetrics


class PositionalAnalyzer:
    """Calculates positional, structural, and strategic deltas before and after a move."""

    @classmethod
    def analyze(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        played_move: chess.Move,
    ) -> PositionalMetrics:
        player_color = before_board.turn
        opponent_color = not player_color

        from_sq = played_move.from_square
        to_sq = played_move.to_square
        moved_piece = after_board.piece_at(to_sq)

        # 1. Space & Central Control Deltas
        controlled_before = ChessRulesHelper.get_controlled_squares(before_board, player_color)
        controlled_after = ChessRulesHelper.get_controlled_squares(after_board, player_color)

        space_delta = len(controlled_after) - len(controlled_before)
        center_before = len(controlled_before.intersection(CENTER_SQUARES))
        center_after = len(controlled_after.intersection(CENTER_SQUARES))
        center_delta = center_after - center_before

        # 2. Activity / Mobility Delta
        mob_before = ChessRulesHelper.get_mobility(before_board, player_color)
        mob_after = ChessRulesHelper.get_mobility(after_board, player_color)
        activity_delta = mob_after - mob_before

        # 3. Outpost Detection (Knight/Bishop anchored in enemy territory defended by pawn)
        is_outpost, outpost_sq = cls._detect_outpost(after_board, player_color, to_sq, moved_piece)

        # 4. Open / Semi-Open File Control
        open_file_ctrl, open_file_letter = cls._detect_open_file(after_board, to_sq, moved_piece)
        open_files, semi_open_files = cls._detect_all_open_files(after_board, player_color)

        # 5. Pawn Structure Analysis
        pawn_metrics = cls._analyze_pawn_structure(before_board, after_board, played_move, player_color)

        # 6. Color Complex Weaknesses
        color_weaknesses = cls._analyze_color_complex(after_board, player_color)

        # 7. Bishop Quality (Good vs Bad Bishop)
        bishop_evals = cls._analyze_bishop_quality(after_board, player_color)

        # 8. King Safety & Shield
        king_safety_delta, shield_intact = cls._analyze_king_safety(before_board, after_board, player_color)
        king_safety_details = cls._analyze_detailed_king_safety(before_board, after_board, player_color, played_move)

        # 9. Rook Lift Detection
        is_rook_lift, rook_lift_note = cls._detect_rook_lift(before_board, after_board, played_move, player_color, moved_piece)

        # 10. Tempo & Development
        tempo_dev, repeated_move = cls._analyze_development(before_board, played_move, moved_piece)

        # 11. Initiative (Check, Capture, or Direct Threat)
        initiative = after_board.is_check() or before_board.is_capture(played_move)

        # 12. Move Intent Analysis (Prophylaxis, Maneuver, Defense, Attack)
        prophylaxis, maneuvers, defended, attacked = cls._analyze_move_intents(
            before_board=before_board,
            after_board=after_board,
            move=played_move,
            player_color=player_color,
            moved_piece=moved_piece,
        )

        return PositionalMetrics(
            space_control_delta=space_delta,
            central_control_delta=center_delta,
            activity_delta=activity_delta,
            is_outpost=is_outpost,
            outpost_square=outpost_sq,
            open_file_control=open_file_ctrl,
            open_file_name=open_file_letter,
            open_files=open_files,
            semi_open_files=semi_open_files,
            color_complex_weaknesses=color_weaknesses,
            bishop_quality=bishop_evals,
            pawn_structure=pawn_metrics,
            king_safety_delta=king_safety_delta,
            pawn_shield_intact=shield_intact,
            king_safety_details=king_safety_details,
            is_rook_lift=is_rook_lift,
            rook_lift_note=rook_lift_note,
            tempo_development=tempo_dev,
            is_repeated_move=repeated_move,
            initiative=initiative,
            prophylaxis_notes=prophylaxis,
            maneuver_notes=maneuvers,
            defended_targets_notes=defended,
            attacked_targets_notes=attacked,
        )

    @classmethod
    def _detect_outpost(
        cls,
        board: chess.Board,
        color: chess.Color,
        to_sq: chess.Square,
        piece: Optional[chess.Piece],
    ) -> Tuple[bool, Optional[str]]:
        if not piece or piece.piece_type not in (chess.KNIGHT, chess.BISHOP):
            return False, None

        rank = chess.square_rank(to_sq)
        valid_rank = (rank in (3, 4, 5)) if color == chess.WHITE else (rank in (2, 3, 4))
        if not valid_rank:
            return False, None

        defenders = board.attackers(color, to_sq)
        has_pawn_defender = any(
            board.piece_at(d_sq) and board.piece_at(d_sq).piece_type == chess.PAWN
            for d_sq in defenders
        )
        if not has_pawn_defender:
            return False, None

        file_idx = chess.square_file(to_sq)
        opp_color = not color
        opp_pawns = board.pieces(chess.PAWN, opp_color)

        can_be_attacked_by_pawn = False
        for p_sq in opp_pawns:
            p_file = chess.square_file(p_sq)
            p_rank = chess.square_rank(p_sq)
            if abs(p_file - file_idx) == 1:
                if (color == chess.WHITE and p_rank > rank) or (color == chess.BLACK and p_rank < rank):
                    can_be_attacked_by_pawn = True
                    break

        if not can_be_attacked_by_pawn:
            return True, chess.square_name(to_sq)

        return False, None

    @classmethod
    def _detect_open_file(
        cls,
        board: chess.Board,
        to_sq: chess.Square,
        piece: Optional[chess.Piece],
    ) -> Tuple[bool, Optional[str]]:
        if not piece or piece.piece_type not in (chess.ROOK, chess.QUEEN):
            return False, None

        file_idx = chess.square_file(to_sq)
        pawns_on_file = [
            sq for sq in chess.SQUARES
            if chess.square_file(sq) == file_idx and board.piece_at(sq) and board.piece_at(sq).piece_type == chess.PAWN
        ]

        if len(pawns_on_file) == 0:
            file_name = chess.FILE_NAMES[file_idx]
            return True, file_name
        return False, None

    @classmethod
    def _detect_all_open_files(
        cls,
        board: chess.Board,
        color: chess.Color,
    ) -> Tuple[List[str], List[str]]:
        open_files: List[str] = []
        semi_open_files: List[str] = []
        for f in range(8):
            file_name = chess.FILE_NAMES[f]
            white_pawns = any(board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, chess.WHITE) for r in range(8))
            black_pawns = any(board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, chess.BLACK) for r in range(8))

            if not white_pawns and not black_pawns:
                open_files.append(f"{file_name}-file")
            elif color == chess.WHITE and not white_pawns and black_pawns:
                semi_open_files.append(f"{file_name}-file")
            elif color == chess.BLACK and not black_pawns and white_pawns:
                semi_open_files.append(f"{file_name}-file")

        return open_files, semi_open_files

    @classmethod
    def _analyze_pawn_structure(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> PawnStructureMetrics:
        friendly_pawns_after = after_board.pieces(chess.PAWN, color)
        opp_pawns_after = after_board.pieces(chess.PAWN, not color)

        isolated_files: List[str] = []
        doubled_files: List[str] = []
        backward_pawns: List[str] = []
        pawn_dynamics: List[str] = []
        pawn_breaks: List[str] = []
        file_pawn_counts = [0] * 8

        for sq in friendly_pawns_after:
            f = chess.square_file(sq)
            file_pawn_counts[f] += 1

        for f in range(8):
            if file_pawn_counts[f] > 1:
                doubled_files.append(chess.FILE_NAMES[f])
            if file_pawn_counts[f] > 0:
                left_has = (file_pawn_counts[f - 1] > 0) if f > 0 else False
                right_has = (file_pawn_counts[f + 1] > 0) if f < 7 else False
                if not left_has and not right_has:
                    isolated_files.append(chess.FILE_NAMES[f])

        # Backward pawns
        for sq in friendly_pawns_after:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
            # If adjacent friendly pawns are ahead and cannot defend this pawn
            adjacent_pawns_behind = False
            for f_adj in (f - 1, f + 1):
                if 0 <= f_adj <= 7:
                    for r_adj in range(8):
                        if (color == chess.WHITE and r_adj <= r) or (color == chess.BLACK and r_adj >= r):
                            if after_board.piece_at(chess.square(f_adj, r_adj)) == chess.Piece(chess.PAWN, color):
                                adjacent_pawns_behind = True
            if not adjacent_pawns_behind and file_pawn_counts[f] > 0:
                # Square ahead is controlled by enemy
                stop_sq = chess.square(f, r + 1 if color == chess.WHITE else r - 1)
                if after_board.attackers(not color, stop_sq):
                    backward_pawns.append(chess.square_name(sq))

        # Structure type (Center d & e files)
        d_pawns = len([sq for sq in chess.SQUARES if chess.square_file(sq) == 3 and after_board.piece_at(sq) and after_board.piece_at(sq).piece_type == chess.PAWN])
        e_pawns = len([sq for sq in chess.SQUARES if chess.square_file(sq) == 4 and after_board.piece_at(sq) and after_board.piece_at(sq).piece_type == chess.PAWN])

        if d_pawns == 0 and e_pawns == 0:
            structure_type = "Open"
        elif d_pawns >= 2 and e_pawns >= 2:
            # Check if locked
            structure_type = "Closed" if (after_board.piece_at(chess.D4) and after_board.piece_at(chess.D5)) or (after_board.piece_at(chess.E4) and after_board.piece_at(chess.E5)) else "Dynamic"
        elif d_pawns == 0 or e_pawns == 0:
            structure_type = "Semi-Open"
        else:
            structure_type = "Dynamic"

        # Pawn Dynamics of played move
        moved_p = after_board.piece_at(move.to_square)
        if moved_p and moved_p.piece_type == chess.PAWN:
            if before_board.is_capture(move):
                pawn_dynamics.append("Pawn Trade / Capture")
            to_rank = chess.square_rank(move.to_square)
            to_file = chess.square_file(move.to_square)
            if to_file in (2, 3, 4, 5):  # c, d, e, f central advance
                if (color == chess.WHITE and to_rank in (3, 4)) or (color == chess.BLACK and to_rank in (4, 3)):
                    pawn_breaks.append(f"{chess.square_name(move.to_square)} Central Break")
                    pawn_dynamics.append("Central Break / Expansion")
            # Closed check
            opp_block_sq = chess.square(to_file, to_rank + 1 if color == chess.WHITE else to_rank - 1)
            if 0 <= opp_block_sq <= 63 and after_board.piece_at(opp_block_sq) == chess.Piece(chess.PAWN, not color):
                pawn_dynamics.append("File Closed / Center Lock")

        # Passed pawns created
        passed_created: List[str] = []
        for sq in friendly_pawns_after:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
            is_passed = True
            for opp_sq in opp_pawns_after:
                opp_f = chess.square_file(opp_sq)
                opp_r = chess.square_rank(opp_sq)
                if abs(opp_f - f) <= 1:
                    if (color == chess.WHITE and opp_r > r) or (color == chess.BLACK and opp_r < r):
                        is_passed = False
                        break
            if is_passed:
                passed_created.append(chess.square_name(sq))

        return PawnStructureMetrics(
            pawn_structure_type=structure_type,
            passed_pawns_created=passed_created,
            isolated_pawns=isolated_files,
            doubled_pawns=doubled_files,
            backward_pawns=backward_pawns[:2],
            pawn_breaks=pawn_breaks,
            pawn_dynamics=pawn_dynamics,
        )

    @classmethod
    def _analyze_color_complex(
        cls,
        board: chess.Board,
        color: chess.Color,
    ) -> List[str]:
        weaknesses: List[str] = []
        opp_color = not color
        opp_pawns = board.pieces(chess.PAWN, opp_color)

        # Check dark squares around opponent king
        opp_king = board.king(opp_color)
        if opp_king:
            king_rank = chess.square_rank(opp_king)
            king_file = chess.square_file(opp_king)
            # Count friendly control over dark vs light squares near opp king
            dark_control = 0
            light_control = 0
            for f in range(max(0, king_file - 1), min(8, king_file + 2)):
                for r in range(max(0, king_rank - 1), min(8, king_rank + 2)):
                    sq = chess.square(f, r)
                    is_dark = (f + r) % 2 == 0
                    if board.attackers(color, sq):
                        if is_dark:
                            dark_control += 1
                        else:
                            light_control += 1
            if dark_control >= 3:
                weaknesses.append("상대 킹 진영의 어두운 칸 약점(Dark-square weakness)")
            elif light_control >= 3:
                weaknesses.append("상대 킹 진영의 밝은 칸 약점(Light-square weakness)")

        return weaknesses[:2]

    @classmethod
    def _analyze_bishop_quality(
        cls,
        board: chess.Board,
        color: chess.Color,
    ) -> List[str]:
        bishops = board.pieces(chess.BISHOP, color)
        evals: List[str] = []
        center_sqs = (chess.D4, chess.D5, chess.E4, chess.E5)
        friendly_pawns = board.pieces(chess.PAWN, color)

        for b_sq in bishops:
            b_is_dark = (chess.square_file(b_sq) + chess.square_rank(b_sq)) % 2 == 0
            same_color_center_pawns = sum(
                1 for p_sq in friendly_pawns
                if p_sq in center_sqs and ((chess.square_file(p_sq) + chess.square_rank(p_sq)) % 2 == 0) == b_is_dark
            )
            attacks = len(board.attacks(b_sq))
            sq_name = chess.square_name(b_sq)
            if attacks >= 7:
                evals.append(f"{sq_name} 비숍의 강력한 대각선 통제력과 높은 활동성(Active Bishop)")
            elif same_color_center_pawns >= 2:
                evals.append(f"{sq_name} 비숍이 아군 중앙 폰에 막힌 나쁜 비숍(Bad Bishop)")

        return evals[:2]

    @classmethod
    def _analyze_king_safety(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        color: chess.Color,
    ) -> Tuple[int, bool]:
        king_sq = after_board.king(color)
        if king_sq is None:
            return 0, True

        opp_color = not color
        king_zone = ChessRulesHelper.get_king_zone(king_sq)

        threats_before = sum(len(before_board.attackers(opp_color, sq)) for sq in king_zone)
        threats_after = sum(len(after_board.attackers(opp_color, sq)) for sq in king_zone)
        safety_delta = threats_before - threats_after

        # Pawn Shield Analysis:
        # Pushing a single pawn for luft (e.g. h3/h6) or fianchetto (g3/g6) is standard & safe.
        # Shield is considered compromised only if:
        # 1) King uncastled in center past move 10, or
        # 2) 2+ shield pawns are missing, or
        # 3) An open file adjacent to king with opponent heavy pieces, or
        # 4) Severe attacker pressure (safety_delta <= -2).
        shield_intact = True
        rank = chess.square_rank(king_sq)
        file_idx = chess.square_file(king_sq)

        # Castled King zone (b/c files for queenside, g/h files for kingside)
        if file_idx in (1, 2, 6, 7):
            shield_rank = rank + 1 if color == chess.WHITE else rank - 1
            shield_files = (file_idx - 1, file_idx, file_idx + 1)
            
            missing_pawns = 0
            for f in shield_files:
                if 0 <= f <= 7:
                    # Check if pawn exists on shield rank or 1 step ahead (luft)
                    p_base = after_board.piece_at(chess.square(f, shield_rank)) if 0 <= shield_rank <= 7 else None
                    advanced_rank = shield_rank + 1 if color == chess.WHITE else shield_rank - 1
                    p_adv = after_board.piece_at(chess.square(f, advanced_rank)) if 0 <= advanced_rank <= 7 else None

                    has_friendly_pawn = (p_base and p_base.piece_type == chess.PAWN and p_base.color == color) or \
                                        (p_adv and p_adv.piece_type == chess.PAWN and p_adv.color == color)
                    if not has_friendly_pawn:
                        missing_pawns += 1

            if missing_pawns >= 2 or safety_delta <= -2:
                shield_intact = False
        elif after_board.fullmove_number > 10:
            # Uncastled King in center
            shield_intact = False

        return safety_delta, shield_intact

    @classmethod
    def _analyze_detailed_king_safety(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        color: chess.Color,
        played_move: chess.Move,
    ) -> List[str]:
        details: List[str] = []
        opp_color = not color

        my_king = after_board.king(color)
        opp_king = after_board.king(opp_color)

        # 1. Opponent King Pawn Shield damage (e.g. Bxh6+, Bxg7, etc.)
        if opp_king is not None:
            opp_k_sq_name = chess.square_name(opp_king)
            opp_rank = chess.square_rank(opp_king)
            opp_file = chess.square_file(opp_king)

            # Check if this move captured a shield pawn in front of opponent king
            if before_board.is_capture(played_move):
                to_sq = played_move.to_square
                captured = before_board.piece_at(to_sq)
                if captured and captured.piece_type == chess.PAWN:
                    if abs(chess.square_file(to_sq) - opp_file) <= 1 and abs(chess.square_rank(to_sq) - opp_rank) <= 2:
                        details.append(f"상대 킹({opp_k_sq_name})의 폰 실드(Pawn Shield)가 해체되어 킹사이드 방어선이 노출됨")

            # Check open attacking vectors focusing on opponent King zone
            king_zone = ChessRulesHelper.get_king_zone(opp_king)
            opp_attackers = sum(len(after_board.attackers(color, sq)) for sq in king_zone)
            if opp_attackers >= 4:
                details.append(f"아군 기물들이 상대 킹({opp_k_sq_name}) 주변 거점을 강력하게 집중 조준 중")

        # 2. Friendly King Vulnerabilities / Air (Luft)
        if my_king is not None:
            my_k_sq_name = chess.square_name(my_king)
            my_rank = chess.square_rank(my_king)
            my_file = chess.square_file(my_king)
            back_rank = 0 if color == chess.WHITE else 7

            # Back-rank vulnerability check
            if my_rank == back_rank and after_board.fullmove_number >= 15:
                front_rank = back_rank + 1 if color == chess.WHITE else back_rank - 1
                front_sqs = [chess.square(f, front_rank) for f in (my_file - 1, my_file, my_file + 1) if 0 <= f <= 7]
                friendly_pawns_in_front = sum(1 for sq in front_sqs if after_board.piece_at(sq) == chess.Piece(chess.PAWN, color))
                if friendly_pawns_in_front >= 3:
                    enemy_heavy = any(p.piece_type in (chess.ROOK, chess.QUEEN) and p.color == opp_color for p in after_board.piece_map().values())
                    if enemy_heavy:
                        details.append(f"킹({my_k_sq_name})의 탈출로(Luft)가 없어 백랭크(Back-rank) 기습에 유의 필요")

        return details[:2]

    @classmethod
    def _detect_rook_lift(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        color: chess.Color,
        piece: Optional[chess.Piece],
    ) -> Tuple[bool, Optional[str]]:
        if not piece or piece.piece_type != chess.ROOK:
            return False, None

        from_sq = move.from_square
        to_sq = move.to_square
        from_rank = chess.square_rank(from_sq)
        to_rank = chess.square_rank(to_sq)
        from_file = chess.square_file(from_sq)
        to_file = chess.square_file(to_sq)

        # White: Rank 0/1 -> Rank 2/3 (e.g. e1 -> e3, a1 -> a3, d1 -> d3)
        # Black: Rank 7/6 -> Rank 5/4 (e.g. e8 -> e6, a8 -> a6, d8 -> d6)
        is_lift_advance = (
            (color == chess.WHITE and from_rank in (0, 1) and to_rank in (2, 3) and from_file == to_file) or
            (color == chess.BLACK and from_rank in (7, 6) and to_rank in (5, 4) and from_file == to_file)
        )

        if is_lift_advance:
            # Check if rook has horizontal mobility to swing towards kingside/flank
            attacks = after_board.attacks(to_sq)
            has_horizontal_swing = any(chess.square_rank(sq) == to_rank and abs(chess.square_file(sq) - to_file) >= 1 for sq in attacks)
            if has_horizontal_swing:
                rank_num = to_rank + 1
                return True, f"킹사이드 직접 공격 전개를 위한 {rank_num}열 룩 리프트(Rook Lift)"

        return False, None

    @classmethod
    def _analyze_development(
        cls,
        before_board: chess.Board,
        move: chess.Move,
        moved_piece: Optional[chess.Piece],
    ) -> Tuple[bool, bool]:
        if not moved_piece:
            return False, False

        if before_board.fullmove_number > 10:
            return False, False

        from_sq = move.from_square
        from_rank = chess.square_rank(from_sq)
        player_color = before_board.turn
        back_rank = 0 if player_color == chess.WHITE else 7
        is_attacked_before = before_board.is_attacked_by(not player_color, from_sq)

        tempo_dev = (
            moved_piece.piece_type in (chess.KNIGHT, chess.BISHOP)
            and from_rank == back_rank
        )

        repeated_move = (
            moved_piece.piece_type in (chess.KNIGHT, chess.BISHOP)
            and from_rank != back_rank
            and not before_board.is_capture(move)
        )

        return tempo_dev, repeated_move

    @classmethod
    def _analyze_move_intents(
        cls,
        before_board: chess.Board,
        after_board: chess.Board,
        move: chess.Move,
        player_color: chess.Color,
        moved_piece: Optional[chess.Piece],
    ) -> Tuple[List[str], List[str], List[str], List[str]]:
        prophylaxis_notes: List[str] = []
        maneuver_notes: List[str] = []
        defended_notes: List[str] = []
        attacked_notes: List[str] = []

        if not moved_piece:
            return prophylaxis_notes, maneuver_notes, defended_notes, attacked_notes

        opp_color = not player_color
        from_sq = move.from_square
        to_sq = move.to_square
        to_name = chess.square_name(to_sq)
        from_name = chess.square_name(from_sq)
        piece_type = moved_piece.piece_type

        # 1. Defended / Overprotected Friendly Pieces
        attacks_after = after_board.attacks(to_sq)
        for sq in attacks_after:
            p = after_board.piece_at(sq)
            if p and p.color == player_color and sq != to_sq:
                was_defended = from_sq in before_board.attackers(player_color, sq)
                if not was_defended:
                    opp_attackers = after_board.attackers(opp_color, sq)
                    p_sym = p.symbol().upper()
                    if opp_attackers:
                        defended_notes.append(f"{p_sym}({chess.square_name(sq)}) 폰/기물에 대한 직접적 수비 보강")
                    elif sq in (chess.E4, chess.E5, chess.D4, chess.D5):
                        defended_notes.append(f"중앙 {p_sym}({chess.square_name(sq)}) 거점에 대한 견고한 방어선 지원(Overprotection)")

        # 2. Prophylaxis & Escape square creation
        if piece_type == chess.PAWN:
            if to_name == 'a6' and player_color == chess.BLACK:
                prophylaxis_notes.append("백의 b4 확장 및 Nb5/Bb5 침투를 차단하고, c5 비숍의 a7 퇴로 확보")
            elif to_name == 'a3' and player_color == chess.WHITE:
                prophylaxis_notes.append("흑의 b5 확장 및 Nb4/Bb4 침투를 차단하고, c4 비숍의 a2 퇴로 확보")
            elif to_name == 'h6' and player_color == chess.BLACK:
                prophylaxis_notes.append("백의 Bg5 핀 및 Ng5 침투를 사전 차단하며 킹의 숨구멍(Luft) 확보")
            elif to_name == 'h3' and player_color == chess.WHITE:
                prophylaxis_notes.append("흑의 Bg4 핀 및 Ng4 침투를 사전 차단하며 킹의 숨구멍(Luft) 확보")
            elif to_name in ('c3', 'c6'):
                prophylaxis_notes.append("중앙 폰(d4/d5) 전진을 지지하는 폰 베이스 구축")
            elif to_name in ('d3', 'd6', 'e3', 'e6'):
                prophylaxis_notes.append("중앙 폰을 수비하고 비숍의 전개 사선 개방")
            elif to_name in ('f4', 'f5'):
                opp_k_sq = before_board.king(opp_color)
                opp_k_f = chess.square_file(opp_k_sq) if opp_k_sq is not None else 0
                if opp_k_f in (5, 6, 7):
                    prophylaxis_notes.append("캐슬링된 상대 킹 앞을 압박하는 킹사이드 폰 스톰 전진 및 비숍 활동 사선 확보")
                else:
                    prophylaxis_notes.append(f"{to_name} 폰 전진으로 킹사이드 공간 확보 및 비숍 사선 개방")
            elif to_name in ('e4', 'e5', 'd4', 'd5'):
                prophylaxis_notes.append(f"중앙 {to_name} 공간을 점유하고 주요 기물들의 활동 사선 개방")

        # 3. Piece Maneuvers & Target Outposts
        if piece_type == chess.KNIGHT:
            if to_name in ('f1', 'd2', 'e2', 'd7', 'e7'):
                maneuver_notes.append(f"{to_name}을 거쳐 더 강력한 거점으로 이동하기 위한 나이트 재기동(Knight Rerouting)")
            elif to_name in ('f5', 'f4'):
                maneuver_notes.append(f"상대 킹사이드 핵심 공격 초소인 {to_name} 거점(Outpost) 진입 및 전방위 압박")
            elif to_name in ('h4', 'h5'):
                maneuver_notes.append(f"킹사이드 공격 거점(f5/f4) 투입을 위한 전진 도약대 마련")
            elif to_name in ('g3', 'g6'):
                maneuver_notes.append(f"킹사이드 측면 화력 지원 및 {to_name} 거점 침투 발판 마련")
            elif to_name in ('e4', 'd5', 'c5', 'e5', 'd4', 'c4'):
                maneuver_notes.append(f"중앙 {to_name} 요충지로 나이트 전진 배치")
        elif piece_type == chess.ROOK:
            if to_name in ('e1', 'e8'):
                maneuver_notes.append(f"e-파일에 룩을 배치하여 중앙 통제력 확보 및 중앙 폰 지원")
            elif to_name in ('d1', 'd8'):
                maneuver_notes.append(f"d-파일에 룩을 배치하여 중앙 사선 장악 및 잠재적 개방 대비")
        elif piece_type == chess.BISHOP:
            if to_name in ('a7', 'a2', 'b3', 'b6', 'c2', 'c7'):
                maneuver_notes.append(f"비숍을 안전한 {to_name} 칸으로 후퇴/재배치하여 핵심 대각선 사정거리 유지")
            elif to_name in ('c4', 'c5'):
                maneuver_notes.append("상대 진영을 조준하는 강력한 대각선 사선 장악")
            elif to_name in ('e6', 'e3', 'd5', 'd4'):
                # Check if facing enemy bishop on the same diagonal
                has_opp_bishop = any(
                    after_board.piece_at(s) and after_board.piece_at(s).piece_type == chess.BISHOP and after_board.piece_at(s).color == opp_color
                    for s in attacks_after
                )
                if has_opp_bishop:
                    maneuver_notes.append("상대 비숍과 대각선에서 맞서며(Challenge) 중앙 사선 지배력 경합")
                else:
                    maneuver_notes.append(f"{to_name} 대각선에 비숍을 배치하여 중앙 통제력 경합")
        elif piece_type == chess.QUEEN:
            if to_name in ('d7', 'd2', 'e7', 'e2', 'c7', 'c2', 'f6', 'f3'):
                maneuver_notes.append(f"퀸을 {to_name}으로 전개하여 룩 간의 연결을 완성하고 중앙/측면 지원")

        # 4. Attacked Enemy Targets (Strict Real Threats Only)
        attacker_val = ChessRulesHelper.get_piece_value(moved_piece)
        for sq in attacks_after:
            opp_p = after_board.piece_at(sq)
            if opp_p and opp_p.color == opp_color:
                p_val = ChessRulesHelper.get_piece_value(opp_p)
                p_sym = opp_p.symbol().upper()
                opp_defenders = after_board.attackers(opp_color, sq)
                is_undefended = (len(opp_defenders) == 0)

                # Real threat: Only if target is truly undefended, or attacker has strictly lower value
                if is_undefended:
                    attacked_notes.append(f"무방비 상대 {p_sym}({chess.square_name(sq)}) 압박")
                elif p_val > attacker_val:
                    attacked_notes.append(f"상대 주요 기물 {p_sym}({chess.square_name(sq)}) 직접 위협")

        return (
            prophylaxis_notes[:2],
            maneuver_notes[:2],
            defended_notes[:2],
            attacked_notes[:2],
        )

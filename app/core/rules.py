import chess
from typing import Optional, Set, List, Tuple, Dict

PIECE_VALUES: Dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}

CENTER_SQUARES: Set[chess.Square] = {
    chess.D4, chess.D5, chess.E4, chess.E5
}

EXTENDED_CENTER_SQUARES: Set[chess.Square] = {
    chess.C3, chess.C4, chess.C5, chess.C6,
    chess.D3, chess.D4, chess.D5, chess.D6,
    chess.E3, chess.E4, chess.E5, chess.E6,
    chess.F3, chess.F4, chess.F5, chess.F6,
}


class ChessRulesHelper:
    @staticmethod
    def create_board(fen: str) -> chess.Board:
        """Create and validate a chess.Board from FEN."""
        return chess.Board(fen)

    @staticmethod
    def parse_move(board: chess.Board, move_san_or_uci: str) -> Optional[chess.Move]:
        """Attempt to parse a move either by SAN or UCI, tolerating trailing annotations like ! and ?"""
        cleaned = move_san_or_uci.strip().rstrip("?!")
        try:
            return board.parse_san(cleaned)
        except Exception:
            pass
        try:
            return board.parse_uci(cleaned)
        except Exception:
            pass
        return None

    @staticmethod
    def san_to_uci(board: chess.Board, move_san: str) -> Optional[str]:
        move = ChessRulesHelper.parse_move(board, move_san)
        return move.uci() if move else None

    @staticmethod
    def uci_to_san(board: chess.Board, move_uci: str) -> Optional[str]:
        move = ChessRulesHelper.parse_move(board, move_uci)
        return board.san(move) if move else None

    PIECE_KOREAN_NAMES: Dict[chess.PieceType, str] = {
        chess.PAWN: "폰",
        chess.KNIGHT: "나이트",
        chess.BISHOP: "비숍",
        chess.ROOK: "룩",
        chess.QUEEN: "퀸",
        chess.KING: "킹",
    }

    @staticmethod
    def get_piece_korean_name(piece: Optional[chess.Piece]) -> str:
        if piece is None:
            return "기물"
        return ChessRulesHelper.PIECE_KOREAN_NAMES.get(piece.piece_type, "기물")

    @staticmethod
    def get_piece_value(piece: Optional[chess.Piece]) -> int:
        if piece is None:
            return 0
        return PIECE_VALUES.get(piece.piece_type, 0)

    @staticmethod
    def get_attackers(board: chess.Board, color: chess.Color, square: chess.Square) -> Set[chess.Square]:
        """Returns set of attacker squares of given color attacking square."""
        return set(board.attackers(color, square))

    @staticmethod
    def get_defenders(board: chess.Board, color: chess.Color, square: chess.Square) -> Set[chess.Square]:
        """Returns set of friendly pieces defending a square containing a friendly piece."""
        # To find defenders in python-chess, we look at attackers of friendly color on that square
        return set(board.attackers(color, square))

    @staticmethod
    def get_controlled_squares(board: chess.Board, color: chess.Color) -> Set[chess.Square]:
        """Returns all squares attacked/controlled by the specified color."""
        controlled: Set[chess.Square] = set()
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                controlled.update(board.attacks(square))
        return controlled

    @staticmethod
    def get_mobility(board: chess.Board, color: chess.Color) -> int:
        """Returns legal move count for the specified color (board's turn must match or be simulated)."""
        temp_board = board.copy(stack=False)
        temp_board.turn = color
        return temp_board.legal_moves.count()

    @staticmethod
    def get_king_zone(king_square: chess.Square) -> Set[chess.Square]:
        """Returns immediate surrounding squares of a King."""
        zone: Set[chess.Square] = set()
        file_idx = chess.square_file(king_square)
        rank_idx = chess.square_rank(king_square)

        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                f, r = file_idx + df, rank_idx + dr
                if 0 <= f <= 7 and 0 <= r <= 7:
                    zone.add(chess.square(f, r))
        return zone

    @staticmethod
    def pv_uci_to_san(initial_board: chess.Board, pv_uci_list: List[str]) -> List[str]:
        """Convert a sequence of UCI moves to SAN strings on a cloned board."""
        board = initial_board.copy(stack=False)
        san_list: List[str] = []
        for uci_str in pv_uci_list:
            try:
                move = board.parse_uci(uci_str)
                san_list.append(board.san(move))
                board.push(move)
            except Exception:
                break
        return san_list

    @staticmethod
    def format_pv_line(initial_board: chess.Board, pv_uci_list: List[str]) -> str:
        """Formats a UCI sequence into full notation with move numbers: e.g. '1. e4 e5 2. Nf3 Nc6'."""
        board = initial_board.copy(stack=False)
        tokens: List[str] = []
        for i, uci_str in enumerate(pv_uci_list):
            try:
                move = board.parse_uci(uci_str)
                san = board.san(move)
                num = board.fullmove_number
                if board.turn == chess.WHITE:
                    tokens.append(f"{num}. {san}")
                else:
                    if i == 0:
                        tokens.append(f"{num}... {san}")
                    else:
                        tokens.append(f"{san}")
                board.push(move)
            except Exception:
                break
        return " ".join(tokens)

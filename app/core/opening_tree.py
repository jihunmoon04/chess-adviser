"""Trie-based Hierarchical Chess Opening Matcher & Out-of-Book Transition Detector.
Integrates 3,810 official Lichess/ECO openings with curated strategic master plans.
"""
import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from app.core.openings_data import OPENING_DATABASE


@dataclass
class OpeningMatch:
    eco: str
    name: str
    name_ko: str
    defining_move: Optional[str]
    purpose: str
    white_plan: str
    black_plan: str
    key_ideas: str
    is_book: bool
    is_out_of_book_step: bool = False
    previous_opening_name: Optional[str] = None


class TrieNode:
    def __init__(self):
        self.children: Dict[str, TrieNode] = {}
        self.opening: Optional[Dict[str, Any]] = None


TERM_MAP = {
    "Sicilian Defense": "시실리안 디펜스",
    "French Defense": "프렌치 디펜스",
    "Caro-Kann Defense": "카로-칸 디펜스",
    "King's Indian Defense": "킹스 인디언 디펜스",
    "King's Indian Attack": "킹스 인디언 어택",
    "Nimzo-Indian Defense": "님조-인디언 디펜스",
    "Queen's Indian Defense": "퀸스 인디언 디펜스",
    "Bogo-Indian Defense": "보고-인디언 디펜스",
    "Grünfeld Defense": "그륀펠트 디펜스",
    "Grunfeld Defense": "그륀펠트 디펜스",
    "Queen's Gambit Declined": "퀸즈 갬빗 거절",
    "Queen's Gambit Accepted": "퀸즈 갬빗 수락",
    "Queen's Gambit": "퀸즈 갬빗",
    "King's Gambit Accepted": "킹스 갬빗 수락",
    "King's Gambit Declined": "킹스 갬빗 거절",
    "King's Gambit": "킹스 갬빗",
    "Ruy Lopez": "루이 로페즈",
    "Italian Game": "이탈리안 게임",
    "Two Knights Defense": "투 나이츠 디펜스",
    "Four Knights Game": "포 나이츠 게임",
    "Scotch Game": "스카치 게임",
    "Vienna Game": "비엔나 게임",
    "Scandinavian Defense": "스칸디나비안 디펜스",
    "English Opening": "잉글리시 오프닝",
    "Réti Opening": "레티 오프닝",
    "Reti Opening": "레티 오프닝",
    "Dutch Defense": "더치 디펜스",
    "Slav Defense": "슬라브 디펜스",
    "Semi-Slav Defense": "세미-슬라브 디펜스",
    "Catalan Opening": "카탈란 오프닝",
    "Benoni Defense": "베노니 디펜스",
    "Benko Gambit": "벵코 갬빗",
    "Alekhine Defense": "알레킨 디펜스",
    "Pirc Defense": "피르츠 디펜스",
    "Modern Defense": "모던 디펜스",
    "London System": "런던 시스템",
    "Trompowsky Attack": "트롬포우스키 어택",
    "Budapest Gambit": "부다페스트 갬빗",
    "Bird Opening": "버드 오프닝",
    "Nimzowitsch-Larsen Attack": "님조-라르센 어택",
    "King's Pawn Game": "킹스 폰 게임",
    "Queen's Pawn Game": "퀸스 폰 게임",
    "Bishop's Opening": "비숍스 오프닝",
    "Evans Gambit": "에반스 갬빗",
    "Giuoco Piano": "지우오코 피아노",
    "Giuoco Pianissimo": "지우오코 피아니시모",
    "Fried Liver Attack": "프라이드 리버 어택",
    "Najdorf Variation": "나이돌프 바리에이션",
    "Dragon Variation": "드래곤 바리에이션",
    "Scheveningen Variation": "셰베닝겐 바리에이션",
    "Sveshnikov Variation": "스베시니코프 바리에이션",
    "Classical Variation": "클래시컬 바리에이션",
    "Advance Variation": "어드밴스 바리에이션",
    "Exchange Variation": "익스체인지 바리에이션",
    "Winawer Variation": "위나워 바리에이션",
    "Tarrasch Variation": "타라시 바리에이션",
    "Berlin Defense": "베를린 디펜스",
    "Morphy Defense": "모피 디펜스",
    "Marshall Attack": "마샬 어택",
    "Open Sicilian": "오픈 시실리안",
    "Closed Sicilian": "클로즈드 시실리안",
    "Alapin Variation": "알라핀 바리에이션",
    "Petrov's Defense": "페트로프 디펜스",
    "Russian Game": "러시안 게임",
    "Philidor Defense": "필리도어 디펜스",
    "Center Game": "센터 게임",
    "Danish Gambit": "대니쉬 갬빗",
    "Blackmar-Diemer Gambit": "블랙마-디머 갬빗",
    "Colle System": "콜 시스템",
    "Torre Attack": "토레 어택",
    "Richter-Veresov Attack": "리히터-베레소프 어택",
    "Albin Countergambit": "알빈 카운터갬빗",
    "Chigorin Defense": "치고린 디펜스",
    "Smith-Morra Gambit": "스미스-모라 갬빗",
}

SUB_TERMS = [
    ("Variation", "바리에이션"),
    ("Gambit", "갬빗"),
    ("Attack", "어택"),
    ("Defense", "디펜스"),
    ("Opening", "오프닝"),
    ("Game", "게임"),
    ("System", "시스템"),
    ("Accepted", "수락"),
    ("Declined", "거절"),
    ("Countergambit", "카운터갬빗"),
    ("Exchange", "익스체인지"),
    ("Advance", "어드밴스"),
    ("Classical", "클래시컬"),
    ("Modern", "모던"),
    ("Accelerated", "액셀러레이티드"),
    ("Main Line", "메인 라인"),
    ("Side Line", "사이드라인"),
    ("Line", "라인"),
    ("Endgame", "엔드게임"),
    ("Positional", "포지셔널"),
]


def translate_opening_name(name: str) -> str:
    res = name
    for k, v in TERM_MAP.items():
        if k in res:
            res = res.replace(k, v)
    for k, v in SUB_TERMS:
        if k in res:
            res = res.replace(k, v)
    return res


class OpeningTree:
    _root: Optional[TrieNode] = None

    @classmethod
    def _get_root(cls) -> TrieNode:
        if cls._root is not None:
            return cls._root

        cls._root = TrieNode()

        # 1. Load full Lichess dataset (3,810 openings) if available
        data_path = Path(__file__).resolve().parent.parent / "data" / "lichess_openings.json"
        if data_path.exists():
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    lichess_entries = json.load(f)

                for item in lichess_entries:
                    moves = item["moves"]
                    curr = cls._root
                    for m in moves:
                        if m not in curr.children:
                            curr.children[m] = TrieNode()
                        curr = curr.children[m]

                    ko_name = translate_opening_name(item["name"])
                    curr.opening = {
                        "eco": item["eco"],
                        "name": item["name"],
                        "name_ko": ko_name,
                        "defining_move": item.get("defining_move") or (moves[-1] if moves else None),
                        "purpose": f"{ko_name} 정석 라인입니다.",
                        "white_plan": "",
                        "black_plan": "",
                        "key_ideas": "",
                        "is_curated": False,
                    }
            except Exception as e:
                pass

        # 2. Overlay Curated Master Openings (highest strategic priority)
        for entry in OPENING_DATABASE:
            moves = entry["moves"]
            curr = cls._root
            for m in moves:
                if m not in curr.children:
                    curr.children[m] = TrieNode()
                curr = curr.children[m]

            curr.opening = {
                "eco": entry["eco"],
                "name": entry["name"],
                "name_ko": entry["name_ko"],
                "defining_move": entry.get("defining_move"),
                "purpose": entry["purpose"],
                "white_plan": entry["white_plan"],
                "black_plan": entry["black_plan"],
                "key_ideas": entry.get("key_ideas", ""),
                "is_curated": True,
            }

        # 3. Propagate strategic plans down the Trie so all 3,810 sublines inherit parent plans
        def _propagate(node: TrieNode, last_ancestor_opening: Optional[Dict[str, Any]]):
            curr_opening = node.opening
            effective_ancestor = last_ancestor_opening

            if curr_opening:
                if not curr_opening.get("is_curated") and last_ancestor_opening:
                    if not curr_opening.get("white_plan"):
                        curr_opening["white_plan"] = last_ancestor_opening.get("white_plan", "")
                    if not curr_opening.get("black_plan"):
                        curr_opening["black_plan"] = last_ancestor_opening.get("black_plan", "")
                    if not curr_opening.get("key_ideas"):
                        curr_opening["key_ideas"] = last_ancestor_opening.get("key_ideas", "")
                    
                    parent_purpose = last_ancestor_opening.get("purpose", "")
                    if "라인으로, " in parent_purpose:
                        parent_purpose = parent_purpose.split("라인으로, ")[-1]
                    curr_opening["purpose"] = f"{curr_opening['name_ko']} 라인으로, {parent_purpose}"
                effective_ancestor = curr_opening

            for child in node.children.values():
                _propagate(child, effective_ancestor)

        _propagate(cls._root, None)
        return cls._root

    @classmethod
    def match_history(cls, moves_san: List[str]) -> Optional[OpeningMatch]:
        """Matches a list of SAN moves against the Opening Trie.
        Returns:
            OpeningMatch with deepest variation details, is_book status, and out_of_book transition info.
        """
        if not moves_san:
            return None

        root = cls._get_root()
        curr = root
        deepest_opening: Optional[Dict[str, Any]] = None
        deepest_depth = 0
        still_in_book = True

        for i, move in enumerate(moves_san):
            clean_m = move.rstrip("?!+#")
            matched_child = curr.children.get(move) or curr.children.get(clean_m)

            if matched_child:
                curr = matched_child
                if curr.opening:
                    deepest_opening = curr.opening
                    deepest_depth = i + 1
            else:
                still_in_book = False
                break

        if deepest_opening is None:
            return None

        # Check if this exact move was the first step out of book
        is_out_of_book_step = (not still_in_book) and (len(moves_san) == deepest_depth + 1)

        return OpeningMatch(
            eco=deepest_opening["eco"],
            name=deepest_opening["name"],
            name_ko=deepest_opening["name_ko"],
            defining_move=deepest_opening.get("defining_move"),
            purpose=deepest_opening["purpose"],
            white_plan=deepest_opening.get("white_plan", ""),
            black_plan=deepest_opening.get("black_plan", ""),
            key_ideas=deepest_opening.get("key_ideas", ""),
            is_book=still_in_book,
            is_out_of_book_step=is_out_of_book_step,
            previous_opening_name=deepest_opening["name_ko"] if is_out_of_book_step else None,
        )

    @classmethod
    def get_candidate_continuation_insight(cls, current_history: List[str], next_san: str) -> Optional[str]:
        """Checks if playing next_san transitions into a recognized opening line."""
        trial_history = current_history + [next_san]
        match = cls.match_history(trial_history)
        if match and match.is_book:
            return f"📖 {match.name_ko} ({match.eco}) 정석 라인 지속"
        return None

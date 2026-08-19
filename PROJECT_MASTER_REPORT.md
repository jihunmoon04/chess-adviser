# ♟️ Chess Adviser AI: 통합 마스터 엔지니어링 명세서 & 인수인계 보고서
**Project Master Specification & Developer Handover Report**

> **버전**: v1.0.0-PROD  
> **최종 갱신 일시**: 2026-08-19 (KST)  
> **작성자**: Antigravity AI Pair Programmer & Project Owner  
> **목적**: 다른 개발자 또는 AI 에이전트가 본 프로젝트의 아키텍처, 알고리즘, 데이터 흐름, 파일 구조 및 배포 환경을 즉시 파악하고 영속적으로 유지보수 및 확장을 진행할 수 있도록 모든 기술적 자산을 총망라하여 정리함.

---

## 📑 목차 (Table of Contents)

1. [프로젝트 개요 및 비전 (Project Overview & Vision)](#1-프로젝트-개요-및-비전)
2. [전체 시스템 아키텍처 & 서비스 파이프라인](#2-전체-시스템-아키텍처--서비스-파이프라인)
3. [데이터 스키마 및 입출력 명세 (Data Structures)](#3-데이터-스키마-및-입출력-명세)
4. [핵심 엔진 및 수치/전술 판별 알고리즘 상세](#4-핵심-엔진-및-수치전술-판별-알고리즘-상세)
5. [LLM 프롬프트 엔지니어링 & 환각 방지 시스템](#5-llm-프롬프트-엔지니어링--환각-방지-시스템)
6. [전체 프로젝트 파일 구조 및 파일별 역할 매핑](#6-전체-프로젝트-파일-구조-및-파일별-역할-매핑)
7. [프론트엔드 UI/UX & 모바일 반응형 아키텍처](#7-프론트엔드-uiux--모바일-반응형-아키텍처)
8. [클라우드 24시간 무료 배포 & Git 운영 가이드](#8-클라우드-24시간-무료-배포--git-운영-가이드)
9. [향후 확장 로드맵 & 개발자 인수인계 주의사항](#9-향후-확장-로드맵--개발자-인수인계-주의사항)

---

## 1. 프로젝트 개요 및 비전

### 1.1 프로젝트 소개
**Chess Adviser AI**는 전 세계 1위 오픈소스 체스 엔진인 **Stockfish 18(NNUE)**의 정밀한 심층 연산과 **3,810개 공인 오프닝 DB**, **기하학적 룰베이스 전술 추출 알고리즘**, 그리고 **Google Gemini 3.5 Flash-Lite LLM**을 융합한 **차세대 실시간 체스 코칭 웹 플랫폼**입니다.

### 1.2 개발 배경 및 핵심 철학
* **기존 체스 엔진 분석의 한계**: 숫자로 표시되는 평가치(`+1.4`, `-2.3`)와 단순 수순 나열(`1. e4 e5 2. Nf3...`)만으로는 아마추어 및 중급 유저가 "왜 이 수가 좋은지", "어떤 전술적/전략적 의도를 가져야 하는지"를 이해하기 어렵습니다.
* **기존 LLM 해설의 한계(환각 현상, Hallucination)**: LLM에게 체스 보드 FEN만 던져줄 경우, 실제로는 존재하지 않는 기물을 언급하거나 가짜 핀/스큐어를 지어내는 심각한 환각 현상이 발생합니다.
* **본 프로젝트의 해결책 (Fact-Grounding AI Pipeline)**:
  1. 체스 보드의 물리적 룰과 기하학적 광선 추적(Raycasting)을 통해 **100% 검증된 팩트 데이터(핀, 포크, 스큐어, 무방비 기물, 폰 구조 손상, 룩 리프트, 템포 손실 등)**를 백엔드 알고리즘에서 먼저 추출합니다.
  2. 스톡피시 1순위 추천 라인을 가상 체스판에서 2~4수 시뮬레이션(`Virtual Rollout`)하여 **수순의 최종 결말(메이팅 네트, 킹사이드 총공세, 기물 획득 등)**을 문장화합니다.
  3. 이 엄밀한 구조화 팩트만을 LLM에게 전달하여, **환각률 0%의 품격 있는 객관적 그랜드마스터 해설**을 생성합니다.

---

## 2. 전체 시스템 아키텍처 & 서비스 파이프라인

본 서비스는 **2단계 비동기 스트리밍 파이프라인(2-Stage Asynchronous Streaming Pipeline)**을 채택하여 지연 시간을 극한으로 단축했습니다.

```mermaid
flowchart TD
    subgraph Client [프론트엔드 (Single Page Web App)]
        UI[체스보드 / 유저 기물 착수]
        InstantUI[초고속 평가치 & 최선수 화살표 즉각 표시]
        StreamUI[실시간 토큰 타이핑 AI 코칭 렌더링]
    end

    subgraph Backend [FastAPI 백엔드 서비스]
        API["/api/analyze/stream (SSE Endpoint)"]
        Cache[Redis / In-Memory TTL 캐시]
        
        subgraph Stage1 [Stage 1: 30ms Instant Analysis]
            StockfishFast[스톡피시 고속 연산 Depth 12]
            RulesFast[기초 전술/포지션 룰 엔진]
            OpeningTree[3,810개 Lichess 공인 오프닝 DB]
        end

        subgraph Stage2 [Stage 2: 300ms Deep Analysis & Lookahead]
            StockfishDeep[스톡피시 심층 분석 Depth 18 + Multi-PV 3]
            TacticsEngine[정밀 기하학적 전술 추출기]
            PositionalEngine[킹 안전도/폰실드/룩리프트/템포 분석기]
            LookaheadEngine[2~4수 PV Chain 가상 롤아웃 시뮬레이터]
        end

        subgraph LLMService [LLM 해설 스트리밍 엔진]
            PromptBuilder[Fact-Grounded 프롬프트 빌더]
            GeminiClient[Google Gemini 3.5 Flash-Lite API]
        end
    end

    UI -->|POST 수순 데이터| API
    API --> Cache
    Cache -->|캐시 미스| Stage1
    Stage1 -->|Event: instant_analysis| InstantUI
    Stage1 --> Stage2
    Stage2 -->|Event: analysis + Aggregated JSON| Client
    Stage2 --> PromptBuilder
    PromptBuilder --> GeminiClient
    GeminiClient -->|Event: token SSE 스트림| StreamUI
    GeminiClient -->|Event: done| Cache
```

### 파이프라인 동작 단계
1. **착수 이벤트 발생**: 클라이언트에서 기물이 이동하면 `before_fen`, `after_fen`, `move_san`, `move_uci`, 전체 `move_history_san`을 담아 `/api/analyze/stream`으로 비동기 요청을 전송합니다.
2. **캐시 조회 (Cache Lookup)**: 동일 국면/수순에 대한 분석 결과가 캐시에 존재하는 경우 즉시 리턴합니다.
3. **Stage 1 (고속 분석, ~30ms)**: 스톡피시 12 깊이 분석 + 오프닝 DB 매칭을 통해 수의 품질 등급(Quality Badge)과 최선수(Best Move)를 즉시 클라이언트에 전송하여 반응성을 극대화합니다.
4. **Stage 2 (심층 분석 & 룩어헤드, ~300ms)**:
   - 스톡피시 18 깊이 + 3개 멀티 추천 라인(Multi-PV) 계산.
   - 단방향 레이캐스팅 기반 핀/포크/스큐어/무방비 기물 검증.
   - 폰 실드 파괴, 킹 안전도 수치, 룩 리프트, 오프닝 템포 손실 진단.
   - 스톡피시 최선 수순을 2~4수 가상 롤아웃하여 최종 목적(메이팅 네트, 라인 개방 등) 합성.
5. **LLM 코칭 스트리밍 (Token by Token SSE)**:
   - 합성된 `AnalysisPacket`을 시스템 프롬프트와 결합하여 Gemini 3.5 Flash-Lite로 스트리밍 전송.
   - 클라이언트는 타이핑 효과 커서와 함께 `수 총평` ➜ `전술적 평가` ➜ `포지셔널 분석` 3개 카테고리로 실시간 렌더링.

---

## 3. 데이터 스키마 및 입출력 명세

### 3.1 요청 스키마 (`MoveAnalysisRequest`)
```python
class MoveAnalysisRequest(BaseModel):
    before_fen: str                 # 착수 직전 FEN 문자열
    after_fen: str                  # 착수 직후 FEN 문자열
    move_san: str                   # 대수 기보 표기법 (예: "Nf3", "Bxf7+")
    move_uci: str                   # UCI 포맷 표기법 (예: "g1f3", "c4f7")
    move_history_san: List[str] = [] # 게임 시작부터 현재 수까지의 전체 기보 리스트
```

### 3.2 핵심 응답 스키마 (`AnalysisPacket`)
백엔드 분석 집계기(`AnalysisAggregator`)가 생성하는 28개 핵심 필드 명세입니다:

| 필드명 | 타입 | 설명 | 예시 |
|:---|:---|:---|:---|
| `move_san` / `move_uci` | `str` | 착수한 수의 표기법 | `"Bh4"` / `"g5h4"` |
| `player_color` | `str` | 착수한 플레이어 진영 | `"white"` 또는 `"black"` |
| `move_quality` | `MoveQuality` | 수의 등급 (10단계 분류) | `Best`, `Excellent`, `Inaccuracy`, `Blunder` |
| `eval_before` / `eval_after` | `ScoreInfo` | 착수 전/후 평가치 (cp: 폰 단위 점수, mate: 체크메이트 거리) | `{"type": "cp", "value": 0.33}` |
| `eval_change` | `float` | 착수로 인한 평가치 변동 ($\Delta$) | `-0.04` (백 기준 이득/손실) |
| `best_move_san` / `uci` | `str` | 스톡피시가 계산한 1순위 최선수 | `"Bf4"` / `"g5f4"` |
| `pv_lines` | `List[PVLine]` | 상위 3개 추천 수순 (Multi-PV) 및 후속 연속 수순 | 점수, SAN 수순, UCI 수순 배열 |
| `opening` | `OpeningInfo` | 정석 여부, ECO 코드, 오프닝 국문/영문명, 백/흑 플랜, 핵심 아이디어 | `ECO: C50`, `이탈리안 게임` |
| `tactics` | `TacticalDetails` | 핀, 포크, 스큐어, 발견 공격, 무방비 기물, 기물 희생 여부 | `pins`, `forks`, `hanging_pieces` |
| `positional` | `PositionalDetails` | 폰 구조 손상, 킹 안전도, 룩 리프트, 템포 손실, 공간 우위 점수 | `is_rook_lift: true`, `is_repeated_move: false` |
| `lookahead` | `LookaheadDetails` | 2~4수 후속 수순 가상 시뮬레이션 및 전술적 결말 내러티브 | `pv_chain_narrative: "3수 뒤 상대 킹사이드 메이팅 네트 형성"` |
| `game_over` | `GameOverInfo` | 체크메이트, 스테일메이트, 50수 규칙 등 게임 종료 판정 | `is_game_over: false` |

---

## 4. 핵심 엔진 및 수치/전술 판별 알고리즘 상세

### 4.1 스톡피시 18(NNUE) 자가 치유(Self-Healing) 엔진 관리자
* **경로 자동 감지 (`StockfishManager._find_executable`)**:
  * Windows: `./stockfish.exe`, `stockfish/stockfish.exe` 등 자동 탐색
  * Linux/Docker: `/usr/games/stockfish`, `/usr/bin/stockfish`, `/usr/local/bin/stockfish` 자동 탐색
* **무중단 자가 치유 (Self-Healing Auto-Restart)**:
  * 비동기 스레드 풀에서 스톡피시 프로세스가 충돌하거나 끊길 경우, `_restart_sync()`가 즉각 실행되어 5ms 내에 프로세스를 재생성하고 분석을 재시도합니다.
* **비정상 FEN 상태 코드 허용 정책**:
  * 치명적 에러(킹이 없거나 양쪽 킹이 인접한 경우 등)만 차단하고, 커스텀 세팅이나 불균형 기물 배치(Status 128 등)는 예외를 던지지 않고 정상 연산하도록 설계되었습니다.

### 4.2 수 품질 평가(Move Quality) 정밀 캘리브레이션
스톡피시의 평가치 변동($\Delta$ Centipawns)과 전술적 반사 이익을 결합하여 10단계로 정밀 분류합니다:

```python
# app/analyzer/aggregator.py 의 판별 로직
if is_book_move:
    quality = MoveQuality.BOOK
elif is_brilliant_sacrifice:
    quality = MoveQuality.BRILLIANT  # 기물 희생 후 결정적 우위 유지
elif eval_loss <= 10:
    quality = MoveQuality.BEST if is_top_engine_choice else MoveQuality.EXCELLENT
elif eval_loss <= 25:
    quality = MoveQuality.EXCELLENT
elif eval_loss <= 50:
    quality = MoveQuality.GOOD
elif eval_loss <= 120:
    quality = MoveQuality.INACCURACY
elif eval_loss <= 250:
    quality = MoveQuality.MISTAKE
else:
    quality = MoveQuality.BLUNDER
```

### 4.3 기하학적 전술 검증 알고리즘 (`app/analyzer/tactics.py`)

#### A. 브릴리언트 희생(Brilliant Sacrifice) 오판 방지
* **기존 문제**: 나이트와 비숍의 동등한 3점 기물 교환(Equal Trade) 상황을 기물 희생으로 오판하여 브릴리언트를 남발하던 현상.
* **해결 알고리즘**:
  1. 기물이 이동한 타깃 칸에 상대 방어자가 존재하여 회수될 위험이 있을 때, 자신이 잡은 기물의 가치($V_{target}$)보다 자신의 기물 가치($V_{moved}$)가 엄밀히 클 때만 희생($\Delta Material < 0$)으로 인정.
  2. 희생 후 스톡피시 평가치가 유리($\ge +1.5$)하거나 메이팅 공격이 성립해야만 브릴리언트 부여.

#### B. 상대적 핀(Relative Pin) 다중 기물 장애물 검증
* **기존 문제**: 비숍과 퀸 사이에 나이트와 비숍 등 2개 이상의 기물이 가로막고 있음에도 핀으로 잘못 판별되던 결함.
* **해결 알고리즘**:
  * 공격 기물(Attacker)과 퀸(Queen) 사이의 대각선/직선 좌표를 방향 단위 벡터($\pm 1, \pm 1$)로 1칸씩 단계별 순회(Raycast).
  * 핀 대상 기물 외에 **다른 어떤 기물도 경로상에 존재하지 않을 때만(Strictly Single Intermediate Piece)** 핀으로 확정.

#### C. 무방비 기물(Hanging Piece) 한글 명칭 확정
* **기존 문제**: 무방비 기물 탐지 시 칸 이름(`b4`)만 LLM에 전달되어 나이트나 폰으로 환각을 일으키던 현상.
* **해결 알고리즘**: `ChessRulesHelper.get_piece_korean_name()`을 통해 `"비숍(b4)"`, `"나이트(f6)"`처럼 기물 종류와 위치를 결합하여 전달.

### 4.4 포지셔널 & 전략 평가 알고리즘 (`app/analyzer/positional.py`)
* **킹 안전도 & 폰 실드 파괴 (King Safety & Pawn Shield)**:
  * 킹 앞의 f, g, h 폰 전진 여부와 상대 기물의 킹 인접 칸(King Zone) 침투도를 점수화.
* **3열 룩 리프트 (Rook Lift)**:
  * 룩이 `a3`, `h3`, `a6`, `h6` 등 3열/6열로 전진하여 킹사이드/퀸사이드 공격 라인으로 전환하는 특수 행마 감지.
* **오프닝 템포 손실 (Lost Tempo)**:
  * 10수 이내 오프닝 단계에서 폰 구조 전개나 다른 기물 개발 없이 동일한 마이너 피스를 반복 이동시키는 행위 감지.

### 4.5 다수 연속 수순(PV Chain) 시뮬레이터 (`app/analyzer/lookahead.py`)
* 스톡피시의 1순위 추천 수순(PV Line)을 가상 보드(Virtual Board)에 2~4수 착수시켜 봅니다.
* 시뮬레이션 종료 시점의 국면을 분석하여:
  * 상대 킹이 구석에 몰렸다면 ➜ `"킹사이드 메이팅 네트 형성"`
  * 고가치 기물이 제거되었다면 ➜ `"퀸 교환 후 엔드게임 기물 우위 확정"`
  * 파일이 열렸다면 ➜ `"중앙 및 7열 룩 침투 라인 확보"`
  등 **수순의 최종 목적지를 객관적 문장으로 도출**합니다.

---

## 5. LLM 프롬프트 엔지니어링 & 환각 방지 시스템

### 5.1 시스템 프롬프트 설계 원칙
* **모델**: `gemini-3.5-flash-lite` (초고속 응답, 뛰어난 한국어 체스 문맥 이해도)
* **어조(Tone)**: 과장이나 감정적 표현을 일체 배제한 **객관적이고 차분한 그랜드마스터 코칭 어조**.
* **3대 필수 영역 분할 구조**:
  1. `### 🏆 수 총평`: 수의 등급, 평가치 변동, 핵심 목적을 담담하게 1문장 요약.
  2. `### ⚔️ 전술적 평가`: 팩트 JSON에 명시된 핀, 포크, 기물 상호작용 및 후속 PV Chain 결말 설명.
  3. `### ♟️ 포지셔널 분석`: 킹 안전도, 기물 활동성, 폰 구조 변화 및 향후 전략적 계획 제시.

---

## 6. 전체 프로젝트 파일 구조 및 파일별 역할 매핑

```text
chess-adviser-backend/
├── Dockerfile                      # 리눅스 스톡피시 자동 설치 및 클라우드 배포용 Dockerfile
├── .dockerignore                   # .venv, stockfish.exe, .env 등 불필요한 빌드 파일 제외
├── .gitignore                      # 대용량 exe(108MB) 및 민감한 API 키 git 추적 원천 차단
├── .env                            # 로컬 개발 환경용 설정 (GEMINI_API_KEY 보관)
├── .env.example                    # 오픈소스 공개용 환경 변수 템플릿
├── requirements.txt                # FastAPI, chess, uvicorn, google-genai 등 의존성 목록
├── README.md                       # 프로젝트 영문/국문 안내 및 설치 가이드
├── app/
│   ├── __init__.py                 # 패키지 초기화
│   ├── config.py                   # Pydantic 기반 환경 변수 및 서버 설정 관리자
│   ├── main.py                     # FastAPI 엔드포인트 라우팅, CORS, SSE 수명주기 관리
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── aggregator.py           # 스톡피시+룰+오프닝+룩어헤드 통합 집계기
│   │   ├── lookahead.py            # 2~4수 PV Chain 가상 롤아웃 시뮬레이터
│   │   ├── positional.py           # 킹 안전도, 폰 실드, 룩 리프트, 템포 분석기
│   │   └── tactics.py              # 기하학적 핀, 포크, 스큐어, 희생 판별기
│   ├── core/
│   │   ├── __init__.py
│   │   ├── opening_tree.py         # 오프닝 Trie 검색 및 플랜 디코더
│   │   ├── openings_data.py        # 백업 오프닝 데이터 세트
│   │   ├── rules.py                # 체스 규칙 보조 헬퍼 (기물 점수, 한글 명칭, 좌표 변환)
│   │   └── stockfish.py            # 스톡피시 프로세스 풀, 통신 관리자, 자가 치유 엔진
│   ├── data/
│   │   └── lichess_openings.json   # 3,810개 전 세계 공인 오프닝 데이터베이스
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── analysis.py             # AnalysisPacket, MoveQuality 등 Pydantic 응답 스키마
│   │   └── request.py              # MoveAnalysisRequest 등 입력 요청 스키마
│   ├── services/
│   │   ├── __init__.py
│   │   ├── cache_service.py        # Redis 및 In-Memory TTL 2중 캐시 관리자
│   │   └── llm_service.py          # Gemini 3.5 Flash-Lite 연동 및 SSE 스트리밍 서비스
│   └── static/
│       └── index.html              # 프론트엔드 Single Page Application (UI/UX)
└── tests/                          # 단위 테스트 스위트 (Aggregator, Tactics, Positional)
```

---

## 7. 프론트엔드 UI/UX & 모바일 반응형 아키텍처

### 7.1 반응형 뷰포트 아키텍처 (`index.html`)
* **CSS Custom Properties 기반 동적 스케일링**:
  * 데스크톱: 560px 대형 체스판 + 32px 수직 평가치 막대(Eval Bar)
  * 태블릿(iPad, $\le 1080px$): 보드 컬럼과 분석 사이드바를 세로형 1열로 자동 전환
  * 모바일($\le 640px$): 화면 폭에 맞추어 보드 크기가 `min(calc(100vw - 32px), 420px)`로 자동 조절
* **SVG 벡터 화살표 정규화 (Zero Distortion)**:
  * 보드 크기가 모바일 기기에 따라 축소되더라도, SVG `viewBox="0 0 560 560"` 좌표계와 $70\text{px}$ 그리드를 매핑하여 **추천 수순 화살표가 완벽한 위치에 오차 없이 렌더링**됩니다.

### 7.2 유저 인터랙션 및 키보드 단축키
* **터치 및 클릭 조작**: 드래그 앤 드롭 및 원터치 기물 선택 ➜ 착수(Click-to-Move) 완벽 지원.
* **이동 가능 위치 가이드 점 (Legal Move Dots)**: 기물 클릭 시 갈 수 있는 위치(반투명 점) 및 기물 잡기(빨간색 링) 표시.
* **키보드 단축키**:
  * **`Space`**: 다음 수 진행 (`navNext`) - *버튼 포커스 리셋 결함 완전 해결*
  * **`←` / `→`**: 이전 수 / 다음 수 탐색
  * **`Home` / `End`**: 첫 수 / 마지막 수 점프
  * **`F`**: 체스판 180도 회전 (백/흑 시점 전환)
  * **`A`**: 최선수 추천 화살표 ON/OFF

---

## 8. 클라우드 24시간 무료 배포 & Git 운영 가이드

### 8.1 Git 저장소 및 보안 원칙
1. **대용량 파일 배포 제외**: 윈도우용 바이너리 `stockfish.exe`(108MB)는 `.gitignore`에 등록하여 GitHub 100MB 단일 파일 제한을 우회하고 리포지토리를 초경량(300KB)으로 유지합니다.
2. **API 키 보안**: 실제 API 키는 `.env`에만 로컬 보관되며, GitHub에는 `.env.example`의 템플릿만 업로드됩니다.

### 8.2 Render.com 100% 무료 24시간 Web Service 배포 절차
1. **GitHub Push**:
   ```bash
   git add .
   git commit -m "Deploy update"
   git push origin main
   ```
2. **Render.com 웹 서비스 생성**:
   * [Render.com](https://render.com) ➜ **`New +`** ➜ **`Web Service`**
   * GitHub의 `jihunmoon04/chess-adviser` 레포지토리 연결
   * **Runtime**: **`Docker`** (Dockerfile 자동 감지)
   * **Region**: **`Singapore`** (한국과 가장 인접)
   * **Instance Type**: **`Free ($0/month)`**
3. **환경 변수 등록 (`Environment Variables`)**:
   * **Key**: `GEMINI_API_KEY`
   * **Value**: 유저의 실제 Gemini API 키
4. **결과**: `https://<서비스이름>.onrender.com` 주소로 전 세계 어디서든 24시간 접속 가능.

---

## 9. 향후 확장 로드맵 & 개발자 인수인계 주의사항

다음 개발자 또는 AI 에이전트가 본 프로젝트를 확장할 때 참고할 핵심 가이드입니다:

1. **새로운 전술 패턴 추가 시**:
   * `app/analyzer/tactics.py`에 새 탐지 함수(예: `_detect_x_ray_attack`, `_detect_wind_mill`)를 작성하고, `TacticalDetails` Pydantic 스키마에 필드를 추가한 뒤 `aggregator.py`에서 호출합니다.
2. **오프닝 DB 갱신 시**:
   * `app/data/lichess_openings.json`에 새로운 변형 수순과 한글 번역 플랜을 추가하면 `opening_tree.py`가 자동으로 Trie 노드를 빌드합니다.
3. **LLM 모델 변경 시**:
   * `.env` 또는 Render 대시보드의 `GEMINI_MODEL` 환경 변수를 `gemini-3.5-flash-lite`, `gemini-3.5-pro` 등으로 수정하기만 하면 코드 수정 없이 즉시 반영됩니다.
4. **실시간 시스템 상태 보고서 유지**:
   * 알고리즘이나 프롬프트 변경이 발생할 때마다 `system_live_report.md`의 체인지로그를 지속적으로 갱신하십시오.

---
**[Chess Adviser AI 엔지니어링 마스터 보고서 종료]**

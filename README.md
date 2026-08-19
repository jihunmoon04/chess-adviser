# Chess Adviser Backend (체스 실시간 AI 해설 백엔드 엔진)

체스 게임 중 유저가 기물을 이동할 때마다 **Stockfish 수치 연산(Multi-PV)**과 **python-chess 정적 규칙 델타 분석**을 결합하여 전술적/포지셔널 의미를 역산하고, 정제된 `Analysis JSON`을 기반으로 **LLM(Gemini / OpenAI)이 1~2문장의 실시간 한국어 코칭 해설을 SSE(Server-Sent Events) 스트리밍**하는 백엔드 엔진입니다.

---

## 1. 주요 특징 및 아키텍처

- **환각 방지(Anti-Hallucination) 하이브리드 아키텍처**:
  - 체스판 기물 위치, 합법성, 전술/전략적 사실 관계(기물 방치, 수비 이탈, 전초기지 등)는 백엔드 엔진에서 100% 확정적 연산.
  - LLM은 객관적 사실이 담긴 JSON을 입력받아 **자연스러운 1~2문장 코칭 해설 번역**만 수행.
- **Stockfish UCI 비동기 매니저**:
  - `asyncio.subprocess` 및 `asyncio.Lock`을 통한 프로세스 재사용 및 Multi-PV(기본 3개 라인) 분석.
  - 로컬에 Stockfish 바이너리가 없는 경우에도 자체 휴리스틱 연산으로 원활하게 테스트 가능한 Fallback 탑재.
- **듀얼 LLM 지원**:
  - `Google Gemini` (`gemini-3.6-flash` 등) & `OpenAI` (`gpt-4o-mini` 등) 지원 (`LLM_PROVIDER` 환경변수로 선택).
- **2계층 캐싱**:
  - `before_fen + move_san` 기준 Redis 및 In-Memory TTL 캐시 지원.
- **실시간 SSE 스트리밍**:
  - `POST /api/analyze/stream` 호출 시 초기 Analysis JSON 메타데이터 전송 후 타이핑 효과의 텍스트 토큰 실시간 스트리밍.

---

## 2. 프로젝트 디렉토리 구조

```text
chess-adviser-backend/
├── app/
│   ├── main.py                  # FastAPI 앱, Lifespan, SSE 엔드포인트
│   ├── config.py                # Pydantic BaseSettings 환경설정
│   ├── core/
│   │   ├── stockfish.py         # StockfishManager (UCI 제어, Multi-PV)
│   │   └── rules.py             # python-chess 보드 헬퍼
│   ├── analyzer/
│   │   ├── tactics.py           # Hanging, Undefended, Brilliant Sacrifice 등
│   │   ├── positional.py        # 공간 지배력, 열린 열, 폰 구조, 킹 안전도 Delta
│   │   └── aggregator.py        # 엔진 결과 + 정적 분석 취합 및 Analysis JSON 조립
│   ├── services/
│   │   ├── llm_service.py       # LLM 스트리밍 해설 (Gemini & OpenAI)
│   │   └── cache_service.py     # Redis & In-Memory 캐시
│   └── schemas/
│       ├── request.py           # MoveAnalysisRequest DTO
│       └── analysis.py          # AnalysisPacket, MoveQuality DTO
├── tests/
│   ├── test_tactics.py          # 전술 지표 테스트
│   ├── test_positional.py       # 포지셔널 지표 테스트
│   └── test_aggregator.py       # 패킷 조립 및 품질 판정 테스트
├── requirements.txt
├── .env.example
└── README.md
```

---

## 3. 설치 및 실행 방법

### ① 필수 패키지 설치
```bash
pip install -r requirements.txt
```

### ② 환경변수 설정
`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 필요한 값을 설정합니다:
```bash
cp .env.example .env
```

`.env` 설정 예시:
```env
# LLM 프로바이더 선택 ('gemini' 또는 'openai')
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash

# Stockfish 바이너리 경로 (설치된 경우 지정, 없으면 휴리스틱 fallback)
STOCKFISH_PATH=stockfish
```

### ③ 서버 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. API 명세

### 1) 실시간 SSE 스트리밍 분석 (`POST /api/analyze/stream`)
클라이언트에서 기물을 이동할 때 호출합니다 (1~1.5초 디바운싱 권장).

**Request Body (JSON):**
```json
{
  "before_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "after_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
  "move_san": "e4",
  "move_uci": "e2e4"
}
```

**SSE Events Output:**
1. `event: analysis` : 완전한 전술/포지셔널 및 엔진 평가치 JSON 메타데이터
2. `event: token` : LLM이 생성하는 실시간 한국어 코칭 해설 텍스트 청크
3. `event: done` : 스트리밍 완료 알림 및 전체 완성 텍스트

### 2) 동기식 JSON 분석 (`POST /api/analyze`)
SSE 스트리밍 대신 한 번에 전체 JSON과 해설 결과를 수신할 때 사용합니다.

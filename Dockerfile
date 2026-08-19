FROM python:3.11-slim

# Install system dependencies & native Linux Stockfish engine
RUN apt-get update && apt-get install -y --no-install-recommends \
    stockfish \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Environment settings
ENV HOST=0.0.0.0
ENV PORT=7860
ENV STOCKFISH_PATH=/usr/games/stockfish
ENV LLM_PROVIDER=gemini
ENV GEMINI_MODEL=gemini-3.5-flash-lite

EXPOSE 7860

# Run FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]

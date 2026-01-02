import json
import os
import sqlite3
from pathlib import Path
from typing import List

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
DB_PATH = DATA_DIR / "chunks.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="C2 German Coach")

static_dir = APP_ROOT / "frontend"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, text TEXT NOT NULL)"
    )
    return conn


def chunk_text(text: str, max_chars: int = 800) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 > max_chars:
            if current:
                chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current.strip())
    return chunks


def ingest_pdf(file_path: Path) -> int:
    reader = PdfReader(str(file_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in PDF.")
    chunks = chunk_text(text)
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM chunks")
        conn.executemany("INSERT INTO chunks (text) VALUES (?)", [(c,) for c in chunks])
    conn.close()
    return len(chunks)


def search_chunks(query: str, limit: int = 4) -> List[str]:
    tokens = [t.lower() for t in query.split() if t.strip()]
    if not tokens:
        return []
    conn = get_db()
    cursor = conn.execute("SELECT text FROM chunks")
    scored = []
    for (text,) in cursor.fetchall():
        score = sum(text.lower().count(token) for token in tokens)
        if score:
            scored.append((score, text))
    conn.close()
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in scored[:limit]]


def call_ollama(prompt: str) -> str:
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="Ollama request failed.")
    return response.json().get("response", "").strip()


def call_openai(prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY not set.")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a C2 German writing coach."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        },
        timeout=120,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="OpenAI request failed.")
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_response(prompt: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        return call_ollama(prompt)
    if provider == "openai":
        return call_openai(prompt)
    return "LLM provider not configured. Set LLM_PROVIDER to ollama or openai."


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")
    content = await file.read()
    file_path = DATA_DIR / "source.pdf"
    file_path.write_bytes(content)
    chunk_count = ingest_pdf(file_path)
    return {"chunks": chunk_count}


@app.post("/api/ask")
def ask(question: str = Form(...), mode: str = Form("writing")) -> dict:
    context_chunks = search_chunks(question)
    context = "\n\n".join(context_chunks)
    prompt = (
        "Mode: "
        f"{mode}\n"
        "Task: Provide C2-level German guidance with corrections, explanations, and improved phrasing. "
        "If context is provided, use it to answer.\n\n"
        f"Context:\n{context}\n\n"
        f"User Input:\n{question}\n"
    )
    answer = generate_response(prompt)
    return {"answer": answer, "context_used": len(context_chunks)}


@app.get("/api/chunks")
def list_chunks() -> dict:
    conn = get_db()
    cursor = conn.execute("SELECT id, text FROM chunks ORDER BY id LIMIT 5")
    rows = cursor.fetchall()
    conn.close()
    preview = [{"id": row[0], "text": row[1][:200]} for row in rows]
    return {"preview": preview}


@app.get("/app", response_class=HTMLResponse)
def serve_app() -> str:
    index_path = static_dir / "index.html"
    return index_path.read_text(encoding="utf-8")

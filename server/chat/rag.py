"""BM25 retrieval over the Obsidian vault."""
from __future__ import annotations

from pathlib import Path

from rank_bm25 import BM25Okapi  # type: ignore[import]

EFFORT_CONFIG = {
    "low":    {"top_k": 3,  "chunk_size": 400},
    "medium": {"top_k": 6,  "chunk_size": 600},
    "high":   {"top_k": 12, "chunk_size": 900},
}

_SKIP_DIRS = {".obsidian", ".trash"}


def load_vault_chunks(vault_path: str, chunk_size: int) -> list[dict]:
    root = Path(vault_path)
    chunks: list[dict] = []
    for md_file in root.rglob("*.md"):
        if any(skip in md_file.parts for skip in _SKIP_DIRS):
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        words = text.split()
        rel = str(md_file.relative_to(root))
        title = md_file.stem
        for i in range(0, max(1, len(words)), chunk_size):
            chunk_words = words[i : i + chunk_size]
            chunks.append({
                "path": str(md_file),
                "relative_path": rel,
                "title": title,
                "chunk": " ".join(chunk_words),
                "word_count": len(chunk_words),
            })
    return chunks


_MIN_SCORE = 2.0  # chunks below this are treated as irrelevant


def bm25_search(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    if not chunks:
        return []
    tokenized = [c["chunk"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    if max(scores) < _MIN_SCORE:
        return []
    ranked = sorted(zip(scores, chunks), key=lambda x: -x[0])
    return [c for score, c in ranked[:top_k] if score >= _MIN_SCORE]


def format_context(chunks: list[dict]) -> tuple[str, list[str]]:
    if not chunks:
        return "", []
    parts: list[str] = []
    sources: list[str] = []
    for c in chunks:
        rel = c["relative_path"]
        parts.append(f"[SOURCE: {rel}]\n{c['chunk']}\n---")
        if rel not in sources:
            sources.append(rel)
    return "\n".join(parts), sources

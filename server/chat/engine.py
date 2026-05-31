"""Streaming chat engine using llama-server (OpenAI-compatible API)."""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
from typing import AsyncGenerator

import requests  # type: ignore[import]

LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://localhost:8080")

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the internet for current information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"],
        },
    },
}

_THINK_START = "<|think|>"
_THINK_END = "<|/think|>"


def build_system_prompt(vault_context: str, has_context: bool, internet_enabled: bool = False) -> str:
    if not has_context and not internet_enabled:
        return (
            "You are Arc, a personal assistant with access to the user's notes.\n"
            "The user asked a question but no relevant notes were found in the vault.\n"
            'You MUST respond with exactly: "I don\'t have notes on that topic."\n'
            "Do not answer from general knowledge. Do not add anything else."
        )
    if not has_context and internet_enabled:
        return (
            "You are Arc, a personal assistant. No relevant vault notes were found for this query.\n"
            "Internet search is enabled — use the web_search tool to find current information.\n"
            "Summarise search results clearly and cite sources."
        )
    return (
        "You are Arc, a personal assistant with access to the user's private notes and meeting transcripts.\n\n"
        "STRICT RULES:\n"
        "- Answer ONLY from the provided notes context below\n"
        "- If the context doesn't contain enough information, say \"I don't have notes on that topic.\"\n"
        "- Never hallucinate facts not present in the notes\n"
        "- Cite which note/meeting your answer comes from\n\n"
        f"=== YOUR NOTES ===\n{vault_context}"
    )


def _get_model_name() -> str:
    try:
        resp = requests.get(f"{LLAMACPP_HOST}/v1/models", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("data") or data.get("models") or []
        if models:
            return models[0].get("id") or models[0].get("name") or "local"
    except Exception:
        pass
    return "local"


def _vision_supported() -> bool:
    try:
        resp = requests.get(f"{LLAMACPP_HOST}/v1/models", timeout=5)
        data = resp.json()
        for m in data.get("data") or []:
            meta = m.get("meta") or {}
            if meta.get("vision") or "vision" in str(m.get("id", "")).lower():
                return True
    except Exception:
        pass
    return False


class _ThinkParser:
    """State machine that splits streaming content into thinking/text events."""

    def __init__(self) -> None:
        self.in_think = False
        self._buf = ""

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self._buf += chunk
        events: list[tuple[str, str]] = []
        while True:
            tag_start = _THINK_START if not self.in_think else _THINK_END
            idx = self._buf.find(tag_start)
            if idx == -1:
                safe = max(0, len(self._buf) - len(tag_start) + 1)
                if safe > 0:
                    kind = "thinking" if self.in_think else "text"
                    events.append((kind, self._buf[:safe]))
                    self._buf = self._buf[safe:]
                break
            if idx > 0:
                kind = "thinking" if self.in_think else "text"
                events.append((kind, self._buf[:idx]))
            self._buf = self._buf[idx + len(tag_start):]
            self.in_think = not self.in_think
        return events

    def flush(self) -> list[tuple[str, str]]:
        if not self._buf:
            return []
        kind = "thinking" if self.in_think else "text"
        out = [(kind, self._buf)]
        self._buf = ""
        return out


def _sync_stream_to_queue(url: str, payload: dict, q: "queue.Queue[object]") -> None:
    try:
        resp = requests.post(url, json=payload, stream=True, timeout=180)
        for line in resp.iter_lines():
            q.put(line)
    except Exception as exc:
        q.put(exc)
    finally:
        q.put(None)


async def stream_response(
    messages: list[dict],
    system_prompt: str,
    thinking_enabled: bool,
    internet_enabled: bool,
    uploaded_files: list[dict],
    sources: list[str],
) -> AsyncGenerator[str, None]:
    host = LLAMACPP_HOST
    model = _get_model_name()
    url = f"{host}/v1/chat/completions"

    full_system = f"{_THINK_START}\n{system_prompt}" if thinking_enabled else system_prompt

    # Build OpenAI-style message list (skip 'thinking' role rows)
    api_messages: list[dict] = [{"role": "system", "content": full_system}]
    for msg in messages:
        if msg["role"] == "thinking":
            continue
        api_messages.append({"role": msg["role"], "content": msg["content"]})

    # Augment last user message with file attachments
    if uploaded_files:
        last_user = next(
            (i for i in range(len(api_messages) - 1, -1, -1) if api_messages[i]["role"] == "user"),
            None,
        )
        if last_user is not None:
            base_text = api_messages[last_user]["content"]
            images = [f for f in uploaded_files if f["type"] == "image"]
            texts = [f for f in uploaded_files if f["type"] == "text"]

            if images and _vision_supported():
                parts: list[dict] = [{"type": "text", "text": base_text}]
                for f in images:
                    parts.append({"type": "image_url", "image_url": {"url": f"data:{f['mime_type']};base64,{f['content']}"}})
                for f in texts:
                    parts.append({"type": "text", "text": f"\n[File: {f['filename']}]\n{f['content']}"})
                api_messages[last_user] = {"role": "user", "content": parts}
            else:
                extra = ""
                for f in images:
                    extra += "\n[Note: image uploaded but vision model not loaded — restart llama-server with --mmproj for image support.]"
                for f in texts:
                    extra += f"\n\n[File: {f['filename']}]\n{f['content']}"
                api_messages[last_user] = {"role": "user", "content": base_text + extra}

    payload: dict = {
        "model": model,
        "messages": api_messages,
        "stream": True,
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    if internet_enabled:
        payload["tools"] = [SEARCH_TOOL]
        payload["tool_choice"] = "auto"

    if sources:
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    q: queue.Queue[object] = queue.Queue()
    threading.Thread(target=_sync_stream_to_queue, args=(url, payload, q), daemon=True).start()

    loop = asyncio.get_running_loop()
    parser = _ThinkParser()
    tool_name: str | None = None
    tool_args = ""

    while True:
        item = await loop.run_in_executor(None, q.get)
        if item is None:
            break
        if isinstance(item, Exception):
            yield f"data: {json.dumps({'type': 'error', 'message': str(item)})}\n\n"
            break

        line = item.decode("utf-8") if isinstance(item, bytes) else item
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if raw == "[DONE]":
            break

        try:
            chunk = json.loads(raw)
        except json.JSONDecodeError:
            continue

        choice = (chunk.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}

        # Accumulate tool call args
        for tc in delta.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if fn.get("name"):
                tool_name = fn["name"]
            if fn.get("arguments"):
                tool_args += fn["arguments"]

        finish_reason = choice.get("finish_reason")
        if finish_reason == "tool_calls" and tool_name == "web_search":
            try:
                query = json.loads(tool_args).get("query", "")
                yield f"data: {json.dumps({'type': 'text', 'delta': f'🔍 Searching: {query}\\n\\n'})}\n\n"
                from ddgs import DDGS  # type: ignore[import]
                results = list(DDGS().text(query, max_results=5))
                result_text = "\n\n".join(
                    f"**{r['title']}**\n{r['body']}\n{r['href']}" for r in results
                ) or "No results found."
                tool_messages = api_messages + [
                    {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "web_search", "arguments": tool_args},
                    }]},
                    {"role": "tool", "content": result_text, "tool_call_id": "call_1"},
                ]
                payload2 = {**payload, "messages": tool_messages}
                payload2.pop("tools", None)
                payload2.pop("tool_choice", None)
                q2: queue.Queue[object] = queue.Queue()
                threading.Thread(target=_sync_stream_to_queue, args=(url, payload2, q2), daemon=True).start()
                while True:
                    item2 = await loop.run_in_executor(None, q2.get)
                    if item2 is None:
                        break
                    if isinstance(item2, Exception):
                        break
                    line2 = item2.decode("utf-8") if isinstance(item2, bytes) else item2
                    if not line2.startswith("data:"):
                        continue
                    raw2 = line2[5:].strip()
                    if raw2 == "[DONE]":
                        break
                    try:
                        chunk2 = json.loads(raw2)
                    except json.JSONDecodeError:
                        continue
                    content2 = ((chunk2.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                    for kind, text in parser.feed(content2):
                        if text:
                            yield f"data: {json.dumps({'type': kind, 'delta': text})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': f'Search failed: {exc}'})}\n\n"
            continue

        content = delta.get("content") or ""
        if content:
            for kind, text in parser.feed(content):
                if text:
                    yield f"data: {json.dumps({'type': kind, 'delta': text})}\n\n"

    for kind, text in parser.flush():
        if text:
            yield f"data: {json.dumps({'type': kind, 'delta': text})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

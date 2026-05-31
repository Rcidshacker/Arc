"""Process uploaded files for chat context."""
from __future__ import annotations

import base64
from pathlib import Path

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_IMAGE_MIMES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
}


def process_uploaded_file(filename: str, content: bytes) -> dict:
    ext = Path(filename).suffix.lower()

    if ext in _IMAGE_EXTS:
        return {
            "type": "image",
            "content": base64.b64encode(content).decode("ascii"),
            "mime_type": _IMAGE_MIMES.get(ext, "image/jpeg"),
            "filename": filename,
        }

    if ext == ".pdf":
        import pdfplumber  # type: ignore[import]
        import io
        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text)
        return {"type": "text", "content": "\n".join(text_parts), "mime_type": "text/plain", "filename": filename}

    if ext == ".docx":
        import docx  # type: ignore[import]
        import io
        doc = docx.Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return {"type": "text", "content": text, "mime_type": "text/plain", "filename": filename}

    if ext in {".txt", ".md", ""}:
        return {"type": "text", "content": content.decode("utf-8", errors="replace"), "mime_type": "text/plain", "filename": filename}

    raise ValueError(f"Unsupported file type: {ext}")

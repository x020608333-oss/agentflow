"""递归字符分块：段落 -> 句子 -> 硬切片，带重叠窗口，中英文通吃。"""
from __future__ import annotations

SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", "，", ", ", " "]


def recursive_split(
    text: str, chunk_size: int = 500, chunk_overlap: int = 80
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    # 找到能切动的最大分隔符层级
    seps = [s for s in SEPARATORS if s in text] or [""]
    sep = seps[0]

    parts = text.split(sep) if sep else [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    parts = [p for p in parts if p.strip()]

    chunks: list[str] = []
    buf = ""
    for part in parts:
        candidate = f"{buf}{sep}{part}" if buf else part
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        # 单段超长则递归下钻
        if len(part) > chunk_size:
            sub = recursive_split(part, chunk_size, chunk_overlap) if sep else [part[i:i+chunk_size] for i in range(0, len(part), chunk_size)]
            chunks.extend(sub[:-1])
            buf = sub[-1] if sub else ""
        else:
            buf = part
    if buf:
        chunks.append(buf)

    # 加重叠窗口：后块前缀继承前块尾部，避免语义断裂
    if chunk_overlap > 0 and len(chunks) > 1:
        overlaid = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            tail = prev[-chunk_overlap:]
            overlaid.append(tail + cur if not cur.startswith(tail) else cur)
        chunks = overlaid
    return [c.strip() for c in chunks if c.strip()]

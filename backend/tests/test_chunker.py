"""分块器测试。"""
from app.rag.chunker import recursive_split


def test_short_text_single_chunk():
    assert recursive_split("你好世界", 100, 10) == ["你好世界"]


def test_long_chinese_text_splits_within_size():
    text = "云途CRM是一款客户管理产品。" * 60  # ~840 字
    chunks = recursive_split(text, 200, 40)
    assert len(chunks) > 1
    assert all(len(c) <= 260 for c in chunks), [len(c) for c in chunks]
    assert "".join(chunks).startswith("云途CRM")


def test_empty_text():
    assert recursive_split("", 100, 10) == []
    assert recursive_split("   \n  ", 100, 10) == []


def test_overlap_present():
    text = "。".join(f"这是第{i}句话用于测试分块的重叠窗口功能" for i in range(20))
    chunks = recursive_split(text, 80, 30)
    assert len(chunks) >= 2
    # 后一块开头应包含前一块尾部片段（重叠生效）
    assert chunks[0][-15:] in chunks[1][:45] or chunks[0][-10:] in chunks[1][:30]

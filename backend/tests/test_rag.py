"""RAG 链路测试：入库 -> 向量检索。"""
from pathlib import Path

from app.db.session import get_session_factory
from app.llm.embeddings import get_embedder
from app.rag.ingestion import extract_text
from app.rag.store import vector_store


def test_extract_text_txt(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("知识库测试内容", encoding="utf-8")
    assert extract_text(f) == "知识库测试内容"


def test_ingest_and_search(seeded):
    from app.config import get_settings
    from app.db.models import Dataset
    from app.rag.ingestion import ingest_document

    settings = get_settings()
    db = get_session_factory()()
    try:
        ds = Dataset(name="测试知识库", kind="docs")
        db.add(ds)
        db.commit()

        f = db.query  # noqa
        path = settings.uploads_dir / "test_doc.txt"
        path.write_text(
            "云途CRM的专业版价格为每人每月99元，支持全部报表功能。\n"
            "企业版价格为每人每月299元，增加权限体系与API能力。\n"
            "退款政策：付费版本7天内无理由退款。\n",
            encoding="utf-8",
        )
        doc = ingest_document(db, settings, ds, path, "test_doc.txt")
        assert doc.chunk_count >= 1

        embedder = get_embedder(settings)
        qvec = embedder.embed(["专业版多少钱"])[0]
        hits = vector_store.search(db, [ds.id], qvec, top_k=2)
        assert hits, "应至少命中一个分片"
        assert hits[0]["score"] > 0
    finally:
        db.close()


def test_search_empty_dataset(seeded):
    from app.db.session import get_session_factory
    from app.llm.embeddings import get_embedder
    from app.config import get_settings

    db = get_session_factory()()
    try:
        qvec = get_embedder(get_settings()).embed(["任何问题"])[0]
        hits = vector_store.search(db, ["不存在的数据集"], qvec, top_k=3)
        assert hits == []
    finally:
        db.close()

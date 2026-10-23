"""知识库/数据集：创建、文档上传（自动分块向量化）、语义检索测试、表格预览。"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import verify_auth
from app.api.schemas import DatasetCreate
from app.config import get_settings
from app.db.models import Chunk, Dataset, Document
from app.db.session import get_db
from app.llm.embeddings import get_embedder
from app.rag.ingestion import MAX_FILE_SIZE, ingest_document, ingest_table
from app.rag.store import vector_store

router = APIRouter(prefix="/api/datasets", tags=["datasets"], dependencies=[Depends(verify_auth)])

UPLOAD_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(413, "文件超过 20MB 上限")
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_upload_path(dataset_id: str, filename: str) -> tuple[Path, str]:
    """只保留 basename,并把最终路径限制在 uploads_dir 内,防止 ../ 穿越。"""
    settings = get_settings()
    name = Path((filename or "upload.bin").replace("\\", "/")).name.strip()
    name = re.sub(r'[\\/:*?"<>|\r\n]', "_", name)
    if not name or name in (".", ".."):
        raise HTTPException(400, "非法文件名")
    root = settings.uploads_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / f"{dataset_id[:8]}_{uuid.uuid4().hex[:6]}_{name}").resolve()
    if not path.is_relative_to(root):
        raise HTTPException(400, "非法上传路径")
    return path, name


def serialize(ds: Dataset, db: Session | None = None) -> dict:
    data = {
        "id": ds.id,
        "name": ds.name,
        "description": ds.description,
        "kind": ds.kind,
        "table_name": ds.table_name,
        "meta": ds.meta or {},
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }
    if db is not None:
        docs = db.query(Document).filter(Document.dataset_id == ds.id).all()
        data["documents"] = [
            {"id": d.id, "filename": d.filename, "size": d.size, "chunk_count": d.chunk_count, "status": d.status}
            for d in docs
        ]
    return data


@router.get("")
def list_datasets(db: Session = Depends(get_db)):
    items = db.query(Dataset).order_by(Dataset.created_at).all()
    return {"items": [serialize(d, db) for d in items]}


@router.post("")
def create_dataset(body: DatasetCreate, db: Session = Depends(get_db)):
    if body.kind not in ("docs", "table"):
        raise HTTPException(400, "kind 必须是 docs 或 table")
    ds = Dataset(**body.model_dump())
    db.add(ds)
    db.commit()
    return serialize(ds)


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "数据集不存在")
    return serialize(ds, db)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "数据集不存在")
    # 表格数据集需同时删除物理表
    if ds.kind == "table" and ds.table_name:
        from sqlalchemy import text

        try:
            with db.get_bind().begin() as conn:
                conn.execute(text(f'DROP TABLE IF EXISTS "{ds.table_name}"'))
        except Exception:
            pass
    db.query(Chunk).filter(Chunk.dataset_id == dataset_id).delete()
    db.query(Document).filter(Document.dataset_id == dataset_id).delete()
    db.delete(ds)
    db.commit()
    vector_store.invalidate(dataset_id)
    return {"ok": True}


@router.post("/{dataset_id}/documents")
async def upload_document(dataset_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "数据集不存在")
    content = await _read_limited(file, MAX_FILE_SIZE)
    if not content:
        raise HTTPException(400, "空文件")

    save_path, safe_name = _safe_upload_path(dataset_id, file.filename or "upload.bin")
    save_path.write_bytes(content)

    try:
        if ds.kind == "table":
            info = ingest_table(db, get_settings(), ds, save_path, safe_name)
            return {"ok": True, "type": "table", **info}
        doc = ingest_document(db, get_settings(), ds, save_path, safe_name)
        return {"ok": True, "type": "document", "document_id": doc.id, "chunks": doc.chunk_count}
    except ValueError as exc:
        save_path.unlink(missing_ok=True)
        raise HTTPException(400, str(exc))
    except Exception:
        save_path.unlink(missing_ok=True)
        raise


@router.post("/{dataset_id}/search")
def search_dataset(dataset_id: str, body: dict, db: Session = Depends(get_db)):
    """知识库检索测试：返回 top-k 命中片段与相关度。"""
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "数据集不存在")
    if ds.kind != "docs":
        raise HTTPException(400, "仅文档知识库支持语义检索")
    query = str(body.get("query", "")).strip()
    top_k = int(body.get("top_k", 5))
    if not query:
        raise HTTPException(400, "query 不能为空")
    settings = get_settings()
    qvec = get_embedder(settings).embed([query])[0]
    hits = vector_store.search(db, [dataset_id], qvec, top_k=top_k)
    return {"query": query, "hits": hits}


@router.get("/{dataset_id}/preview")
def preview_table(dataset_id: str, limit: int = 20, db: Session = Depends(get_db)):
    """表格数据集预览：列结构与前 N 行。"""
    import pandas as pd

    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(404, "数据集不存在")
    if ds.kind != "table" or not ds.table_name:
        raise HTTPException(400, "仅表格数据集支持预览")
    df = pd.read_sql(f'SELECT * FROM "{ds.table_name}" LIMIT {int(limit)}', db.get_bind())
    return {
        "meta": ds.meta or {},
        "columns": list(df.columns),
        "rows": df.replace({pd.NA: None}).to_dict(orient="records"),
    }

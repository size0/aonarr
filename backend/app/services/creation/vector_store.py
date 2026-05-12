"""向量语义检索 — ChromaDB 集成

为每部小说维护独立的 ChromaDB 集合，支持：
1. 章节写入后自动 embed → 存入向量库
2. 创作时按语义检索相关段落用于上下文增强
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings

from app.db.connection import DATA_DIR

logger = logging.getLogger(__name__)

CHROMA_DIR = DATA_DIR / "chromadb"


def _get_chroma_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 持久化客户端"""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def _collection_name(novel_id: str) -> str:
    """生成合法的集合名称（ChromaDB 要求 3-63 字符，无特殊字符）"""
    short = hashlib.md5(novel_id.encode()).hexdigest()[:12]
    return f"novel_{short}"


class NovelVectorStore:
    """单部小说的向量存储"""

    def __init__(self, novel_id: str):
        self.novel_id = novel_id
        self._client = _get_chroma_client()
        self._collection = self._client.get_or_create_collection(
            name=_collection_name(novel_id),
            metadata={"novel_id": novel_id, "hnsw:space": "cosine"},
        )

    def upsert_chapter(self, chapter_number: int, content: str, *, chunk_size: int = 500, overlap: int = 100) -> int:
        """将章节内容切分为段落并 upsert 到向量库

        Args:
            chapter_number: 章节号
            content: 章节完整文本
            chunk_size: 每段落字数
            overlap: 段落重叠字数

        Returns:
            写入的段落数
        """
        if not content.strip():
            return 0

        # 先删除该章节的旧数据
        try:
            old_ids = self._collection.get(
                where={"chapter_number": chapter_number}
            )["ids"]
            if old_ids:
                self._collection.delete(ids=old_ids)
        except Exception:
            pass

        # 切分段落
        chunks = self._split_text(content, chunk_size, overlap)
        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"ch{chapter_number}_p{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "novel_id": self.novel_id,
                "chapter_number": chapter_number,
                "chunk_index": i,
                "char_count": len(chunk),
            })

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info("向量库 upsert: novel=%s chapter=%d, %d 段落", self.novel_id, chapter_number, len(chunks))
        return len(chunks)

    def query_similar(
        self,
        query_text: str,
        *,
        n_results: int = 5,
        exclude_chapter: Optional[int] = None,
    ) -> list[dict]:
        """语义检索相关段落

        Args:
            query_text: 查询文本
            n_results: 返回结果数
            exclude_chapter: 排除指定章节号的结果

        Returns:
            [{"text": "...", "chapter_number": N, "distance": 0.xx}, ...]
        """
        if self._collection.count() == 0:
            return []

        where_filter = None
        if exclude_chapter is not None:
            where_filter = {"chapter_number": {"$ne": exclude_chapter}}

        try:
            results = self._collection.query(
                query_texts=[query_text],
                n_results=min(n_results, self._collection.count()),
                where=where_filter,
            )
        except Exception as e:
            logger.warning("向量检索失败: %s", e)
            return []

        output = []
        if results and results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                output.append({
                    "text": doc,
                    "chapter_number": meta.get("chapter_number", 0),
                    "chunk_index": meta.get("chunk_index", 0),
                    "distance": round(dist, 4),
                })
        return output

    def delete_novel(self) -> None:
        """删除整个小说的向量集合"""
        try:
            self._client.delete_collection(_collection_name(self.novel_id))
            logger.info("向量集合已删除: %s", self.novel_id)
        except Exception as e:
            logger.warning("删除向量集合失败: %s", e)

    @staticmethod
    def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
        """按字数切分文本，带重叠"""
        text = text.strip()
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - overlap
        return chunks

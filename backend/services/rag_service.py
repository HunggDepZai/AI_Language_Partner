"""
RAG Service — Hybrid Retrieval-Augmented Generation
Pipeline: Vector Search ║ BM25 Keyword Search → RRF Fusion → Re-Ranking → Metadata Filter

Thành phần:
  1. Vector Search      — Qdrant Cloud + HuggingFace vietnamese-embedding (ngữ nghĩa sâu)
  2. Keyword Search     — BM25 (rank-bm25), exact/partial match
  3. Hybrid Layer       — Reciprocal Rank Fusion (RRF) kết hợp 2 ranking
  4. Dynamic Re-Ranking — cross-encoder ms-marco (sentence-transformers, local ~80ms)
  5. Metadata Filtering — lọc theo file_type, source, department, urgency
"""
import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from langchain_qdrant import QdrantVectorStore
from langchain_community.embeddings import HuggingFaceEmbeddings
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
QDRANT_URL         = os.getenv("QDRANT_URL",              "http://localhost:6333")
QDRANT_API_KEY     = os.getenv("QDRANT_API_KEY",          "")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL",         "dangvantuan/vietnamese-embedding")
COLLECTION_NAME    = "tourism_knowledge"
TOP_K_VECTOR       = int(os.getenv("RAG_TOP_K_VECTOR",  "20"))
TOP_K_BM25         = int(os.getenv("RAG_TOP_K_BM25",    "10"))
TOP_K_FINAL        = int(os.getenv("RAG_TOP_K_FINAL",   "5"))
SCORE_THRESHOLD    = float(os.getenv("RAG_SCORE_THRESHOLD", "0.20"))
MAX_CONTEXT_CHARS  = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
RRF_K              = int(os.getenv("RAG_RRF_K",         "60"))
RERANK_MODEL       = os.getenv("RAG_RERANK_MODEL", "cosine")   # "cosine" | "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_ENABLED     = os.getenv("RAG_RERANK_ENABLED", "false").lower() == "true"
DEFAULT_FILTERS: dict = {}


class RAGService:
    def __init__(self):
        self.vectorstore: Optional[QdrantVectorStore] = None
        self.qdrant_client: Optional[QdrantClient] = None
        self.embeddings = None
        self._ready = False
        self._bm25 = None
        self._bm25_docs: list = []
        self._reranker = None
        self._reranker_loaded = False

    # ── INIT ──────────────────────────────────────────────────────────────────

    async def initialize(self):
        """Load Qdrant vectorstore và build BM25 index song song."""
        try:
            logger.info(f"⚙️  Đang load embedding model: {EMBEDDING_MODEL}...")
            self.embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            logger.info(f"✅ Embedding model loaded: {EMBEDDING_MODEL}")

            # Kết nối Qdrant Cloud
            if not QDRANT_URL or not QDRANT_API_KEY:
                logger.warning("⚠️  Chưa cấu hình QDRANT_URL / QDRANT_API_KEY — RAG tắt")
                return

            self.qdrant_client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
            )

            # Kiểm tra collection có tồn tại không
            try:
                collections = self.qdrant_client.get_collections().collections
                collection_names = [c.name for c in collections]
                if COLLECTION_NAME not in collection_names:
                    logger.warning(f"⚠️  Collection '{COLLECTION_NAME}' chưa tồn tại trên Qdrant. Chạy ingest.py trước.")
                    return
            except Exception as e:
                logger.error(f"❌ Không thể kết nối Qdrant Cloud: {e}")
                return

            self.vectorstore = QdrantVectorStore(
                client=self.qdrant_client,
                collection_name=COLLECTION_NAME,
                embedding=self.embeddings,
            )

            # Lấy số lượng vectors
            try:
                collection_info = self.qdrant_client.get_collection(COLLECTION_NAME)
                count = collection_info.points_count
            except Exception:
                count = 0

            if count == 0:
                logger.warning("⚠️  Qdrant collection rỗng. Chạy ingest.py trước.")
                return

            logger.info(f"✅ Qdrant Cloud: {count} chunks")
            # Build BM25 trong thread để không block event loop
            await asyncio.get_event_loop().run_in_executor(None, self._build_bm25_index)
            self._ready = True
            logger.info("✅ RAG Hybrid sẵn sàng (Vector + BM25 + RRF + Rerank)")

        except Exception as e:
            logger.error(f"❌ RAG init lỗi: {e}", exc_info=True)

    def _build_bm25_index(self):
        """Build BM25 index từ toàn bộ corpus Qdrant."""
        try:
            from rank_bm25 import BM25Okapi
            from langchain_core.documents import Document

            # Scroll toàn bộ points từ Qdrant
            all_texts = []
            all_metadatas = []

            offset = None
            while True:
                results, next_offset = self.qdrant_client.scroll(
                    collection_name=COLLECTION_NAME,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not results:
                    break
                for point in results:
                    payload = point.payload or {}
                    text = payload.get("page_content", "")
                    metadata = payload.get("metadata", {})
                    if text:
                        all_texts.append(text)
                        all_metadatas.append(metadata)
                if next_offset is None:
                    break
                offset = next_offset

            if not all_texts:
                return

            tokenized = [t.lower().split() for t in all_texts]
            self._bm25 = BM25Okapi(tokenized)
            self._bm25_docs = [
                Document(
                    page_content=all_texts[i],
                    metadata=all_metadatas[i] if i < len(all_metadatas) else {}
                )
                for i in range(len(all_texts))
            ]
            logger.info(f"✅ BM25: {len(self._bm25_docs)} docs indexed")
        except ImportError:
            logger.warning("rank-bm25 chưa cài. pip install rank-bm25")
        except Exception as e:
            logger.error(f"BM25 build lỗi: {e}")

    def _load_reranker(self):
        """
        Thử load cross-encoder (sentence-transformers).
        Nếu không có / lỗi → dùng cosine rerank bằng HuggingFace embeddings.
        """
        if self._reranker_loaded:
            return
        if RERANK_MODEL != "cosine":
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder(RERANK_MODEL, max_length=512)
                logger.info(f"✅ Reranker: CrossEncoder({RERANK_MODEL})")
                self._reranker_loaded = True
                return
            except Exception as e:
                logger.warning(f"CrossEncoder load lỗi ({e}), chuyển sang cosine rerank.")
        # Fallback: Cosine rerank (dùng embeddings đã khởi tạo)
        self._reranker = "cosine"
        logger.info("✅ Reranker: Cosine similarity (HuggingFace embeddings)")
        self._reranker_loaded = True

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    @property
    def is_ready(self):
        return self._ready

    async def retrieve(
        self,
        query: str,
        filters: Optional[dict] = None
    ) -> tuple[str, list[dict]]:
        """
        Hybrid retrieve: Vector ║ BM25 → RRF → Metadata Filter → Rerank → Top-K.
        Vector và BM25 chạy song song (asyncio.gather) để tối thiểu latency.
        """
        if not self._ready:
            return "", []

        t0 = time.monotonic()
        try:
            # Bước 1+2: song song
            vector_hits, bm25_hits = await asyncio.gather(
                self._vector_search(query),
                self._bm25_search(query),
            )

            # Bước 3: RRF fusion
            fused = self._rrf_fusion(vector_hits, bm25_hits)

            # Bước 4: Metadata filter
            active_filters = {**DEFAULT_FILTERS, **(filters or {})}
            if active_filters:
                fused = self._apply_metadata_filter(fused, active_filters)

            if not fused:
                logger.debug(f"RAG: không có context cho '{query[:50]}'")
                return "", []

            # Bước 5: Rerank (CPU, trong thread)
            if RERANK_ENABLED:
                fused = await asyncio.get_event_loop().run_in_executor(
                    None, self._rerank, query, fused
                )

            # Bước 6: Build context
            top = fused[:TOP_K_FINAL]
            context, sources = self._build_context(top)

            ms = (time.monotonic() - t0) * 1000
            logger.info(
                f"✅ RAG: {len(top)} chunks | vec={len(vector_hits)} bm25={len(bm25_hits)} "
                f"fused={len(fused)} | {ms:.0f}ms"
            )
            return context, sources

        except Exception as e:
            logger.error(f"RAG retrieve lỗi: {e}", exc_info=True)
            return "", []

    # ── STEP 1: VECTOR SEARCH ─────────────────────────────────────────────────

    async def _vector_search(self, query: str) -> list[tuple]:
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self.vectorstore.similarity_search_with_score(
                    query, k=TOP_K_VECTOR
                )
            )
            hits = []
            for rank, (doc, score) in enumerate(results):
                # Qdrant trả distance (cosine), score càng cao càng tốt
                # LangChain Qdrant đã chuẩn hoá score
                if score >= SCORE_THRESHOLD:
                    hits.append((doc, score, rank))
            logger.debug(f"Vector: {len(hits)}/{TOP_K_VECTOR} above threshold={SCORE_THRESHOLD}")
            return hits
        except Exception as e:
            logger.error(f"Vector search lỗi: {e}")
            return []

    # ── STEP 2: BM25 KEYWORD SEARCH ───────────────────────────────────────────

    async def _bm25_search(self, query: str) -> list[tuple]:
        if not self._bm25 or not self._bm25_docs:
            return []
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._bm25_search_sync, query
            )
        except Exception as e:
            logger.error(f"BM25 search lỗi: {e}")
            return []

    def _bm25_search_sync(self, query: str) -> list[tuple]:
        import numpy as np
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        top_idx = np.argsort(scores)[::-1][:TOP_K_BM25]
        hits = []
        for rank, idx in enumerate(top_idx):
            s = float(scores[idx])
            if s <= 0:
                break
            hits.append((self._bm25_docs[idx], s, rank))
        logger.debug(f"BM25: {len(hits)} hits")
        return hits

    # ── STEP 3: RRF FUSION ────────────────────────────────────────────────────

    def _rrf_fusion(self, vector_hits: list, bm25_hits: list) -> list[tuple]:
        """Reciprocal Rank Fusion — kết hợp 2 ranked list thành 1."""
        rrf: dict[str, float] = {}
        doc_map: dict[str, any] = {}

        def _id(doc) -> str:
            cid = doc.metadata.get("chunk_id", "")
            return cid if cid else str(hash(doc.page_content[:80]))

        for rank, (doc, score, _) in enumerate(vector_hits):
            did = _id(doc)
            rrf[did] = rrf.get(did, 0.0) + 1.0 / (RRF_K + rank + 1)
            doc_map[did] = (doc, score)

        for rank, (doc, score, _) in enumerate(bm25_hits):
            did = _id(doc)
            rrf[did] = rrf.get(did, 0.0) + 1.0 / (RRF_K + rank + 1)
            if did not in doc_map:
                doc_map[did] = (doc, score)

        sorted_ids = sorted(rrf, key=lambda x: rrf[x], reverse=True)
        fused = [(doc_map[did][0], rrf[did]) for did in sorted_ids]
        logger.debug(f"RRF: {len(fused)} unique docs")
        return fused

    # ── STEP 4: METADATA FILTER ───────────────────────────────────────────────

    def _apply_metadata_filter(self, docs: list[tuple], filters: dict) -> list[tuple]:
        """
        Hỗ trợ:  exact {"file_type":"pdf"}
                  list  {"department": ["sales","hr"]}
                  ops   {"urgency": {"$ne":"low"}, "tag": {"$in":["vip"]}}
        """
        out = []
        for doc, score in docs:
            meta = doc.metadata
            ok = True
            for key, val in filters.items():
                mv = meta.get(key)
                if isinstance(val, dict):
                    if "$ne"  in val and mv == val["$ne"]:  ok = False; break
                    if "$in"  in val and mv not in val["$in"]:  ok = False; break
                    if "$nin" in val and mv in val["$nin"]: ok = False; break
                elif isinstance(val, list):
                    if mv not in val: ok = False; break
                else:
                    if mv != val: ok = False; break
            if ok:
                out.append((doc, score))
        logger.debug(f"Metadata filter: {len(out)}/{len(docs)} pass")
        return out

    # ── STEP 5: DYNAMIC RE-RANKING ────────────────────────────────────────────

    def _rerank(self, query: str, docs: list[tuple]) -> list[tuple]:
        """
        Re-rank docs theo query:
          - CrossEncoder (sentence-transformers) nếu load được
          - OpenAI cosine similarity nếu không có torch
        Chạy trong executor (thread) để không block event loop.
        """
        if not self._reranker_loaded:
            self._load_reranker()
        if not self._reranker or not docs:
            return docs

        try:
            if self._reranker == "cosine":
                return self._cosine_rerank(query, docs)
            else:
                # CrossEncoder
                pairs  = [(query, doc.page_content) for doc, _ in docs]
                scores = self._reranker.predict(pairs)
                reranked = sorted(
                    zip([d for d, _ in docs], scores),
                    key=lambda x: x[1], reverse=True
                )
                logger.debug(f"CrossEncoder rerank top={reranked[0][1]:.3f}")
                return [(d, float(s)) for d, s in reranked]
        except Exception as e:
            logger.warning(f"Rerank lỗi, dùng RRF order: {e}")
            return docs

    def _cosine_rerank(self, query: str, docs: list[tuple]) -> list[tuple]:
        """
        Cosine re-rank: embed query + mỗi chunk rồi tính cosine.
        Dùng embeddings object (HuggingFace) đã khởi tạo sẵn.
        """
        import numpy as np
        try:
            texts  = [query] + [doc.page_content for doc, _ in docs]
            vecs   = self.embeddings.embed_documents(texts)
            q_vec  = np.array(vecs[0])
            scores = []
            for i, (doc, rrf_score) in enumerate(docs):
                d_vec = np.array(vecs[i + 1])
                cosine = float(np.dot(q_vec, d_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(d_vec) + 1e-9))
                scores.append((doc, cosine))
            reranked = sorted(scores, key=lambda x: x[1], reverse=True)
            logger.debug(f"Cosine rerank top={reranked[0][1]:.3f}")
            return reranked
        except Exception as e:
            logger.warning(f"Cosine rerank lỗi: {e}")
            return docs

    # ── BUILD CONTEXT & PROMPT ────────────────────────────────────────────────

    def _build_context(self, docs: list[tuple]) -> tuple[str, list[dict]]:
        parts, sources, total = [], [], 0
        for doc, score in docs:
            chunk = doc.page_content
            if total + len(chunk) > MAX_CONTEXT_CHARS:
                left = MAX_CONTEXT_CHARS - total
                if left > 150:
                    parts.append(chunk[:left] + "...")
                break
            parts.append(chunk)
            total += len(chunk)
            sources.append({
                "source":    doc.metadata.get("source",    "Không rõ"),
                "page":      doc.metadata.get("page",      "?"),
                "score":     round(score, 4),
                "chunk_id":  doc.metadata.get("chunk_id",  ""),
                "file_type": doc.metadata.get("file_type", ""),
            })
        return "\n\n---\n\n".join(parts), sources

    def build_rag_prompt(self, query: str, context: str, sources: list[dict]) -> str:
        """System prompt chứa RAG context, inject vào LLM qua llm_service."""
        if not context:
            return ""
        src_lines = "\n".join(
            f"  [{i+1}] {s['source']} — trang {s['page']} (relevance: {s['score']})"
            for i, s in enumerate(sources)
        )
        return f"""Bạn là hướng dẫn viên du lịch Việt Nam chuyên nghiệp.
Dưới đây là thông tin từ tài liệu chính thức (tìm kiếm bằng Hybrid Search + Re-Ranking).

=== TÀI LIỆU THAM KHẢO ===
{context}
=== HẾT TÀI LIỆU ===

Nguồn ({len(sources)} đoạn):
{src_lines}

Hướng dẫn:
- Ưu tiên thông tin từ tài liệu, ghi nguồn [số] nếu cần.
- Nếu tài liệu chưa đủ, bổ sung từ kiến thức chung du lịch Việt Nam.
- Trả lời bằng tiếng Việt, ngắn gọn, tự nhiên (giọng nói — không dùng markdown)."""

    # ── HEALTH / DEBUG ────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        count = 0
        if self.qdrant_client:
            try:
                collection_info = self.qdrant_client.get_collection(COLLECTION_NAME)
                count = collection_info.points_count
            except Exception:
                count = 0
        return {
            "ready":           self._ready,
            "qdrant_url":      QDRANT_URL,
            "total_chunks":    count,
            "bm25_docs":       len(self._bm25_docs),
            "rerank_enabled":  RERANK_ENABLED,
            "rerank_model":    RERANK_MODEL if self._reranker != "cosine" else "cosine-similarity",
            "top_k_vector":    TOP_K_VECTOR,
            "top_k_bm25":      TOP_K_BM25,
            "top_k_final":     TOP_K_FINAL,
            "score_threshold": SCORE_THRESHOLD,
        }

"""
RAG Service — Hybrid Retrieval-Augmented Generation
Pipeline: Vector Search ║ BM25 Keyword Search → RRF Fusion → Re-Ranking → Metadata Filter

Thành phần:
  1. Vector Search      — ChromaDB + OpenAI text-embedding-3-small (ngữ nghĩa sâu)
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

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_BASE_DIR          = Path(__file__).resolve().parent.parent
CHROMA_DIR         = os.getenv("CHROMA_DB_PATH",        str(_BASE_DIR / "chroma_db"))
COLLECTION_NAME    = "tourism_knowledge"
TOP_K_VECTOR       = int(os.getenv("RAG_TOP_K_VECTOR",  "20"))
TOP_K_BM25         = int(os.getenv("RAG_TOP_K_BM25",    "10"))
TOP_K_FINAL        = int(os.getenv("RAG_TOP_K_FINAL",   "5"))
SCORE_THRESHOLD    = float(os.getenv("RAG_SCORE_THRESHOLD", "0.20"))
MAX_CONTEXT_CHARS  = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
RRF_K              = int(os.getenv("RAG_RRF_K",         "60"))
RERANK_MODEL       = os.getenv("RAG_RERANK_MODEL", "openai")   # "openai" | "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_ENABLED     = os.getenv("RAG_RERANK_ENABLED", "false").lower() == "true"
DEFAULT_FILTERS: dict = {}


class RAGService:
    def __init__(self):
        self.vectorstore: Optional[Chroma] = None
        self.embeddings = None
        self._ready = False
        self._bm25 = None
        self._bm25_docs: list = []
        self._reranker = None
        self._reranker_loaded = False

    # ── INIT ──────────────────────────────────────────────────────────────────

    async def initialize(self):
        """Load ChromaDB và build BM25 index song song."""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("⚠️  Không có OPENAI_API_KEY — RAG tắt")
                return

            self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=api_key)

            if not Path(CHROMA_DIR).exists():
                logger.warning(f"⚠️  Chưa có ChromaDB tại {CHROMA_DIR}. Chạy ingest.py trước.")
                return

            self.vectorstore = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=self.embeddings,
                persist_directory=CHROMA_DIR
            )
            try:
                count = self.vectorstore._collection.count()
            except Exception:
                count = len(self.vectorstore.get()["ids"])

            if count == 0:
                logger.warning("⚠️  ChromaDB rỗng. Chạy ingest.py trước.")
                return

            logger.info(f"✅ ChromaDB: {count} chunks")
            # Build BM25 trong thread để không block event loop
            await asyncio.get_event_loop().run_in_executor(None, self._build_bm25_index)
            self._ready = True
            logger.info("✅ RAG Hybrid sẵn sàng (Vector + BM25 + RRF + Rerank)")

        except Exception as e:
            logger.error(f"❌ RAG init lỗi: {e}", exc_info=True)

    def _build_bm25_index(self):
        """Build BM25 index từ toàn bộ corpus ChromaDB."""
        try:
            from rank_bm25 import BM25Okapi
            try:
                from langchain_core.documents import Document
            except ImportError:
                from langchain.schema import Document  # fallback phiên bản cũ
            data = self.vectorstore.get()
            docs_text  = data.get("documents", [])
            metadatas  = data.get("metadatas", [])
            ids        = data.get("ids", [])
            if not docs_text:
                return
            tokenized = [t.lower().split() for t in docs_text]
            self._bm25 = BM25Okapi(tokenized)
            self._bm25_docs = [
                Document(
                    page_content=docs_text[i],
                    metadata=metadatas[i] if i < len(metadatas) else {"id": ids[i]}
                )
                for i in range(len(docs_text))
            ]
            logger.info(f"✅ BM25: {len(self._bm25_docs)} docs indexed")
        except ImportError:
            logger.warning("rank-bm25 chưa cài. pip install rank-bm25")
        except Exception as e:
            logger.error(f"BM25 build lỗi: {e}")

    def _load_reranker(self):
        """
        Thử load cross-encoder (sentence-transformers).
        Nếu không có / lỗi torch → dùng OpenAI cosine rerank (không cần torch).
        """
        if self._reranker_loaded:
            return
        if RERANK_MODEL != "openai":
            try:
                from sentence_transformers import CrossEncoder
                self._reranker = CrossEncoder(RERANK_MODEL, max_length=512)
                logger.info(f"✅ Reranker: CrossEncoder({RERANK_MODEL})")
                self._reranker_loaded = True
                return
            except Exception as e:
                logger.warning(f"CrossEncoder load lỗi ({e}), chuyển sang OpenAI rerank.")
        # Fallback: OpenAI cosine rerank (dùng embeddings đã khởi tạo)
        self._reranker = "openai"
        logger.info("✅ Reranker: OpenAI cosine similarity (torch-free)")
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
                lambda: self.vectorstore.similarity_search_with_relevance_scores(
                    query, k=TOP_K_VECTOR
                )
            )
            hits = [
                (doc, score, rank)
                for rank, (doc, score) in enumerate(results)
                if score >= SCORE_THRESHOLD
            ]
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
            if self._reranker == "openai":
                return self._rerank_openai_cosine(query, docs)
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

    def _rerank_openai_cosine(self, query: str, docs: list[tuple]) -> list[tuple]:
        """
        OpenAI cosine re-rank: embed query + mỗi chunk rồi tính cosine.
        Không cần torch. Dùng embeddings object đã khởi tạo sẵn.
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
            logger.debug(f"OpenAI cosine rerank top={reranked[0][1]:.3f}")
            return reranked
        except Exception as e:
            logger.warning(f"OpenAI cosine rerank lỗi: {e}")
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
        if self.vectorstore:
            try:
                count = self.vectorstore._collection.count()
            except Exception:
                count = len(self.vectorstore.get()["ids"])
        return {
            "ready":           self._ready,
            "chroma_dir":      CHROMA_DIR,
            "total_chunks":    count,
            "bm25_docs":       len(self._bm25_docs),
            "rerank_enabled":  RERANK_ENABLED,
            "rerank_model":    RERANK_MODEL if self._reranker != "openai" else "openai-cosine",
            "top_k_vector":    TOP_K_VECTOR,
            "top_k_bm25":      TOP_K_BM25,
            "top_k_final":     TOP_K_FINAL,
            "score_threshold": SCORE_THRESHOLD,
        }

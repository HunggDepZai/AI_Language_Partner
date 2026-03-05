"""
RAG Service — Hướng Dẫn Viên Du Lịch Số
Retrieval-Augmented Generation với ChromaDB + LangChain
"""
import os
import logging
from pathlib import Path
from typing import Optional

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

CHROMA_DIR = os.getenv("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "tourism_knowledge"
TOP_K = int(os.getenv("RAG_TOP_K", "5"))
SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.45"))


class RAGService:
    def __init__(self):
        self.vectorstore: Optional[Chroma] = None
        self.embeddings = None
        self._ready = False

    async def initialize(self):
        """Khởi tạo RAG service — load ChromaDB đã có sẵn."""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("⚠️  Không có OPENAI_API_KEY — RAG sẽ tắt")
                return

            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=api_key
            )

            if Path(CHROMA_DIR).exists():
                self.vectorstore = Chroma(
                    collection_name=COLLECTION_NAME,
                    embedding_function=self.embeddings,
                    persist_directory=CHROMA_DIR
                )
                count = self.vectorstore._collection.count()
                if count > 0:
                    self._ready = True
                    logger.info(f"✅ RAG sẵn sàng — {count} chunks trong ChromaDB")
                else:
                    logger.warning("⚠️  ChromaDB rỗng. Chạy python ingest.py trước.")
            else:
                logger.warning(f"⚠️  Chưa có ChromaDB tại {CHROMA_DIR}. Chạy python ingest.py trước.")

        except Exception as e:
            logger.error(f"❌ RAG init lỗi: {e}")

    @property
    def is_ready(self):
        return self._ready

    async def retrieve(self, query: str) -> tuple[str, list[dict]]:
        """
        Tìm kiếm thông tin liên quan đến câu hỏi.
        
        Returns:
            (context_text, sources_list)
        """
        if not self._ready:
            return "", []

        try:
            # Tìm kiếm với similarity score
            results = self.vectorstore.similarity_search_with_relevance_scores(
                query,
                k=TOP_K
            )

            # Lọc theo threshold
            filtered = [(doc, score) for doc, score in results if score >= SCORE_THRESHOLD]

            if not filtered:
                logger.debug(f"RAG: Không tìm thấy context phù hợp cho '{query[:50]}...'")
                return "", []

            # Tổng hợp context
            context_parts = []
            sources = []

            for doc, score in filtered:
                context_parts.append(doc.page_content)
                sources.append({
                    "source": doc.metadata.get("source", "Không rõ"),
                    "page": doc.metadata.get("page", "?"),
                    "score": round(score, 3),
                    "chunk_id": doc.metadata.get("chunk_id", "")
                })
                logger.debug(f"RAG hit: score={score:.3f}, src={doc.metadata.get('source','?')}")

            context = "\n\n---\n\n".join(context_parts)
            logger.info(f"✅ RAG: {len(filtered)} chunks retrieved cho '{query[:40]}...'")
            return context, sources

        except Exception as e:
            logger.error(f"RAG retrieve lỗi: {e}")
            return "", []

    def build_rag_prompt(self, query: str, context: str, sources: list[dict]) -> str:
        """
        Xây dựng prompt có RAG context cho LLM.
        Inject vào system prompt của LLM service.
        """
        if not context:
            return ""  # LLM dùng kiến thức tổng quát

        source_list = "\n".join([
            f"  - {s['source']} (trang {s['page']}, độ liên quan: {s['score']})"
            for s in sources[:3]
        ])

        return f"""
Dưới đây là thông tin từ tài liệu du lịch liên quan đến câu hỏi của khách:

=== TÀI LIỆU THAM KHẢO ===
{context}
=== HẾT TÀI LIỆU ===

Nguồn tài liệu:
{source_list}

Hãy trả lời dựa trên tài liệu trên. Nếu tài liệu không đủ thông tin, hãy nói thêm từ kiến thức chung về du lịch Việt Nam.
"""

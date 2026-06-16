#!/usr/bin/env python3
"""
🏛️ Ingest tài liệu du lịch vào Qdrant Cloud
Chạy: python ingest.py

Đặt các file PDF/Word vào thư mục ./data/ trước khi chạy.
"""
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Dùng absolute path tính từ vị trí file ingest.py để tránh lỗi khi chạy từ thư mục khác
_INGEST_DIR = Path(__file__).resolve().parent
DATA_DIR = os.getenv("DATA_DIR", str(_INGEST_DIR / "data"))
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION_NAME = "tourism_knowledge"
CHUNK_SIZE = 150      # tokens per chunk (PhoBERT max ~256 tokens)
CHUNK_OVERLAP = 30   # tokens overlap


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Chia text thành các chunk nhỏ theo từ."""
    words = text.split()
    chunks = []
    step = chunk_size - overlap
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if len(chunk.strip()) > 100:
            chunks.append(chunk.strip())
    return chunks


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "dangvantuan/vietnamese-embedding")


def main():
    # Thử đọc từ .env
    env_file = Path("../.env") if not Path(".env").exists() else Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

    # Re-read after .env parsing
    qdrant_url = os.getenv("QDRANT_URL", QDRANT_URL)
    qdrant_api_key = os.getenv("QDRANT_API_KEY", QDRANT_API_KEY)

    if not qdrant_url or not qdrant_api_key:
        print("❌ Cần QDRANT_URL và QDRANT_API_KEY để kết nối Qdrant Cloud!")
        print("   Thêm vào file .env:")
        print("   QDRANT_URL=https://your-cluster.cloud.qdrant.io")
        print("   QDRANT_API_KEY=your-api-key")
        sys.exit(1)

    # Import sau khi có API key
    try:
        from langchain_qdrant import QdrantVectorStore
        from langchain_community.embeddings import HuggingFaceEmbeddings
        from langchain_core.documents import Document
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams
    except ImportError as e:
        print(f"❌ Thiếu dependency: {e}")
        print("   Chạy: uv add langchain-core langchain-community langchain-qdrant qdrant-client sentence-transformers")
        sys.exit(1)

    from services.document_loader import load_document

    # Kiểm tra thư mục data
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        data_path.mkdir(parents=True)
        print(f"📁 Đã tạo thư mục {DATA_DIR}")
        print(f"   Hãy đặt các file PDF/Word vào {DATA_DIR}/ rồi chạy lại!")
        sys.exit(0)

    # Tìm tất cả file tài liệu
    supported_exts = [".pdf", ".docx", ".doc", ".txt", ".md"]
    files = []
    for ext in supported_exts:
        files.extend(data_path.glob(f"**/*{ext}"))

    if not files:
        print(f"⚠️  Không tìm thấy tài liệu trong {DATA_DIR}/")
        print(f"   Hỗ trợ: {', '.join(supported_exts)}")

    print(f"\n🔍 Tìm thấy {len(files)} file tài liệu:")
    for f in files:
        print(f"   📄 {f.name}")

    # Khởi tạo embeddings
    embedding_model = os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)
    print(f"\n⚙️  Đang load HuggingFace Embedding ({embedding_model})...")
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    print(f"✅ Embedding model loaded: {embedding_model}")

    # Load & chunk tất cả tài liệu
    print(f"\n📖 Đang xử lý tài liệu...\n")
    all_docs = []
    total_chunks = 0

    for file_path in files:
        file_docs = 0
        for page_data in load_document(str(file_path)):
            chunks = chunk_text(page_data["text"])
            for i, chunk in enumerate(chunks):
                meta = page_data["metadata"].copy()
                meta["chunk_id"] = f"{file_path.stem}_p{meta['page']}_c{i}"
                # ── Metadata mở rộng cho Filtering ──────────────────────────
                # Gán tự động dựa trên tên file; có thể mở rộng bằng config YAML
                meta.setdefault("department", "general")
                meta.setdefault("urgency",    "normal")
                meta.setdefault("tags",       "tourism,vietnam")
                # Phân loại nhanh theo tên file
                name_lower = file_path.stem.lower()
                if any(k in name_lower for k in ["hanoi", "ha_noi", "thủ đô"]):
                    meta["tags"] = "tourism,vietnam,hanoi"
                elif any(k in name_lower for k in ["hoian", "hoi_an", "hội an"]):
                    meta["tags"] = "tourism,vietnam,hoian"
                elif any(k in name_lower for k in ["sapa", "sa pa"]):
                    meta["tags"] = "tourism,vietnam,sapa"
                # ─────────────────────────────────────────────────────────────
                all_docs.append(Document(page_content=chunk, metadata=meta))
                file_docs += 1
        total_chunks += file_docs
        print(f"   ✅ {file_path.name}: {file_docs} chunks")

    print(f"\n📊 Tổng: {total_chunks} chunks từ {len(files)} file")

    if total_chunks == 0:
        print("\n❌ Không có chunk nào được tạo ra!")
        print("   Kiểm tra lại file tài liệu trong thư mục data/")
        print("   Đảm bảo PyMuPDF đã cài: pip install pymupdf")
        sys.exit(1)

    # Kết nối Qdrant Cloud
    print(f"\n💾 Đang kết nối Qdrant Cloud ({qdrant_url})...")
    client = QdrantClient(
        url=qdrant_url,
        api_key=qdrant_api_key,
    )

    # Xóa collection cũ để tránh duplicate khi ingest lại
    try:
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        if COLLECTION_NAME in collection_names:
            client.delete_collection(COLLECTION_NAME)
            print(f"   🧹 Đã xóa collection cũ: {COLLECTION_NAME}")
    except Exception as e:
        print(f"   ⚠️  Lỗi khi kiểm tra collection: {e}")

    # Batch để tránh rate limit
    print(f"\n📤 Đang upload {total_chunks} chunks lên Qdrant Cloud...")
    batch_size = 100
    vectorstore = None

    for i in range(0, len(all_docs), batch_size):
        batch = all_docs[i:i + batch_size]
        if vectorstore is None:
            vectorstore = QdrantVectorStore.from_documents(
                documents=batch,
                embedding=embeddings,
                url=qdrant_url,
                api_key=qdrant_api_key,
                collection_name=COLLECTION_NAME,
            )
        else:
            vectorstore.add_documents(batch)

        progress = min(i + batch_size, len(all_docs))
        print(f"   [{progress}/{len(all_docs)}] chunks đã upload...", end="\r")

    # Xác nhận kết quả
    try:
        collection_info = client.get_collection(COLLECTION_NAME)
        count = collection_info.points_count
    except Exception:
        count = total_chunks

    print(f"\n\n✅ Hoàn tất! Qdrant Cloud đã sẵn sàng")
    print(f"   URL: {qdrant_url}")
    print(f"   Collection: {COLLECTION_NAME}")
    print(f"   Tổng chunks: {count}")
    print(f"\n🚀 Giờ chạy backend: python main.py\n")




if __name__ == "__main__":
    main()

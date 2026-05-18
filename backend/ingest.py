#!/usr/bin/env python3
"""
🏛️ Ingest tài liệu du lịch vào ChromaDB
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
CHROMA_DIR = os.getenv("CHROMA_DB_PATH", str(_INGEST_DIR / "chroma_db"))
COLLECTION_NAME = "tourism_knowledge"
CHUNK_SIZE = 500      # tokens per chunk
CHUNK_OVERLAP = 50   # tokens overlap


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


def main():
    # Kiểm tra API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Thử đọc từ .env
        env_file = Path("../.env") if not Path(".env").exists() else Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    os.environ["OPENAI_API_KEY"] = api_key
                    break
    
    if not api_key:
        print("❌ Cần OPENAI_API_KEY để tạo embeddings!")
        print("   Thêm vào file .env: OPENAI_API_KEY=sk-...")
        sys.exit(1)

    # Import sau khi có API key
    try:
        from langchain_community.vectorstores import Chroma
        from langchain_openai import OpenAIEmbeddings
        try:
            from langchain_core.documents import Document
        except ImportError:
            from langchain.schema import Document  # fallback phiên bản cũ
    except ImportError as e:
        print(f"❌ Thiếu dependency: {e}")
        print("   Chạy: pip install langchain langchain-core langchain-community langchain-openai chromadb")
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
    print(f"\n⚙️  Khởi tạo OpenAI Embeddings (text-embedding-3-small)...")
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key
    )

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

    # Lưu vào ChromaDB
    print(f"\n💾 Đang lưu vào ChromaDB ({CHROMA_DIR})...")

    # Xóa index cũ để tránh duplicate khi ingest lại
    chroma_path = Path(CHROMA_DIR)
    if chroma_path.exists():
        import shutil
        shutil.rmtree(chroma_path)
        print(f"   🧹 Đã xóa index cũ tại {CHROMA_DIR}")

    # Batch để tránh rate limit
    batch_size = 100
    vectorstore = None

    for i in range(0, len(all_docs), batch_size):
        batch = all_docs[i:i + batch_size]
        if vectorstore is None:
            vectorstore = Chroma.from_documents(
                documents=batch,
                embedding=embeddings,
                persist_directory=CHROMA_DIR,
                collection_name=COLLECTION_NAME
            )
        else:
            vectorstore.add_documents(batch)
        
        progress = min(i + batch_size, len(all_docs))
        print(f"   [{progress}/{len(all_docs)}] chunks đã lưu...", end="\r")

    print(f"\n\n✅ Hoàn tất! ChromaDB đã sẵn sàng tại: {CHROMA_DIR}")
    print(f"   Collection: {COLLECTION_NAME}")
    if vectorstore is not None:
        try:
            count = vectorstore._collection.count()
        except Exception:
            count = total_chunks
    else:
        count = total_chunks
    print(f"   Tổng chunks: {count}")
    print(f"\n🚀 Giờ chạy backend: python main.py\n")




if __name__ == "__main__":
    main()

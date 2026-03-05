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

DATA_DIR = os.getenv("DATA_DIR", "./data")
CHROMA_DIR = os.getenv("CHROMA_DB_PATH", "./chroma_db")
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
            for line in env_file.read_text().splitlines():
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
        from langchain.schema import Document
    except ImportError as e:
        print(f"❌ Thiếu dependency: {e}")
        print("   Chạy: pip install langchain langchain-community langchain-openai chromadb")
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
        
        # Tạo tài liệu mẫu
        sample_file = data_path / "sample_hanoi.txt"
        sample_file.write_text(SAMPLE_CONTENT, encoding="utf-8")
        print(f"✅ Đã tạo tài liệu mẫu: {sample_file}")
        files = [sample_file]

    print(f"\n🔍 Tìm thấy {len(files)} file tài liệu:")
    for f in files:
        print(f"   📄 {f.name}")

    # Khởi tạo embeddings
    print(f"\n⚙️  Khởi tạo OpenAI Embeddings (text-embedding-3-small)...")
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=api_key
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
                all_docs.append(Document(page_content=chunk, metadata=meta))
                file_docs += 1
        total_chunks += file_docs
        print(f"   ✅ {file_path.name}: {file_docs} chunks")

    print(f"\n📊 Tổng: {total_chunks} chunks từ {len(files)} file")

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
    print(f"   Tổng chunks: {vectorstore._collection.count()}")
    print(f"\n🚀 Giờ chạy backend: python main.py\n")


SAMPLE_CONTENT = """
Hà Nội - Thủ đô ngàn năm văn hiến

Hà Nội là thủ đô của Việt Nam, nằm ở đồng bằng sông Hồng, miền Bắc Việt Nam.
Thành phố có lịch sử hơn 1000 năm với nhiều di tích văn hóa lịch sử quý giá.

Hồ Hoàn Kiếm - Trái tim của Hà Nội
Hồ Hoàn Kiếm hay còn gọi là Hồ Gươm nằm ngay trung tâm Hà Nội.
Theo truyền thuyết, vua Lê Lợi trả lại thanh gươm thần cho Rùa vàng tại đây sau khi đánh đuổi quân Minh.
Tháp Rùa nằm giữa hồ là biểu tượng nổi tiếng của Hà Nội.
Đền Ngọc Sơn trên đảo nhỏ trong hồ được kết nối với bờ bằng cầu Thê Húc màu đỏ.

Phố cổ Hà Nội
Khu phố cổ Hà Nội gồm 36 phố phường, mỗi phố chuyên bán một loại hàng hóa.
Phố Hàng Đào chuyên vải lụa, Phố Hàng Bạc chuyên đồ bạc, Phố Hàng Gai chuyên đồ thủ công.
Kiến trúc nhà ống đặc trưng với mặt tiền hẹp nhưng chiều sâu lớn.
Thời gian tốt nhất để thăm: sáng sớm hoặc chiều tối để tránh nắng.

Văn Miếu - Quốc Tử Giám
Văn Miếu được xây dựng năm 1070 dưới triều vua Lý Thánh Tông.
Đây là trường đại học đầu tiên của Việt Nam, đào tạo nhân tài cho đất nước.
82 bia tiến sĩ khắc tên các vị đỗ đạt từ 1442 đến 1779.
Giờ mở cửa: 8h-17h các ngày trong tuần.
Giá vé: 30.000đ người lớn, 15.000đ học sinh.

Ẩm thực Hà Nội
Phở Hà Nội có nước dùng trong, ngọt từ xương bò, thịt mỏng và bánh phở mềm.
Bún chả là món đặc sản với bún trắng, chả nướng và nước chấm chua ngọt.
Bánh cuốn Thanh Trì được làm từ gạo xay mịn, tráng mỏng, nhân thịt và mộc nhĩ.
Chả cá Lã Vọng là món ăn truyền thống với cá lăng nướng trên than hoa.
Cà phê trứng Hà Nội - đặc sản độc đáo với lòng đỏ trứng đánh bông phủ lên cà phê.

Hội An - Phố cổ UNESCO

Hội An là thành phố cổ nằm bên bờ sông Thu Bồn, tỉnh Quảng Nam.
Được UNESCO công nhận là Di sản Văn hóa Thế giới năm 1999.

Kiến trúc độc đáo
Hội An có hơn 1000 công trình kiến trúc cổ được bảo tồn nguyên vẹn.
Chùa Cầu - biểu tượng của Hội An, được xây dựng vào thế kỷ 18 bởi người Nhật.
Nhà cổ Tấn Ký có tuổi đời hơn 200 năm với kiến trúc pha trộn Nhật-Trung-Việt.

Ẩm thực Hội An
Cao lầu - món mì đặc trưng chỉ có ở Hội An, nước dùng từ tro củi Cham.
Mì Quảng - sợi mì vàng với tôm, thịt, rau sống và bánh đa giòn.
Bánh mì Hội An nổi tiếng thế giới với vỏ giòn, nhân đa dạng.

Thời điểm tốt nhất để đến Hội An: tháng 2-4 và tháng 8-10, tránh mùa mưa bão.
"""

if __name__ == "__main__":
    main()

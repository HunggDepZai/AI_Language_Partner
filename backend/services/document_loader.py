"""
Document Loader — Nạp tài liệu du lịch PDF/Word vào ChromaDB
Chạy: python ingest.py
"""
import os
import logging
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)


def load_pdf(file_path: str) -> Generator:
    """Load PDF bằng PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        filename = Path(file_path).name
        total_pages = len(doc)

        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text").strip()
            if len(text) < 50:  # Bỏ trang quá ngắn
                continue
            yield {
                "text": text,
                "metadata": {
                    "source": filename,
                    "page": page_num,
                    "total_pages": total_pages,
                    "file_type": "pdf"
                }
            }
        doc.close()
        logger.info(f"✅ Loaded PDF: {filename} ({total_pages} trang)")

    except ImportError:
        logger.error("Chưa cài PyMuPDF. Chạy: pip install pymupdf")
    except Exception as e:
        logger.error(f"Lỗi load PDF {file_path}: {e}")


def load_docx(file_path: str) -> Generator:
    """Load Word document."""
    try:
        from docx import Document
        doc = Document(file_path)
        filename = Path(file_path).name
        full_text = []

        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())

        # Gom thành chunks theo đoạn (mỗi 10 đoạn = 1 chunk)
        chunk_size = 10
        for i in range(0, len(full_text), chunk_size):
            chunk = "\n".join(full_text[i:i + chunk_size])
            if len(chunk) < 50:
                continue
            yield {
                "text": chunk,
                "metadata": {
                    "source": filename,
                    "page": f"đoạn {i//chunk_size + 1}",
                    "file_type": "docx"
                }
            }
        logger.info(f"✅ Loaded DOCX: {filename}")

    except ImportError:
        logger.error("Chưa cài python-docx. Chạy: pip install python-docx")
    except Exception as e:
        logger.error(f"Lỗi load DOCX {file_path}: {e}")


def load_txt(file_path: str) -> Generator:
    """Load plain text file."""
    filename = Path(file_path).name
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        # Chia theo dòng trống (đoạn văn)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunk_size = 5
        for i in range(0, len(paragraphs), chunk_size):
            chunk = "\n\n".join(paragraphs[i:i + chunk_size])
            if len(chunk) < 50:
                continue
            yield {
                "text": chunk,
                "metadata": {
                    "source": filename,
                    "page": f"đoạn {i//chunk_size + 1}",
                    "file_type": "txt"
                }
            }
        logger.info(f"✅ Loaded TXT: {filename}")
    except Exception as e:
        logger.error(f"Lỗi load TXT {file_path}: {e}")


def load_document(file_path: str) -> Generator:
    """Auto-detect file type và load."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        yield from load_pdf(file_path)
    elif ext in (".docx", ".doc"):
        yield from load_docx(file_path)
    elif ext in (".txt", ".md"):
        yield from load_txt(file_path)
    else:
        logger.warning(f"Không hỗ trợ định dạng: {ext}")

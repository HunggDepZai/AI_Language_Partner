import re

# Từ điển viết tắt phổ biến
ABBREVIATIONS = {
    r"\bTCN\b": "Trước công nguyên",
    r"\bSCN\b": "Sau công nguyên",
    r"\bkm\b": "ki lô mét",
    r"\bm\b": "mét",
    r"\bkg\b": "ki lô gam",
    r"\bg\b": "gam",
    r"\bđ\b": "đồng",
    r"\bvnđ\b": "việt nam đồng",
    r"\bUSD\b": "đô la mỹ",
    r"\bTP\b": "thành phố",
    r"\bHĐND\b": "Hội đồng nhân dân",
    r"\bUBND\b": "Ủy ban nhân dân",
}

def number_to_vietnamese(number_str):
    """
    Chuyển đổi chuỗi số (có thể có dấu chấm/phẩy) sang chữ.
    Ví dụ: 50.000 -> năm mươi nghìn
    LƯU Ý: Đây là bản rút gọn, xử lý các trường hợp phổ biến.
    """
    # Xóa bỏ dấu chấm phân cách hàng nghìn
    clean_num = number_str.replace(".", "").replace(",", "")
    if not clean_num.isdigit():
        return number_str
    
    try:
        from num2words import num2words
        return num2words(int(clean_num), lang='vi')
    except ImportError:
        # Fallback nếu không có thư viện num2words
        return number_str

def normalize_vietnamese_text(text: str) -> str:
    """
    Chuẩn hóa văn bản tiếng Việt cho TTS.
    """
    if not text:
        return ""

    # 1. Xử lý các từ viết tắt
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 2. Tìm và xử lý các con số (VD: 50.000, 1.234)
    # Regex tìm các cụm số có dấu chấm/phẩy
    number_pattern = r'\b\d{1,3}(?:\.\d{3})*(?:,\d+)?\b|\b\d+\b'
    
    def replace_num(match):
        return number_to_vietnamese(match.group(0))

    try:
        # Chỉ xử lý số nếu có thư viện hỗ trợ truyền tải tự nhiên
        import num2words
        text = re.sub(number_pattern, replace_num, text)
    except ImportError:
        pass

    # 3. Làm sạch ký tự lạ
    text = text.replace("*", "").replace("_", "").replace("#", "")
    
    return text

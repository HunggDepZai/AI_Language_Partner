# 🇻🇳 HƯỚNG DẪN CHẠY PROJECT — Trợ Lý AI Tiếng Việt

> Từ 0 đến chạy được trong **5 phút**

---

## 📋 Bước 0: Chuẩn bị (chỉ cần làm 1 lần)

### ✅ Cài Python 3.10+
```bash
# Kiểm tra đã có chưa
python --version        # hoặc python3 --version

# Nếu chưa có → tải tại: https://www.python.org/downloads/
# Windows: nhớ tick ✅ "Add Python to PATH" khi cài
```

### ✅ Cài Node.js 18+
```bash
# Kiểm tra đã có chưa
node --version

# Nếu chưa có → tải tại: https://nodejs.org/
```

### ✅ Lấy API Key (chọn 1 trong 2)

**Cách 1 — OpenAI (trả phí, chất lượng cao nhất):**
1. Vào https://platform.openai.com/api-keys
2. Tạo tài khoản → Nạp $5 credit
3. Nhấn "Create new secret key" → Copy key `sk-...`

**Cách 2 — Groq (MIỄN PHÍ, nhanh hơn):**
1. Vào https://console.groq.com/keys
2. Đăng ký bằng Google/GitHub
3. Nhấn "Create API Key" → Copy key `gsk_...`

---

## 🚀 Bước 1: Tải project

```bash
# Giải nén file đã tải
tar -xzf vietnamese-voice-ai.tar.gz
cd vietnamese-voice-ai
```

Hoặc nếu clone từ GitHub:
```bash
git clone <repo-url>
cd vietnamese-voice-ai
```

---

## 🔑 Bước 2: Cấu hình API Key

```bash
# Copy file cấu hình mẫu
cp .env.example .env
```

Mở file `.env` bằng bất kỳ text editor nào và **điền API key:**

### Nếu dùng OpenAI:
```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

STT_PROVIDER=openai
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
TTS_ENGINE=edge
```

### Nếu dùng Groq (MIỄN PHÍ):
```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx

STT_PROVIDER=groq
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
TTS_ENGINE=edge
```

> 💡 **TTS_ENGINE=edge** là giọng nói Microsoft miễn phí, không cần key gì thêm!

---

## 📦 Bước 3: Cài đặt dependencies

### Cách nhanh (Linux/Mac):
```bash
chmod +x setup.sh
./setup.sh
```

### Cách thủ công (Windows hoặc nếu script lỗi):

**Terminal 1 — Cài Backend:**
```bash
cd backend
pip install -r requirements.txt
```

> ⚠️ Nếu gặp lỗi `torch` quá nặng, có thể bỏ qua VAD bằng cách xóa 2 dòng cuối
> trong `requirements.txt` (dòng `torch` và `torchaudio`). VAD là optional.

**Terminal 2 — Cài Frontend:**
```bash
cd frontend
npm install
```

---

## ▶️ Bước 4: Chạy ứng dụng

### Cách nhanh (Linux/Mac):
```bash
./run.sh
```

### Cách thủ công (KHUYÊN DÙNG cho Windows):

**Mở Terminal 1 — Chạy Backend:**
```bash
cd backend
python main.py
```

Thấy dòng này là thành công:
```
🚀 Khởi động Vietnamese Voice AI Assistant...
✅ Tất cả services đã sẵn sàng!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Mở Terminal 2 — Chạy Frontend:**
```bash
cd frontend
npm run dev
```

Thấy dòng này là thành công:
```
  VITE v6.x.x  ready in xxx ms
  ➜  Local:   http://localhost:3000/
```

---

## 🌐 Bước 5: Sử dụng

1. **Mở trình duyệt** → Vào `http://localhost:3000`
2. **Nhấn nút micro** (mũi tên) để kết nối lần đầu
3. **Cho phép microphone** khi browser hỏi
4. **Giữ nút micro** → Nói tiếng Việt → **Thả ra** để gửi
5. Chờ AI nhận dạng → Suy nghĩ → Trả lời bằng giọng nói tiếng Việt!

### Các nút điều khiển:
| Nút | Chức năng |
|-----|-----------|
| 🎤 **Giữ micro** | Giữ để nói, thả để gửi |
| ⏸️ **Nhấn khi AI nói** | Ngắt AI giữa chừng |
| 🗑️ **Xóa** | Xóa lịch sử hội thoại |
| 📋 **Chọn giọng** | Đổi giọng nam/nữ |

---

## 🐳 Chạy bằng Docker (thay thế Bước 3-4)

Nếu đã có Docker:
```bash
# Đảm bảo đã có file .env (Bước 2)
docker compose up --build

# Mở http://localhost:3000
```

Dừng:
```bash
docker compose down
```

---

## ❓ Xử lý lỗi

### "Không kết nối được server"
→ Backend chưa chạy. Kiểm tra Terminal 1 có lỗi gì không.

### "Không truy cập microphone"
→ Nhấn vào icon 🔒 trên thanh địa chỉ browser → Cho phép Microphone.
→ Phải dùng `http://localhost:3000`, không dùng IP khác (browser chặn mic trên HTTP).

### "openai.AuthenticationError" hoặc "Invalid API Key"
→ Kiểm tra lại API key trong file `.env`. Đảm bảo không có khoảng trắng thừa.

### "Không nghe rõ, vui lòng nói lại"
→ Nói to hơn, rõ hơn. Giữ nút micro ít nhất 1-2 giây.

### pip install lỗi torch
→ Torch rất nặng (~2GB). Có thể bỏ qua:
```bash
# Sửa requirements.txt, xóa 2 dòng:
# torch>=2.0.0
# torchaudio>=2.0.0

# Rồi cài lại
pip install -r requirements.txt
```
VAD sẽ tự tắt, project vẫn chạy bình thường.

### Frontend lỗi "Cannot find module"
```bash
cd frontend
rm -rf node_modules
npm install
npm run dev
```

### Port 8000 hoặc 3000 đã bị chiếm
```bash
# Tìm process đang dùng port
# Linux/Mac:
lsof -i :8000
kill -9 <PID>

# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

---

## 🔄 Quy trình hoạt động

```
Bạn nói tiếng Việt
        ↓
   [Microphone thu âm]
        ↓ WebSocket
   [Silero VAD] → Phát hiện có người nói
        ↓
   [Whisper API] → "Xin chào, hôm nay thời tiết thế nào?"
        ↓
   [GPT-4o streaming] → "Chào bạn! Hôm nay trời khá đẹp..."
        ↓ (từng câu một)
   [Edge-TTS Vietnamese] → 🔊 Phát giọng nói
        ↓
   Bạn nghe AI trả lời bằng tiếng Việt
```

---

## 💰 Chi phí ước tính

| Combo | STT | LLM | TTS | Chi phí/cuộc hội thoại |
|-------|-----|-----|-----|------------------------|
| **Miễn phí** | Groq (free) | Groq Llama (free) | Edge-TTS (free) | **$0** |
| **Rẻ nhất** | Groq (free) | GPT-4o-mini | Edge-TTS (free) | **~$0.005** |
| **Tốt nhất** | Groq (free) | GPT-4o | Edge-TTS (free) | **~$0.02** |

> Groq cho miễn phí 14,400 giây STT/ngày + 14,400 request LLM/ngày
> Edge-TTS hoàn toàn miễn phí, không giới hạn

---

**Chúc bạn thành công! 🎉**

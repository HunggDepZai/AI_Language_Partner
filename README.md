# 🇻🇳 Trợ Lý AI Tiếng Việt — Vietnamese Voice AI Assistant

> Trò chuyện bằng giọng nói tiếng Việt với AI, tương tự ChatGPT Advanced Voice Mode.

![Pipeline](https://img.shields.io/badge/Pipeline-VAD→STT→LLM→TTS-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![React](https://img.shields.io/badge/React-18-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🎯 Tính năng

- 🎤 **Nhận dạng giọng nói tiếng Việt** — Whisper Large V3 (OpenAI/Groq)
- 🧠 **Trí tuệ nhân tạo** — GPT-4o / GPT-4o-mini / Llama / Ollama
- 🔊 **Giọng nói AI tiếng Việt** — Edge-TTS (miễn phí) / VieNeu-TTS (local) / VietTTS
- ⚡ **Streaming thời gian thực** — AI trả lời theo từng câu, không phải chờ hết
- 🎛️ **2 giọng Việt** — Hoài My (nữ) và Nam Minh (nam)
- 🛑 **Ngắt giữa chừng** — Nhấn để ngắt khi AI đang nói
- 📱 **Responsive** — Chạy tốt trên điện thoại
- 🐳 **Docker** — 1 lệnh chạy tất cả

---

## 🏗️ Kiến trúc

```
┌─────────────────────────────────────────────┐
│                  FRONTEND                    │
│          React + Vite + WebSocket           │
│    ┌──────┐  ┌──────┐  ┌───────────┐       │
│    │ Mic  │→ │Record│→ │ WebSocket │──┐    │
│    └──────┘  └──────┘  └───────────┘  │    │
│    ┌──────┐  ┌──────┐  ┌───────────┐  │    │
│    │Speaker│← │ Play │← │  Audio   │←─┘    │
│    └──────┘  └──────┘  └───────────┘       │
└─────────────────────────────────────────────┘
                    ↕ WebSocket
┌─────────────────────────────────────────────┐
│                  BACKEND                     │
│              FastAPI + Python                │
│                                             │
│  Audio → [VAD] → [STT] → [LLM] → [TTS] → Audio
│           │        │        │        │       │
│         Silero   Whisper  GPT-4o  Edge-TTS  │
│          VAD    Large V3          Tiếng Việt │
└─────────────────────────────────────────────┘
```

---

## 🚀 Cài đặt nhanh (3 phút)

### Yêu cầu
- Python 3.10+
- Node.js 18+
- OpenAI API key (hoặc Groq API key miễn phí)

### Cách 1: Script tự động

```bash
git clone https://github.com/your-repo/vietnamese-voice-ai.git
cd vietnamese-voice-ai

# Cài đặt tất cả
chmod +x setup.sh run.sh
./setup.sh

# Chạy
./run.sh

# Mở http://localhost:3000
```

### Cách 2: Chạy thủ công

```bash
# 1. Clone project
git clone https://github.com/your-repo/vietnamese-voice-ai.git
cd vietnamese-voice-ai

# 2. Cấu hình
cp .env.example .env
# Mở .env và điền OPENAI_API_KEY=sk-...

# 3. Cài backend
cd backend
pip install -r requirements.txt
cd ..

# 4. Cài frontend
cd frontend
npm install
cd ..

# 5. Chạy backend (Terminal 1)
cd backend
python main.py

# 6. Chạy frontend (Terminal 2)
cd frontend
npm run dev

# 7. Mở http://localhost:3000
```

### Cách 3: Docker

```bash
cp .env.example .env
# Điền API key vào .env

docker compose up --build

# Mở http://localhost:3000
```

---

## ⚙️ Cấu hình

Chỉnh file `.env` để thay đổi cấu hình:

### STT (Nhận dạng giọng nói)

| Provider | Model | Tốc độ | Chi phí | Cách dùng |
|----------|-------|--------|---------|-----------|
| **OpenAI** | whisper-1 | ~1-2s | $0.006/phút | `STT_PROVIDER=openai` |
| **Groq** | whisper-large-v3 | ~0.1s | Miễn phí* | `STT_PROVIDER=groq` |

*Groq miễn phí 14,400 giây/ngày

### LLM (Trí tuệ nhân tạo)

| Provider | Model | Chất lượng | Chi phí |
|----------|-------|-----------|---------|
| **OpenAI** | gpt-4o-mini | ⭐⭐⭐⭐ | Rẻ |
| **OpenAI** | gpt-4o | ⭐⭐⭐⭐⭐ | Trung bình |
| **Groq** | llama-3.3-70b-versatile | ⭐⭐⭐⭐ | Miễn phí* |
| **Ollama** | qwen2.5:7b | ⭐⭐⭐ | Miễn phí (local) |

### TTS (Giọng nói AI)

| Engine | Giọng Việt | Chất lượng | Chi phí | GPU |
|--------|-----------|-----------|---------|-----|
| **Edge-TTS** | Hoài My, Nam Minh | ⭐⭐⭐⭐ | Miễn phí | Không |
| **VieNeu-TTS** | Voice cloning | ⭐⭐⭐⭐⭐ | Miễn phí | Không (CPU) |
| **VietTTS** | 10+ giọng | ⭐⭐⭐⭐⭐ | Miễn phí | Có (NVIDIA) |

---

## 💡 Combo gợi ý

### 🆓 Hoàn toàn miễn phí (chất lượng tốt)
```env
STT_PROVIDER=groq
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
TTS_ENGINE=edge
```

### 💰 Chất lượng cao nhất (~$0.02/cuộc hội thoại)
```env
STT_PROVIDER=groq
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
TTS_ENGINE=edge
```

### 🖥️ Offline hoàn toàn (cần máy mạnh)
```env
STT_PROVIDER=openai  # thay bằng local whisper
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
TTS_ENGINE=vieneu
OLLAMA_URL=http://localhost:11434
```

---

## 📁 Cấu trúc project

```
vietnamese-voice-ai/
├── .env.example          # Mẫu cấu hình
├── docker-compose.yml    # Docker deployment
├── setup.sh             # Script cài đặt tự động
├── run.sh               # Script chạy ứng dụng
├── README.md            # Tài liệu này
│
├── backend/
│   ├── main.py          # FastAPI server + WebSocket
│   ├── requirements.txt # Python dependencies
│   ├── Dockerfile
│   └── services/
│       ├── vad_service.py   # Silero VAD - phát hiện giọng nói
│       ├── stt_service.py   # Whisper - nhận dạng tiếng Việt
│       ├── llm_service.py   # GPT-4o - xử lý ngôn ngữ
│       └── tts_service.py   # Edge-TTS - tổng hợp giọng nói
│
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── Dockerfile
    └── src/
        ├── main.jsx
        ├── App.jsx          # Main app component
        ├── styles.css       # Global styles
        ├── hooks/
        │   └── useVoiceChat.js  # WebSocket + audio logic
        └── components/
            ├── ChatMessages.jsx    # Hiển thị tin nhắn
            ├── VoiceControl.jsx    # Nút mic + controls
            └── AudioVisualizer.jsx # Sóng âm thanh
```

---

## 🔧 Nâng cấp

### Thêm VieNeu-TTS (TTS local, voice cloning)

```bash
# Windows
pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/

# macOS
pip install vieneu --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/metal/

# Linux
pip install vieneu

# Đổi .env
TTS_ENGINE=vieneu
```

### Thêm VietTTS Server (nhiều giọng đẹp, cần GPU)

```bash
git clone https://github.com/dangvansam/viet-tts.git
cd viet-tts
docker compose up -d
# Server chạy tại http://localhost:8298

# Đổi .env
TTS_ENGINE=viettts
VIETTTS_URL=http://localhost:8298
```

### Dùng Ollama (LLM offline)

```bash
# Cài Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Tải model
ollama pull qwen2.5:7b

# Đổi .env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
```

---

## 🐛 Xử lý lỗi thường gặp

| Lỗi | Nguyên nhân | Cách fix |
|-----|-------------|----------|
| "Không kết nối được server" | Backend chưa chạy | Chạy `cd backend && python main.py` |
| "Không truy cập microphone" | Browser chặn mic | Cho phép quyền mic trong browser settings |
| "Không nghe rõ" | Âm thanh quá ngắn/nhỏ | Nói to hơn, giữ nút lâu hơn |
| OpenAI API error | Sai API key | Kiểm tra OPENAI_API_KEY trong .env |
| "Module not found" | Chưa cài dependencies | Chạy `pip install -r requirements.txt` |

---

## 📊 So sánh với các project khác

| Tính năng | Project này | VietGPT VoiceBot | HF Speech-to-Speech |
|-----------|-------------|-------------------|---------------------|
| Tiếng Việt native | ✅ | ✅ | ⚠️ (cần config) |
| Streaming response | ✅ | ❌ | ✅ |
| Web UI đẹp | ✅ | ❌ (terminal) | ❌ |
| Nhiều TTS engine | ✅ (3 engine) | ❌ (gTTS) | ✅ |
| Ngắt giữa chừng | ✅ | ❌ | ❌ |
| Voice cloning | ✅ (VieNeu) | ❌ | ❌ |
| Docker | ✅ | ❌ | ✅ |
| Dễ cài đặt | ✅ (3 phút) | ✅ | ⚠️ |

---

## 📝 License

MIT License - Sử dụng tự do cho mục đích cá nhân và thương mại.

---

## 🙏 Credits

- [OpenAI Whisper](https://github.com/openai/whisper) — Speech recognition
- [Edge-TTS](https://github.com/rany2/edge-tts) — Microsoft TTS miễn phí
- [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS) — Vietnamese TTS + voice cloning
- [VietTTS](https://github.com/dangvansam/viet-tts) — Vietnamese TTS server
- [Silero VAD](https://github.com/snakers4/silero-vad) — Voice Activity Detection
- [FastAPI](https://fastapi.tiangolo.com/) — Python web framework
- [Vite](https://vitejs.dev/) + [React](https://react.dev/) — Frontend

---

**Made with ❤️ for Vietnamese 🇻🇳**

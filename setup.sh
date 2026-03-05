#!/bin/bash
# ╔═══════════════════════════════════════════════════════╗
# ║  Vietnamese Voice AI Assistant - Quick Start          ║
# ║  Cài đặt và chạy tự động                             ║
# ╚═══════════════════════════════════════════════════════╝

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  🇻🇳  Trợ Lý AI Tiếng Việt - Cài Đặt Nhanh     ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Check Python ──
echo -e "${YELLOW}[1/5] Kiểm tra Python...${NC}"
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo -e "${RED}❌ Chưa cài Python! Hãy cài Python 3.10+ trước.${NC}"
    exit 1
fi
echo -e "${GREEN}  ✅ $($PYTHON --version)${NC}"

# ── Check Node.js ──
echo -e "${YELLOW}[2/5] Kiểm tra Node.js...${NC}"
if command -v node &>/dev/null; then
    echo -e "${GREEN}  ✅ Node $(node --version)${NC}"
else
    echo -e "${RED}❌ Chưa cài Node.js! Hãy cài Node 18+ trước.${NC}"
    exit 1
fi

# ── Setup .env ──
echo -e "${YELLOW}[3/5] Cấu hình API keys...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo -e "${YELLOW}  ⚠️  Chưa có file .env. Đã tạo từ .env.example${NC}"
    echo -e "${YELLOW}  📝 Hãy mở file .env và điền OPENAI_API_KEY${NC}"
    echo ""

    read -p "  Nhập OpenAI API Key (hoặc Enter để bỏ qua): " api_key
    if [ ! -z "$api_key" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/sk-your-openai-key-here/$api_key/" .env
        else
            sed -i "s/sk-your-openai-key-here/$api_key/" .env
        fi
        echo -e "${GREEN}  ✅ Đã lưu API key${NC}"
    fi

    read -p "  Nhập Groq API Key (hoặc Enter để bỏ qua): " groq_key
    if [ ! -z "$groq_key" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/gsk_your-groq-key-here/$groq_key/" .env
        else
            sed -i "s/gsk_your-groq-key-here/$groq_key/" .env
        fi
        echo -e "${GREEN}  ✅ Đã lưu Groq API key${NC}"
    fi
else
    echo -e "${GREEN}  ✅ File .env đã tồn tại${NC}"
fi

# ── Install Backend ──
echo -e "${YELLOW}[4/5] Cài đặt Backend (Python)...${NC}"
cd backend
$PYTHON -m pip install --upgrade pip -q
$PYTHON -m pip install -r requirements.txt -q 2>&1 | tail -5
echo -e "${GREEN}  ✅ Backend đã cài xong${NC}"
cd ..

# ── Install Frontend ──
echo -e "${YELLOW}[5/5] Cài đặt Frontend (React)...${NC}"
cd frontend
npm install --silent 2>&1 | tail -3
echo -e "${GREEN}  ✅ Frontend đã cài xong${NC}"
cd ..

# ── Done! ──
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ CÀI ĐẶT HOÀN TẤT!                          ║${NC}"
echo -e "${GREEN}╠═══════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                   ║${NC}"
echo -e "${GREEN}║  Chạy ứng dụng:                                  ║${NC}"
echo -e "${GREEN}║    ./run.sh                                       ║${NC}"
echo -e "${GREEN}║                                                   ║${NC}"
echo -e "${GREEN}║  Hoặc chạy thủ công:                              ║${NC}"
echo -e "${GREEN}║    Terminal 1: cd backend && python main.py       ║${NC}"
echo -e "${GREEN}║    Terminal 2: cd frontend && npm run dev         ║${NC}"
echo -e "${GREEN}║                                                   ║${NC}"
echo -e "${GREEN}║  Mở trình duyệt: http://localhost:3000           ║${NC}"
echo -e "${GREEN}║                                                   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

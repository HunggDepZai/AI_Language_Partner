#!/bin/bash
# ╔═══════════════════════════════════════════════════════╗
# ║  Vietnamese Voice AI - Khởi chạy                      ║
# ╚═══════════════════════════════════════════════════════╝

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}🇻🇳 Khởi động Trợ Lý AI Tiếng Việt...${NC}"
echo ""

# Check .env
if [ ! -f .env ]; then
    echo -e "${RED}❌ Chưa có file .env! Chạy ./setup.sh trước.${NC}"
    exit 1
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Đang tắt servers...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}👋 Đã tắt. Hẹn gặp lại!${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start Backend
echo -e "${YELLOW}[1/2] Khởi động Backend (port 8000)...${NC}"
cd backend
python3 main.py &
BACKEND_PID=$!
cd ..
sleep 2

# Check if backend started
if kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${GREEN}  ✅ Backend đang chạy (PID: $BACKEND_PID)${NC}"
else
    echo -e "${RED}  ❌ Backend không khởi động được. Kiểm tra .env và logs.${NC}"
    exit 1
fi

# Start Frontend
echo -e "${YELLOW}[2/2] Khởi động Frontend (port 3000)...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..
sleep 3

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ Ứng dụng đã sẵn sàng!${NC}"
echo -e "${GREEN}  🌐 Mở trình duyệt: ${BLUE}http://localhost:3000${NC}"
echo -e "${GREEN}  🔌 API Backend:     ${BLUE}http://localhost:8000${NC}"
echo -e "${GREEN}  ⌨️  Nhấn Ctrl+C để dừng${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""

# Wait for both processes
wait

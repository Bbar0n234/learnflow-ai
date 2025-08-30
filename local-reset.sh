#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔄 LearnFlow AI - Reset Development Environment${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════${NC}"
echo -e "${RED}⚠️  WARNING: This will delete all local data and dependencies${NC}"
echo ""

# Запрос подтверждения
read -p "Are you sure you want to reset everything? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}✅ Reset cancelled${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Starting reset process...${NC}"

# Остановка всех Python процессов проекта
echo -e "${YELLOW}🛑 Stopping any running services...${NC}"
pkill -f "python -m learnflow.main" 2>/dev/null || true
pkill -f "python -m bot.main" 2>/dev/null || true
pkill -f "python main.py" 2>/dev/null || true
pkill -f "python -m prompt-config-service.main" 2>/dev/null || true
echo -e "  Stopped all Python processes"

# Остановка и удаление Docker контейнеров
echo -e "${YELLOW}🐳 Stopping and removing Docker containers...${NC}"
docker compose down -v 2>/dev/null || true
echo -e "  Removed all containers and volumes"

# Удаление виртуального окружения
if [ -d ".venv" ]; then
    echo -e "${YELLOW}📦 Removing virtual environment...${NC}"
    rm -rf .venv
    echo -e "  Removed .venv directory"
fi

# Очистка логов
if [ -d "logs" ]; then
    echo -e "${YELLOW}📄 Cleaning logs...${NC}"
    rm -rf logs/*.log
    echo -e "  Cleaned all log files"
fi

# Очистка временных данных
if [ -d "data" ]; then
    echo -e "${YELLOW}🗑️  Cleaning temporary data...${NC}"
    find data -type f -name "*.tmp" -delete 2>/dev/null || true
    find data -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo -e "  Cleaned temporary files"
fi

# Очистка Python кэша
echo -e "${YELLOW}🧹 Cleaning Python cache...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type f -name ".coverage" -delete 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
echo -e "  Cleaned Python cache files"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Reset complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Run ${YELLOW}./local-dev.sh${NC} to start fresh"
echo -e "  2. Dependencies will be reinstalled automatically"
echo -e "  3. Databases will be recreated"
echo -e "  4. Migrations will be applied"
echo ""
echo -e "${BLUE}Current status:${NC}"
echo -e "  • Virtual environment: ${RED}Removed${NC}"
echo -e "  • Docker containers:   ${RED}Removed${NC}"
echo -e "  • Docker volumes:      ${RED}Removed${NC}"
echo -e "  • Log files:          ${RED}Cleaned${NC}"
echo -e "  • Python cache:       ${RED}Cleaned${NC}"
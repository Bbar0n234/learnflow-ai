#!/bin/bash
set -e

# Переход в корневую директорию проекта
cd "$(dirname "$0")/.."

# Цвета для красивого вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting LearnFlow AI - Local Development Mode${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"

# Проверка .env.local
if [ ! -f .env.local ]; then
    echo -e "${YELLOW}📝 Creating .env.local from example...${NC}"
    cp .env.local.example .env.local
    echo -e "${RED}⚠️  Please edit .env.local with your API keys and run again${NC}"
    exit 1
fi

# Создание директории для логов
mkdir -p logs

# Загружаем переменные окружения из .env.local для дочерних процессов
export $(grep -v '^#' .env.local | xargs)

# Проверка зависимостей
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}📦 Installing dependencies (first time setup)...${NC}"
    uv sync
    echo -e "${GREEN}✅ Dependencies installed${NC}"
fi

# PostgreSQL
echo -e "${BLUE}🗄️  Starting PostgreSQL...${NC}"
docker compose up -d postgres

# Ждем PostgreSQL
echo -e "${YELLOW}⏳ Waiting for PostgreSQL to be ready...${NC}"
for i in {1..30}; do
    if docker compose exec postgres pg_isready -U postgres &>/dev/null; then
        # Контейнер готов, теперь проверяем доступность порта
        if PGPASSWORD=postgres psql -h 127.0.0.1 -p 5433 -U postgres -c "SELECT 1" &>/dev/null; then
            echo -e "${GREEN}✅ PostgreSQL is ready!${NC}"
            break
        fi
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ PostgreSQL failed to start${NC}"
        exit 1
    fi
    printf "."
    sleep 1
done
echo ""

# Создание баз данных
echo -e "${BLUE}📁 Creating databases if needed...${NC}"
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'learnflow'" | grep -q 1 || \
    (PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE learnflow;" && echo -e "  Created database: learnflow")
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'prompts_db'" | grep -q 1 || \
    (PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE prompts_db;" && echo -e "  Created database: prompts_db")

# Миграции Artifacts Service
echo -e "${BLUE}🔄 Running Artifacts Service migrations...${NC}"
(cd artifacts-service && DATABASE_URL="postgresql://postgres:postgres@localhost:5433/learnflow" uv run alembic upgrade head 2>/dev/null || true)
echo -e "${GREEN}✅ Migrations completed${NC}"

# Массив PID для отслеживания процессов
declare -a PIDS

# Запуск сервисов с live логами
echo -e "${BLUE}🚀 Starting all services with live logging...${NC}"
echo ""

# FastAPI
echo -e "  ${YELLOW}→${NC} Starting FastAPI..."
uv run --package learnflow-core python -m learnflow.api.main 2>&1 | tee logs/fastapi.log | sed "s/^/${BLUE}[FastAPI]${NC} /" &
PIDS+=($!)

# Artifacts Service
echo -e "  ${YELLOW}→${NC} Starting Artifacts Service..."
(cd artifacts-service && uv run python main.py 2>&1 | tee ../logs/artifacts.log | sed "s/^/${GREEN}[Artifacts]${NC} /") &
PIDS+=($!)

# Prompt Config Service (миграции применятся автоматически при старте)
echo -e "  ${YELLOW}→${NC} Starting Prompt Config Service..."
(cd prompt-config-service && uv run python main.py 2>&1 | tee ../logs/prompt-config.log | sed "s/^/${YELLOW}[PromptCfg]${NC} /") &
PIDS+=($!)

# Telegram Bot
echo -e "  ${YELLOW}→${NC} Starting Telegram Bot..."
uv run --package learnflow-bot python -m bot 2>&1 | tee logs/bot.log | sed "s/^/${RED}[Bot]${NC} /" &
PIDS+=($!)

# Функция для остановки всех сервисов
cleanup() {
    echo -e "\n${YELLOW}🛑 Stopping all services...${NC}"
    for pid in ${PIDS[@]}; do
        if kill -0 $pid 2>/dev/null; then
            kill $pid 2>/dev/null || true
            echo -e "  Stopped process $pid"
        fi
    done
    echo -e "${YELLOW}🛑 Stopping PostgreSQL...${NC}"
    docker compose down
    echo -e "${GREEN}✅ All services stopped${NC}"
    exit 0
}

# Обработка Ctrl+C
trap cleanup SIGINT SIGTERM EXIT

# Ждем пока сервисы запустятся
echo -e "${YELLOW}⏳ Waiting for services to start...${NC}"
sleep 7

# Проверка что все работает
echo -e "\n${BLUE}🔍 Checking service health...${NC}"
SERVICES_OK=true

if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅${NC} FastAPI is running at http://localhost:8000"
else
    echo -e "  ${RED}❌${NC} FastAPI failed to start (check logs/fastapi.log)"
    SERVICES_OK=false
fi

if curl -s -f http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅${NC} Artifacts Service is running at http://localhost:8001"
else
    echo -e "  ${RED}❌${NC} Artifacts Service failed to start (check logs/artifacts.log)"
    SERVICES_OK=false
fi

if curl -s -f http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅${NC} Prompt Config Service is running at http://localhost:8002"
else
    echo -e "  ${RED}❌${NC} Prompt Config Service failed to start (check logs/prompt-config.log)"
    SERVICES_OK=false
fi

echo -e "  ${GREEN}✅${NC} Telegram Bot is running (check logs/bot.log for status)"

if [ "$SERVICES_OK" = true ]; then
    echo -e "\n${GREEN}═══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ All services are running successfully!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
else
    echo -e "\n${YELLOW}═══════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}⚠️  Some services failed to start${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════${NC}"
fi

echo -e "\n${BLUE}📡 Services:${NC}"
echo -e "  FastAPI:           ${GREEN}http://localhost:8000${NC}"
echo -e "  API Documentation: ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  Artifacts:         ${GREEN}http://localhost:8001${NC}"
echo -e "  Prompt Config:     ${GREEN}http://localhost:8002${NC}"
echo -e "  PostgreSQL:        ${GREEN}localhost:5433${NC}"

echo -e "\n${BLUE}📄 Logs:${NC}"
echo -e "  FastAPI:        ${YELLOW}logs/fastapi.log${NC}"
echo -e "  Artifacts:      ${YELLOW}logs/artifacts.log${NC}"
echo -e "  Prompt Config:  ${YELLOW}logs/prompt-config.log${NC}"
echo -e "  Telegram Bot:   ${YELLOW}logs/bot.log${NC}"

echo -e "\n${BLUE}💡 Tips:${NC}"
echo -e "  • Reset everything: ${YELLOW}make local-reset${NC}"
echo -e "  • Web UI: ${YELLOW}cd web-ui && npm run dev${NC}"

echo -e "\n${YELLOW}Press Ctrl+C to stop all services${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"

# Ждем пока пользователь не остановит
while true; do
    sleep 1
    # Проверяем что процессы еще живы
    for pid in ${PIDS[@]}; do
        if ! kill -0 $pid 2>/dev/null; then
            echo -e "${RED}⚠️  Process $pid died unexpectedly${NC}"
        fi
    done
done
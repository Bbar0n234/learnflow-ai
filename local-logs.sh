#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}📄 LearnFlow AI - Log Viewer${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"

# Проверка наличия директории с логами
if [ ! -d "logs" ]; then
    echo -e "${YELLOW}⚠️  Logs directory not found. Run ./local-dev.sh first${NC}"
    exit 1
fi

# Проверка наличия log файлов
if [ -z "$(ls -A logs/*.log 2>/dev/null)" ]; then
    echo -e "${YELLOW}⚠️  No log files found. Services may not be running${NC}"
    exit 1
fi

echo -e "${BLUE}Available logs:${NC}"
echo -e "  • FastAPI:        logs/fastapi.log"
echo -e "  • Artifacts:      logs/artifacts.log"
echo -e "  • Prompt Config:  logs/prompt-config.log"
echo -e "  • Telegram Bot:   logs/bot.log"
echo -e ""
echo -e "${YELLOW}Showing all logs (Press Ctrl+C to exit)...${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""

# Используем tail с префиксом файла для различения логов
tail -f logs/*.log 2>/dev/null | while IFS= read -r line; do
    # Добавляем цветовую маркировку в зависимости от типа лога
    if [[ $line == *"ERROR"* ]]; then
        echo -e "${RED}$line${NC}"
    elif [[ $line == *"WARNING"* ]]; then
        echo -e "${YELLOW}$line${NC}"
    elif [[ $line == *"INFO"* ]]; then
        echo -e "${GREEN}$line${NC}"
    else
        echo "$line"
    fi
done
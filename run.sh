#!/bin/bash

# LearnFlow AI - быстрый запуск системы

set -e

echo "🚀 Запуск LearnFlow AI..."

# Проверка зависимостей
echo "📦 Проверка зависимостей..."
if ! command -v poetry &> /dev/null; then
    echo "❌ Poetry не найден. Установите Poetry: https://python-poetry.org/docs/#installation"
    exit 1
fi

# Проверка .env файла
if [ ! -f .env ]; then
    echo "⚠️ Файл .env не найден. Создайте его на основе env.example"
    echo "cp env.example .env && nano .env"
    exit 1
fi

# Установка зависимостей если нужно
echo "📥 Установка зависимостей..."
poetry install --group core --group learnflow --group bot

# Функция для проверки портов
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null ; then
        echo "❌ Порт $port уже занят"
        return 1
    fi
    return 0
}

# Проверка портов
if ! check_port 8000; then
    echo "Остановите процесс на порту 8000 или измените LEARNFLOW_PORT в .env"
    exit 1
fi

echo "✅ Зависимости готовы"

# Создание директорий если нужно
mkdir -p data/outputs

# Функция остановки
cleanup() {
    echo "🛑 Остановка сервисов..."
    jobs -p | xargs -r kill
    exit 0
}

trap cleanup SIGINT SIGTERM

# Запуск FastAPI сервиса в фоне
echo "🔧 Запуск FastAPI сервиса..."
poetry run python -m learnflow.main &
FASTAPI_PID=$!

# Ждем запуска FastAPI
echo "⏳ Ожидание запуска FastAPI сервиса..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ FastAPI сервис запущен"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ FastAPI сервис не запустился за 30 секунд"
        kill $FASTAPI_PID
        exit 1
    fi
    sleep 1
done

# Запуск Telegram бота
echo "🤖 Запуск Telegram бота..."
poetry run python -m bot.main &
BOT_PID=$!

echo ""
echo "🎉 LearnFlow AI успешно запущен!"
echo ""
echo "📊 Статус сервисов:"
echo "   FastAPI: http://localhost:8000"
echo "   Health: http://localhost:8000/health"
echo "   Telegram Bot: Активен"
echo ""
echo "📖 Документация API: http://localhost:8000/docs"
echo "🔧 Логи отображаются ниже..."
echo ""
echo "Для остановки нажмите Ctrl+C"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ожидание завершения
wait 
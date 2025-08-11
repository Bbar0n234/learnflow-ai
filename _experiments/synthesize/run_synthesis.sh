#!/bin/bash

# Скрипт для запуска синтезирования учебного материала

echo "🚀 Запуск синтезирования учебного материала"

# Переход в корневую директорию проекта
cd "$(dirname "$0")/.."

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "⚠️  Файл .env не найден. Скопируйте env.example в .env и заполните API ключи"
    exit 1
fi

# Загрузка переменных окружения
export $(cat .env | grep -v '^#' | xargs)

# Запуск синтезирования с различными опциями
echo "📋 Доступные опции запуска:"
echo "1. Полный процесс (распознавание + генерация + синтез)"
echo "2. Только синтез (пропустить распознавание и генерацию)"
echo "3. Пропустить только распознавание"
echo "4. Пропустить только генерацию"

read -p "Выберите опцию (1-4): " choice

case $choice in
    1)
        echo "🔄 Запускаю полный процесс..."
        python synthesize/main.py
        ;;
    2)
        echo "🔄 Запускаю только синтез..."
        python synthesize/main.py --skip-recognition --skip-generation
        ;;
    3)
        echo "🔄 Пропускаю распознавание..."
        python synthesize/main.py --skip-recognition
        ;;
    4)
        echo "🔄 Пропускаю генерацию..."
        python synthesize/main.py --skip-generation
        ;;
    *)
        echo "❌ Неверный выбор. Запускаю полный процесс..."
        python synthesize/main.py
        ;;
esac

echo "✅ Скрипт завершен" 
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем poetry
RUN pip install --no-cache-dir poetry

# Копируем только файлы, необходимые для установки зависимостей
COPY pyproject.toml poetry.lock ./

# Устанавливаем зависимости (без разработческих)
RUN poetry config virtualenvs.create false && poetry install --no-root --only learnflow

# Копируем код сервиса
COPY learnflow/ ./learnflow/

# Порт для FastAPI
EXPOSE 8000

# Запуск API
CMD ["python", "-m", "learnflow"] 
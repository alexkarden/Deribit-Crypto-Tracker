# app/../Dockerfile
# Указываем базовый образ с Python (соответствует вашему локальному окружению)
FROM python:3.12-slim

# Устанавливаем системные зависимости (netcat нужен для проверки доступности PostgreSQL)
RUN apt-get update && \
    apt-get install -y --no-install-recommends netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей в контейнер
COPY requirements.txt .

# Устанавливаем Python-библиотеки из requirements.txt без сохранения кэша для уменьшения веса образа
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию контейнера
COPY . .

# Делаем оркестрационный скрипт исполняемым в Unix-среде контейнера
RUN chmod +x entrypoint.sh

# Открываем порт 8000 для проброса веб-сервера FastAPI наружу
EXPOSE 8000

# Передаем управление скрипту инициализации процессов
ENTRYPOINT ["./entrypoint.sh"]

# app/main.py
from contextlib import asynccontextmanager
from datetime import datetime
from datetime import time as datetime_time

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем всё, что связано с базой данных, из модуля database
from app.database import Base, TickerPrice, async_session_maker, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Контекстный менеджер жизненного цикла приложения (Lifespan).
    Выполняет автоматическое развертывание структуры таблиц в PostgreSQL
    при холодном старте веб-сервера.
    """
    # Подключаемся к базе и создаем таблицы, если они еще не созданы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Корректно закрываем пул соединений с PostgreSQL при остановке сервера
    await engine.dispose()


# Инициализируем FastAPI приложение
app = FastAPI(
    title="Deribit Crypto Tracker API",
    description="API для мониторинга индексных цен криптовалют btc_usd и eth_usd",
    version="1.0.0",
    lifespan=lifespan,
)


async def get_db_session() -> AsyncSession:
    """
    Зависимость (Dependency) для предоставления асинхронной сессии базы данных.
    Обеспечивает изоляцию транзакций: на каждый HTTP-запрос создается своя сессия,
    которая гарантированно закрывается после отправки ответа клиенту.
    """
    async with async_session_maker() as session:
        yield session


# ==============================================================================
# МЕТОД 1: Получение всех сохраненных данных по указанной валюте
# ==============================================================================
@app.get("/prices")
async def get_all_prices(
        ticker: str = Query(..., description="Тикер валюты, например: btc_usd или eth_usd"),
        db: AsyncSession = Depends(get_db_session),
):
    """
    Возвращает полную историю изменений цен для указанного тикера.
    Результаты отсортированы от самых свежих к самым старым.
    """
    # Благодаря индексу на поле ticker в БД, этот запрос выполняется мгновенно
    query = (
        select(TickerPrice)
        .where(TickerPrice.ticker == ticker)
        .order_by(desc(TickerPrice.timestamp))
    )
    result = await db.execute(query)

    # Извлекаем все найденные строки в виде списка объектов
    prices = result.scalars().all()
    return prices


# ==============================================================================
# МЕТОД 2: Получение последней цены валюты
# ==============================================================================
@app.get("/prices/latest")
async def get_latest_price(
        ticker: str = Query(..., description="Тикер валюты, например: btc_usd или eth_usd"),
        db: AsyncSession = Depends(get_db_session),
):
    """
    Возвращает самую последнюю сохраненную цену для указанного тикера.
    """
    # Сортируем по убыванию времени и берем строго одну запись (LIMIT 1)
    query = (
        select(TickerPrice)
        .where(TickerPrice.ticker == ticker)
        .order_by(desc(TickerPrice.timestamp))
        .limit(1)
    )
    result = await db.execute(query)

    latest_price = result.scalars().first()

    # Защитное исключение, если фоновый сборщик Celery еще не успел сделать первый цикл опроса
    if not latest_price:
        raise HTTPException(
            status_code=404,
            detail=f"Данные по тикеру '{ticker}' еще не собраны фоновым воркером.",
        )
    return latest_price


# ==============================================================================
# МЕТОД 3: Получение цены валюты с фильтром по ДАТЕ (с автоконвертацией)
# ==============================================================================
@app.get("/prices/filter")
async def get_prices_by_date_filter(
        ticker: str = Query(..., description="Тикер валюты, например: btc_usd или eth_usd"),
        start_date: datetime = Query(
            ...,
            description="Начало периода в формате ISO (например: 2026-10-15 или 2026-10-15T12:00:00)",
        ),
        end_date: datetime = Query(
            ...,
            description="Конец периода в формате ISO (например: 2026-10-15 или 2026-10-15T23:59:59)",
        ),
        db: AsyncSession = Depends(get_db_session),
):
    """
    Возвращает историю цен за указанный период.
    Принимает привычные даты (строки ISO), конвертирует их в UNIX timestamp
    и делает максимально быстрый поиск по индексам в базе данных.
    """
    # 1. Валидация логики: дата начала не может быть позже даты конца
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Дата начала (start_date) не может быть больше, чем дата конца (end_date).",
        )
    if end_date.time() == datetime_time(0, 0, 0):
        # Заменяем время на последнюю секунду суток
        end_date = end_date.replace(hour=23, minute=59, second=59)

    # 2.Переводим человеческие даты в UNIX timestamp (целое число секунд)
    start_timestamp = int(start_date.timestamp())
    end_timestamp = int(end_date.timestamp())

    # 3. Делаем запрос к PostgreSQL
    query = (
        select(TickerPrice)
        .where(
            TickerPrice.ticker == ticker,
            TickerPrice.timestamp >= start_timestamp,
            TickerPrice.timestamp <= end_timestamp,
        )
        .order_by(desc(TickerPrice.timestamp))
    )

    result = await db.execute(query)
    prices = result.scalars().all()

    return prices

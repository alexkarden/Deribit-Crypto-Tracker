# app/tasks.py
import asyncio
import time
import aiohttp
from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Импортируем только настройки, декларативную базу и модель (БЕЗ глобального движка!)
from app.client import DeribitClient
from app.config import settings
from app.database import Base, TickerPrice


async def init_models_async():
    """Автоматически создает структуру таблиц в PostgreSQL при холодном старте воркера."""
    # Создаем локальный изолированный движок для инициализации схемы
    init_engine = create_async_engine(settings.database_url, echo=True)
    try:
        async with init_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await init_engine.dispose()

# Инициализируем loop для выполнения стартовой корутины
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Запускаем создание таблиц до старта брокера Celery
loop.run_until_complete(init_models_async())



celery_app = Celery("crypto_tasks", broker=settings.celery_broker_url)

celery_app.conf.beat_schedule = {
    "fetch-crypto-prices-every-interval": {
        "task": "app.tasks.fetch_crypto_prices_task",
        "schedule": float(settings.fetch_interval_seconds),
    },
}


async def fetch_and_save_prices_async():
    """
    Асинхронная логика опроса биржи и сохранения данных.
    
    Разделяет сетевые запросы API и транзакции СУБД, а также локально 
    инициализирует движок базы данных для полного исключения ошибки "different loop".
    """
    current_timestamp = int(time.time())
    collected_prices = []

    # ШАГ 1: Асинхронный сбор данных из интернета (База данных не задействована)
    async with aiohttp.ClientSession() as session:
        client = DeribitClient(session)
        
        for ticker in settings.crypto_tickers:
            try:
                price = await client.get_index_price(ticker)
                collected_prices.append((ticker, price))
            except Exception:
                continue

    # Если сетевой пул вернул пустоту, прерываем выполнение
    if not collected_prices:
        return

    # ШАГ 2: Локальная инициализация пула соединений PostgreSQL строго внутри текущего Loop
    local_engine = create_async_engine(settings.database_url, echo=True)
    local_session_maker = async_sessionmaker(bind=local_engine, expire_on_commit=False)

    # ШАГ 3: Запись всей собранной пачки котировок за одну быструю транзакцию
    async with local_session_maker() as db_session:
        try:
            for ticker, price in collected_prices:
                db_price = TickerPrice(
                    ticker=ticker,
                    price=price,
                    timestamp=current_timestamp
                )
                db_session.add(db_price)
            
            # Финальный коммит всей пачки в PostgreSQL
            await db_session.commit()
            print(f"[Celery] Успешно записано котировок в PostgreSQL: {len(collected_prices)}")
        except Exception:
            await db_session.rollback()
            raise
        finally:
            # Жестко закрываем сокеты локального движка для предотвращения утечек памяти
            await local_engine.dispose()


@celery_app.task
def fetch_crypto_prices_task():
    """Синхронная точка входа планировщика Celery Beat."""
    asyncio.run(fetch_and_save_prices_async())

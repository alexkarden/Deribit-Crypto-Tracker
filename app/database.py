# app/database.py
import time

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


def get_current_timestamp() -> int:
    """
    Возвращает текущее UNIX-время в секундах как целое число.
    Использует time.time_ns() для предотвращения работы с дробной частью float.
    """
    return time.time_ns() // 1_000_000_000


# Создаем асинхронный движок, используя DATABASE_URL из настроек settings (.env)
engine = create_async_engine(settings.database_url, echo=True)

# Фабрика для генерации асинхронных сессий работы с БД
async_session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)


# Базовый класс для декларативных моделей SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass


# Модель таблицы для хранения истории цен криптовалют
class TickerPrice(Base):
    __tablename__ = "ticker_prices"

    # Идентификатор записи (Первичный ключ с автоинкрементом)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Тикер валюты (например, btc_usd, eth_usd). Индекс необходим для быстрого поиска через API
    ticker: Mapped[str] = mapped_column(index=True, nullable=False)

    # Текущая индексная цена криптовалюты
    price: Mapped[float] = mapped_column(nullable=False)

    # UNIX timestamp времени сбора
    timestamp: Mapped[int] = mapped_column(
        index=True,
        nullable=False,
        default=get_current_timestamp,
    )

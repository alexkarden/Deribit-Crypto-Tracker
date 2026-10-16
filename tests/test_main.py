# tests/test_main.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.database import Base, TickerPrice
# Импортируем компоненты нашего приложения напрямую из модулей (защита от циклического импорта)
from app.main import app, get_db_session

# ==============================================================================
# НАСТРОЙКА ТЕСТОВОЙ БАЗЫ ДАННЫХ (ИЗОЛИРОВАННОЕ ОКРУЖЕНИЕ)
# ==============================================================================

# Создаем асинхронный движок для SQLite в оперативной памяти (:memory:).
# StaticPool гарантирует, что база данных не закроется и не сотрется между сессиями в рамках одного теста.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Фабрика сессий для работы с тестовой базой данных
TestingSessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncSession:
    """
    Фикстура для подготовки структуры БД перед каждым тестом.

    Перед запуском теста создает пустые таблицы, предоставляет асинхронную сессию,
    а после завершения теста полностью уничтожает базу данных, очищая окружение.
    """
    # Создаем структуру таблиц на основе декларативных моделей
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionMaker() as session:
        yield session

    # Полностью удаляем таблицы после выполнения теста
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncClient:
    """
    Фикстура для создания виртуального асинхронного HTTP-клиента.

    Переопределяет (подменяет) реальную зависимость подключения к Postgres в FastAPI
    на изолированную тестовую сессию SQLite в памяти. Настроена под синтаксис httpx 0.28+.
    """

    async def _override_get_db_session():
        yield db_session

    # Подменяем реальную сессию БД на тестовую в приложении FastAPI
    app.dependency_overrides[get_db_session] = _override_get_db_session

    # Инициализируем ASGI транспорт для работы со свежими версиями библиотеки httpx
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Обязательно сбрасываем подмену зависимостей после завершения теста
    app.dependency_overrides.clear()


# ==============================================================================
# UNIT-ТЕСТЫ ДЛЯ ОСНОВНЫХ МЕТОДОВ API
# ==============================================================================

@pytest.mark.asyncio
async def test_get_all_prices_empty(client: AsyncClient):
    """Тест эндпоинта /prices: Проверка возврата пустого списка, если данных нет."""
    response = await client.get("/prices?ticker=btc_usd")

    assert response.status_code == 200
    assert response.json() == []  # База данных пустая, должен вернуться пустой массив


@pytest.mark.asyncio
async def test_get_latest_price_not_found(client: AsyncClient):
    """Тест эндпоинта /prices/latest: Возврат ошибки 404, если тикер не собирался."""
    response = await client.get("/prices/latest?ticker=btc_usd")

    assert response.status_code == 404
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_flow_save_and_get_prices(client: AsyncClient, db_session: AsyncSession):
    """
    Комплексный тест: Имитируем сохранение котировок воркером Celery
    и последующее успешное извлечение через эндпоинты /prices и /prices/latest.
    """
    # 1. Наполняем тестовую БД фейковыми котировками (имитируем работу Celery)
    test_price_1 = TickerPrice(ticker="btc_usd", price=62500.0, timestamp=1792040000)
    test_price_2 = TickerPrice(ticker="btc_usd", price=62600.0, timestamp=1792040060)
    test_price_eth = TickerPrice(ticker="eth_usd", price=3400.0, timestamp=1792040000)

    db_session.add_all([test_price_1, test_price_2, test_price_eth])
    await db_session.commit()

    # 2. Проверяем метод получения всей истории (/prices)
    response_all = await client.get("/prices?ticker=btc_usd")
    assert response_all.status_code == 200
    data_all = response_all.json()
    assert len(data_all) == 2  # Должно вернуться ровно 2 записи для btc_usd
    assert data_all[0]["price"] == 62600.0  # Проверка сортировки desc: первая запись самая свежая

    # 3. Проверяем метод получения последней актуальной цены (/prices/latest)
    response_latest = await client.get("/prices/latest?ticker=btc_usd")
    assert response_latest.status_code == 200
    data_latest = response_latest.json()
    assert data_latest["price"] == 62600.0  # Должна вернуться строго последняя сохраненная цена


@pytest.mark.asyncio
async def test_prices_by_date_filter(client: AsyncClient, db_session: AsyncSession):
    """Тест эндпоинта /prices/filter: Проверка работы умного фильтра по датам."""
    # Записываем тестовую котировку за конкретную дату (15 октября 2026 года)
    target_price = TickerPrice(ticker="btc_usd", price=65000.0, timestamp=1792065600)  # 21:20:00 MSK
    db_session.add(target_price)
    await db_session.commit()

    # Делаем запрос с фильтрацией, указывая чистые даты без времени
    response = await client.get("/prices/filter?ticker=btc_usd&start_date=2026-10-15&end_date=2026-10-15")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1  # Умный фильтр должен расширить границы дня до 23:59:59 и найти запись
    assert data[0]["price"] == 65000.0

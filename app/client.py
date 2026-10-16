# app/client.py
import aiohttp

from app.config import settings


class DeribitClient:
    """
    Асинхронный клиент для взаимодействия с публичным API биржи Deribit.

    Реализует паттерн Dependency Injection (Внедрение зависимостей),
    принимая сессию aiohttp извне для переиспользования сетевого соединения.
    """

    def __init__(self, session: aiohttp.ClientSession):
        """
        Инициализация клиента Deribit.

        :param session: Активная асинхронная сессия aiohttp.ClientSession
        """
        self.session = session
        # Подтягиваем базовый URL API из централизованных настроек .env
        self.base_url = settings.deribit_base_url

    async def get_index_price(self, index_name: str) -> float:
        """
        Запрашивает текущую индексную цену (Index Price) для указанной валютной пары.

        Вызывает публичный эндпоинт GET /public/get_index_price.

        :param index_name: Строковый тикер валюты на бирже (например, 'btc_usd' или 'eth_usd')
        :return: Текущая цена криптовалюты в формате дробного числа (float)
        :raises aiohttp.ClientError: При сетевых ошибках (таймаут, падение сервера биржи)
        :raises ValueError: Если структура ответа API Deribit изменилась или некорректна
        """
        # Формируем полный URL к конкретному методу API биржи
        url = f"{self.base_url}/api/v2/public/get_index_price"
        # Передаем query-параметр index_name, требуемый документацией Deribit
        params = {"index_name": index_name}

        try:
            # Выполняем асинхронный GET-запрос к бирже
            async with self.session.get(url, params=params) as response:
                # Генерирует исключение, если HTTP-статус ответа не 200 OK (например, 400, 500)
                response.raise_for_status()

                # Асинхронно читаем тело ответа и автоматически парсим JSON в Python-словарь
                data = await response.json()

                # Защитная проверка структуры данных перед извлечением цены (профилактика KeyError)
                if "result" in data and "index_price" in data["result"]:
                    # Извлекаем цену и принудительно приводим к float по требованиям ТЗ
                    return float(data["result"]["index_price"])

                # Если ключей 'result' или 'index_price' нет, значит структура ответа невалидна
                raise ValueError(f"Неожиданная структура ответа от Deribit API: {data}")

        except Exception:
            # Просто пробрасываем ошибку дальше (в Celery или FastAPI) для обработки на верхнем уровне
            raise

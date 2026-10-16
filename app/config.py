# app/config.py
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Вычисляем точный путь к файлу .env в корне проекта
env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """
    Класс конфигурации приложения.

    Автоматически считывает и валидирует переменные из .env или окружения Docker,
    динамически формируя строки подключения для SQLAlchemy и Celery.
    """

    #Настройки интеграции с биржей
    deribit_base_url: str = Field(default="https://deribit.com")
    
    # Pydantic автоматически преобразует строку "btc_usd,eth_usd" в список Python
    crypto_tickers: list[str] = Field(default=["btc_usd", "eth_usd"])
    
    fetch_interval_seconds: int = Field(default=60)

    #Настройки СУБД PostgreSQL (Обязательные поля)
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int = 5432
    postgres_db: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


    @property
    def celery_broker_url(self) -> str:
        """
        Динамически собирает строку брокера задач для Celery.
        Использует транспорт 'sqla' (SQLAlchemy) через синхронный драйвер 'psycopg2',
        что позволяет Celery работать через таблицы Postgres без Redis.
        """
        return (
            f"sqla+postgresql://{self.postgres_user}:{self.postgres_password}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    #Настройки парсинга конфигурации Pydantic
    model_config = SettingsConfigDict(
        env_file=env_path,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False  
    )


# Создаем единственный экземпляр настроек (паттерн Singleton).
settings = Settings()

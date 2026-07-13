import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql+psycopg2://tracker:tracker@localhost:5432/tracker',
    )
    # Отдельный read-only пользователь БД для SQL-запросов досок и быстрых
    # фильтров. Если не задан, используется основное подключение, но запросы
    # всё равно выполняются в read-only транзакции.
    READONLY_DATABASE_URL = os.environ.get('READONLY_DATABASE_URL')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 МБ на запрос

    # Время жизни ссылки на сброс пароля, секунды
    PASSWORD_RESET_MAX_AGE = 3600

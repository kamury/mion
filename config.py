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

    # ---------- Почта (уведомления) ----------
    # Если MAIL_SERVER не задан — уведомления просто не отправляются.
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 25))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', '').lower() in ('1', 'true', 'yes')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    # Отправитель: по умолчанию совпадает с логином
    MAIL_FROM = os.environ.get('MAIL_FROM') or os.environ.get('MAIL_USERNAME')
    MAIL_FROM_NAME = os.environ.get('MAIL_FROM_NAME', 'Трекер Мион')
    # Базовый адрес приложения для ссылок в письмах, напр. http://tracker.local
    APP_BASE_URL = os.environ.get('APP_BASE_URL', '')

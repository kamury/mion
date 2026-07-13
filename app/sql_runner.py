"""Выполнение пользовательского SQL для досок и быстрых фильтров.

Запрос пользователя должен возвращать множество id задач, например:
    SELECT id FROM issues WHERE project_id = 1

Доступен именованный параметр :current_user_id (id текущего пользователя).

Защита:
- запрос оборачивается в SELECT DISTINCT id FROM (...) — наружу выходят только id;
- один statement, только SELECT/WITH, без ';';
- выполняется в READ ONLY транзакции;
- если в конфиге задан READONLY_DATABASE_URL — под отдельным
  read-only пользователем БД.
"""
from flask import current_app
from sqlalchemy import create_engine, text

_engines = {}


def _get_engine():
    url = (current_app.config.get('READONLY_DATABASE_URL')
           or current_app.config['SQLALCHEMY_DATABASE_URI'])
    if url not in _engines:
        _engines[url] = create_engine(url, pool_pre_ping=True)
    return _engines[url]


def run_ids_query(sql, available_params=None):
    """Выполняет пользовательский SQL, возвращает set() id задач."""
    cleaned = (sql or '').strip().rstrip(';').strip()
    if not cleaned:
        raise ValueError('Пустой запрос')
    if ';' in cleaned:
        raise ValueError('Разрешён только один запрос (без ";")')
    lowered = cleaned.lower()
    if not (lowered.startswith('select') or lowered.startswith('with')):
        raise ValueError('Запрос должен начинаться с SELECT или WITH')

    wrapped = f'SELECT DISTINCT id FROM ({cleaned}) AS board_query'

    # Передаём только те параметры, которые реально используются в запросе
    params = {}
    for key, value in (available_params or {}).items():
        if f':{key}' in cleaned:
            params[key] = value

    engine = _get_engine()
    with engine.connect() as conn:
        if engine.dialect.name == 'postgresql':
            conn = conn.execution_options(postgresql_readonly=True)
        rows = conn.execute(text(wrapped), params).fetchall()
    return {row[0] for row in rows}

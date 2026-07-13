# Трекер задач

Мини-Jira: Flask + PostgreSQL + Jinja2. Задачи (Epic → Feature → Task/Bug),
спринты, доски на пользовательском SQL, workflow-статусы, история изменений,
комментарии и файлы, WYSIWYG с картинками.

## Стек

- **Backend:** Python 3.10+, Flask, SQLAlchemy, Flask-Login, Flask-Migrate
- **БД:** PostgreSQL
- **Frontend:** Jinja2 + Bootstrap 5, Quill (WYSIWYG), SortableJS (drag&drop) — всё с CDN, сборка не нужна

## Установка

```powershell
cd C:\k\dev\tracker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### База данных

В psql (или pgAdmin):

```sql
CREATE ROLE tracker LOGIN PASSWORD 'tracker';
CREATE DATABASE tracker OWNER tracker;
```

Опционально — отдельный read-only пользователь для SQL-запросов досок
(рекомендую; тогда пользовательский SQL физически не сможет ничего изменить):

```sql
CREATE ROLE tracker_ro LOGIN PASSWORD 'ro_password';
GRANT CONNECT ON DATABASE tracker TO tracker_ro;
\c tracker
GRANT USAGE ON SCHEMA public TO tracker_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO tracker_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE tracker IN SCHEMA public
  GRANT SELECT ON TABLES TO tracker_ro;
```

### Конфигурация

```powershell
copy .env.example .env
# поправь DATABASE_URL и SECRET_KEY, при желании раскомментируй READONLY_DATABASE_URL
```

### Инициализация и запуск

```powershell
$env:FLASK_APP = "run.py"
flask init-db     # создаёт таблицы + статусы To Do / In Progress / Done
flask run --debug # http://127.0.0.1:5000
```

Первый пользователь регистрируется через форму «Регистрация».

## Как пользоваться

- **Справочники** (меню) — проекты, команды, заказчики и статусы workflow.
  Порядок статуса задаёт колонку на доске; галочка «Done» помечает закрывающий
  статус (учитывается при закрытии спринта).
- **Доска** собирается по SQL-запросу, который возвращает `id` задач, например
  `SELECT id FROM issues WHERE project_id = 1`. В запросе доступен параметр
  `:current_user_id`. Быстрые фильтры — такие же запросы; на доске остаётся
  пересечение с запросом доски.
- Карточки на доске перетаскиваются между колонками (смена статуса) и
  свимлейнами (смена спринта). Спринты создаются/редактируются/закрываются
  прямо с доски; при закрытии спринта незакрытые задачи переносятся в выбранный
  спринт или в Backlog.
- **История** изменений — вкладка в задаче: кто, когда и что поменял.

## Восстановление пароля

SMTP пока не настроен: письмо со ссылкой сброса выводится в консоль сервера
(см. `app/emails.py`). Для реальной отправки достаточно заменить реализацию
`send_email`.

## Замечания по безопасности

Проект рассчитан на доверенную внутреннюю среду:

- SQL досок выполняется в read-only транзакции (и, если настроен
  `READONLY_DATABASE_URL`, под read-only пользователем БД), но писать эти
  запросы могут все пользователи.
- HTML из WYSIWYG сохраняется и рендерится как есть (без санитизации).
- CSRF-токенов нет.

Для выхода наружу (интернет) это нужно будет ужесточить.

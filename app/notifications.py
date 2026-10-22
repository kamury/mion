"""Почтовые уведомления.

Шлём простые письма через SMTP (без лишних зависимостей, stdlib). Отправка —
в фоновом потоке, чтобы не блокировать запрос и чтобы сбой почты не ломал
действие пользователя. Если MAIL_SERVER не задан — тихо ничего не делаем
(так работает локальная разработка и тесты без почты).
"""
import re
import smtplib
import threading
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app

from .extensions import db
from .models import User


def _plain(html, limit=500):
    """Грубый текст из HTML комментария для тела письма."""
    if not html:
        return ''
    text = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', html)
    text = re.sub(r'(?i)</\s*(p|div|li|h[1-6]|blockquote|pre|tr)\s*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()
    return text[:limit] + '…' if len(text) > limit else text


def _issue_url(app, issue_id):
    base = (app.config.get('APP_BASE_URL') or '').rstrip('/')
    return f'{base}/issues/{issue_id}' if base else None


def _deliver(app, to_addr, subject, body):
    """Собственно отправка одного письма. Все ошибки — в лог, не наружу."""
    with app.app_context():
        server = app.config.get('MAIL_SERVER')
        if not server or not to_addr:
            return
        msg = EmailMessage()
        msg['Subject'] = subject
        from_addr = app.config.get('MAIL_FROM') or app.config.get('MAIL_USERNAME')
        from_name = app.config.get('MAIL_FROM_NAME') or 'Трекер'
        msg['From'] = formataddr((from_name, from_addr))
        msg['To'] = to_addr
        msg.set_content(body)
        try:
            port = int(app.config.get('MAIL_PORT') or 25)
            with smtplib.SMTP(server, port, timeout=15) as smtp:
                if app.config.get('MAIL_USE_TLS'):
                    smtp.starttls()
                user = app.config.get('MAIL_USERNAME')
                password = app.config.get('MAIL_PASSWORD')
                if user and password:
                    smtp.login(user, password)
                smtp.send_message(msg)
        except Exception:
            app.logger.exception('Не удалось отправить письмо на %s', to_addr)


def send_email(to_addr, subject, body):
    """Ставит письмо в отправку (в фоне). No-op, если почта не настроена."""
    app = current_app._get_current_object()
    if not app.config.get('MAIL_SERVER') or not to_addr:
        return
    if app.config.get('MAIL_SYNC'):  # для тестов — синхронно
        _deliver(app, to_addr, subject, body)
    else:
        threading.Thread(target=_deliver, args=(app, to_addr, subject, body),
                         daemon=True).start()


def _signature(app, issue):
    url = _issue_url(app, issue.id)
    return f'\n\nОткрыть задачу: {url}\n' if url else '\n'


def notify_assignment(issue, old_assignee_id, actor):
    """Письмо новому исполнителю задачи. Не шлём, если исполнитель не менялся
    или человек назначил задачу сам на себя."""
    new_id = issue.assignee_id
    if not new_id or new_id == old_assignee_id or (actor and new_id == actor.id):
        return
    assignee = db.session.get(User, new_id)
    if not assignee or not assignee.email:
        return
    app = current_app._get_current_object()
    who = actor.name if actor else 'Кто-то'
    subject = f'На вас назначена задача #{issue.id}: {issue.title}'
    body = (f'{who} назначил(а) вас исполнителем задачи:\n\n'
            f'#{issue.id} — {issue.title}'
            f'{_signature(app, issue)}')
    send_email(assignee.email, subject, body)


def notify_comment(issue, comment, actor):
    """Письмо исполнителю и автору задачи о новом комментарии (кроме самого
    комментатора)."""
    actor_id = actor.id if actor else None
    recipients = {}
    for uid in (issue.assignee_id, issue.reporter_id):
        if uid and uid != actor_id:
            user = db.session.get(User, uid)
            if user and user.email:
                recipients[user.email] = user
    if not recipients:
        return
    app = current_app._get_current_object()
    who = actor.name if actor else 'Кто-то'
    snippet = _plain(comment.body)
    subject = f'Новый комментарий к задаче #{issue.id}: {issue.title}'
    body = (f'{who} оставил(а) комментарий к задаче #{issue.id} — {issue.title}:\n\n'
            f'{snippet or "(без текста)"}'
            f'{_signature(app, issue)}')
    for email in recipients:
        send_email(email, subject, body)

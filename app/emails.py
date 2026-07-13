"""Отправка почты.

Пока SMTP не настроен: письмо пишется в лог/консоль приложения.
Когда появится реальный SMTP, достаточно заменить реализацию send_email.
"""
from flask import current_app


def send_email(to, subject, body):
    message = (
        '\n================ EMAIL (консоль, SMTP не настроен) ================\n'
        f'To:      {to}\n'
        f'Subject: {subject}\n'
        f'{body}\n'
        '====================================================================\n'
    )
    current_app.logger.info(message)
    try:
        print(message)
    except UnicodeEncodeError:
        # Windows-консоль с не-UTF8 кодировкой (cp1252 и т.п.)
        print(message.encode(errors='backslashreplace').decode('ascii', errors='replace'))

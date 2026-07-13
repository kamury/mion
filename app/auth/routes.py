from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import or_

from ..emails import send_email
from ..extensions import db
from ..files import save_upload
from ..models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'],
                                  salt='password-reset')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        login_field = request.form.get('login', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter(
            or_(User.login == login_field, User.email == login_field)
        ).first()
        if user and user.check_password(password):
            login_user(user, remember=bool(request.form.get('remember')))
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        flash('Неверный логин или пароль.', 'danger')
    return render_template('auth/login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        login_field = request.form.get('login', '').strip()
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        error = None
        if not login_field or not email or not name or not password:
            error = 'Заполни все обязательные поля.'
        elif password != password2:
            error = 'Пароли не совпадают.'
        elif User.query.filter_by(login=login_field).first():
            error = 'Такой логин уже занят.'
        elif User.query.filter_by(email=email).first():
            error = 'Пользователь с такой почтой уже зарегистрирован.'

        if error:
            flash(error, 'danger')
        else:
            user = User(login=login_field, email=email, name=name)
            user.set_password(password)
            avatar = request.files.get('avatar')
            if avatar and avatar.filename:
                user.avatar = save_upload(avatar, 'avatars')
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f'Добро пожаловать, {user.name}!', 'success')
            return redirect(url_for('index'))
    return render_template('auth/register.html')


@bp.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = _serializer().dumps(user.id)
            link = url_for('auth.reset', token=token, _external=True)
            send_email(
                user.email,
                'Восстановление пароля — Трекер',
                f'Здравствуйте, {user.name}!\n\n'
                f'Чтобы задать новый пароль, перейдите по ссылке:\n{link}\n\n'
                f'Ссылка действует 1 час. Если вы не запрашивали сброс — '
                f'просто проигнорируйте это письмо.',
            )
        # Не раскрываем, есть ли такая почта в системе
        flash('Если такая почта зарегистрирована, письмо со ссылкой отправлено. '
              'Пока SMTP не настроен — ссылка выводится в консоль сервера.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot.html')


@bp.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    try:
        user_id = _serializer().loads(
            token, max_age=current_app.config['PASSWORD_RESET_MAX_AGE'])
    except SignatureExpired:
        flash('Ссылка устарела. Запроси восстановление ещё раз.', 'danger')
        return redirect(url_for('auth.forgot'))
    except BadSignature:
        flash('Некорректная ссылка.', 'danger')
        return redirect(url_for('auth.forgot'))

    user = db.session.get(User, user_id)
    if not user:
        flash('Пользователь не найден.', 'danger')
        return redirect(url_for('auth.forgot'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if not password or password != password2:
            flash('Пароли пустые или не совпадают.', 'danger')
        else:
            user.set_password(password)
            db.session.commit()
            flash('Пароль обновлён, теперь можно войти.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/reset.html', token=token)


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if name:
            current_user.name = name
        avatar = request.files.get('avatar')
        if avatar and avatar.filename:
            current_user.avatar = save_upload(avatar, 'avatars')
        password = request.form.get('password', '')
        if password:
            if password != request.form.get('password2', ''):
                flash('Пароли не совпадают, пароль не изменён.', 'danger')
                return redirect(url_for('auth.profile'))
            current_user.set_password(password)
        db.session.commit()
        flash('Профиль обновлён.', 'success')
        return redirect(url_for('auth.profile'))
    return render_template('auth/profile.html')

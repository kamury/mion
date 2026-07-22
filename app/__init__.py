import os

from flask import Flask, redirect, url_for
from flask_login import current_user

from .extensions import db, login_manager, migrate


def create_app():
    app = Flask(__name__)
    app.config.from_object('config.Config')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Войдите, чтобы продолжить.'

    from . import models

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from .auth.routes import bp as auth_bp
    from .issues.routes import bp as issues_bp
    from .boards.routes import bp as boards_bp
    from .roadmap.routes import bp as roadmap_bp
    from .admin.routes import bp as admin_bp
    from .files import bp as files_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(boards_bp)
    app.register_blueprint(roadmap_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(files_bp)

    @app.context_processor
    def inject_nav_boards():
        """Список досок для выпадающего меню в навбаре."""
        if current_user.is_authenticated:
            boards = models.Board.query.order_by(models.Board.name).all()
        else:
            boards = []
        return {'nav_boards': boards}

    @app.template_filter('dt')
    def format_dt(value):
        return value.strftime('%d.%m.%Y %H:%M') if value else ''

    @app.template_filter('d')
    def format_d(value):
        return value.strftime('%d.%m.%Y') if value else ''

    @app.route('/')
    def index():
        return redirect(url_for('issues.index'))

    _register_cli(app)
    return app


def _register_cli(app):
    @app.cli.command('init-db')
    def init_db():
        """Создать таблицы и добавить стартовые данные."""
        from .models import Customer, Project, Status, Team

        db.create_all()

        if Status.query.count() == 0:
            db.session.add_all([
                Status(name='To Do', position=1),
                Status(name='In Progress', position=2),
                Status(name='Done', position=3, is_done=True),
            ])
        if Project.query.count() == 0:
            db.session.add(Project(name='Default'))
        if Team.query.count() == 0:
            db.session.add(Team(name='Default'))
        if Customer.query.count() == 0:
            db.session.add(Customer(name='Internal'))
        db.session.commit()
        print('База инициализирована: таблицы созданы, стартовые данные добавлены.')

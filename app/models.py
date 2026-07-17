from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

ISSUE_TYPES = {
    'epic': 'Epic',
    'feature': 'Feature',
    'task': 'Task',
    'bug': 'Bug',
}

PRIORITIES = {
    'critical': 'Critical',
    'highest': 'Highest',
    'high': 'High',
    'normal': 'Normal',
    'low': 'Low',
}

# Порядок сортировки: чем меньше, тем важнее
PRIORITY_ORDER = {p: i for i, p in enumerate(PRIORITIES)}

# Какой тип может быть родителем для данного типа
PARENT_TYPE = {
    'epic': None,
    'feature': 'epic',
    'task': 'feature',
    'bug': 'feature',
}


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.String(255))  # относительный путь в UPLOAD_FOLDER
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.login}>'


class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)


class Team(db.Model):
    __tablename__ = 'teams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)


class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)


class Component(db.Model):
    __tablename__ = 'components'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)


class Status(db.Model):
    __tablename__ = 'statuses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)  # порядок колонок на доске
    is_done = db.Column(db.Boolean, default=False, nullable=False)  # «закрывающий» статус


class Sprint(db.Model):
    __tablename__ = 'sprints'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    # Доска, на которой спринт создан. Пустой спринт виден только на ней;
    # NULL — виден на всех досках (спринты, созданные до этого правила).
    board_id = db.Column(db.Integer, db.ForeignKey('boards.id'))

    board = db.relationship('Board')
    issues = db.relationship('Issue', backref='sprint')


class Issue(db.Model):
    __tablename__ = 'issues'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # epic / feature / task / bug
    parent_id = db.Column(db.Integer, db.ForeignKey('issues.id'))

    title = db.Column(db.String(300), nullable=False)
    summary = db.Column(db.Text, default='')  # HTML из WYSIWYG
    priority = db.Column(db.String(20), default='normal',
                         server_default='normal', nullable=False)

    reporter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    component_id = db.Column(db.Integer, db.ForeignKey('components.id'))

    sprint_id = db.Column(db.Integer, db.ForeignKey('sprints.id'))
    status_id = db.Column(db.Integer, db.ForeignKey('statuses.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    parent = db.relationship('Issue', remote_side=[id], backref='children')
    reporter = db.relationship('User', foreign_keys=[reporter_id])
    assignee = db.relationship('User', foreign_keys=[assignee_id])
    project = db.relationship('Project')
    team = db.relationship('Team')
    customer = db.relationship('Customer')
    component = db.relationship('Component')
    status = db.relationship('Status')

    comments = db.relationship('Comment', backref='issue',
                               cascade='all, delete-orphan',
                               order_by='Comment.created_at')
    attachments = db.relationship('Attachment', backref='issue',
                                  cascade='all, delete-orphan',
                                  foreign_keys='Attachment.issue_id')
    history = db.relationship('IssueHistory', backref='issue',
                              cascade='all, delete-orphan',
                              order_by='IssueHistory.created_at.desc()')

    @property
    def type_label(self):
        return ISSUE_TYPES.get(self.type, self.type)

    @property
    def priority_label(self):
        return PRIORITIES.get(self.priority, self.priority)


class Comment(db.Model):
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)  # HTML из WYSIWYG
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    author = db.relationship('User')
    attachments = db.relationship('Attachment', backref='comment',
                                  cascade='all, delete-orphan',
                                  foreign_keys='Attachment.comment_id')


class Attachment(db.Model):
    __tablename__ = 'attachments'

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'))
    original_name = db.Column(db.String(300), nullable=False)
    stored_name = db.Column(db.String(300), nullable=False)  # путь внутри UPLOAD_FOLDER
    size = db.Column(db.Integer, default=0, nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by = db.relationship('User')


class IssueHistory(db.Model):
    __tablename__ = 'issue_history'

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # created / updated / commented / attached
    field = db.Column(db.String(80))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User')


class Board(db.Model):
    __tablename__ = 'boards'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    query_sql = db.Column(db.Text, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owner = db.relationship('User')
    filters = db.relationship('QuickFilter', backref='board',
                              cascade='all, delete-orphan',
                              order_by='QuickFilter.id')


class QuickFilter(db.Model):
    __tablename__ = 'quick_filters'

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.Integer, db.ForeignKey('boards.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    query_sql = db.Column(db.Text, nullable=False)

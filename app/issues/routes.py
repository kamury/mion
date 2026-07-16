import os
import re
import time
from uuid import uuid4

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, url_for)
from flask_login import current_user, login_required

from ..excel import build_export, import_rows, read_rows
from ..extensions import db
from ..files import save_upload
from ..history import add_event, record_update, snapshot
from ..models import (ISSUE_TYPES, PARENT_TYPE, Attachment, Comment, Component,
                      Customer, Issue, Project, Sprint, Status, Team, User)
from ..sql_runner import run_ids_query
from ..textutils import normalize_spaces

bp = Blueprint('issues', __name__, url_prefix='/issues')


def _form_choices():
    return dict(
        users=User.query.order_by(User.name).all(),
        projects=Project.query.order_by(Project.name).all(),
        teams=Team.query.order_by(Team.name).all(),
        customers=Customer.query.order_by(Customer.name).all(),
        components=Component.query.order_by(Component.name).all(),
        sprints=Sprint.query.filter_by(is_closed=False)
                            .order_by(Sprint.start_date).all(),
        statuses=Status.query.order_by(Status.position).all(),
        issue_types=ISSUE_TYPES,
    )


def _parent_options(current_issue=None):
    """Списки возможных родителей для JS-селекта, по типам."""
    exclude_id = current_issue.id if current_issue else None
    def pack(issue_type):
        return [
            {'id': i.id, 'title': i.title}
            for i in Issue.query.filter_by(type=issue_type)
                                .order_by(Issue.title).all()
            if i.id != exclude_id
        ]
    return {'epic': pack('epic'), 'feature': pack('feature')}


def _apply_form(issue):
    """Заполняет issue из request.form. Бросает ValueError с текстом ошибки."""
    form = request.form

    issue_type = form.get('type', '')
    if issue_type not in ISSUE_TYPES:
        raise ValueError('Неизвестный тип задачи.')
    issue.type = issue_type

    title = form.get('title', '').strip()
    if not title:
        raise ValueError('Название обязательно.')
    issue.title = title
    issue.summary = normalize_spaces(form.get('summary', ''))

    parent_id = form.get('parent_id') or None
    expected_parent = PARENT_TYPE[issue_type]
    if parent_id:
        parent = db.session.get(Issue, int(parent_id))
        if not parent or expected_parent is None or parent.type != expected_parent:
            raise ValueError('Некорректный родитель для этого типа задачи.')
        if parent.id == issue.id:
            raise ValueError('Задача не может быть родителем сама себе.')
        issue.parent_id = parent.id
    else:
        issue.parent_id = None

    # reporter_id из формы не принимаем: автор задаётся при создании и не меняется
    for field in ('assignee_id', 'project_id', 'team_id',
                  'customer_id', 'component_id', 'sprint_id', 'status_id'):
        value = form.get(field) or None
        setattr(issue, field, int(value) if value else None)

    if not issue.reporter_id:
        issue.reporter_id = current_user.id
    if not issue.status_id:
        first_status = Status.query.order_by(Status.position).first()
        if not first_status:
            raise ValueError('В системе нет ни одного статуса — добавь в справочниках.')
        issue.status_id = first_status.id


def _save_attachments(issue, files, comment=None):
    count = 0
    for file in files:
        if not file or not file.filename:
            continue
        rel = save_upload(file, 'attachments')
        size = os.path.getsize(os.path.join(current_app.config['UPLOAD_FOLDER'], rel))
        db.session.add(Attachment(
            issue_id=issue.id,
            comment_id=comment.id if comment else None,
            original_name=file.filename,
            stored_name=rel,
            size=size,
            uploaded_by_id=current_user.id,
        ))
        if not comment:
            add_event(issue, current_user, 'attached', new_value=file.filename)
        count += 1
    return count


def _filtered_issues(args):
    query = Issue.query
    types = [v for v in args.getlist('type') if v]
    if types:
        query = query.filter(Issue.type.in_(types))
    for field, column in (('status_id', Issue.status_id),
                          ('assignee_id', Issue.assignee_id),
                          ('project_id', Issue.project_id),
                          ('team_id', Issue.team_id),
                          ('component_id', Issue.component_id)):
        ids = [int(v) for v in args.getlist(field) if v]
        if ids:
            query = query.filter(column.in_(ids))
    if args.get('q'):
        query = query.filter(Issue.title.ilike(f"%{args['q']}%"))
    return query.order_by(Issue.id.desc()).all()


@bp.route('/')
@login_required
def index():
    issues = _filtered_issues(request.args)
    return render_template('issues/index.html', issues=issues, args=request.args,
                           **_form_choices())


@bp.route('/export')
@login_required
def export():
    """Экспорт задач в xlsx (учитывает фильтры со страницы списка)."""
    issues = _filtered_issues(request.args)
    output = build_export(issues)
    return send_file(
        output,
        as_attachment=True,
        download_name='issues.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


def _import_tmp_dir():
    """Папка для файлов, ожидающих подтверждения импорта. Чистит старые."""
    tmp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'import_tmp')
    os.makedirs(tmp_dir, exist_ok=True)
    now = time.time()
    for name in os.listdir(tmp_dir):
        path = os.path.join(tmp_dir, name)
        if now - os.path.getmtime(path) > 24 * 3600:
            os.remove(path)
    return tmp_dir


@bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel():
    """Импорт в два шага: предпросмотр (сухой прогон) -> подтверждение."""
    result = preview = None
    token = filename = ''

    if request.method == 'POST' and request.form.get('action') == 'confirm':
        token = request.form.get('token', '')
        filename = request.form.get('filename', '')
        path = os.path.join(_import_tmp_dir(), token)
        if not re.fullmatch(r'[0-9a-f]{32}', token) or not os.path.exists(path):
            flash('Файл предпросмотра не найден (мог устареть) — загрузи его ещё раз.', 'danger')
        else:
            with open(path, 'rb') as f:
                data = f.read()
            os.remove(path)
            try:
                result = import_rows(read_rows(data, filename), current_user)
                flash(f"Импортировано задач: {result['created']}.", 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка импорта: {e}', 'danger')
        token = filename = ''
    elif request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename:
            flash('Выбери файл.', 'danger')
        else:
            data = file.read()
            try:
                preview = import_rows(read_rows(data, file.filename),
                                      current_user, dry_run=True)
            except Exception as e:
                db.session.rollback()
                flash(f'Ошибка чтения файла: {e}', 'danger')
            else:
                token = uuid4().hex
                with open(os.path.join(_import_tmp_dir(), token), 'wb') as f:
                    f.write(data)
                filename = file.filename

    return render_template('issues/import.html', result=result, preview=preview,
                           token=token, filename=filename)


BULK_FIELDS = ('status_id', 'assignee_id', 'reporter_id', 'project_id',
               'team_id', 'customer_id', 'component_id', 'sprint_id')
# Поля, которые нельзя очистить (NOT NULL)
BULK_REQUIRED = {'status_id', 'reporter_id'}


@bp.route('/bulk', methods=['GET', 'POST'])
@login_required
def bulk():
    """Групповое редактирование: выборка по SQL + установка значений полей."""
    sql = request.form.get('query_sql', '').strip()
    action = request.form.get('action')
    issues, error = [], None

    if request.method == 'POST' and sql:
        try:
            ids = run_ids_query(sql, {'current_user_id': current_user.id})
            if ids:
                issues = (Issue.query.filter(Issue.id.in_(ids))
                          .order_by(Issue.id).all())
        except Exception as e:
            error = f'Ошибка в запросе: {e}'

        if action == 'apply' and not error:
            changes = {}
            for field in BULK_FIELDS:
                raw = request.form.get('set_' + field, '')
                if raw == '':
                    continue  # не менять
                if raw == '__clear__':
                    changes[field] = None
                else:
                    changes[field] = int(raw)
            if not changes:
                flash('Не выбрано ни одного поля для изменения.', 'warning')
            elif not issues:
                flash('Запрос не вернул ни одной задачи.', 'warning')
            else:
                changed = 0
                for issue in issues:
                    old = snapshot(issue)
                    for field, value in changes.items():
                        setattr(issue, field, value)
                    if record_update(issue, old, current_user):
                        changed += 1
                db.session.commit()
                flash(f'Обновлено задач: {changed} из {len(issues)}.', 'success')

    return render_template('issues/bulk.html', sql=sql, issues=issues,
                           error=error, **_form_choices())


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if request.method == 'POST':
        issue = Issue()
        try:
            _apply_form(issue)
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('issues/form.html', issue=None,
                                   form_data=request.form,
                                   parent_options=_parent_options(),
                                   **_form_choices())
        db.session.add(issue)
        db.session.flush()  # получаем issue.id
        add_event(issue, current_user, 'created')
        _save_attachments(issue, request.files.getlist('files'))
        db.session.commit()
        flash(f'Задача #{issue.id} создана.', 'success')
        return redirect(url_for('issues.view', issue_id=issue.id))
    # «Добавить связанную задачу» со страницы эпика/фичи: предзаполняем
    # тип, родителя и поля из родителя.
    form_data = None
    raw_parent = request.args.get('parent_id', '')
    if raw_parent.isdigit():
        parent = db.session.get(Issue, int(raw_parent))
        child_type = {'epic': 'feature', 'feature': 'task'}.get(parent.type) if parent else None
        if parent and child_type:
            form_data = {
                'type': child_type,
                'parent_id': parent.id,
                'project_id': parent.project_id or '',
                'customer_id': parent.customer_id or '',
                'team_id': parent.team_id or '',
                'component_id': parent.component_id or '',
                'sprint_id': (parent.sprint_id
                              if parent.sprint and not parent.sprint.is_closed
                              else ''),
            }
    return render_template('issues/form.html', issue=None, form_data=form_data,
                           parent_options=_parent_options(), **_form_choices())


@bp.route('/<int:issue_id>')
@login_required
def view(issue_id):
    issue = db.session.get(Issue, issue_id) or abort(404)
    return render_template('issues/view.html', issue=issue, **_form_choices())


@bp.route('/<int:issue_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(issue_id):
    issue = db.session.get(Issue, issue_id) or abort(404)
    if request.method == 'POST':
        old = snapshot(issue)
        try:
            _apply_form(issue)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return render_template('issues/form.html', issue=issue,
                                   form_data=request.form,
                                   parent_options=_parent_options(issue),
                                   **_form_choices())
        record_update(issue, old, current_user)
        db.session.commit()
        flash('Задача обновлена.', 'success')
        return redirect(url_for('issues.view', issue_id=issue.id))
    return render_template('issues/form.html', issue=issue, form_data=None,
                           parent_options=_parent_options(issue),
                           **_form_choices())


@bp.post('/<int:issue_id>/delete')
@login_required
def delete(issue_id):
    issue = db.session.get(Issue, issue_id) or abort(404)
    if issue.children:
        flash('Сначала удали или перенеси дочерние задачи.', 'danger')
        return redirect(url_for('issues.view', issue_id=issue.id))
    db.session.delete(issue)
    db.session.commit()
    flash(f'Задача #{issue_id} удалена.', 'success')
    return redirect(url_for('issues.index'))


@bp.post('/<int:issue_id>/comment')
@login_required
def comment(issue_id):
    issue = db.session.get(Issue, issue_id) or abort(404)
    body = normalize_spaces(request.form.get('body', '').strip())
    files = [f for f in request.files.getlist('files') if f and f.filename]
    if not body and not files:
        flash('Пустой комментарий.', 'danger')
        return redirect(url_for('issues.view', issue_id=issue.id) + '#comments')
    new_comment = Comment(issue_id=issue.id, author_id=current_user.id,
                          body=body or '')
    db.session.add(new_comment)
    db.session.flush()
    _save_attachments(issue, files, comment=new_comment)
    add_event(issue, current_user, 'commented')
    db.session.commit()
    return redirect(url_for('issues.view', issue_id=issue.id) + '#comments')


@bp.post('/<int:issue_id>/attach')
@login_required
def attach(issue_id):
    issue = db.session.get(Issue, issue_id) or abort(404)
    count = _save_attachments(issue, request.files.getlist('files'))
    if count:
        db.session.commit()
        flash(f'Файлов добавлено: {count}.', 'success')
    else:
        flash('Файлы не выбраны.', 'danger')
    return redirect(url_for('issues.view', issue_id=issue.id) + '#files')


# Поля, которые можно менять прямо со страницы просмотра задачи:
# поле -> (модель для проверки id, можно ли очистить)
INLINE_FIELDS = {
    'status_id': (Status, False),
    'assignee_id': (User, True),
    'project_id': (Project, True),
    'team_id': (Team, True),
    'customer_id': (Customer, True),
    'component_id': (Component, True),
    'sprint_id': (Sprint, True),
}


@bp.post('/<int:issue_id>/set')
@login_required
def set_field(issue_id):
    """Смена одного поля со страницы просмотра задачи."""
    issue = db.session.get(Issue, issue_id) or abort(404)
    field = request.form.get('field', '')
    if field not in INLINE_FIELDS:
        abort(400)
    model, nullable = INLINE_FIELDS[field]
    raw = request.form.get('value') or None
    old = snapshot(issue)
    if raw:
        obj = db.session.get(model, int(raw)) or abort(400)
        setattr(issue, field, obj.id)
    elif nullable:
        setattr(issue, field, None)
    else:
        abort(400)
    record_update(issue, old, current_user)
    db.session.commit()
    return redirect(url_for('issues.view', issue_id=issue.id))


@bp.post('/<int:issue_id>/move')
@login_required
def move(issue_id):
    """Смена статуса и/или спринта — с доски (JSON) или со страницы задачи (форма)."""
    issue = db.session.get(Issue, issue_id) or abort(404)
    data = request.get_json(silent=True) or request.form
    old = snapshot(issue)

    if 'status_id' in data and data.get('status_id'):
        status = db.session.get(Status, int(data['status_id'])) or abort(400)
        issue.status_id = status.id
    if 'sprint_id' in data:
        sprint_id = data.get('sprint_id') or None
        if sprint_id:
            sprint = db.session.get(Sprint, int(sprint_id)) or abort(400)
            issue.sprint_id = sprint.id
        else:
            issue.sprint_id = None

    record_update(issue, old, current_user)
    db.session.commit()

    if request.is_json:
        return jsonify(ok=True)
    return redirect(request.referrer or url_for('issues.view', issue_id=issue.id))

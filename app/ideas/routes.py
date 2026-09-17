"""Раздел «Идеи»: своя доска, свои статусы, архивация и передача в разработку."""
import os
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from markupsafe import Markup, escape

from ..extensions import db
from ..files import save_upload
from ..filters import any_condition, multi_condition
from ..models import (PRIORITIES, Attachment, Component, Customer, Idea,
                      IdeaComment, IdeaStatus, Issue, Project, Status, Team,
                      User, assign_components)
from ..textutils import normalize_spaces

bp = Blueprint('ideas', __name__, url_prefix='/ideas')

# Поля идеи с одним значением-ссылкой (для формы, вью и переноса в эпик).
# Спринт у идей нет — исключён осознанно. Компонент обрабатывается отдельно
# (может быть мультивыбором).
IDEA_FIELDS = ('assignee_id', 'project_id', 'team_id', 'customer_id')


def _first_status():
    return IdeaStatus.query.order_by(IdeaStatus.position).first()


def _choices():
    return dict(
        statuses=IdeaStatus.query.order_by(IdeaStatus.position).all(),
        users=User.query.order_by(User.name).all(),
        projects=Project.query.order_by(Project.name).all(),
        teams=Team.query.order_by(Team.name).all(),
        customers=Customer.query.order_by(Customer.name).all(),
        components=Component.query.order_by(Component.name).all(),
        priorities=PRIORITIES,
    )


def _apply_fields(idea):
    """Проставляет из формы приоритет и поля-ссылки идеи."""
    priority = request.form.get('priority') or 'normal'
    idea.priority = priority if priority in PRIORITIES else 'normal'
    for field in IDEA_FIELDS:
        value = request.form.get(field) or None
        setattr(idea, field, int(value) if value else None)
    # компоненты — мультивыбор
    assign_components(idea, request.form.getlist('component_ids'))


def _save_idea_files(idea, files):
    count = 0
    for file in files:
        if not file or not file.filename:
            continue
        rel = save_upload(file, 'attachments')
        size = os.path.getsize(os.path.join(current_app.config['UPLOAD_FOLDER'], rel))
        db.session.add(Attachment(idea_id=idea.id, original_name=file.filename,
                                  stored_name=rel, size=size,
                                  uploaded_by_id=current_user.id))
        count += 1
    return count


def _apply_idea_filters(query, args):
    """Фильтры доски идей: проект, команда, заказчик, компонент (мультивыбор
    + «не задано»), как на вкладке «Задачи»."""
    for field, column in (('project_id', Idea.project_id),
                          ('team_id', Idea.team_id),
                          ('customer_id', Idea.customer_id)):
        cond = multi_condition(column, args.getlist(field))
        if cond is not None:
            query = query.filter(cond)
    comp_cond = any_condition(Idea.components, Component.id,
                              args.getlist('component_id'))
    if comp_cond is not None:
        query = query.filter(comp_cond)
    return query


@bp.route('/')
@login_required
def board():
    statuses = IdeaStatus.query.order_by(IdeaStatus.position).all()
    active = (_apply_idea_filters(Idea.query.filter_by(archived=False), request.args)
              .order_by(Idea.id.desc()).all())
    cells = {s.id: [] for s in statuses}
    no_status = []
    for idea in active:
        if idea.status_id in cells:
            cells[idea.status_id].append(idea)
        else:
            no_status.append(idea)

    show_archived = request.args.get('show_archived') == '1'
    archived = []
    if show_archived:
        archived = (_apply_idea_filters(Idea.query.filter_by(archived=True), request.args)
                    .order_by(Idea.archived_at.desc().nullslast(), Idea.id.desc()).all())

    return render_template('ideas/board.html', cells=cells,
                           no_status=no_status, archived=archived,
                           show_archived=show_archived, active_count=len(active),
                           args=request.args, **_choices())


# Поля-ссылки идеи для группового блока (приоритет обрабатывается отдельно)
IDEA_BULK_FIELDS = ('status_id', 'assignee_id', 'project_id', 'team_id',
                    'customer_id', 'component_id')


@bp.post('/bulk-apply')
@login_required
def bulk_apply():
    """Групповая установка полей для всех активных идей текущего фильтра."""
    ideas = _apply_idea_filters(Idea.query.filter_by(archived=False),
                                request.form).all()
    changes = {}
    for field in IDEA_BULK_FIELDS:
        raw = request.form.get('set_' + field, '')
        if raw == '':
            continue
        changes[field] = None if raw == '__clear__' else int(raw)
    new_priority = request.form.get('set_priority', '')
    apply_priority = new_priority in PRIORITIES

    # вернёмся на тот же отфильтрованный список
    filter_args = {k: request.form.getlist(k)
                   for k in ('project_id', 'team_id', 'customer_id', 'component_id')
                   if request.form.getlist(k)}
    if request.form.get('show_archived'):
        filter_args['show_archived'] = '1'
    target = url_for('ideas.board', **filter_args)

    if not changes and not apply_priority:
        flash('Не выбрано ни одного поля для изменения.', 'warning')
    elif not ideas:
        flash('Под текущий фильтр не попала ни одна идея.', 'warning')
    else:
        for idea in ideas:
            for field, value in changes.items():
                if field == 'component_id':
                    assign_components(idea, [value] if value else [])
                else:
                    setattr(idea, field, value)
            if apply_priority:
                idea.priority = new_priority
        db.session.commit()
        flash(f'Обновлено идей: {len(ideas)}.', 'success')
    return redirect(target)


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Название обязательно.', 'danger')
            return render_template('ideas/form.html', idea=None,
                                   form_data=request.form, **_choices())
        idea = Idea(title=title,
                    summary=normalize_spaces(request.form.get('summary', '')),
                    reporter_id=current_user.id)
        status_id = request.form.get('status_id', type=int)
        idea.status_id = status_id or (_first_status().id if _first_status() else None)
        _apply_fields(idea)
        db.session.add(idea)
        db.session.flush()
        _save_idea_files(idea, request.files.getlist('files'))
        db.session.commit()
        flash(f'Идея #{idea.id} создана.', 'success')
        return redirect(url_for('ideas.view', idea_id=idea.id))
    return render_template('ideas/form.html', idea=None, form_data=None, **_choices())


@bp.route('/<int:idea_id>')
@login_required
def view(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    return render_template('ideas/view.html', idea=idea, **_choices())


@bp.route('/<int:idea_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Название обязательно.', 'danger')
            return render_template('ideas/form.html', idea=idea,
                                   form_data=request.form, **_choices())
        idea.title = title
        idea.summary = normalize_spaces(request.form.get('summary', ''))
        status_id = request.form.get('status_id', type=int)
        if status_id:
            idea.status_id = status_id
        _apply_fields(idea)
        db.session.commit()
        flash('Идея обновлена.', 'success')
        return redirect(url_for('ideas.view', idea_id=idea.id))
    return render_template('ideas/form.html', idea=idea, form_data=None, **_choices())


# Поля идеи, редактируемые прямо со страницы просмотра
INLINE_FIELDS = {
    'assignee_id': User,
    'project_id': Project,
    'team_id': Team,
    'customer_id': Customer,
    'component_id': Component,
}


@bp.post('/<int:idea_id>/set')
@login_required
def set_field(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    field = request.form.get('field', '')
    if field == 'priority':
        value = request.form.get('value', '')
        if value not in PRIORITIES:
            abort(400)
        idea.priority = value
    elif field == 'status_id':
        value = request.form.get('value') or None
        idea.status_id = int(value) if value else None
    elif field == 'component_id':
        raw = request.form.get('value') or None
        assign_components(idea, [raw] if raw else [])
    elif field in INLINE_FIELDS:
        raw = request.form.get('value') or None
        if raw:
            obj = db.session.get(INLINE_FIELDS[field], int(raw)) or abort(400)
            setattr(idea, field, obj.id)
        else:
            setattr(idea, field, None)
    else:
        abort(400)
    db.session.commit()
    return redirect(url_for('ideas.view', idea_id=idea.id))


@bp.post('/<int:idea_id>/set-components')
@login_required
def set_components(idea_id):
    """Установка нескольких компонентов идеи (форма: component_ids[])."""
    idea = db.session.get(Idea, idea_id) or abort(404)
    assign_components(idea, request.form.getlist('component_ids'))
    db.session.commit()
    return redirect(url_for('ideas.view', idea_id=idea.id))


@bp.post('/<int:idea_id>/attach')
@login_required
def attach(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    count = _save_idea_files(idea, request.files.getlist('files'))
    if count:
        db.session.commit()
        flash(f'Файлов добавлено: {count}.', 'success')
    else:
        flash('Файлы не выбраны.', 'danger')
    return redirect(url_for('ideas.view', idea_id=idea.id) + '#files')


@bp.post('/<int:idea_id>/move')
@login_required
def move(idea_id):
    """Смена статуса идеи — с доски (JSON) или со страницы (форма)."""
    idea = db.session.get(Idea, idea_id) or abort(404)
    data = request.get_json(silent=True) or request.form
    status_id = data.get('status_id')
    if status_id:
        status = db.session.get(IdeaStatus, int(status_id)) or abort(400)
        idea.status_id = status.id
        db.session.commit()
    if request.is_json:
        return jsonify(ok=True)
    return redirect(url_for('ideas.view', idea_id=idea.id))


@bp.post('/<int:idea_id>/reject')
@login_required
def reject(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    if not idea.archived:
        idea.archived = True
        idea.archive_reason = 'rejected'
        idea.archived_at = datetime.utcnow()
        db.session.commit()
        flash(f'Идея #{idea.id} отклонена и убрана в архив.', 'success')
    return redirect(url_for('ideas.view', idea_id=idea.id))


@bp.post('/<int:idea_id>/to-dev')
@login_required
def to_dev(idea_id):
    """Передать идею в разработку: создать эпик из идеи и архивировать идею."""
    idea = db.session.get(Idea, idea_id) or abort(404)
    if idea.archived:
        flash('Идея уже в архиве.', 'info')
        return redirect(url_for('ideas.view', idea_id=idea.id))

    first_issue_status = Status.query.order_by(Status.position).first()
    if not first_issue_status:
        flash('В системе нет статусов задач — добавьте в Справочниках.', 'danger')
        return redirect(url_for('ideas.view', idea_id=idea.id))

    # Переносим в эпик всё, кроме комментариев и истории; ссылка на исходную идею.
    epic = Issue(type='epic', title=idea.title, summary=idea.summary,
                 priority=idea.priority, reporter_id=current_user.id,
                 assignee_id=idea.assignee_id, project_id=idea.project_id,
                 team_id=idea.team_id, customer_id=idea.customer_id,
                 component_id=idea.component_id, status_id=first_issue_status.id,
                 source_idea_id=idea.id)
    db.session.add(epic)
    db.session.flush()
    # переносим весь набор компонентов идеи на эпик
    assign_components(epic, [c.id for c in idea.component_list])
    # Переносим вложения идеи на эпик
    for att in idea.attachments:
        db.session.add(Attachment(
            issue_id=epic.id, original_name=att.original_name,
            stored_name=att.stored_name, size=att.size,
            uploaded_by_id=att.uploaded_by_id))

    idea.archived = True
    idea.archive_reason = 'to_dev'
    idea.archived_at = datetime.utcnow()
    db.session.commit()

    epic_url = url_for('issues.view', issue_id=epic.id)
    flash(Markup(
        f'Идея #{escape(idea.id)} передана в разработку — создан эпик '
        f'<a href="{escape(epic_url)}" class="alert-link">#{escape(epic.id)} '
        f'{escape(epic.title)}</a>.'), 'success')
    return redirect(epic_url)


@bp.post('/<int:idea_id>/restore')
@login_required
def restore(idea_id):
    """Вернуть идею из архива (например, отклонённую передумали закрывать)."""
    idea = db.session.get(Idea, idea_id) or abort(404)
    idea.archived = False
    idea.archive_reason = None
    idea.archived_at = None
    db.session.commit()
    flash(f'Идея #{idea.id} возвращена из архива.', 'success')
    return redirect(url_for('ideas.view', idea_id=idea.id))


@bp.post('/<int:idea_id>/delete')
@login_required
def delete(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    if idea.epic:
        flash('Нельзя удалить: из идеи создан эпик #%d.' % idea.epic.id, 'danger')
        return redirect(url_for('ideas.view', idea_id=idea.id))
    db.session.delete(idea)
    db.session.commit()
    flash(f'Идея #{idea_id} удалена.', 'success')
    return redirect(url_for('ideas.board'))


@bp.post('/<int:idea_id>/comment')
@login_required
def comment(idea_id):
    idea = db.session.get(Idea, idea_id) or abort(404)
    body = normalize_spaces(request.form.get('body', '').strip())
    if not body:
        flash('Пустой комментарий.', 'danger')
        return redirect(url_for('ideas.view', idea_id=idea.id) + '#comments')
    db.session.add(IdeaComment(idea_id=idea.id, author_id=current_user.id, body=body))
    db.session.commit()
    return redirect(url_for('ideas.view', idea_id=idea.id) + '#comments')


@bp.post('/<int:idea_id>/comment/<int:comment_id>/edit')
@login_required
def comment_edit(idea_id, comment_id):
    cm = db.session.get(IdeaComment, comment_id) or abort(404)
    if cm.idea_id != idea_id:
        abort(404)
    if cm.author_id != current_user.id:
        abort(403)
    body = normalize_spaces(request.form.get('body', '').strip())
    anchor = url_for('ideas.view', idea_id=idea_id) + '#comments'
    if not body:
        flash('Комментарий не может быть пустым.', 'danger')
        return redirect(anchor)
    cm.body = body
    cm.edited_at = datetime.utcnow()
    db.session.commit()
    return redirect(anchor)

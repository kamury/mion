from datetime import datetime

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..history import add_event
from ..models import Board, Issue, QuickFilter, Sprint, Status
from ..sql_runner import run_ids_query

bp = Blueprint('boards', __name__, url_prefix='/boards')


def _parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


@bp.route('/')
@login_required
def index():
    boards = Board.query.order_by(Board.name).all()
    return render_template('boards/index.html', boards=boards)


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        query_sql = request.form.get('query_sql', '').strip()
        if not name or not query_sql:
            flash('Название и SQL-запрос обязательны.', 'danger')
        else:
            board = Board(name=name, query_sql=query_sql, owner_id=current_user.id)
            db.session.add(board)
            db.session.commit()
            flash('Доска создана.', 'success')
            return redirect(url_for('boards.view', board_id=board.id))
    return render_template('boards/form.html', board=None)


@bp.route('/<int:board_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(board_id):
    board = db.session.get(Board, board_id) or abort(404)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        query_sql = request.form.get('query_sql', '').strip()
        if not name or not query_sql:
            flash('Название и SQL-запрос обязательны.', 'danger')
        else:
            board.name = name
            board.query_sql = query_sql
            db.session.commit()
            flash('Доска сохранена.', 'success')
            return redirect(url_for('boards.view', board_id=board.id))
    return render_template('boards/form.html', board=board)


@bp.post('/<int:board_id>/delete')
@login_required
def delete(board_id):
    board = db.session.get(Board, board_id) or abort(404)
    # Спринты удаляемой доски отвязываем — станут видны на всех досках
    Sprint.query.filter_by(board_id=board.id).update({'board_id': None})
    db.session.delete(board)
    db.session.commit()
    flash('Доска удалена.', 'success')
    return redirect(url_for('boards.index'))


@bp.post('/<int:board_id>/filters/add')
@login_required
def add_filter(board_id):
    board = db.session.get(Board, board_id) or abort(404)
    name = request.form.get('name', '').strip()
    query_sql = request.form.get('query_sql', '').strip()
    if not name or not query_sql:
        flash('Название и SQL-запрос фильтра обязательны.', 'danger')
    else:
        db.session.add(QuickFilter(board_id=board.id, name=name,
                                   query_sql=query_sql))
        db.session.commit()
        flash('Быстрый фильтр добавлен.', 'success')
    return redirect(url_for('boards.edit', board_id=board.id))


@bp.post('/filters/<int:filter_id>/delete')
@login_required
def delete_filter(filter_id):
    qfilter = db.session.get(QuickFilter, filter_id) or abort(404)
    board_id = qfilter.board_id
    db.session.delete(qfilter)
    db.session.commit()
    flash('Фильтр удалён.', 'success')
    return redirect(url_for('boards.edit', board_id=board_id))


@bp.route('/<int:board_id>')
@login_required
def view(board_id):
    board = db.session.get(Board, board_id) or abort(404)
    params = {'current_user_id': current_user.id}

    error = None
    issue_ids = set()
    try:
        issue_ids = run_ids_query(board.query_sql, params)
    except Exception as e:
        error = f'Ошибка в запросе доски: {e}'

    # Быстрые фильтры: можно выбрать несколько, выборки пересекаются (И).
    # Взаимоисключающие фильтры дают пустую доску — это ожидаемо.
    selected_ids = set(request.args.getlist('filter', type=int))
    active_filter_ids = []
    if selected_ids and not error:
        for qfilter in board.filters:
            if qfilter.id not in selected_ids:
                continue
            active_filter_ids.append(qfilter.id)
            try:
                issue_ids &= run_ids_query(qfilter.query_sql, params)
            except Exception as e:
                error = f'Ошибка в быстром фильтре «{qfilter.name}»: {e}'
                break

    issues = (Issue.query.filter(Issue.id.in_(issue_ids)).all()
              if issue_ids else [])

    statuses = Status.query.order_by(Status.position).all()
    all_open_sprints = (Sprint.query.filter_by(is_closed=False)
                        .order_by(Sprint.start_date.asc().nullslast(), Sprint.id)
                        .all())

    # Видимость спринта на доске:
    # - спринт этой доски (или без привязки) виден всегда, даже пустой;
    # - чужой спринт виден, только если на доске есть его задачи.
    sprints_with_issues_here = {i.sprint_id for i in issues if i.sprint_id}
    board_sprints = [
        s for s in all_open_sprints
        if s.board_id in (None, board.id) or s.id in sprints_with_issues_here
    ]
    visible_sprint_ids = {s.id for s in board_sprints}

    # Свимлейны: видимые спринты + Backlog (без спринта или спринт закрыт)
    lanes = []
    for sprint in board_sprints:
        lanes.append({'sprint': sprint,
                      'cells': {s.id: [] for s in statuses}})
    backlog = {'sprint': None, 'cells': {s.id: [] for s in statuses}}

    lane_by_sprint = {lane['sprint'].id: lane for lane in lanes}
    for issue in sorted(issues, key=lambda i: i.id):
        lane = (lane_by_sprint.get(issue.sprint_id)
                if issue.sprint_id in visible_sprint_ids else None) or backlog
        if issue.status_id in lane['cells']:
            lane['cells'][issue.status_id].append(issue)
    lanes.append(backlog)

    # Незакрытые задачи каждого спринта (для диалога закрытия) — независимо
    # от запроса доски, чтобы цифры не расходились с тем, что видно на доске
    unfinished_by_sprint = {}
    for sprint in board_sprints:
        unfinished_by_sprint[sprint.id] = (
            Issue.query.join(Status)
            .filter(Issue.sprint_id == sprint.id, Status.is_done.is_(False))
            .order_by(Issue.id).all())

    return render_template('boards/view.html', board=board, lanes=lanes,
                           statuses=statuses, board_sprints=board_sprints,
                           all_open_sprints=all_open_sprints,
                           unfinished_by_sprint=unfinished_by_sprint,
                           active_filter_ids=active_filter_ids, error=error,
                           issue_count=len(issues))


# ---------- Спринты ----------

@bp.post('/sprints/new')
@login_required
def sprint_new():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Название спринта обязательно.', 'danger')
    else:
        db.session.add(Sprint(
            name=name,
            start_date=_parse_date(request.form.get('start_date')),
            end_date=_parse_date(request.form.get('end_date')),
            board_id=request.form.get('board_id', type=int),
        ))
        db.session.commit()
        flash('Спринт создан.', 'success')
    return redirect(request.referrer or url_for('boards.index'))


@bp.post('/sprints/<int:sprint_id>/edit')
@login_required
def sprint_edit(sprint_id):
    sprint = db.session.get(Sprint, sprint_id) or abort(404)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Название спринта обязательно.', 'danger')
    else:
        sprint.name = name
        sprint.start_date = _parse_date(request.form.get('start_date'))
        sprint.end_date = _parse_date(request.form.get('end_date'))
        db.session.commit()
        flash('Спринт обновлён.', 'success')
    return redirect(request.referrer or url_for('boards.index'))


@bp.post('/sprints/<int:sprint_id>/close')
@login_required
def sprint_close(sprint_id):
    sprint = db.session.get(Sprint, sprint_id) or abort(404)
    if sprint.is_closed:
        flash('Спринт уже закрыт.', 'info')
        return redirect(request.referrer or url_for('boards.index'))

    target_id = request.form.get('target_sprint_id') or None
    target = db.session.get(Sprint, int(target_id)) if target_id else None
    if target_id and (not target or target.is_closed or target.id == sprint.id):
        flash('Некорректный спринт для переноса задач.', 'danger')
        return redirect(request.referrer or url_for('boards.index'))

    unfinished = (Issue.query.join(Status)
                  .filter(Issue.sprint_id == sprint.id, Status.is_done.is_(False))
                  .all())
    for issue in unfinished:
        issue.sprint_id = target.id if target else None
        add_event(issue, current_user, 'updated', field='Спринт',
                  old_value=sprint.name,
                  new_value=target.name if target else None)

    sprint.is_closed = True
    db.session.commit()

    moved_to = f'в «{target.name}»' if target else 'в Backlog'
    flash(f'Спринт «{sprint.name}» закрыт. '
          f'Незакрытых задач перенесено {moved_to}: {len(unfinished)}.', 'success')
    return redirect(request.referrer or url_for('boards.index'))

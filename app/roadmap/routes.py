"""Роадмап эпиков: таймлайн по датам + сводка по задачам эпика."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import (Blueprint, abort, flash, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from ..extensions import db
from ..filters import scalar_ok, set_ok
from ..history import record_update, snapshot
from ..models import (ISSUE_TYPES, PRIORITIES, Component, Issue, Project,
                      Status, Team, User)

bp = Blueprint('roadmap', __name__, url_prefix='/roadmap')

# Порядок типов в сводке «по статусам»
TYPE_ORDER = ['feature', 'task', 'bug']

MONTHS_RU = ['янв', 'фев', 'мар', 'апр', 'май', 'июн',
             'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']


def _next_month(d):
    return (d.replace(day=28) + timedelta(days=7)).replace(day=1)


def _parse_date(value):
    value = (value or '').strip()
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


def _descendants(epic, children_map):
    """Все задачи под эпиком (фичи + их таски/баги), вглубь по дереву."""
    out, stack = [], list(children_map.get(epic.id, []))
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(children_map.get(node.id, []))
    return out


def _build_rows(epics, children_map, statuses):
    """Для каждого эпика — исполнители и разбивка задач по статусам/типам."""
    rows = []
    for epic in epics:
        desc = _descendants(epic, children_map)

        assignees = sorted(
            {i.assignee for i in desc if i.assignee},
            key=lambda u: u.name.lower())

        # {status_id: Counter(type)}
        by_status = defaultdict(Counter)
        for i in desc:
            by_status[i.status_id][i.type] += 1

        breakdown = []
        for st in statuses:
            counts = by_status.get(st.id)
            if not counts:
                continue
            parts = [(ISSUE_TYPES[t], counts[t]) for t in TYPE_ORDER if counts[t]]
            breakdown.append({'status': st, 'parts': parts,
                              'total': sum(counts.values())})

        rows.append({
            'epic': epic,
            'total': len(desc),
            'assignees': assignees,
            'breakdown': breakdown,
        })
    return rows


def _timeline(epics_with_dates):
    """Помесячная шкала и позиции полос (в процентах) для эпиков с датами."""
    if not epics_with_dates:
        return None

    # шкала от начала первого месяца до начала месяца после последнего
    span_start = min(e.start_date for e in epics_with_dates).replace(day=1)
    span_end = max(e.end_date for e in epics_with_dates)
    scale_end = _next_month(span_end.replace(day=1))
    total_days = (scale_end - span_start).days

    # помесячные колонки, ширина пропорциональна числу дней в месяце
    months, cur = [], span_start
    while cur < scale_end:
        nxt = _next_month(cur)
        months.append({
            'label': f'{MONTHS_RU[cur.month - 1]} {cur.year}',
            'width': round((nxt - cur).days / total_days * 100, 3),
        })
        cur = nxt

    # накопительный left для вертикальных линий сетки
    acc = 0
    for m in months:
        m['left'] = round(acc, 3)
        acc += m['width']

    bars = {}
    for e in epics_with_dates:
        left = (e.start_date - span_start).days / total_days * 100
        # +1 день, чтобы однодневный эпик имел ненулевую ширину
        width = ((e.end_date - e.start_date).days + 1) / total_days * 100
        bars[e.id] = {'left': round(left, 3), 'width': round(width, 3)}

    return {'months': months, 'bars': bars}


def _passes_filters(row, args):
    """Фильтры как на вкладке «Задачи», применённые к эпику и его задачам."""
    epic = row['epic']

    if not scalar_ok(epic.priority, args.getlist('priority')):
        return False
    for field in ('project_id', 'team_id', 'component_id'):
        if not scalar_ok(getattr(epic, field), args.getlist(field)):
            return False

    # исполнитель и статус — по задачам эпика (то, что показано в строке);
    # «не задано» = нет исполнителей / нет задач
    if not set_ok({u.id for u in row['assignees']}, args.getlist('assignee_id')):
        return False
    if not set_ok({b['status'].id for b in row['breakdown']},
                  args.getlist('status_id')):
        return False

    q = (args.get('q') or '').strip().lower()
    if q and q not in epic.title.lower():
        return False

    return True


@bp.route('/')
@login_required
def index():
    epics = Issue.query.filter_by(type='epic').order_by(Issue.id).all()

    # Всё дерево задач одним запросом -> карта родитель->дети
    children_map = defaultdict(list)
    for i in Issue.query.filter(Issue.parent_id.isnot(None)).all():
        children_map[i.parent_id].append(i)

    statuses = Status.query.order_by(Status.position).all()
    rows = _build_rows(epics, children_map, statuses)
    rows = [r for r in rows if _passes_filters(r, request.args)]

    # эпики с обеими датами — на таймлайн (по дате начала), остальные —
    # списком снизу в стабильном порядке по id (чтобы не «прыгали», пока
    # не заданы обе даты)
    dated = [r for r in rows if r['epic'].start_date and r['epic'].end_date]
    dated.sort(key=lambda r: (r['epic'].start_date, r['epic'].id))
    undated = [r for r in rows if r not in dated]
    timeline = _timeline([r['epic'] for r in dated])

    choices = dict(
        priorities=PRIORITIES,
        statuses=statuses,
        users=User.query.order_by(User.name).all(),
        projects=Project.query.order_by(Project.name).all(),
        teams=Team.query.order_by(Team.name).all(),
        components=Component.query.order_by(Component.name).all(),
    )

    return render_template('roadmap/index.html', dated_rows=dated,
                           undated_rows=undated, timeline=timeline,
                           any_epics=bool(epics), args=request.args, **choices)


@bp.post('/<int:epic_id>/dates')
@login_required
def set_dates(epic_id):
    epic = db.session.get(Issue, epic_id) or abort(404)
    if epic.type != 'epic':
        abort(400)
    # Роадмап сохраняет даты фоново (fetch) — тогда отвечаем JSON без редиректа,
    # чтобы страница не перезагружалась после каждого поля.
    ajax = request.headers.get('X-Requested-With') == 'fetch'
    base = (request.referrer or url_for('roadmap.index')).split('#')[0]

    def fail(msg):
        if ajax:
            return jsonify(ok=False, error=msg)
        flash(msg, 'danger')
        return redirect(base + f'#epic-{epic.id}')

    try:
        start = _parse_date(request.form.get('start_date'))
        end = _parse_date(request.form.get('end_date'))
    except ValueError:
        return fail('Некорректная дата.')

    if start and end and end < start:
        return fail(f'У эпика #{epic.id}: дата конца раньше даты начала.')

    old = snapshot(epic)
    epic.start_date = start
    epic.end_date = end
    record_update(epic, old, current_user)
    db.session.commit()

    if ajax:
        return jsonify(ok=True, both=bool(start and end))
    return redirect(base + f'#epic-{epic.id}')

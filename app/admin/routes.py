"""Справочники: проекты, команды, заказчики, статусы workflow."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Customer, Project, Status, Team

bp = Blueprint('admin', __name__, url_prefix='/admin')

KINDS = {
    'project': (Project, 'Проект'),
    'team': (Team, 'Команда'),
    'customer': (Customer, 'Заказчик'),
    'status': (Status, 'Статус'),
}


def _model(kind):
    if kind not in KINDS:
        abort(404)
    return KINDS[kind][0]


@bp.route('/')
@login_required
def index():
    return render_template(
        'admin/index.html',
        projects=Project.query.order_by(Project.name).all(),
        teams=Team.query.order_by(Team.name).all(),
        customers=Customer.query.order_by(Customer.name).all(),
        statuses=Status.query.order_by(Status.position).all(),
    )


@bp.post('/<kind>/add')
@login_required
def add(kind):
    model = _model(kind)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Название обязательно.', 'danger')
        return redirect(url_for('admin.index'))
    item = model(name=name)
    if kind == 'status':
        item.position = request.form.get('position', type=int) or 0
        item.is_done = bool(request.form.get('is_done'))
    db.session.add(item)
    try:
        db.session.commit()
        flash(f'{KINDS[kind][1]} «{name}» добавлен(а).', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Такое название уже есть.', 'danger')
    return redirect(url_for('admin.index'))


@bp.post('/<kind>/<int:item_id>/update')
@login_required
def update(kind, item_id):
    model = _model(kind)
    item = db.session.get(model, item_id) or abort(404)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Название обязательно.', 'danger')
        return redirect(url_for('admin.index'))
    item.name = name
    if kind == 'status':
        item.position = request.form.get('position', type=int) or 0
        item.is_done = bool(request.form.get('is_done'))
    try:
        db.session.commit()
        flash('Сохранено.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Такое название уже есть.', 'danger')
    return redirect(url_for('admin.index'))


@bp.post('/<kind>/<int:item_id>/delete')
@login_required
def delete(kind, item_id):
    model = _model(kind)
    item = db.session.get(model, item_id) or abort(404)
    db.session.delete(item)
    try:
        db.session.commit()
        flash('Удалено.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Нельзя удалить: значение используется в задачах.', 'danger')
    return redirect(url_for('admin.index'))

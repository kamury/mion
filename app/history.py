"""Запись истории изменений issue."""
import re

from .extensions import db
from . import models

# Отслеживаемые поля и их человекочитаемые названия.
# Компоненты обрабатываются отдельно (это набор значений, а не одно) — см. ниже.
FIELD_LABELS = {
    'type': 'Тип',
    'parent_id': 'Родитель',
    'title': 'Название',
    'summary': 'Описание',
    'priority': 'Приоритет',
    'reporter_id': 'Автор',
    'assignee_id': 'Исполнитель',
    'project_id': 'Проект',
    'team_id': 'Команда',
    'customer_id': 'Заказчик',
    'sprint_id': 'Спринт',
    'status_id': 'Статус',
    'start_date': 'Дата начала',
    'end_date': 'Дата конца',
}

_FK_MODELS = {
    'parent_id': ('Issue', 'title'),
    'reporter_id': ('User', 'name'),
    'assignee_id': ('User', 'name'),
    'project_id': ('Project', 'name'),
    'team_id': ('Team', 'name'),
    'customer_id': ('Customer', 'name'),
    'sprint_id': ('Sprint', 'name'),
    'status_id': ('Status', 'name'),
}

# Ключ в снимке под набор компонентов (M2M). Отдельно от скалярных полей.
_COMPONENTS = '_components'


def snapshot(issue):
    """Снимок отслеживаемых полей до изменения (плюс набор компонентов)."""
    snap = {field: getattr(issue, field) for field in FIELD_LABELS}
    snap[_COMPONENTS] = tuple(sorted(c.id for c in issue.component_list))
    return snap


def _display(field, value):
    """Человекочитаемое значение поля для записи в историю."""
    if value is None or value == '':
        return None
    if field == 'summary':
        text = re.sub(r'<[^>]+>', ' ', value)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:200] + '…' if len(text) > 200 else text
    if field == 'type':
        return models.ISSUE_TYPES.get(value, str(value))
    if field == 'priority':
        return models.PRIORITIES.get(value, str(value))
    if field in ('start_date', 'end_date'):
        return value.strftime('%d.%m.%Y')
    if field in _FK_MODELS:
        model_name, attr = _FK_MODELS[field]
        obj = db.session.get(getattr(models, model_name), value)
        return getattr(obj, attr) if obj else str(value)
    return str(value)


def _component_names(ids):
    """Имена компонентов по id (через запятую) для записи в историю."""
    if not ids:
        return None
    names = []
    for cid in ids:
        obj = db.session.get(models.Component, cid)
        names.append(obj.name if obj else str(cid))
    return ', '.join(names) or None


def record_update(issue, old_snapshot, user):
    """Сравнивает snapshot с текущим состоянием и пишет изменения в историю."""
    changed = False
    for field, old_value in old_snapshot.items():
        if field == _COMPONENTS:
            continue  # набор компонентов — отдельной записью ниже
        new_value = getattr(issue, field)
        if new_value != old_value:
            changed = True
            db.session.add(models.IssueHistory(
                issue=issue,
                user_id=user.id,
                action='updated',
                field=FIELD_LABELS[field],
                old_value=_display(field, old_value),
                new_value=_display(field, new_value),
            ))
    # Компоненты: пишем изменение всего набора (видно и добавления, и удаления)
    old_components = old_snapshot.get(_COMPONENTS, ())
    new_components = tuple(sorted(c.id for c in issue.component_list))
    if old_components != new_components:
        changed = True
        db.session.add(models.IssueHistory(
            issue=issue,
            user_id=user.id,
            action='updated',
            field='Компоненты',
            old_value=_component_names(old_components),
            new_value=_component_names(new_components),
        ))
    return changed


def add_event(issue, user, action, field=None, old_value=None, new_value=None):
    db.session.add(models.IssueHistory(
        issue=issue,
        user_id=user.id,
        action=action,
        field=field,
        old_value=old_value,
        new_value=new_value,
    ))

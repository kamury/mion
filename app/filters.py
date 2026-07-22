"""Помощники для фильтров списков (мультивыбор + «значение не задано»)."""
from sqlalchemy import or_

# Спецзначение опции «— не задано —» в мультиселектах фильтров
NONE_TOKEN = '__none__'


def _split(raw):
    """Разбивает выбранные значения на конкретные id и флаг «не задано»."""
    ids = {v for v in raw if v and v != NONE_TOKEN}
    return ids, (NONE_TOKEN in raw)


def multi_condition(column, raw):
    """SQL-условие для мультифильтра по колонке (id + опционально NULL).

    Возвращает None, если фильтр по этому полю не задан.
    """
    ids, want_none = _split(raw)
    conds = []
    if ids:
        conds.append(column.in_([int(v) for v in ids]))
    if want_none:
        conds.append(column.is_(None))
    return or_(*conds) if conds else None


def scalar_ok(value, raw):
    """Проходит ли скалярное значение поля под выбранный мультифильтр."""
    ids, want_none = _split(raw)
    if not ids and not want_none:
        return True  # фильтр не задан
    if value is None:
        return want_none
    return str(value) in ids


def set_ok(values, raw):
    """Проходит ли набор значений (напр. исполнители эпика) под фильтр.

    «Не задано» трактуется как пустой набор.
    """
    ids, want_none = _split(raw)
    if not ids and not want_none:
        return True
    values = {str(v) for v in values}
    if ids & values:
        return True
    return want_none and not values

import re
from html import unescape

import markdown as _markdown
from markupsafe import Markup

# Маркер в начале описания: значит, дальше — Markdown
MD_MARKER = '[md]'


def normalize_spaces(html):
    """Заменяет неразрывные пробелы на обычные.

    Quill при вставке текста сохраняет пробелы как &nbsp;, из-за чего
    браузер не переносит строки и текст выезжает за пределы блока.
    """
    if not html:
        return html
    return html.replace('&nbsp;', ' ').replace('\xa0', ' ')


def _html_to_text(html):
    """Грубо восстанавливает текст из HTML редактора: блоки -> переводы строк.

    Нужно на случай, если markdown-описание сохранилось обёрнутым в HTML.
    """
    text = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', html)
    text = re.sub(r'(?i)</\s*(p|div|li|h[1-6]|blockquote|pre|tr)\s*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    return unescape(text)


def _render_md(source):
    html = _markdown.markdown(
        source,
        extensions=['extra', 'sane_lists', 'nl2br'],
        output_format='html5',
    )
    # Чек-листы в стиле GitHub: «- [ ]» / «- [x]» -> настоящие чекбоксы
    html = re.sub(r'<li>\s*\[\s\]\s*',
                  '<li class="task-item"><input type="checkbox" disabled> ', html)
    html = re.sub(r'<li>\s*\[[xX]\]\s*',
                  '<li class="task-item"><input type="checkbox" checked disabled> ', html)
    # убираем висящие переносы строки в конце ячеек/пунктов/абзацев
    html = re.sub(r'(?i)<br\s*/?>\s*(</(?:li|p|td|th)>)', r'\1', html)
    return html


def render_description(summary):
    """HTML для показа описания.

    Если описание начинается с «[md]» — сам маркер не показываем, а остальной
    текст рендерим как Markdown. Иначе отдаём как есть (HTML из WYSIWYG).
    """
    if not summary:
        return Markup('')
    stripped = summary.lstrip()
    if stripped[:len(MD_MARKER)].lower() == MD_MARKER:
        # хранится как «сырой» markdown-текст
        return Markup(_render_md(stripped[len(MD_MARKER):]))
    # запасной путь: markdown, но сохранён обёрнутым в HTML редактором
    text = _html_to_text(summary).lstrip()
    if text[:len(MD_MARKER)].lower() == MD_MARKER:
        return Markup(_render_md(text[len(MD_MARKER):]))
    return Markup(summary)

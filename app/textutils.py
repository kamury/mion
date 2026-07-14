def normalize_spaces(html):
    """Заменяет неразрывные пробелы на обычные.

    Quill при вставке текста сохраняет пробелы как &nbsp;, из-за чего
    браузер не переносит строки и текст выезжает за пределы блока.
    """
    if not html:
        return html
    return html.replace('&nbsp;', ' ').replace('\xa0', ' ')

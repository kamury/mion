import os
import uuid

from flask import Blueprint, current_app, jsonify, request, send_from_directory, url_for
from flask_login import login_required

bp = Blueprint('files', __name__, url_prefix='/files')

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg'}


def save_upload(file_storage, subdir=''):
    """Сохраняет файл в UPLOAD_FOLDER, возвращает относительный путь."""
    ext = os.path.splitext(file_storage.filename or '')[1].lower()[:16]
    stored = uuid.uuid4().hex + ext
    dest_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subdir)
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, stored))
    return f'{subdir}/{stored}' if subdir else stored


@bp.get('/<path:name>')
@login_required
def serve(name):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], name)


@bp.post('/image')
@login_required
def upload_image():
    """Загрузка картинки из WYSIWYG-редактора (Quill)."""
    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify(error='Файл не передан'), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        return jsonify(error='Можно загружать только изображения'), 400
    rel = save_upload(file, 'images')
    return jsonify(url=url_for('files.serve', name=rel))

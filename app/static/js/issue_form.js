/* Форма задачи: WYSIWYG для описания + зависимый select родителя с поиском. */

initEditor('#summary-editor', '#summary-input');

const typeSelect = document.getElementById('type-select');
const parentSelect = document.getElementById('parent-select');
const parentWrap = document.getElementById('parent-wrap');
const parentHint = document.getElementById('parent-hint');
const parentOptions = JSON.parse(document.getElementById('parent-options').textContent);

// Какой тип может быть родителем
const PARENT_TYPE = { epic: null, feature: 'epic', task: 'feature', bug: 'feature' };
const TYPE_LABELS = { epic: 'Epic', feature: 'Feature' };

let parentTomSelect = null;

function refreshParentSelect() {
  const issueType = typeSelect.value;
  const parentType = PARENT_TYPE[issueType];
  const current = parentSelect.dataset.current;

  if (parentTomSelect) {
    parentTomSelect.destroy();
    parentTomSelect = null;
  }
  parentSelect.innerHTML = '';

  if (!parentType) {
    parentWrap.style.display = 'none';
    return;
  }
  parentWrap.style.display = '';

  const items = parentOptions[parentType] || [];

  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = '— без родителя —';
  parentSelect.appendChild(empty);

  items.forEach((item) => {
    const opt = document.createElement('option');
    opt.value = item.id;
    opt.textContent = `#${item.id} ${item.title}`;
    if (String(item.id) === String(current)) opt.selected = true;
    parentSelect.appendChild(opt);
  });

  if (items.length === 0) {
    parentHint.textContent = `В системе пока нет ни одной задачи типа ${TYPE_LABELS[parentType]} — создай её, чтобы выбрать родителем.`;
    parentHint.classList.add('text-warning-emphasis');
    return;
  }
  parentHint.textContent = 'Поиск по названию или номеру.';
  parentHint.classList.remove('text-warning-emphasis');

  parentTomSelect = new TomSelect(parentSelect, {
    allowEmptyOption: true,
    maxOptions: null,
    placeholder: '— без родителя —',
  });
}

typeSelect.addEventListener('change', refreshParentSelect);
refreshParentSelect();

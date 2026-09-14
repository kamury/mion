/* Модальное окно задачи.

   Открывается по клику на задачу в списке задач и на карточке доски —
   можно посмотреть детали, поправить выпадающие поля, оставить комментарий,
   добавить связь или файл, не уходя со страницы.

   Флоу с полями: при изменении любого выпадающего поля крестик «закрыть»
   сменяется на «Сохранить / Отменить». «Отменить» просто закрывает без
   сохранения, «Сохранить» — пишет изменения. Комментарии, связи и файлы
   отправляются отдельно и сразу отображаются (крестик при этом не меняется). */
(function () {
  if (!window.bootstrap) return;

  var modalEl = document.getElementById('issue-modal');
  var contentEl = document.getElementById('issue-modal-content');
  if (!modalEl || !contentEl) return;

  var modal = null;
  var commentQuill = null;   // Quill формы комментария в текущем окне
  var linkTS = null;         // Tom Select выбора задачи для связи
  var pageDirty = false;     // были ли сохранены изменения -> обновить страницу при закрытии

  function getModal() {
    if (!modal) modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    return modal;
  }

  // ---- Открытие / загрузка фрагмента ----
  async function loadFragment(id) {
    commentQuill = null;
    linkTS = null;
    var res = await fetch('/issues/' + id + '/panel', {
      headers: { 'X-Requested-With': 'fetch' },
    });
    if (!res.ok) {
      contentEl.innerHTML = '<div class="modal-body text-danger">Не удалось загрузить задачу.</div>';
      return;
    }
    contentEl.innerHTML = await res.text();
    initPanel(id);
  }

  function openPanel(id) {
    contentEl.innerHTML = '<div class="modal-body text-center text-muted py-5">Загрузка…</div>';
    getModal().show();
    loadFragment(id);
  }

  // ---- Настройка содержимого окна после загрузки ----
  function initPanel(id) {
    var root = contentEl.querySelector('[data-panel-root]');
    if (!root) return;

    // Запоминаем исходные значения полей для отслеживания изменений
    var selects = contentEl.querySelectorAll('[data-panel-field]');
    selects.forEach(function (s) {
      s.dataset.initial = s.value;
      s.addEventListener('change', refreshDirty);
    });

    // «на меня» — проставляет исполнителя и помечает поле изменённым
    var assignBtn = contentEl.querySelector('[data-panel-assignme]');
    if (assignBtn) {
      assignBtn.addEventListener('click', function () {
        var sel = contentEl.querySelector('[data-panel-field="assignee_id"]');
        if (sel) { sel.value = assignBtn.dataset.panelAssignme; refreshDirty(); }
      });
    }

    // Крестик и «Отменить» — просто закрыть; «Сохранить» — записать поля
    contentEl.querySelector('[data-panel-close]').addEventListener('click', function () { getModal().hide(); });
    contentEl.querySelector('[data-panel-cancel]').addEventListener('click', function () { getModal().hide(); });
    contentEl.querySelector('[data-panel-save]').addEventListener('click', function () { savePanel(id); });

    // Редактор комментария
    var editorEl = contentEl.querySelector('[data-panel-commenteditor]');
    var inputEl = contentEl.querySelector('[data-panel-commentinput]');
    if (editorEl && inputEl && window.initEditor) {
      editorEl.id = 'panel-comment-editor';
      inputEl.id = 'panel-comment-input';
      commentQuill = initEditor('#panel-comment-editor', '#panel-comment-input');
    }

    // Блок связей: показать форму по «+», поиск задачи через Tom Select
    var addLinkBtn = contentEl.querySelector('[data-panel-addlink]');
    var linkForm = contentEl.querySelector('[data-panel-linkform]');
    if (addLinkBtn && linkForm) {
      addLinkBtn.addEventListener('click', function () {
        linkForm.classList.remove('d-none');
        addLinkBtn.classList.add('d-none');
        if (!linkTS && window.TomSelect) {
          linkTS = new TomSelect(linkForm.querySelector('[data-panel-linktarget]'), {
            placeholder: 'Найдите задачу по номеру или названию…',
          });
        }
      });
      linkForm.querySelector('[data-panel-canlink]').addEventListener('click', function () {
        linkForm.classList.add('d-none');
        addLinkBtn.classList.remove('d-none');
      });
    }

    // Отправка комментария / связи / файла — без ухода со страницы
    contentEl.querySelectorAll('form[data-panel-reload]').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        submitSubform(form, id);
      });
    });
  }

  function refreshDirty() {
    var selects = contentEl.querySelectorAll('[data-panel-field]');
    var dirty = false;
    selects.forEach(function (s) { if (s.value !== s.dataset.initial) dirty = true; });
    contentEl.querySelector('[data-panel-close]').classList.toggle('d-none', dirty);
    var group = contentEl.querySelector('[data-panel-savegroup]');
    group.classList.toggle('d-none', !dirty);
    group.classList.toggle('d-flex', dirty);
  }

  async function savePanel(id) {
    var payload = {};
    contentEl.querySelectorAll('[data-panel-field]').forEach(function (s) {
      if (s.value !== s.dataset.initial) payload[s.dataset.panelField] = s.value === '' ? null : s.value;
    });
    if (!Object.keys(payload).length) { getModal().hide(); return; }
    try {
      var res = await fetch('/issues/' + id + '/fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
    } catch (err) {
      alert('Не удалось сохранить изменения: ' + err.message);
      return;
    }
    pageDirty = true;
    getModal().hide();        // закрываем окно; страница под ним обновится
  }

  async function submitSubform(form, id) {
    // Комментарий: переносим HTML из Quill в скрытое поле перед отправкой
    if (form.hasAttribute('data-panel-commentform') && commentQuill) {
      var input = form.querySelector('[data-panel-commentinput]');
      input.value = commentQuill.getSemanticHTML ? commentQuill.getSemanticHTML() : commentQuill.root.innerHTML;
    }
    try {
      var res = await fetch(form.action, { method: 'POST', body: new FormData(form) });
      if (!res.ok) throw new Error('HTTP ' + res.status);
    } catch (err) {
      alert('Не удалось выполнить действие: ' + err.message);
      return;
    }
    pageDirty = true;
    await loadFragment(id);
  }

  // Сохранённые изменения могли изменить доску/список — обновляем страницу
  // при закрытии, оставаясь там же, где были.
  modalEl.addEventListener('hidden.bs.modal', function () {
    if (pageDirty) location.reload();
  });

  // ---- Клик по задаче открывает окно ----
  document.addEventListener('click', function (e) {
    if (window.__boardDragging) return;                       // не мешаем drag&drop
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;  // среднему клику — новую вкладку
    var link = e.target.closest('a.js-issue-open');
    var host = e.target.closest('.issue-card, [data-issue-open]');
    var el = link || host;
    if (!el || !el.dataset.issueId) return;
    e.preventDefault();
    openPanel(el.dataset.issueId);
  });
})();

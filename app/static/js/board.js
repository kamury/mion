/* Доска: drag&drop карточек между статусами (колонки) и спринтами (свимлейны). */

// id первого статуса (To Do) — в беклоге допускается только он
const boardGrid = document.querySelector('.board-grid');
const FIRST_STATUS = boardGrid ? boardGrid.dataset.firstStatus : '';
const BACKLOG_ERROR = 'Чтобы сменить статус задачи, добавьте её в спринт.';

// Возвращает карточку на исходное место (когда перенос недопустим)
function revertDrag(evt) {
  const ref = evt.from.children[evt.oldIndex] || null;
  evt.from.insertBefore(evt.item, ref);
}

document.querySelectorAll('.board-cell:not(.readonly)').forEach((cell) => {
  new Sortable(cell, {
    group: 'board',
    animation: 150,
    ghostClass: 'sortable-ghost',
    dragClass: 'sortable-drag',
    // пока тащим карточку — глушим открытие модалки задачи по клику
    onStart: () => { window.__boardDragging = true; },
    onEnd: async (evt) => {
      window.__boardDragging = false;
      // браузер после перетаскивания шлёт «клик» — гасим его один раз,
      // чтобы не открылось окно задачи и не сработала ссылка на карточке
      document.addEventListener('click', function swallow(e) {
        e.stopPropagation();
        e.preventDefault();
        document.removeEventListener('click', swallow, true);
      }, true);

      if (evt.to === evt.from) return; // перенос внутри той же ячейки — ничего не меняем

      const toStatus = evt.to.dataset.statusId;
      const toSprint = evt.to.dataset.sprintId; // '' у беклога

      // В беклоге держим только первый статус: попытка сменить статус без
      // спринта — откатываем карточку и показываем подсказку.
      if (!toSprint && FIRST_STATUS && toStatus !== FIRST_STATUS) {
        revertDrag(evt);
        alert(BACKLOG_ERROR);
        return;
      }

      const issueId = evt.item.dataset.issueId;
      const payload = { status_id: toStatus, sprint_id: toSprint || null };
      try {
        const res = await fetch(`/issues/${issueId}/move`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.error || ('HTTP ' + res.status));
        }
      } catch (e) {
        alert('Не удалось переместить задачу: ' + e.message);
        location.reload();
      }
    },
  });
});

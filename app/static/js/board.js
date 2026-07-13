/* Доска: drag&drop карточек между статусами (колонки) и спринтами (свимлейны). */

document.querySelectorAll('.board-cell').forEach((cell) => {
  new Sortable(cell, {
    group: 'board',
    animation: 150,
    ghostClass: 'sortable-ghost',
    dragClass: 'sortable-drag',
    onEnd: async (evt) => {
      if (evt.to === evt.from) return; // перенос внутри той же ячейки — ничего не меняем

      const issueId = evt.item.dataset.issueId;
      const payload = {
        status_id: evt.to.dataset.statusId,
        sprint_id: evt.to.dataset.sprintId || null,
      };
      try {
        const res = await fetch(`/issues/${issueId}/move`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
      } catch (e) {
        alert('Не удалось переместить задачу: ' + e.message);
        location.reload();
      }
    },
  });
});

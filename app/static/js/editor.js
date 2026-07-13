/* Общая инициализация Quill-редактора с загрузкой картинок на сервер. */

function initEditor(editorSelector, inputSelector) {
  const editorEl = document.querySelector(editorSelector);
  const input = document.querySelector(inputSelector);
  if (!editorEl || !input) return null;

  const quill = new Quill(editorEl, {
    theme: 'snow',
    modules: {
      toolbar: {
        container: [
          ['bold', 'italic', 'underline', 'strike'],
          [{ header: [1, 2, 3, false] }],
          [{ list: 'ordered' }, { list: 'bullet' }],
          ['blockquote', 'code-block'],
          ['link', 'image'],
          ['clean'],
        ],
        handlers: {
          image() { pickAndUploadImage(this.quill); },
        },
      },
    },
  });

  if (input.value) {
    quill.clipboard.dangerouslyPasteHTML(input.value);
  }

  // Вставка картинок из буфера обмена: перехватываем base64 и грузим на сервер
  quill.getModule('toolbar'); // ensure init
  quill.root.addEventListener('paste', () => {
    setTimeout(() => uploadInlineBase64Images(quill), 50);
  });

  const form = input.closest('form');
  if (form) {
    form.addEventListener('submit', () => {
      input.value = quill.getSemanticHTML ? quill.getSemanticHTML() : quill.root.innerHTML;
    });
  }
  return quill;
}

function pickAndUploadImage(quill) {
  const picker = document.createElement('input');
  picker.type = 'file';
  picker.accept = 'image/*';
  picker.onchange = async () => {
    const file = picker.files[0];
    if (!file) return;
    const url = await uploadImage(file);
    if (url) {
      const range = quill.getSelection(true);
      quill.insertEmbed(range ? range.index : 0, 'image', url);
    }
  };
  picker.click();
}

async function uploadImage(file) {
  const formData = new FormData();
  formData.append('image', file);
  try {
    const res = await fetch('/files/image', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');
    return data.url;
  } catch (e) {
    alert('Не удалось загрузить картинку: ' + e.message);
    return null;
  }
}

/* Заменяет вставленные из буфера base64-картинки на загруженные файлы. */
async function uploadInlineBase64Images(quill) {
  const images = quill.root.querySelectorAll('img[src^="data:image/"]');
  for (const img of images) {
    try {
      const blob = await (await fetch(img.src)).blob();
      const file = new File([blob], 'pasted.png', { type: blob.type });
      const url = await uploadImage(file);
      if (url) img.src = url;
    } catch (e) {
      /* оставляем base64 как есть */
    }
  }
}

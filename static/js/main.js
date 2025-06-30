document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('ocr-form');
    const errorMessage = document.getElementById('error-message');
    const loadingIndicator = document.getElementById('loading');

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Сбросить предыдущие состояния
        errorMessage.style.display = 'none';
        errorMessage.textContent = '';
        loadingIndicator.style.display = 'block';
        
        // Блокируем кнопкуSubmit
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;

        const formData = new FormData(form);

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            // Проверяем, что ответ корректный
            if (!response.ok) {
                throw new Error('Ошибка сервера: ' + response.statusText);
            }
            return response.json();
        })
        .then(data => {
            // Скрываем индикатор загрузки
            loadingIndicator.style.display = 'none';
            submitButton.disabled = false;

            if (data.status === 'success') {
                const format = data.format;
                
                if (format === 'json') {
                    // Создаем JSON blob и ссылку для скачивания
                    const jsonBlob = new Blob([JSON.stringify(data.data, null, 2)], {type: 'application/json'});
                    const downloadLink = document.createElement('a');
                    downloadLink.href = URL.createObjectURL(jsonBlob);
                    downloadLink.download = 'ocr_result.json';
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    document.body.removeChild(downloadLink);
                } else {
                    // Создаем Markdown blob и ссылку для скачивания
                    const markdownBlob = new Blob([data.markdown], {type: 'text/markdown'});
                    const downloadLink = document.createElement('a');
                    downloadLink.href = URL.createObjectURL(markdownBlob);
                    downloadLink.download = 'ocr_result.md';
                    document.body.appendChild(downloadLink);
                    downloadLink.click();
                    document.body.removeChild(downloadLink);
                }
                
                // Показываем детальную информацию о результате
                let message = 'Документ успешно обработан! Файл загружен.';
                
                // Добавляем статистику если доступна
                if (data.processing_info) {
                    const info = data.processing_info;
                    message += `\n\n📊 Статистика обработки:`;
                    message += `\n🖼️ Изображений найдено: ${info.total_images}`;
                    if (info.fallback_used) {
                        message += `\n🔧 Fallback извлечение: Да (${info.fallback_pages} стр.)`;
                    }
                    if (info.embedded_images) {
                        message += `\n✅ Изображения встроены в markdown как base64`;
                        message += `\n🧹 Временные файлы автоматически удалены`;
                    }
                    message += `\n📄 Формат экспорта: ${info.export_format}`;
                }
                
                alert(message);
            } else {
                // Ошибка
                errorMessage.textContent = data.message || 'Неизвестная ошибка';
                errorMessage.style.display = 'block';
            }
        })
        .catch(error => {
            // Скрываем индикатор загрузки
            loadingIndicator.style.display = 'none';
            submitButton.disabled = false;

            // Обработка сетевых ошибок
            errorMessage.textContent = 'Ошибка: ' + error.message;
            errorMessage.style.display = 'block';
            console.error('Подробности ошибки:', error);
        });
    });
});
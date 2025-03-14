document.addEventListener('DOMContentLoaded', function() {
    /* Константы и переменные */
    const API_KEY_STORAGE_KEY = "mistral_ocr_api_key";
    const MAX_FILE_SIZE = 16 * 1024 * 1024; // 16MB
    let selectedFile = null;
    
    /* DOM элементы */
    // API Key
    const apiKeyInput = document.getElementById('apiKey');
    const toggleApiKeyBtn = document.getElementById('toggleApiKey');
    const saveApiKeyBtn = document.getElementById('saveApiKey');
    const testApiKeyBtn = document.getElementById('testApiKey');
    const apiStatusDiv = document.getElementById('apiStatus');
    
    // Tabs
    const urlTabBtn = document.getElementById('urlTabBtn');
    const fileTabBtn = document.getElementById('fileTabBtn');
    const urlTab = document.getElementById('urlTab');
    const fileTab = document.getElementById('fileTab');
    
    // URL form
    const pdfUrlInput = document.getElementById('pdfUrl');
    const processUrlBtn = document.getElementById('processUrlBtn');
    
    // File upload
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const processFileBtn = document.getElementById('processFileBtn');
    
    // Results
    const resultsCard = document.getElementById('resultsCard');
    const resultContent = document.getElementById('resultContent');
    const copyResultBtn = document.getElementById('copyResultBtn');
    const downloadResultBtn = document.getElementById('downloadResultBtn');
    
    // Modal
    const loadingModal = document.getElementById('loadingModal');
    const loadingMessage = document.getElementById('loadingMessage');
    
    /* Инициализация */
    loadApiKey();
    
    /* Обработчики событий для API-ключа */
    // Загрузка сохраненного API-ключа
    function loadApiKey() {
        const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
        if (apiKey) {
            apiKeyInput.value = apiKey;
        }
    }
    
    // Сохранение API-ключа
    saveApiKeyBtn.addEventListener('click', () => {
        const apiKey = apiKeyInput.value.trim();
        
        if (!apiKey) {
            showAlert('Пожалуйста, введите API-ключ', 'error');
            return;
        }
        
        localStorage.setItem(API_KEY_STORAGE_KEY, apiKey);
        showAlert('API-ключ сохранен', 'success');
    });
    
    // Переключение видимости API-ключа
    toggleApiKeyBtn.addEventListener('click', () => {
        if (apiKeyInput.type === 'password') {
            apiKeyInput.type = 'text';
            toggleApiKeyBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
        } else {
            apiKeyInput.type = 'password';
            toggleApiKeyBtn.innerHTML = '<i class="fas fa-eye"></i>';
        }
    });
    
    // Проверка API-ключа
    testApiKeyBtn.addEventListener('click', async () => {
        const apiKey = apiKeyInput.value.trim();
        
        if (!apiKey) {
            showAlert('Пожалуйста, введите API-ключ', 'error');
            return;
        }
        
        showAlert('Проверка подключения к API...', 'info');
        
        try {
            const response = await fetch('/api/status', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${apiKey}`
                }
            });
            
            const data = await response.json();
            
            if (data.status === 'success') {
                showAlert('✅ API-ключ работает корректно!', 'success');
                
                // Сохраняем ключ автоматически
                localStorage.setItem(API_KEY_STORAGE_KEY, apiKey);
            } else {
                showAlert('❌ Ошибка при проверке API-ключа', 'error');
            }
        } catch (error) {
            showAlert(`❌ Ошибка: ${error.message}`, 'error');
        }
    });
    
    /* Обработчики для табов */
    urlTabBtn.addEventListener('click', () => {
        urlTabBtn.classList.add('text-gray-800', 'border-primary-600');
        urlTabBtn.classList.remove('text-gray-500', 'border-transparent');
        
        fileTabBtn.classList.add('text-gray-500', 'border-transparent');
        fileTabBtn.classList.remove('text-gray-800', 'border-primary-600');
        
        urlTab.classList.remove('hidden');
        fileTab.classList.add('hidden');
    });
    
    fileTabBtn.addEventListener('click', () => {
        fileTabBtn.classList.add('text-gray-800', 'border-primary-600');
        fileTabBtn.classList.remove('text-gray-500', 'border-transparent');
        
        urlTabBtn.classList.add('text-gray-500', 'border-transparent');
        urlTabBtn.classList.remove('text-gray-800', 'border-primary-600');
        
        fileTab.classList.remove('hidden');
        urlTab.classList.add('hidden');
    });
    
    /* Обработчики форматов вывода */
    const formatOptions = document.querySelectorAll('.format-option');
    formatOptions.forEach(option => {
        const radioInput = option.previousElementSibling;
        
        option.addEventListener('click', () => {
            // Находим все опции в той же группе и снимаем выделение
            const groupName = radioInput.name;
            document.querySelectorAll(`input[name="${groupName}"]`).forEach(input => {
                input.checked = false;
                input.nextElementSibling.classList.remove('selected');
            });
            
            // Выбираем текущую опцию
            radioInput.checked = true;
            option.classList.add('selected');
        });
    });
    
    /* Обработчики для URL формы */
    processUrlBtn.addEventListener('click', async () => {
        const apiKey = apiKeyInput.value.trim();
        const url = pdfUrlInput.value.trim();
        const format = document.querySelector('input[name="formatUrl"]:checked').value;
        
        if (!apiKey) {
            showAlert('Пожалуйста, введите API-ключ', 'error');
            return;
        }
        
        if (!url) {
            showAlert('Пожалуйста, введите URL PDF-документа', 'error');
            return;
        }
        
        if (!isValidUrl(url)) {
            showAlert('Пожалуйста, введите корректный URL', 'error');
            return;
        }
        
        showLoading('Обработка PDF по URL...');
        
        try {
            const response = await fetch('/api/process_url', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify({
                    url: url,
                    format: format
                })
            });
            
            const data = await response.json();
            
            hideLoading();
            
            if (data.status === 'success') {
                displayResults(data.data, format);
            } else {
                showAlert(`Ошибка: ${data.message}`, 'error');
            }
        } catch (error) {
            hideLoading();
            showAlert(`Ошибка: ${error.message}`, 'error');
        }
    });
    
    /* Обработчики для загрузки файла */
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });
    
    fileInput.addEventListener('change', (e) => {
        handleFileSelection(e.target.files);
    });
    
    // Drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });
    
    function highlight() {
        dropZone.classList.add('highlight');
    }
    
    function unhighlight() {
        dropZone.classList.remove('highlight');
    }
    
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFileSelection(files);
    });
    
    function handleFileSelection(files) {
        if (files.length === 0) return;
        
        const file = files[0];
        
        // Проверка типа файла
        if (file.type !== 'application/pdf') {
            showAlert('Пожалуйста, выберите PDF-файл', 'error');
            return;
        }
        
        // Проверка размера файла
        if (file.size > MAX_FILE_SIZE) {
            showAlert(`Файл слишком большой. Максимальный размер: ${formatFileSize(MAX_FILE_SIZE)}`, 'error');
            return;
        }
        
        // Сохраняем выбранный файл
        selectedFile = file;
        
        // Отображаем информацию о файле
        fileName.textContent = file.name;
        fileSize.textContent = ` (${formatFileSize(file.size)})`;
        fileInfo.classList.remove('hidden');
        
        // Активируем кнопку обработки
        processFileBtn.disabled = false;
    }
    
    processFileBtn.addEventListener('click', async () => {
        const apiKey = apiKeyInput.value.trim();
        const format = document.querySelector('input[name="formatFile"]:checked').value;
        
        if (!apiKey) {
            showAlert('Пожалуйста, введите API-ключ', 'error');
            return;
        }
        
        if (!selectedFile) {
            showAlert('Пожалуйста, выберите PDF-файл', 'error');
            return;
        }
        
        showLoading('Загрузка и обработка PDF-файла...');
        
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('format', format);
        
        try {
            const response = await fetch('/api/process_file', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${apiKey}`
                },
                body: formData
            });
            
            const data = await response.json();
            
            hideLoading();
            
            if (data.status === 'success') {
                displayResults(data.data, format);
            } else {
                showAlert(`Ошибка: ${data.message}`, 'error');
            }
        } catch (error) {
            hideLoading();
            showAlert(`Ошибка: ${error.message}`, 'error');
        }
    });
    
    /* Обработчики результатов */
    copyResultBtn.addEventListener('click', () => {
        const content = resultContent.textContent;
        navigator.clipboard.writeText(content)
            .then(() => {
                // Анимация успешного копирования
                copyResultBtn.classList.add('copy-success');
                copyResultBtn.innerHTML = '<i class="fas fa-check mr-1"></i> Скопировано';
                
                setTimeout(() => {
                    copyResultBtn.classList.remove('copy-success');
                    copyResultBtn.innerHTML = '<i class="fas fa-copy mr-1"></i> Копировать';
                }, 2000);
            })
            .catch(err => {
                showAlert(`Не удалось скопировать: ${err}`, 'error');
            });
    });
    
    downloadResultBtn.addEventListener('click', () => {
        const content = resultContent.textContent;
        const format = resultContent.dataset.format;
        const extension = format === 'json' ? 'json' : 'md';
        const mimeType = format === 'json' ? 'application/json' : 'text/markdown';
        
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        
        a.href = url;
        a.download = `mistral-ocr-result.${extension}`;
        document.body.appendChild(a);
        a.click();
        
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 0);
    });
    
    /* Вспомогательные функции */
    function showAlert(message, type = 'info') {
        apiStatusDiv.innerHTML = message;
        apiStatusDiv.className = 'mt-3 rounded-lg p-3 text-sm fade-in';
        
        // Добавляем класс в зависимости от типа уведомления
        switch (type) {
            case 'success':
                apiStatusDiv.classList.add('alert-success');
                break;
            case 'error':
                apiStatusDiv.classList.add('alert-error');
                break;
            case 'warning':
                apiStatusDiv.classList.add('alert-warning');
                break;
            default:
                apiStatusDiv.classList.add('alert-info');
        }
        
        apiStatusDiv.classList.remove('hidden');
        
        // Автоматически скрываем через 5 секунд для success и info
        if (type === 'success' || type === 'info') {
            setTimeout(() => {
                apiStatusDiv.classList.add('fade-out');
                setTimeout(() => {
                    apiStatusDiv.classList.add('hidden');
                }, 300);
            }, 5000);
        }
    }
    
    function showLoading(message) {
        loadingMessage.textContent = message;
        loadingModal.classList.remove('hidden');
    }
    
    function hideLoading() {
        loadingModal.classList.add('hidden');
    }
    
    function displayResults(data, format) {
        resultContent.textContent = typeof data === 'object' ? JSON.stringify(data, null, 2) : data;
        resultContent.dataset.format = format;
        resultsCard.classList.remove('hidden');
        
        // Прокручиваем к результатам
        resultsCard.scrollIntoView({ behavior: 'smooth' });
    }
    
    function isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
});

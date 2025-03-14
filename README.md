# Mistral OCR - Конвертер PDF в Markdown/JSON

Веб-приложение на базе Flask для извлечения текста и изображений из PDF-документов с использованием технологии Mistral OCR API.

![Mistral OCR App Screenshot](https://static.mistral.ai/mistral-medium.svg)

## Функциональные возможности

- **Современный интерфейс**: Минималистичный тёмный дизайн
- **OCR для PDF по URL**: Обработка PDF-документов по URL-адресу
- **Два формата вывода**: Markdown и JSON
- **Встраивание изображений**: Преобразование изображений в base64 для включения в Markdown
- **Демонстрационный режим**: Работа без API-ключа в демонстрационном режиме
- **Интегрированное API**: REST API для интеграции с другими приложениями

## Структура проекта

```
mistral-ocr-app/
├── app.py                   # Основное Flask-приложение
├── .env                     # Файл с переменными окружения
├── .env.example             # Пример файла окружения
├── static/                  # Статические файлы
│   ├── css/
│   │   └── style.css        # Дополнительные стили
│   └── js/
│       └── main.js          # JavaScript-функциональность
├── templates/
│   └── index.html           # Основной HTML-шаблон
└── requirements.txt         # Зависимости проекта
```

## Требования

- Python 3.8 или выше
- API-ключ Mistral AI с доступом к OCR (опционально, можно использовать демо-режим)

## Установка и запуск

1. **Клонируйте репозиторий**

```bash
git clone https://github.com/yourusername/mistral-ocr-app.git
cd mistral-ocr-app
```

2. **Создайте и активируйте виртуальное окружение**

```bash
# для Windows
python -m venv venv
venv\Scripts\activate

# для macOS/Linux
python -m venv venv
source venv/bin/activate
```

3. **Установите зависимости**

```bash
pip install -r requirements.txt
```

4. **Настройте переменные окружения**

Создайте файл `.env` на основе `.env.example`:

```
# Ваш API ключ Mistral AI (замените на свой ключ)
MISTRAL_API_KEY=your_mistral_api_key_here

# Использовать демо-режим OCR (без обращения к API)
USE_MOCK_OCR=true

# Настройки сервера
PORT=5000
DEBUG=True
```

Если у вас нет API-ключа Mistral с доступом к OCR, оставьте `USE_MOCK_OCR=true` для использования демо-режима.

5. **Запустите приложение**

```bash
python app.py
```

Приложение будет доступно по адресу [http://localhost:5000](http://localhost:5000)

## Демо-режим vs Реальный OCR

### Демо-режим (USE_MOCK_OCR=true)
- Не требует API-ключа Mistral
- Возвращает демонстрационные данные
- Подходит для тестирования интерфейса

### Реальный OCR (USE_MOCK_OCR=false)
- Требует действительный API-ключ Mistral с доступом к OCR
- Обеспечивает реальное распознавание текста и изображений из PDF
- Подходит для боевого использования

## Использование

### Обработка PDF по URL

1. Откройте приложение в браузере
2. Введите URL-адрес PDF-документа
   - Можно использовать ссылки с Google Drive, Dropbox и других сервисов
   - Для Google Drive: скопируйте ссылку общего доступа (приложение автоматически конвертирует её)
3. Выберите формат вывода (Markdown или JSON)
4. Нажмите "Process" для обработки документа
5. Результат будет отображен в интерфейсе
6. Используйте кнопку "Download" для сохранения результата

### API Endpoints

Приложение предоставляет следующие API-эндпоинты:

- `GET /api/markdown?url={PDF_url}` - Получение результатов OCR в формате Markdown
- `GET /api/json?url={PDF_url}` - Получение полных результатов OCR в формате JSON
- `GET /api/status` - Проверка статуса подключения к API Mistral

## Ограничения

- В демо-режиме возвращаются фиксированные данные, а не реальные результаты OCR
- При использовании реального OCR, возможны ограничения со стороны Mistral API:
  - Ограничения по размеру обрабатываемых файлов
  - Ограничения по количеству запросов
  - Ограничения по странам использования

## Дальнейшее развитие

См. раздел [Future Development](#future-development) для информации о планируемых улучшениях.

## Лицензия

MIT

## Авторы

Пожалуйста, укажите ваше имя и контактную информацию здесь.

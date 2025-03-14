from flask import Flask, render_template, request, jsonify, Response
from mistralai import Mistral
import os
import json
import time
import traceback
import logging
import re
from urllib.parse import urlparse
from dotenv import load_dotenv
import tempfile
import base64
import requests
from io import BytesIO

# Загрузка переменных окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

# Константы
MAX_RETRIES = 3
ALLOWED_EXTENSIONS = {'pdf'}
UPLOAD_FOLDER = tempfile.gettempdir()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 Мб лимит на загрузку файлов

# Функция проверки расширения файла
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Функция для преобразования различных ссылок на PDF в прямые ссылки для скачивания
def get_direct_pdf_url(url):
    """Преобразование различных ссылок на PDF в прямые ссылки для скачивания"""
    
    # Google Drive
    gdrive_pattern = r'https://drive\.google\.com/file/d/(.*?)/view'
    if match := re.match(gdrive_pattern, url):
        file_id = match.group(1)
        return f'https://drive.google.com/uc?export=download&id={file_id}'
    
    # Dropbox
    dropbox_pattern = r'https://www\.dropbox\.com/s/(.*?)/(.*?)\?dl=\d'
    if match := re.match(dropbox_pattern, url):
        file_path = match.group(1)
        file_name = match.group(2)
        return f'https://dl.dropboxusercontent.com/s/{file_path}/{file_name}'
    
    # OneDrive (базовая поддержка)
    onedrive_pattern = r'https://onedrive\.live\.com/redir\?(.*?)&resid=(.*?)&authkey=(.*?)'
    if re.match(onedrive_pattern, url):
        # Преобразование сложное, перенаправляем пользователя на более простые ссылки
        logger.info("OneDrive URL detected. Consider using direct sharing links.")
    
    # Если преобразование не требуется - возвращаем исходный URL
    return url

# Функция "заглушка" для имитации OCR (использовать при отсутствии доступа к API)
def mock_ocr_process(url):
    """Функция-заглушка для имитации работы OCR API"""
    from collections import namedtuple
    
    # Создаем структуру, имитирующую ответ API
    Page = namedtuple('Page', ['markdown', 'images'])
    Image = namedtuple('Image', ['id', 'image_base64'])
    
    # Создаем фейковое изображение
    fake_image = Image(
        id='img1',
        image_base64='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
    )
    
    # Создаем фейковый текст
    fake_markdown = f"""# Демонстрационный Markdown

Это демонстрационный текст, сгенерированный вместо настоящей OCR обработки.

## URL документа
{url}

![img1](img1)

## Примечание
Для доступа к настоящему OCR API Mistral необходимо иметь действующий API-ключ с доступом к функции OCR.
    """
    
    # Создаем фейковую страницу
    fake_page = Page(markdown=fake_markdown, images=[fake_image])
    
    # Создаем фейковый ответ
    class MockResponse:
        def __init__(self):
            self.pages = [fake_page]
        
        def model_dump(self):
            return {
                "pages": [{
                    "index": 0,
                    "markdown": fake_markdown,
                    "images": [{
                        "id": "img1",
                        "image_base64": fake_image.image_base64
                    }]
                }]
            }
    
    logger.info("Используется демонстрационная версия OCR (без API)")
    return MockResponse()

# Функция для обработки OCR с URL
def process_ocr_with_retry(url, include_image_base64=True, use_mock=False):
    """Обработка OCR с механизмом повторных попыток для надежности"""
    
    # Если запрошена имитация OCR, возвращаем фейковый результат
    if use_mock:
        return mock_ocr_process(url)
    
    retries = 0
    last_exception = None
    
    while retries < MAX_RETRIES:
        try:
            api_key = os.environ.get("MISTRAL_API_KEY")
            if not api_key:
                raise ValueError("MISTRAL_API_KEY environment variable not set")
            
            direct_url = get_direct_pdf_url(url)
            logger.info(f"Обработка OCR для URL: {direct_url}")
            
            with Mistral(api_key=api_key) as client:
                # OCR запрос
                ocr_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document={
                        "type": "document_url",
                        "document_url": direct_url
                    },
                    include_image_base64=include_image_base64
                )
                
                logger.info("OCR запрос выполнен успешно")
                return ocr_response
            
        except Exception as e:
            last_exception = e
            retries += 1
            logger.error(f"Попытка OCR {retries} не удалась: {str(e)}")
            time.sleep(2 ** retries)  # Экспоненциальная задержка
    
    logger.error(f"Все попытки OCR не удались: {str(last_exception)}")
    
    # Если все попытки не удались и ошибка 401, переключаемся на имитацию
    if '401' in str(last_exception):
        logger.warning("Используется демонстрационный режим из-за ошибки авторизации API")
        return mock_ocr_process(url)
    else:
        raise last_exception

def replace_images_in_markdown(markdown_str: str, images_dict: dict) -> str:
    """Замена ссылок на изображения на base64 данные в markdown"""
    for img_name, base64_str in images_dict.items():
        markdown_str = markdown_str.replace(
            f"![{img_name}]({img_name})", 
            f"![{img_name}]({base64_str})"
        )
    return markdown_str

def get_combined_markdown(ocr_response) -> str:
    """Объединение результатов OCR со встроенными изображениями"""
    markdowns = []
    for page in ocr_response.pages:
        image_data = {img.id: img.image_base64 for img in page.images}
        markdowns.append(replace_images_in_markdown(page.markdown, image_data))
    return "\n\n".join(markdowns)

# Главная страница
@app.route('/')
def index():
    return render_template('index.html')

# Обработка OCR через URL (универсальный маршрут)
@app.route('/process_ocr', methods=['POST'])
def process_ocr():
    try:
        url = request.form['url']
        output_format = request.form['format']
        
        logger.info(f"Обработка OCR для URL: {url}, формат: {output_format}")
        
        # Проверяем доступ к API и при ошибке используем демо-режим
        use_mock = os.environ.get("USE_MOCK_OCR", "False").lower() == "true"
        ocr_response = process_ocr_with_retry(url, use_mock=use_mock)
        
        if output_format == 'json':
            ocr_data = ocr_response.model_dump()
            return jsonify({
                "status": "success",
                "data": ocr_data,
                "format": "json"
            })
        else:
            markdown_content = get_combined_markdown(ocr_response)
            
            return jsonify({
                "status": "success",
                "data": markdown_content,
                "format": "markdown"
            })

    except Exception as e:
        logger.error(f"Ошибка в process_ocr: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500

# API эндпоинт для Markdown
@app.route('/api/markdown', methods=['GET'])
def api_markdown():
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({"status": "error", "message": "URL parameter is required"}), 400
            
        logger.info(f"Обработка OCR для URL: {url} (Markdown API)")
        
        # Проверяем доступ к API и при ошибке используем демо-режим
        use_mock = os.environ.get("USE_MOCK_OCR", "False").lower() == "true"
        ocr_response = process_ocr_with_retry(url, use_mock=use_mock)
        
        markdown_content = get_combined_markdown(ocr_response)
        
        return Response(
            markdown_content,
            mimetype='text/markdown',
            headers={'Content-Type': 'text/markdown; charset=utf-8'}
        )
    except Exception as e:
        logger.error(f"Ошибка в api_markdown: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500
    
# API эндпоинт для JSON
@app.route('/api/json', methods=['GET'])
def api_json():
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({"status": "error", "message": "URL parameter is required"}), 400
            
        logger.info(f"Обработка OCR для URL: {url} (JSON API)")
        
        # Проверяем доступ к API и при ошибке используем демо-режим
        use_mock = os.environ.get("USE_MOCK_OCR", "False").lower() == "true"
        ocr_response = process_ocr_with_retry(url, use_mock=use_mock)
        
        ocr_data = ocr_response.model_dump()
        
        return jsonify({
            "status": "success",
            "data": ocr_data,
            "format": "json"
        })
    except Exception as e:
        logger.error(f"Ошибка в api_json: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500
    
# Проверка статуса API
@app.route('/api/status', methods=['GET'])
def api_status():
    try:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            return jsonify({"status": "error", "message": "MISTRAL_API_KEY environment variable not set"}), 500
            
        # Проверка подключения к API Mistral
        with Mistral(api_key=api_key) as client:
            try:
                # Сначала проверим основной API (список моделей)
                models = client.list_models()
                
                # Теперь проверим доступ к OCR API с помощью минимального запроса
                test_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
                client.ocr.process(
                    model="mistral-ocr-latest",
                    document={
                        "type": "document_url",
                        "document_url": test_url
                    },
                    include_image_base64=False
                )
                
                # Если дошли сюда, значит всё хорошо
                return jsonify({
                    "status": "success",
                    "message": "API connection successful (including OCR API)",
                    "available_models": [model.model_dump() for model in models.data]
                })
            except Exception as ocr_err:
                # Есть доступ к API, но нет доступа к OCR
                if '401' in str(ocr_err):
                    return jsonify({
                        "status": "warning",
                        "message": "API connection successful but OCR API access denied. Check if your API key has OCR access.",
                        "available_models": [model.model_dump() for model in models.data],
                        "ocr_error": str(ocr_err)
                    })
                else:
                    raise ocr_err
            
    except Exception as e:
        logger.error(f"Ошибка проверки статуса API: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Вывод зарегистрированных маршрутов для отладки
    print("Зарегистрированные маршруты:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
    
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == "true"
    app.run(host='0.0.0.0', port=port, debug=debug)

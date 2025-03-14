from flask import Flask, render_template, request, jsonify, send_file
from mistralai import Mistral
import os
import json
import base64
import tempfile
import logging
import traceback
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

# Конфигурация
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 МБ макс размер файла
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

def download_url_file(url):
    """
    Загрузка файла по URL
    
    TODO: 
    - Добавить проверку типа файла
    - Ограничение размера файла
    """
    try:
        # Проверка корректности URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("Некорректный URL")

        # Получение расширения файла
        file_ext = os.path.splitext(parsed_url.path)[1] or '.pdf'
        
        # Генерация временного имени файла
        temp_filename = os.path.join(
            app.config['UPLOAD_FOLDER'], 
            f'downloaded_{os.urandom(8).hex()}{file_ext}'
        )

        # Загрузка файла
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(temp_filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)

        return temp_filename

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        raise ValueError(f"Не удалось загрузить файл: {e}")

def process_ocr_document(file_path, include_images=True):
    """
    Основная функция OCR обработки документа
    """
    try:
        # Получение API-ключа
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("API-ключ не установлен")

        # Инициализация клиента Mistral
        client = Mistral(api_key=api_key)

        # Загрузка файла
        with open(file_path, "rb") as file:
            uploaded_file = client.files.upload(
                file={
                    "file_name": os.path.basename(file_path),
                    "content": file,
                },
                purpose="ocr"
            )

        # Получение подписанного URL
        signed_url = client.files.get_signed_url(file_id=uploaded_file.id)

        # OCR-обработка
        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={
                "type": "document_url",
                "document_url": signed_url.url,
            },
            include_image_base64=include_images
        )

        # Обработка результатов
        result = {
            "document_url": signed_url.url,
            "pages": []
        }

        for page in ocr_response.pages:
            page_data = {
                "index": page.index,
                "markdown": page.markdown,
                "images": []
            }

            # Сохранение изображений
            if include_images:
                for img in page.images:
                    # Декодирование base64
                    img_data = base64.b64decode(img.image_base64.split(',')[1])
                    
                    # Генерация уникального имени файла
                    img_filename = f"page_{page.index}_img_{img.id}.png"
                    img_path = os.path.join(app.config['UPLOAD_FOLDER'], img_filename)
                    
                    # Сохранение изображения
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_data)
                    
                    page_data["images"].append({
                        "id": img.id,
                        "path": img_path
                    })

            result["pages"].append(page_data)

        return result

    except Exception as e:
        logger.error(f"Ошибка OCR: {str(e)}")
        logger.error(traceback.format_exc())
        raise

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_document():
    """
    Загрузка и обработка документа
    """
    try:
        # Определение типа обработки
        processing_type = request.form.get('processing_type', 'file')
        
        # Путь к файлу
        filepath = None

        if processing_type == 'url':
            # Обработка URL
            url = request.form.get('document')
            if not url:
                return jsonify({"status": "error", "message": "URL не указан"}), 400
            
            filepath = download_url_file(url)
        
        elif processing_type == 'file':
            # Обработка файла с диска
            if 'document' not in request.files:
                return jsonify({"status": "error", "message": "Файл не загружен"}), 400

            file = request.files['document']
            
            if file.filename == '':
                return jsonify({"status": "error", "message": "Не выбран файл"}), 400

            # Безопасное имя файла
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
        
        else:
            return jsonify({"status": "error", "message": "Неверный тип обработки"}), 400

        # Обработка документа
        result = process_ocr_document(filepath)

        # Возврат результатов
        return jsonify({
            "status": "success",
            "data": result
        })

    except Exception as e:
        logger.error(f"Ошибка загрузки: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
    finally:
        # Очистка временных файлов
        if filepath and os.path.exists(filepath):
            try:
                os.unlink(filepath)
            except Exception as cleanup_err:
                logger.warning(f"Ошибка очистки файла: {cleanup_err}")

@app.route('/image/<filename>')
def serve_image(filename):
    """
    Эндпоинт для отдачи изображений
    """
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename), 
            mimetype='image/png'
        )
    except Exception as e:
        logger.error(f"Ошибка сервинга изображения: {str(e)}")
        return jsonify({"status": "error", "message": "Изображение не найдено"}), 404

if __name__ == '__main__':
    # TODO: Вынести настройки в конфигурационный файл
    app.run(
        host='0.0.0.0', 
        port=int(os.environ.get('PORT', 5000)), 
        debug=os.environ.get('DEBUG', 'False').lower() == 'true'
    )

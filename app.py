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
import mimetypes

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

        # Проверка, является ли URL Google Drive
        if parsed_url.netloc == 'drive.google.com':
            file_id = None
            if parsed_url.path.startswith('/file/d/'):
                # URL типа /file/d/FILE_ID/...
                file_id = parsed_url.path.split('/')[3]
            elif parsed_url.path.startswith('/uc'):
                # URL типа /uc?export=download&id=FILE_ID
                file_id = request.args.get('id')
            
            if file_id:
                # Преобразование URL Google Drive в URL для скачивания
                url = f'https://drive.google.com/uc?export=download&id={file_id}'
    except ValueError:
        pass

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        raise ValueError(f"Не удалось загрузить файл: {e}")

    # Получение расширения файла
    file_ext = os.path.splitext(parsed_url.path)[1] or '.pdf'

def get_mime_type_by_filename(filename):
    """
    Определение MIME-типа файла по имени файла
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream' # Дефолтный MIME-тип

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

        # Определение MIME-типа файла
        mime_type = None
        if file_path:
            mime_type = get_mime_type_by_filename(file_path)

        # Загрузка файла с указанием MIME-типа
        try:
            with open(file_path, "rb") as file:
                uploaded_file = client.files.upload(
                    file={
                        "file_name": os.path.basename(file_path),
                        "content": file,
                        "mime_type": mime_type, # Явное указание MIME-типа
                    },
                    purpose="ocr"
                )
        except Exception as e:
            logger.error(f"Ошибка загрузки файла в Mistral API: {str(e)}")
            raise

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

        # Сохранение результатов в файлы
        markdown_file, json_file = save_results_to_files(
            result, app.config['UPLOAD_FOLDER']
        )

        # Возврат результатов и имен файлов
        return {
            "document_url": signed_url.url,
            "pages": result["pages"],
            "markdown_file": markdown_file,
            "json_file": json_file
        }

    except Exception as e:
        logger.error(f"Ошибка OCR: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def save_results_to_files(result_data, upload_folder):
    """
    Сохранение результатов OCR в файлы Markdown и JSON
    """
    try:
        # Markdown
        markdown_content_pages = []
        for page in result_data['pages']:
            page_markdown = f"# Страница {page['index'] + 1}\n\n{page['markdown']}"
            if page['images']:
                for img in page['images']:
                    # Чтение изображения и кодирование в base64
                    with open(img['path'], "rb") as image_file:
                        image_data = base64.b64encode(image_file.read()).decode('utf-8')
                    # Вставка изображения в Markdown
                    page_markdown += f"\n\n![image](data:image/png;base64,{image_data})\n\n"
            markdown_content_pages.append(page_markdown)

        markdown_content = "\n\n---\n\n".join(markdown_content_pages)
        markdown_filename = f"document_ocr_{os.urandom(8).hex()}.md"
        markdown_filepath = os.path.join(upload_folder, markdown_filename)
        with open(markdown_filepath, "w", encoding="utf-8") as md_file:
            md_file.write(markdown_content)

        # JSON
        json_filename = f"document_ocr_{os.urandom(8).hex()}.json"
        json_filepath = os.path.join(upload_folder, json_filename)
        with open(json_filepath, "w", encoding="utf-8") as json_file:
            json.dump(result_data, json_file, indent=2, ensure_ascii=False)

        return markdown_filename, json_filename

    except Exception as e:
        logger.error(f"Ошибка сохранения результатов в файлы: {str(e)}")
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
            if not filepath:  # Проверка, что filepath не None после download_url_file
                return jsonify({"status": "error", "message": "Ошибка загрузки файла по URL"}), 500
        
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

@app.route('/download/markdown/<filename>')
def download_markdown(filename):
    """
    Эндпоинт для скачивания Markdown файла
    """
    return send_file(
        os.path.join(app.config['UPLOAD_FOLDER'], filename),
        mimetype='text/markdown',
        as_attachment=True,
        download_name='document_ocr.md'
    )

@app.route('/download/json/<filename>')
def download_json(filename):
    """
    Эндпоинт для скачивания JSON файла
    """
    return send_file(
        os.path.join(app.config['UPLOAD_FOLDER'], filename),
        mimetype='application/json',
        as_attachment=True,
        download_name='document_ocr.json'
    )

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

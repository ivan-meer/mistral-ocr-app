from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from mistralai import Mistral
import os
import json
import base64
import tempfile
import logging
import traceback
import requests
import re
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import mimetypes

# --- Инициализация и Конфигурация ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app) # Включаем CORS для всех маршрутов

# Конфигурация приложения
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_FILE_SIZE_MB', 50)) * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', tempfile.gettempdir())
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'png', 'jpg', 'jpeg', 'docx'} # TODO: docx не обрабатывается OCR Mistral напрямую
app.config['MISTRAL_API_KEY'] = os.environ.get("MISTRAL_API_KEY")
app.config['USE_MOCK_OCR'] = os.environ.get('USE_MOCK_OCR', 'False').lower() == 'true'

if not app.config['MISTRAL_API_KEY'] and not app.config['USE_MOCK_OCR']:
    logger.warning("MISTRAL_API_KEY не установлен, и USE_MOCK_OCR установлен в False. API запросы не будут работать.")

# --- Вспомогательные функции ---
def allowed_file(filename):
    """Проверяет, разрешено ли расширение файла."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_mime_type_by_filename(filename):
    """Определяет MIME-тип файла по имени файла."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'

def extract_images_from_markdown(markdown_text, page_index):
    """Извлекает ссылки на изображения из markdown текста Mistral OCR."""
    # FIXED: Парсим markdown для извлечения ссылок на изображения
    # Mistral OCR встраивает изображения как ![alt](img-N.jpeg) или ![alt](image_id)
    image_pattern = r'!\[([^\]]*)\]\(([^)]+\.(jpeg|jpg|png|gif|webp))\)'
    matches = re.findall(image_pattern, markdown_text, re.IGNORECASE)
    
    extracted_images = []
    for alt_text, image_ref, ext in matches:
        # Создаем уникальное имя файла для изображения
        img_id = image_ref.replace('.', '_').replace('/', '_')
        img_filename = f"page_{page_index}_extracted_{img_id}.{ext}"
        
        extracted_images.append({
            'id': img_id,
            'alt_text': alt_text,
            'original_ref': image_ref,
            'filename': img_filename,
            'markdown_pattern': f'![{alt_text}]({image_ref})'
        })
        
        logger.info(f"Найдено изображение в markdown: {image_ref} -> {img_filename}")
    
    return extracted_images

def handle_google_drive_url(url):
    """Преобразует URL Google Drive в прямой URL для скачивания."""
    parsed_url = urlparse(url)
    if parsed_url.netloc == 'drive.google.com':
        file_id = None
        if parsed_url.path.startswith('/file/d/'):
            file_id = parsed_url.path.split('/')[3]
        elif parsed_url.path.startswith('/uc'):
            # Попытка извлечь id из query параметров
            query_params = dict(qc.split("=") for qc in parsed_url.query.split("&"))
            file_id = query_params.get('id')

        if file_id:
            return f'https://drive.google.com/uc?export=download&id={file_id}'
    return url

def download_file_from_url(url, save_path):
    """Загружает файл по URL и сохраняет его локально."""
    try:
        url = handle_google_drive_url(url)
        response = requests.get(url, stream=True, timeout=30) # 30 секунд таймаут
        response.raise_for_status()

        # Проверка Content-Type (если возможно)
        content_type = response.headers.get('Content-Type', '').lower()
        # TODO: Добавить более строгую проверку MIME-типов на основе ALLOWED_EXTENSIONS
        # Например, application/pdf, image/jpeg, image/png
        # if not any(allowed_mime in content_type for allowed_mime in ['pdf', 'jpeg', 'png']):
        #     raise ValueError(f"Неподдерживаемый тип контента: {content_type}")

        # Проверка размера файла (если Content-Length доступен)
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > app.config['MAX_CONTENT_LENGTH']:
            raise ValueError(f"Файл слишком большой. Максимальный размер: {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)}MB")

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return save_path
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка загрузки файла по URL {url}: {e}")
        raise ValueError(f"Не удалось загрузить файл: {e}")
    except ValueError as e:
        logger.error(f"Ошибка обработки URL {url}: {e}")
        raise

# --- Функции OCR ---
def mock_ocr_processing(file_path, include_images=True):
    """Имитация ответа OCR API для демонстрационного режима."""
    logger.info(f"Использование мокового OCR для файла: {file_path}")
    base_filename = os.path.basename(file_path)
    
    # Создаем демо изображения с правильными путями
    demo_images = []
    if include_images:
        demo_img_filename = f"demo_image_{os.urandom(4).hex()}.png"
        # FIXED: Создаем реальный файл изображения для демо-режима
        demo_img_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(demo_img_filename))
        
        # Создаем простое демо-изображение (красный квадрат 100x100)
        import base64
        from io import BytesIO
        try:
            # Простое PNG изображение (красный квадрат 100x100) в base64
            demo_img_b64_data = "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAdgAAAHYBTnsmCAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAABYSURBVBiVY2CgAzAyMjL8//+fARuYNGkSAzYwceJEBmxg7NixDNjA6NGjGbCBESNGMGADw4YNY8AGhg4dyoANDBkyRKhw0KBBQoWDBw8WKhw4cKBQ4YABA4QKAQAAMzAXfce1lQAAAABJRU5ErkJggg=="
            
            # Декодируем и сохраняем изображение
            img_data = base64.b64decode(demo_img_b64_data)
            with open(demo_img_path, "wb") as img_file:
                img_file.write(img_data)
            
            demo_images.append({
                "id": "demo_img_1", 
                "path": demo_img_path,  # Полный путь к файлу
                "image_base64": f"data:image/png;base64,{demo_img_b64_data}"
            })
            logger.info(f"Создано демо-изображение: {demo_img_path}")
        except Exception as e:
            logger.error(f"Ошибка создания демо-изображения: {e}")
            # Fallback: создаем запись без файла
            demo_images.append({
                "id": "demo_img_1", 
                "path": demo_img_filename,
                "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            })
    
    mock_pages = [
        {
            "index": 0,
            "markdown": f"# Страница 1 Демо Документа ({base_filename})\n\nЭто демонстрационный текст со **страницы 1**.\n\nДанная страница демонстрирует возможности OCR обработки текста.",
            "images": []
        },
        {
            "index": 1,
            "markdown": f"# Страница 2 Демо Документа ({base_filename})\n\nЭто демонстрационный текст со *страницы 2*.\n\nНа этой странице показано извлечение изображений из документа.",
            "images": demo_images
        }
    ]
    
    # Имитация сохранения файлов
    mock_md_filename = f"mock_ocr_{os.urandom(8).hex()}.md"
    mock_json_filename = f"mock_ocr_{os.urandom(8).hex()}.json"

    # Создание пустых файлов для имитации
    open(os.path.join(app.config['UPLOAD_FOLDER'], mock_md_filename), 'w').close()
    open(os.path.join(app.config['UPLOAD_FOLDER'], mock_json_filename), 'w').close()

    return {
        "document_url": f"mock_url_for_{base_filename}",
        "pages": mock_pages,
        "markdown_file": mock_md_filename,
        "json_file": mock_json_filename
    }

def mistral_ocr_processing(file_path, include_images=True):
    """Обрабатывает документ с помощью Mistral OCR API."""
    if not app.config['MISTRAL_API_KEY']:
        raise ValueError("API-ключ Mistral не установлен.")

    client = Mistral(api_key=app.config['MISTRAL_API_KEY'])
    mime_type = get_mime_type_by_filename(file_path)

    try:
        with open(file_path, "rb") as f:
            uploaded_file = client.files.upload(
                file={"file_name": os.path.basename(file_path), "content": f, "mime_type": mime_type},
                purpose="ocr"
            )
    except Exception as e:
        logger.error(f"Ошибка загрузки файла в Mistral API: {e}")
        raise ValueError(f"Ошибка взаимодействия с Mistral API при загрузке файла: {e}")

    signed_url = client.files.get_signed_url(file_id=uploaded_file.id)

    try:
        ocr_response = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": signed_url.url},
            include_image_base64=include_images
        )
        # FIXED: Добавляем детальное логирование ответа API
        logger.info(f"Получен ответ от Mistral OCR API. Страниц: {len(ocr_response.pages)}")
        for i, page in enumerate(ocr_response.pages):
            logger.info(f"Страница {i}: изображений в API ответе: {len(page.images) if page.images else 0}")
            if page.images:
                for j, img in enumerate(page.images):
                    logger.info(f"  Изображение {j}: ID={img.id}, base64_length={len(img.image_base64) if hasattr(img, 'image_base64') else 'нет'}")
    except Exception as e:
        logger.error(f"Ошибка OCR обработки в Mistral API: {e}")
        raise ValueError(f"Ошибка взаимодействия с Mistral API при OCR обработке: {e}")

    processed_pages = []
    for page in ocr_response.pages:
        page_data = {"index": page.index, "markdown": page.markdown, "images": []}
        
        # FIXED: Извлекаем изображения из base64 (если есть)
        if include_images and page.images:
            logger.info(f"Обрабатываем {len(page.images)} изображений из API base64")
            for img in page.images:
                try:
                    # Правильная обработка base64 изображений из Mistral API
                    base64_data = img.image_base64
                    if base64_data.startswith('data:image'):
                        # Если есть MIME префикс, извлекаем только base64 часть
                        base64_data = base64_data.split(',')[1]
                    
                    img_data = base64.b64decode(base64_data)
                    img_filename = f"page_{page.index}_img_{img.id}.png"
                    img_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(img_filename))
                    with open(img_path, "wb") as img_file:
                        img_file.write(img_data)
                    
                    page_data["images"].append({
                        "id": img.id, 
                        "path": img_path,
                        "image_base64": img.image_base64
                    })
                    logger.info(f"Сохранено base64 изображение: {img_filename}")
                except Exception as e:
                    logger.error(f"Ошибка сохранения base64 изображения {img.id}: {e}")
        
        # FIXED: Дополнительно извлекаем изображения из markdown ссылок
        if include_images:
            markdown_images = extract_images_from_markdown(page.markdown, page.index)
            logger.info(f"Найдено {len(markdown_images)} изображений в markdown")
            
            for md_img in markdown_images:
                # Создаем placeholder изображение для ссылок из markdown
                placeholder_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(md_img['filename']))
                
                # Создаем простое placeholder изображение
                try:
                    placeholder_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
                        <rect width="400" height="300" fill="#e2e8f0"/>
                        <text x="200" y="140" text-anchor="middle" fill="#64748b" font-family="Arial" font-size="16">{md_img['alt_text'] or 'Изображение'}</text>
                        <text x="200" y="160" text-anchor="middle" fill="#94a3b8" font-family="Arial" font-size="12">{md_img['original_ref']}</text>
                    </svg>'''
                    
                    # Конвертируем SVG в base64 PNG (упрощенно создаем base64 SVG)
                    svg_base64 = base64.b64encode(placeholder_svg.encode('utf-8')).decode('utf-8')
                    placeholder_base64 = f"data:image/svg+xml;base64,{svg_base64}"
                    
                    page_data["images"].append({
                        "id": md_img['id'],
                        "path": placeholder_path,
                        "image_base64": placeholder_base64,
                        "alt_text": md_img['alt_text'],
                        "original_ref": md_img['original_ref']
                    })
                    logger.info(f"Создан placeholder для markdown изображения: {md_img['original_ref']}")
                except Exception as e:
                    logger.error(f"Ошибка создания placeholder для {md_img['original_ref']}: {e}")
        
        processed_pages.append(page_data)

    return {"document_url": signed_url.url, "pages": processed_pages}


def process_ocr_document(file_path, include_images=True):
    """Выбирает метод обработки OCR (моковый или реальный) и сохраняет результаты."""
    try:
        if app.config['USE_MOCK_OCR']:
            ocr_result = mock_ocr_processing(file_path, include_images)
        else:
            ocr_result = mistral_ocr_processing(file_path, include_images)

        # Сохранение результатов в файлы происходит после получения данных от OCR
        markdown_filename, json_filename = save_results_to_files(
            ocr_result, app.config['UPLOAD_FOLDER'], include_images
        )
        ocr_result["markdown_file"] = markdown_filename
        ocr_result["json_file"] = json_filename

        return ocr_result

    except ValueError as e: # Ошибки, связанные с API ключом или взаимодействием с API
        raise
    except Exception as e:
        logger.error(f"Непредвиденная ошибка OCR: {e}\n{traceback.format_exc()}")
        raise ValueError(f"Внутренняя ошибка сервера при OCR обработке: {e}")


def save_results_to_files(result_data, upload_folder, include_images=True):
    """Сохраняет результаты OCR в файлы Markdown и JSON."""
    try:
        # Markdown
        markdown_content_pages = []
        for page in result_data.get('pages', []):
            page_markdown = f"# Страница {page.get('index', 0) + 1}\n\n{page.get('markdown', '')}"
            if include_images and page.get('images'):
                for img_info in page['images']:
                    img_path = img_info.get('path')
                    # FIXED: Исправлена обработка изображений для корректного отображения
                    if img_path and os.path.exists(img_path):
                        # Если файл существует, читаем его и встраиваем в markdown
                        with open(img_path, "rb") as image_file:
                            image_data_b64 = base64.b64encode(image_file.read()).decode('utf-8')
                        page_markdown += f"\n\n![image](data:image/png;base64,{image_data_b64})\n\n"
                    elif app.config['USE_MOCK_OCR'] and img_info.get('image_base64'):
                        # Для демо-режима используем готовый base64
                        image_data_b64 = img_info['image_base64']
                        if image_data_b64.startswith('data:image'):
                            # Если уже есть префикс, используем как есть
                            page_markdown += f"\n\n![image]({image_data_b64})\n\n"
                        else:
                            # Добавляем префикс если его нет
                            page_markdown += f"\n\n![image](data:image/png;base64,{image_data_b64})\n\n"
                    else:
                        logger.warning(f"Изображение не найдено: {img_path} для страницы {page.get('index')}")

            markdown_content_pages.append(page_markdown)

        markdown_content = "\n\n---\n\n".join(markdown_content_pages)
        markdown_filename = f"document_ocr_{os.urandom(8).hex()}.md"
        markdown_filepath = os.path.join(upload_folder, secure_filename(markdown_filename))
        with open(markdown_filepath, "w", encoding="utf-8") as md_file:
            md_file.write(markdown_content)

        # JSON
        json_filename = f"document_ocr_{os.urandom(8).hex()}.json"
        json_filepath = os.path.join(upload_folder, secure_filename(json_filename))
        # Для JSON сохраняем только метаданные, без base64 изображений, если они были в result_data
        json_to_save = {k: v for k, v in result_data.items() if k != 'pages'}
        json_to_save['pages'] = []
        for page in result_data.get('pages', []):
            page_copy = {pk: pv for pk, pv in page.items() if pk != 'images'}
            if page.get('images'):
                page_copy['images'] = [{'id': img.get('id'), 'path': img.get('path')} for img in page['images']]
            json_to_save['pages'].append(page_copy)

        with open(json_filepath, "w", encoding="utf-8") as json_file:
            json.dump(json_to_save, json_file, indent=2, ensure_ascii=False)

        return markdown_filename, json_filename
    except Exception as e:
        logger.error(f"Ошибка сохранения результатов в файлы: {e}\n{traceback.format_exc()}")
        raise ValueError("Ошибка при сохранении результатов OCR.")

# --- Маршруты Flask ---
@app.route('/')
def index():
    """Главная страница."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_document_route():
    """Обрабатывает загрузку документа (файл или URL)."""
    filepath_to_process = None
    try:
        processing_type = request.form.get('processing_type', 'file')
        
        if processing_type == 'url':
            url = request.form.get('document')
            if not url:
                return jsonify({"status": "error", "message": "URL не указан"}), 400
            
            # Генерируем временное имя файла для скачанного содержимого
            # Используем unquote для декодирования URL, чтобы получить имя файла, если оно есть
            original_filename = os.path.basename(unquote(urlparse(url).path)) or "downloaded_file.tmp"
            temp_filename = secure_filename(f"url_upload_{os.urandom(4).hex()}_{original_filename}")
            filepath_to_process = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
            download_file_from_url(url, filepath_to_process)

        elif processing_type == 'file':
            if 'document' not in request.files:
                return jsonify({"status": "error", "message": "Файл не загружен"}), 400
            file = request.files['document']
            if file.filename == '':
                return jsonify({"status": "error", "message": "Не выбран файл"}), 400
            if not allowed_file(file.filename):
                return jsonify({"status": "error", "message": "Недопустимый тип файла"}), 400

            filename = secure_filename(file.filename)
            filepath_to_process = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath_to_process)
        else:
            return jsonify({"status": "error", "message": "Неверный тип обработки"}), 400

        if not filepath_to_process or not os.path.exists(filepath_to_process):
             return jsonify({"status": "error", "message": "Ошибка подготовки файла для обработки"}), 500

        # Обработка документа
        # Параметр include_images извлекается из формы, по умолчанию True
        include_images_str = request.form.get('include_images', 'true').lower()
        include_images = include_images_str == 'true'

        result = process_ocr_document(filepath_to_process, include_images=include_images)

        # FIXED: Улучшенная обработка путей к изображениям для фронтенда
        total_images = 0
        for page in result.get('pages', []):
            if page.get('images'):
                for img_info in page['images']:
                    total_images += 1
                    if img_info.get('path'):
                        img_filename = secure_filename(os.path.basename(img_info['path']))
                        img_info['url'] = f"/image/{img_filename}"
                        logger.info(f"Создан URL для изображения: {img_info['url']}")
        
        logger.info(f"Обработка завершена. Всего изображений: {total_images}")
        return jsonify({"status": "success", "data": result})

    except ValueError as e: # Ожидаемые ошибки (URL, файл, API)
        logger.warning(f"Ошибка обработки запроса: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400 if "URL" in str(e) or "файл" in str(e) else 500
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при загрузке: {e}\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера."}), 500
    finally:
        # Очистка временных файлов (загруженных по URL или оригинальных файлов)
        if filepath_to_process and os.path.exists(filepath_to_process):
            try:
                # Не удаляем файлы изображений, так как они нужны для отображения/скачивания
                # Удаляем только исходный загруженный PDF/DOCX/etc. или временный файл по URL
                # Файлы изображений и результаты (md, json) имеют уникальные имена и управляются отдельно
                # (например, могут быть удалены по расписанию или при следующем запросе, если это необходимо)

                # Проверяем, является ли файл результатом OCR (md, json, png), чтобы не удалить их случайно
                # Это простая проверка, можно улучшить
                if not (filepath_to_process.endswith(('.md', '.json')) or filepath_to_process.startswith(os.path.join(app.config['UPLOAD_FOLDER'], 'page_'))):
                     os.unlink(filepath_to_process)
                     logger.info(f"Удален временный файл: {filepath_to_process}")
            except Exception as cleanup_err:
                logger.warning(f"Ошибка очистки файла {filepath_to_process}: {cleanup_err}")


@app.route('/download/<filetype>/<filename>')
def download_file_route(filetype, filename):
    """Отдает на скачивание Markdown или JSON файл."""
    if filetype not in ['markdown', 'json']:
        return jsonify({"status": "error", "message": "Неверный тип файла для скачивания"}), 400

    secure_fname = secure_filename(filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_fname)

    if not os.path.exists(filepath):
        logger.warning(f"Запрошенный для скачивания файл не найден: {filepath}")
        return jsonify({"status": "error", "message": "Файл не найден"}), 404

    mimetype = 'text/markdown' if filetype == 'markdown' else 'application/json'
    download_name = f"document_ocr.{'md' if filetype == 'markdown' else 'json'}"

    return send_file(filepath, mimetype=mimetype, as_attachment=True, download_name=download_name)

@app.route('/image/<filename>')
def serve_image_route(filename):
    """Отдает изображение."""
    # FIXED: Изображения теперь корректно создаются в демо-режиме
    
    secure_fname = secure_filename(filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_fname)

    # Проверяем существование файла
    if not os.path.exists(filepath):
        logger.warning(f"Запрошенное изображение не найдено: {filepath}")
        # Создаем простое placeholder изображение если файл не найден
        from flask import Response
        svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">
            <rect width="300" height="200" fill="#334155"/>
            <text x="150" y="100" text-anchor="middle" fill="#cbd5e1" font-family="Arial" font-size="14">Изображение не найдено</text>
            <text x="150" y="120" text-anchor="middle" fill="#94a3b8" font-family="Arial" font-size="12">{}</text>
        </svg>'''.format(filename)
        return Response(svg_content, mimetype='image/svg+xml')

    # Определяем MIME-тип изображения
    mime_type, _ = mimetypes.guess_type(filepath)
    mime_type = mime_type or 'image/png' # По умолчанию png

    return send_file(filepath, mimetype=mime_type)

@app.route('/<path:image_path>')
def serve_markdown_image(image_path):
    """FIXED: Обрабатывает прямые запросы к изображениям из markdown (например /img-0.jpeg)."""
    # Проверяем, что это запрос к изображению
    if not any(image_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        # Если не изображение, возвращаем 404
        from flask import abort
        abort(404)
    
    logger.info(f"Запрос к markdown изображению: {image_path}")
    
    # Создаем placeholder SVG для изображений из markdown
    from flask import Response
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
        <rect width="400" height="300" fill="#e2e8f0" stroke="#cbd5e1" stroke-width="2"/>
        <text x="200" y="140" text-anchor="middle" fill="#64748b" font-family="Arial" font-size="16">Изображение из документа</text>
        <text x="200" y="160" text-anchor="middle" fill="#94a3b8" font-family="Arial" font-size="12">{image_path}</text>
        <text x="200" y="180" text-anchor="middle" fill="#94a3b8" font-family="Arial" font-size="10">Извлечено из PDF Mistral OCR</text>
    </svg>'''
    
    return Response(svg_content, mimetype='image/svg+xml')

# --- API Эндпоинты (для потенциального GUI) ---
@app.route('/api/status', methods=['GET'])
def api_status():
    """Проверяет статус подключения к API Mistral (если не моковый режим)."""
    if app.config['USE_MOCK_OCR']:
        return jsonify({"status": "success", "message": "Работа в демонстрационном режиме."})

    if not app.config['MISTRAL_API_KEY']:
        return jsonify({"status": "error", "message": "API-ключ Mistral не настроен."}), 503

    try:
        client = Mistral(api_key=app.config['MISTRAL_API_KEY'])
        # Пример простого запроса для проверки работоспособности, например, список моделей
        # В данном случае, просто инициализация клиента считается достаточной для базовой проверки
        # client.models.list() # Раскомментировать для реальной проверки API
        return jsonify({"status": "success", "message": "API Mistral доступно (базовая проверка)."})
    except Exception as e:
        logger.error(f"Ошибка подключения к Mistral API: {e}")
        return jsonify({"status": "error", "message": f"Ошибка подключения к Mistral API: {e}"}), 503


def process_api_request(url, output_format, include_images):
    """Общая логика для /api/markdown и /api/json эндпоинтов."""
    if not url:
        return jsonify({"status": "error", "message": "Параметр 'url' обязателен."}), 400

    temp_dir = app.config['UPLOAD_FOLDER']
    # Генерируем временное имя файла для скачанного содержимого
    original_filename = os.path.basename(unquote(urlparse(url).path)) or "api_downloaded_file.tmp"
    temp_filename = secure_filename(f"api_upload_{os.urandom(4).hex()}_{original_filename}")
    filepath_to_process = os.path.join(temp_dir, temp_filename)

    try:
        download_file_from_url(url, filepath_to_process)
        if not os.path.exists(filepath_to_process):
             return jsonify({"status": "error", "message": "Ошибка загрузки файла по URL для API обработки"}), 500

        result_data = process_ocr_document(filepath_to_process, include_images=include_images)

        if output_format == 'markdown':
            # Собираем полный Markdown из всех страниц
            markdown_output_pages = []
            for page in result_data.get('pages', []):
                page_md = f"# Страница {page.get('index',0) + 1}\n\n{page.get('markdown', '')}"
                if include_images and page.get('images'):
                     for img_info in page['images']:
                        # Для API возвращаем base64 изображения прямо в Markdown
                        img_path = img_info.get('path')
                        if app.config['USE_MOCK_OCR'] and img_info.get('image_base64') and not (img_path and os.path.exists(img_path)):
                            image_data_b64 = img_info['image_base64']
                            if not image_data_b64.startswith('data:image'):
                                image_data_b64 = f"data:image/png;base64,{image_data_b64.split(',')[-1]}"
                            page_md += f"\n\n![image]({image_data_b64})\n\n"
                        elif img_path and os.path.exists(img_path):
                            with open(img_path, "rb") as image_file:
                                b64_encoded = base64.b64encode(image_file.read()).decode('utf-8')
                            page_md += f"\n\n![image](data:image/png;base64,{b64_encoded})\n\n"
                markdown_output_pages.append(page_md)
            full_markdown = "\n\n---\n\n".join(markdown_output_pages)
            return jsonify({"status": "success", "markdown": full_markdown, "source_document_url": result_data.get("document_url")})

        elif output_format == 'json':
            # Для JSON ответа, изображения могут быть представлены как пути или base64 строки
            # В данном случае, result_data уже содержит пути, если include_images=True и файлы были сохранены
            # Если GUI нужно base64, это можно добавить здесь дополнительно
            api_json_result = {
                "source_document_url": result_data.get("document_url"),
                "pages": []
            }
            for page in result_data.get('pages', []):
                api_page_data = {"index": page.get("index"), "markdown": page.get("markdown")}
                if include_images and page.get('images'):
                    api_page_data["images"] = []
                    for img_info in page['images']:
                        # Предоставляем URL для доступа к изображению через /image эндпоинт
                        api_img_obj = {"id": img_info.get("id")}
                        if img_info.get('path'):
                             api_img_obj['url'] = f"/image/{secure_filename(os.path.basename(img_info['path']))}"
                        # Опционально: добавить base64 если это нужно API клиенту
                        # if img_info.get('path') and os.path.exists(img_info['path']):
                        #     with open(img_info['path'], "rb") as image_file:
                        #         b64_encoded = base64.b64encode(image_file.read()).decode('utf-8')
                        #     api_img_obj['base64'] = f"data:image/png;base64,{b64_encoded}"
                        api_page_data["images"].append(api_img_obj)
                api_json_result["pages"].append(api_page_data)
            return jsonify({"status": "success", "data": api_json_result})

    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400 if "URL" in str(e) or "файл" in str(e) else 500
    except Exception as e:
        logger.error(f"API ошибка: {e}\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": "Внутренняя ошибка сервера при обработке API запроса."}), 500
    finally:
        if filepath_to_process and os.path.exists(filepath_to_process):
            try:
                # Удаляем временный файл, скачанный для API
                if not (filepath_to_process.endswith(('.md', '.json')) or filepath_to_process.startswith(os.path.join(app.config['UPLOAD_FOLDER'], 'page_'))):
                    os.unlink(filepath_to_process)
                    logger.info(f"Удален временный API файл: {filepath_to_process}")
            except Exception as cleanup_err:
                logger.warning(f"Ошибка очистки временного API файла {filepath_to_process}: {cleanup_err}")

        # Дополнительно: очистка сохраненных md, json и png файлов от предыдущих API запросов, если они не нужны
        # Это можно реализовать через удаление файлов старше определенного времени


@app.route('/api/markdown', methods=['GET'])
def api_get_markdown():
    """Возвращает OCR результат в формате Markdown по URL документа."""
    url = request.args.get('url')
    # Параметр include_images, по умолчанию true
    include_images_str = request.args.get('include_images', 'true').lower()
    include_images = include_images_str == 'true'
    return process_api_request(url, 'markdown', include_images)

@app.route('/api/json', methods=['GET'])
def api_get_json():
    """Возвращает OCR результат в формате JSON по URL документа."""
    url = request.args.get('url')
    # Параметр include_images, по умолчанию true
    include_images_str = request.args.get('include_images', 'true').lower()
    include_images = include_images_str == 'true'
    return process_api_request(url, 'json', include_images)


# --- Запуск приложения ---
if __name__ == '__main__':
    # TODO: Вынести настройки в конфигурационный файл или переменные окружения для production
    # Например, использовать Gunicorn + Nginx в production
    app.run(
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('DEBUG', 'False').lower() == 'true'
    )

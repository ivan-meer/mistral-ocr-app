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
import io

# --- Инициализация и Конфигурация ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Опциональный импорт PyMuPDF и Pillow
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
    logger.info("PyMuPDF успешно загружен - fallback извлечение изображений доступно")
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF не установлен. Fallback извлечение изображений недоступно. Установите: pip install PyMuPDF==1.23.26")

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
    logger.info("Pillow успешно загружен - обработка изображений доступна")
except ImportError:
    PILLOW_AVAILABLE = False
    logger.warning("Pillow не установлен. Обработка изображений ограничена. Установите: pip install Pillow==10.2.0")

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

def update_markdown_image_links(page_data, page_index, include_images):
    """Универсальная функция для обновления ссылок на изображения в markdown."""
    if not include_images:
        logger.info(f"[MARKDOWN UPDATE] Страница {page_index}: include_images=False, пропускаем")
        return
        
    markdown_text = page_data.get('markdown', '')
    if not markdown_text:
        logger.info(f"[MARKDOWN UPDATE] Страница {page_index}: нет markdown текста")
        return
        
    logger.info(f"[MARKDOWN UPDATE] Страница {page_index}: markdown содержит {len(markdown_text)} символов")
    
    markdown_images = extract_images_from_markdown(markdown_text, page_index)
    if not markdown_images:
        logger.info(f"[MARKDOWN UPDATE] Страница {page_index}: не найдено ссылок на изображения в markdown")
        return
        
    # Найдем API изображения с путями (после возможного связывания с fallback)
    saved_api_images_for_page = [img for img in page_data.get("images", []) if img.get("path")]
    logger.info(f"[MARKDOWN UPDATE] Страница {page_index}: найдено {len(markdown_images)} MD ссылок, {len(saved_api_images_for_page)} изображений с путями")
    
    # Детальная отладка найденных изображений
    for i, img in enumerate(page_data.get("images", [])):
        logger.info(f"[MARKDOWN UPDATE] Изображение {i}: id='{img.get('id')}', path='{img.get('path')}', coords={img.get('coordinates')}")
    
    temp_updated_markdown = markdown_text
    updates_made = 0
    for k, md_img in enumerate(markdown_images):
        logger.info(f"[MARKDOWN UPDATE] Обрабатываем MD ссылку {k+1}: '{md_img['markdown_pattern']}'")
        
        if k < len(saved_api_images_for_page):
            api_image_data = saved_api_images_for_page[k]
            img_filename_on_disk = os.path.basename(api_image_data['path'])
            new_url = f"/image/{img_filename_on_disk}"
            
            old_pattern = md_img['markdown_pattern']
            new_pattern = f"![{md_img['alt_text']}]({new_url})"
            
            logger.info(f"[MARKDOWN UPDATE] Замена MD ссылки {k+1}: '{old_pattern}' -> '{new_pattern}'")
            
            if old_pattern in temp_updated_markdown:
                temp_updated_markdown = temp_updated_markdown.replace(old_pattern, new_pattern, 1)
                updates_made += 1
                logger.info(f"[MARKDOWN UPDATE] ✅ Замена выполнена успешно")
            else:
                logger.warning(f"[MARKDOWN UPDATE] ❌ Паттерн '{old_pattern}' не найден в markdown!")
        else:
            logger.warning(f"[MARKDOWN UPDATE] Нет изображения для MD ссылки {k+1}: '{md_img['markdown_pattern']}'")
    
    logger.info(f"[MARKDOWN UPDATE] Страница {page_index}: выполнено {updates_made} замен из {len(markdown_images)} найденных")
    page_data["markdown"] = temp_updated_markdown

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

def validate_ocr_response(ocr_response):
    """Валидация ответа OCR для выявления потенциальных проблем (согласно лучшим практикам)."""
    issues = []
    total_images = 0
    valid_images = 0
    
    for i, page in enumerate(ocr_response.pages):
        if page.images:
            for j, img in enumerate(page.images):
                total_images += 1
                img_id = getattr(img, 'id', f'unknown_{j}')
                base64_data = getattr(img, 'image_base64', None)
                
                if not base64_data:
                    issues.append(f"Страница {i+1}, изображение {img_id}: отсутствуют base64 данные")
                elif len(base64_data) < 100:
                    issues.append(f"Страница {i+1}, изображение {img_id}: подозрительно малый размер данных ({len(base64_data)} символов)")
                else:
                    valid_images += 1
            
            # Проверка ссылок в Markdown
            import re
            img_references = re.findall(r'!\[.*?\]\(img-\d+\.jpe?g\)', page.markdown or '')
            if len(img_references) != len(page.images):
                issues.append(f"Страница {i+1}: несоответствие количества ссылок ({len(img_references)}) и изображений ({len(page.images)})")
    
    logger.info(f"Валидация OCR: {valid_images}/{total_images} изображений валидны")
    for issue in issues:
        logger.warning(f"Проблема валидации: {issue}")
    
    return {
        'total_images': total_images,
        'valid_images': valid_images,
        'issues': issues,
        'success_rate': (valid_images / total_images * 100) if total_images > 0 else 0
    }

def enhanced_base64_processing(base64_data, img_id):
    """Улучшенная обработка base64 данных с проверками."""
    if not base64_data:
        return None
    
    try:
        # Безопасное удаление префикса (рекомендуемый подход)
        if "base64," in base64_data:
            clean_data = base64_data.split("base64,", 1)[1]
        else:
            clean_data = base64_data
        
        # Определение формата изображения
        img_format = "png"  # fallback
        if "image/png" in base64_data:
            img_format = "png"
        elif "image/jpeg" in base64_data or "image/jpg" in base64_data:
            img_format = "jpg"
        elif "image/webp" in base64_data:
            img_format = "webp"
        
        # Декодирование с проверкой
        img_data = base64.b64decode(clean_data)
        
        # Проверка минимального размера (защита от поврежденных данных)
        if len(img_data) < 50:  # менее 50 байт подозрительно
            logger.warning(f"Изображение {img_id}: подозрительно малый размер после декодирования ({len(img_data)} байт)")
            return None
        
        return {
            'data': img_data,
            'format': img_format,
            'size': len(img_data)
        }
    
    except Exception as e:
        logger.error(f"Ошибка декодирования base64 для {img_id}: {e}")
        return None

def save_base64_image(img_id, base64_data, upload_folder):
    """Сохраняет base64 изображение как реальный файл (аналогично Next.js приложению)."""
    try:
        # Определяем MIME тип из base64 данных
        if base64_data.startswith('data:'):
            # Формат: data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ...
            header, data = base64_data.split(',', 1)
            mime_type = header.split(';')[0].split(':')[1]
            extension = mime_type.split('/')[1]
        else:
            # Просто base64 без заголовка
            data = base64_data
            extension = 'jpeg'  # По умолчанию
            
        # Создаем уникальное имя файла
        filename = f"{img_id}-{os.urandom(4).hex()}.{extension}"
        file_path = os.path.join(upload_folder, filename)
        
        # Декодируем и сохраняем
        image_data = base64.b64decode(data)
        with open(file_path, 'wb') as f:
            f.write(image_data)
            
        logger.info(f"Изображение сохранено: {file_path} ({len(image_data)} байт)")
        return file_path
        
    except Exception as e:
        logger.error(f"Ошибка сохранения base64 изображения {img_id}: {e}")
        return None

def create_svg_placeholder(filename, image_id, width, height):
    """Создает и сохраняет SVG-плейсхолдер для изображения без данных."""
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
        <defs>
            <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#f1f5f9" stroke-width="1"/>
            </pattern>
        </defs>
        <rect width="{width}" height="{height}" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>
        <rect width="{width}" height="{height}" fill="url(#grid)" opacity="0.3"/>
        <text x="{width//2}" y="{height//2+20}" text-anchor="middle" fill="#475569" font-family="Arial, sans-serif" font-size="18" font-weight="bold">
            Изображение из документа
        </text>
        <text x="{width//2}" y="{height//2+45}" text-anchor="middle" fill="#64748b" font-family="Arial, sans-serif" font-size="14">
            {image_id}
        </text>
        <text x="{width//2}" y="{height//2+65}" text-anchor="middle" fill="#94a3b8" font-family="Arial, sans-serif" font-size="12">
            (Base64 данные недоступны в API)
        </text>
    </svg>'''
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)
    return filepath

def extract_pdf_pages_as_images(pdf_path, dpi=200):
    """Конвертирует страницы PDF в изображения для сравнения с результатами OCR."""
    if not PYMUPDF_AVAILABLE:
        logger.warning("PyMuPDF недоступен. Установите: pip install PyMuPDF==1.23.26")
        return []
    
    try:
        doc = fitz.open(pdf_path)
        page_images = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Создаем изображение страницы с высоким разрешением
            mat = fitz.Matrix(dpi/72, dpi/72)  # Матрица масштабирования
            pix = page.get_pixmap(matrix=mat)
            
            # Сохраняем как PNG
            img_filename = f"pdf_page_{page_num}.png"
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(img_filename))
            pix.save(img_path)
            
            page_images.append({
                'page_num': page_num,
                'image_path': img_path,
                'width': pix.width,
                'height': pix.height
            })
            logger.info(f"Конвертирована страница {page_num}: {img_path} ({pix.width}x{pix.height})")
        
        doc.close()
        return page_images
    except Exception as e:
        logger.error(f"Ошибка конвертации PDF в изображения: {e}")
        return []

def extract_images_from_pdf(pdf_path):
    """Извлекает встроенные изображения напрямую из PDF (как fallback для Mistral OCR)."""
    if not PYMUPDF_AVAILABLE:
        logger.warning("PyMuPDF недоступен. Установите: pip install PyMuPDF==1.23.26")
        return []
    
    try:
        doc = fitz.open(pdf_path)
        extracted_images = []
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                # Получаем изображение
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                
                if pix.n - pix.alpha < 4:  # Проверяем что это не CMYK
                    # Сохраняем изображение
                    img_filename = f"extracted_page_{page_num}_img_{img_index}.png"
                    img_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(img_filename))
                    
                    if pix.alpha:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    
                    pix.save(img_path)
                    
                    # Получаем координаты изображения на странице
                    rects = page.get_image_rects(xref)
                    bbox = rects[0] if rects else page.rect
                    
                    extracted_images.append({
                        'page_num': page_num,
                        'image_index': img_index,
                        'image_path': img_path,
                        'width': pix.width,
                        'height': pix.height,
                        'bbox': {
                            'x0': bbox.x0, 'y0': bbox.y0,
                            'x1': bbox.x1, 'y1': bbox.y1
                        }
                    })
                    logger.info(f"Извлечено изображение: страница {page_num}, индекс {img_index}")
                
                pix = None  # Освобождаем память
        
        doc.close()
        return extracted_images
    except Exception as e:
        logger.error(f"Ошибка извлечения изображений из PDF: {e}")
        return []

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
        # Применяем secure_filename здесь, чтобы имя файла было "чистым" с самого начала
        secured_demo_img_filename = secure_filename(demo_img_filename)
        demo_img_path = os.path.join(app.config['UPLOAD_FOLDER'], secured_demo_img_filename)
        logger.info(f"[MOCK_OCR] Планируемый путь к демо-изображению: {demo_img_path}")
        
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
            logger.info(f"[MOCK_OCR] Демо-изображение успешно записано в: {demo_img_path}")
            
            demo_images.append({
                "id": "demo_img_1", 
                "path": demo_img_path,  # Полный путь к файлу
                "base64_data": "",  # ПУСТЫЕ base64 данные для тестирования fallback
                "coordinates": {"top_left_x": 100, "top_left_y": 50, "bottom_right_x": 400, "bottom_right_y": 300}
            })
            logger.info(f"[MOCK_OCR] Данные демо-изображения добавлены: id=demo_img_1, path={demo_img_path}")
        except Exception as e:
            logger.error(f"[MOCK_OCR] Ошибка создания демо-изображения: {e}")
            # Fallback: создаем запись без файла, но с тем же именем, которое было бы у файла
            demo_images.append({
                "id": "demo_img_1", 
                "path": demo_img_path, # Используем demo_img_path даже если файл не создан, для консистентности
                "original_filename_if_failed": secured_demo_img_filename, # Доп. инфо для отладки
                "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            })
    
    logger.info(f"[MOCK_OCR] Возвращаемые demo_images: {json.dumps(demo_images, indent=2)}")
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
        # ENHANCED: Валидация ответа согласно лучшим практикам
        validation_result = validate_ocr_response(ocr_response)
        logger.info(f"Получен ответ от Mistral OCR API. Страниц: {len(ocr_response.pages)}")
        logger.info(f"Результаты валидации: {validation_result['valid_images']}/{validation_result['total_images']} изображений валидны ({validation_result['success_rate']:.1f}%)")
        
        for i, page in enumerate(ocr_response.pages):
            logger.info(f"Страница {i}: изображений в API ответе: {len(page.images) if page.images else 0}")
            if page.images:
                for j, img in enumerate(page.images):
                    img_id = getattr(img, 'id', 'unknown')
                    # Детальное логирование структуры изображения
                    img_attrs = []
                    for attr in ['id', 'image_base64', 'top_left_x', 'top_left_y', 'bottom_right_x', 'bottom_right_y']:
                        if hasattr(img, attr):
                            value = getattr(img, attr)
                            if attr == 'image_base64':
                                value_str = f"length={len(value) if value else 0}"
                            else:
                                value_str = str(value)
                            img_attrs.append(f"{attr}={value_str}")
                    logger.info(f"  Изображение {j}: {', '.join(img_attrs)}")
    except Exception as e:
        logger.error(f"Ошибка OCR обработки в Mistral API: {e}")
        raise ValueError(f"Ошибка взаимодействия с Mistral API при OCR обработке: {e}")

    processed_pages = []
    for page in ocr_response.pages:
        page_data = {"index": page.index, "markdown": page.markdown, "images": []}
        
        # FIXED: Извлекаем изображения из API ответа (независимо от настройки include_images)
        # Если API нашел изображения, они должны обрабатываться для fallback
        if page.images:
            logger.info(f"Обрабатываем {len(page.images)} изображений из API base64")
            for img in page.images:
                try:
                    # FIXED: Правильная обработка base64 изображений с защитой от None
                    base64_data = getattr(img, 'image_base64', None)
                    img_id = getattr(img, 'id', f'img_{len(page_data["images"])}')
                    
                    if not base64_data:
                        logger.warning(f"Изображение {img_id} не содержит base64 данных - добавляем для fallback обработки")
                        # Добавляем изображение БЕЗ base64 данных для fallback обработки
                        coordinates = {
                            'top_left_x': getattr(img, 'top_left_x', 0),
                            'top_left_y': getattr(img, 'top_left_y', 0),
                            'bottom_right_x': getattr(img, 'bottom_right_x', 600),
                            'bottom_right_y': getattr(img, 'bottom_right_y', 400)
                        }
                        
                        page_data["images"].append({
                            "id": img_id,
                            "path": None,  # Пока нет пути - будет добавлен fallback логикой
                            "image_base64": None,  # Пустые данные
                            "coordinates": coordinates,
                            "width": coordinates['bottom_right_x'] - coordinates['top_left_x'],
                            "height": coordinates['bottom_right_y'] - coordinates['top_left_y'],
                            "alt_text": f"Изображение {img_id}"
                        })
                        continue
                    
                    # ENHANCED: Используем улучшенную обработку base64 согласно лучшим практикам
                    processed_img = enhanced_base64_processing(base64_data, img_id)
                    if not processed_img:
                        logger.warning(f"Не удалось обработать base64 данные для {img_id}, создаем placeholder")
                        # Fallback к созданию placeholder
                        coordinates = {
                            'top_left_x': getattr(img, 'top_left_x', 0),
                            'top_left_y': getattr(img, 'top_left_y', 0),
                            'bottom_right_x': getattr(img, 'bottom_right_x', 600),
                            'bottom_right_y': getattr(img, 'bottom_right_y', 400)
                        }
                        width = coordinates['bottom_right_x'] - coordinates['top_left_x']
                        height = coordinates['bottom_right_y'] - coordinates['top_left_y']
                        placeholder_filename = f"placeholder_{page.index}_{img_id}.svg"
                        img_path = create_svg_placeholder(placeholder_filename, img_id, width if width > 0 else 600, height if height > 0 else 400)
                    else:
                        img_filename = f"page_{page.index}_img_{img_id}.{processed_img['format']}"
                        img_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(img_filename))
                        with open(img_path, "wb") as img_file:
                            img_file.write(processed_img['data'])
                        logger.info(f"Сохранено изображение: {img_filename} ({processed_img['size']} байт)")
                    
                    page_data["images"].append({
                        "id": img_id, 
                        "path": img_path,
                        "image_base64": getattr(img, 'image_base64', None)
                    })
                    logger.info(f"Сохранено base64 изображение: {img_filename}")
                except Exception as e:
                    img_id = getattr(img, 'id', 'unknown')
                    logger.error(f"Ошибка сохранения base64 изображения {img_id}: {e}")
                    # Добавляем изображение в список даже если не удалось сохранить файл
                    page_data["images"].append({
                        "id": img_id,
                        "path": None,
                        "image_base64": getattr(img, 'image_base64', None)
                    })
        
        processed_pages.append(page_data)

    # ENHANCED: Fallback извлечение изображений из PDF если API нашел изображения но не вернул base64
    # Проверяем есть ли изображения с пустыми base64 данными
    images_with_empty_base64 = 0
    total_images_found = 0
    logger.info(f"[FALLBACK DEBUG] Начинаем проверку processed_pages, всего страниц: {len(processed_pages)}")
    
    for page_idx, page_data in enumerate(processed_pages):
        if page_data.get('images'):
            page_images = len(page_data['images'])
            total_images_found += page_images
            logger.info(f"[FALLBACK DEBUG] Страница {page_idx}: найдено {page_images} изображений")
            
            for img_idx, img_info in enumerate(page_data['images']):
                base64_data = img_info.get('image_base64')
                img_id = img_info.get('id', 'unknown')
                
                logger.info(f"[FALLBACK DEBUG] Страница {page_idx}, изображение {img_idx}: id={img_id}, image_base64={'пустое' if not base64_data else 'есть'}")
                
                if not base64_data:  # ИСПРАВЛЕНО: проверяем правильное поле
                    images_with_empty_base64 += 1
    
    logger.info(f"[FALLBACK DEBUG] Итого найдено изображений: {total_images_found}, с пустыми base64: {images_with_empty_base64}")
    
    needs_fallback = (file_path.lower().endswith('.pdf') and 
                     images_with_empty_base64 > 0 and 
                     PYMUPDF_AVAILABLE)
    
    if needs_fallback:
        logger.info(f"Проверка fallback: найдено {images_with_empty_base64} изображений с пустыми base64")
        logger.info(f"Fallback условия: PyMuPDF={PYMUPDF_AVAILABLE}, Pillow={PILLOW_AVAILABLE}")
        logger.info("Выполняем fallback извлечение изображений из PDF")
            
    if needs_fallback:
        
        # Извлекаем страницы PDF как изображения для сравнения
        pdf_page_images = extract_pdf_pages_as_images(file_path)
        
        # Извлекаем встроенные изображения напрямую из PDF
        pdf_extracted_images = extract_images_from_pdf(file_path)
        
        # Добавляем информацию о страницах PDF к результату
        for i, page_data in enumerate(processed_pages):
            # Добавляем изображение страницы PDF
            if i < len(pdf_page_images):
                page_img = pdf_page_images[i]
                page_data['pdf_page_image'] = {
                    'path': page_img['image_path'],
                    'width': page_img['width'],
                    'height': page_img['height']
                }
            
            # Добавляем извлеченные изображения для этой страницы
            page_extracted = [img for img in pdf_extracted_images if img['page_num'] == i]
            if page_extracted:
                if 'fallback_images' not in page_data:
                    page_data['fallback_images'] = []
                page_data['fallback_images'].extend(page_extracted)
                logger.info(f"Добавлено {len(page_extracted)} fallback изображений для страницы {i}")
                
                # ENHANCED: Связываем пустые API изображения с fallback изображениями
                api_images_with_empty_base64 = [img for img in page_data['images'] if not img.get('image_base64')]
                if api_images_with_empty_base64:
                    logger.info(f"Найдено {len(api_images_with_empty_base64)} API изображений с пустыми base64 на странице {i}")
                    
                    # Сопоставляем API изображения с fallback изображениями (по порядку)
                    for j, api_img in enumerate(api_images_with_empty_base64):
                        if j < len(page_extracted):
                            fallback_img = page_extracted[j]
                            # Обновляем путь API изображения на fallback изображение
                            api_img['path'] = fallback_img['image_path']
                            logger.info(f"Связали API изображение '{api_img['id']}' с fallback файлом: {fallback_img['image_path']}")
                        else:
                            logger.warning(f"Недостаточно fallback изображений для API изображения '{api_img['id']}' на странице {i}")
                    
                    # ENHANCED: Обновляем markdown ссылки после связывания с fallback изображениями
                    update_markdown_image_links(page_data, i, include_images)
    
    # ФИНАЛЬНОЕ ОБНОВЛЕНИЕ: Обновляем markdown ссылки для всех страниц (включая те, где не было fallback)
    for i, page_data in enumerate(processed_pages):
        # ИСПРАВЛЕНИЕ: Обновляем markdown если есть изображения, независимо от include_images
        has_images_with_paths = any(img.get("path") for img in page_data.get("images", []))
        should_update_markdown = include_images or has_images_with_paths
        logger.info(f"[FINAL MARKDOWN] Страница {i}: include_images={include_images}, has_images_with_paths={has_images_with_paths}, should_update={should_update_markdown}")
        update_markdown_image_links(page_data, i, should_update_markdown)

    return {"document_url": signed_url.url, "pages": processed_pages}


def process_ocr_document(file_path, include_images=True, export_format="embedded"):
    """Выбирает метод обработки OCR (моковый или реальный) и сохраняет результаты."""
    try:
        if app.config['USE_MOCK_OCR']:
            ocr_result = mock_ocr_processing(file_path, include_images)
        else:
            ocr_result = mistral_ocr_processing(file_path, include_images)

        # Сохранение результатов в файлы происходит после получения данных от OCR
        markdown_filename, json_filename = save_results_to_files(
            ocr_result, app.config['UPLOAD_FOLDER'], include_images, export_format
        )
        ocr_result["markdown_file"] = markdown_filename
        ocr_result["json_file"] = json_filename

        # НОВОЕ: Автоматическая очистка временных файлов для embedded формата
        if export_format == "embedded":
            cleanup_temp_files(ocr_result)
            
            # Добавляем статистику для пользователя
            total_images = sum(len(page.get('images', [])) for page in ocr_result.get('pages', []))
            fallback_pages = sum(1 for page in ocr_result.get('pages', []) if page.get('fallback_images'))
            
            ocr_result['processing_info'] = {
                'export_format': export_format,
                'total_images': total_images,
                'fallback_used': fallback_pages > 0,
                'fallback_pages': fallback_pages,
                'embedded_images': True if export_format == "embedded" else False
            }
            logger.info(f"Обработка завершена: {total_images} изображений, fallback использован на {fallback_pages} страницах")

        return ocr_result

    except ValueError as e: # Ошибки, связанные с API ключом или взаимодействием с API
        raise
    except Exception as e:
        logger.error(f"Непредвиденная ошибка OCR: {e}\n{traceback.format_exc()}")
        raise ValueError(f"Внутренняя ошибка сервера при OCR обработке: {e}")


def create_embedded_markdown(result_data):
    """Создает markdown с встроенными base64 изображениями"""
    markdown_content_pages = []
    for page in result_data.get('pages', []):
        page_markdown = f"# Страница {page.get('index', 0) + 1}\n\n{page.get('markdown', '')}"
        
        # Встраиваем изображения как base64
        for img_info in page.get('images', []):
            img_path = img_info.get('path')
            img_url = img_info.get('url', '')
            
            if img_path and os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as image_file:
                        image_data_b64 = base64.b64encode(image_file.read()).decode('utf-8')
                    
                    # Определяем формат изображения
                    ext = os.path.splitext(img_path)[1].lower()
                    if ext in ['.png']:
                        mime_type = 'image/png'
                    elif ext in ['.jpg', '.jpeg']:
                        mime_type = 'image/jpeg'
                    else:
                        mime_type = 'image/png'  # По умолчанию
                    
                    data_url = f"data:{mime_type};base64,{image_data_b64}"
                    
                    # Заменяем URL на data URL в markdown
                    if img_url in page_markdown:
                        page_markdown = page_markdown.replace(img_url, data_url)
                        logger.info(f"Встроено изображение {img_info.get('id')} как base64")
                    
                except Exception as e:
                    logger.error(f"Ошибка встраивания изображения {img_path}: {e}")
        
        markdown_content_pages.append(page_markdown)
    
    return "\n\n---\n\n".join(markdown_content_pages)

def cleanup_temp_files(ocr_result):
    """Удаляет временные файлы после встраивания изображений в markdown"""
    cleaned_files = 0
    for page in ocr_result.get('pages', []):
        # Удаляем PDF страницы
        if page.get('pdf_page_image', {}).get('path'):
            if safe_remove_file(page['pdf_page_image']['path']):
                cleaned_files += 1
        
        # Удаляем fallback изображения  
        for fb_img in page.get('fallback_images', []):
            if safe_remove_file(fb_img.get('image_path')):
                cleaned_files += 1
        
        # Удаляем извлеченные изображения
        for img in page.get('images', []):
            if safe_remove_file(img.get('path')):
                cleaned_files += 1
    
    logger.info(f"Автоматически удалено {cleaned_files} временных файлов")

def safe_remove_file(file_path):
    """Безопасно удаляет файл"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Удален временный файл: {file_path}")
            return True
    except Exception as e:
        logger.warning(f"Не удалось удалить файл {file_path}: {e}")
    return False

def save_results_to_files(result_data, upload_folder, include_images=True, export_format="embedded"):
    """Сохраняет результаты OCR в файлы Markdown и JSON."""
    try:
        # Выбираем способ создания markdown в зависимости от формата экспорта
        if export_format == "embedded":
            markdown_content = create_embedded_markdown(result_data)
            logger.info("Создан embedded markdown с встроенными base64 изображениями")
        else:
            # Стандартный markdown с ссылками (для совместимости)
            markdown_content_pages = []
            for page in result_data.get('pages', []):
                page_markdown = f"# Страница {page.get('index', 0) + 1}\n\n{page.get('markdown', '')}"
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
        
        # НОВОЕ: Добавляем параметр формата экспорта (по умолчанию embedded для решения проблемы пользователя)
        export_format = request.form.get('export_format', 'embedded')
        logger.info(f"Используется формат экспорта: {export_format}")

        result = process_ocr_document(filepath_to_process, include_images=include_images, export_format=export_format)

        # FIXED: Улучшенная обработка путей к изображениям для фронтенда
        total_images = 0
        for page_idx, page in enumerate(result.get('pages', [])):
            if page.get('images'):
                logger.info(f"[UPLOAD_ROUTE] Обработка изображений для страницы {page_idx}")
                for img_idx, img_info in enumerate(page['images']):
                    total_images += 1
                    logger.info(f"[UPLOAD_ROUTE] Изображение {img_idx} на странице {page_idx}: исходные данные: {json.dumps(img_info)}")
                    if img_info.get('path'):
                        original_path = img_info['path']
                        logger.info(f"[UPLOAD_ROUTE] Наличие пути к изображению: {original_path}")

                        base_name = os.path.basename(original_path)
                        logger.info(f"[UPLOAD_ROUTE] Имя файла из пути: {base_name}")

                        secured_img_filename = secure_filename(base_name)
                        logger.info(f"[UPLOAD_ROUTE] Имя файла после secure_filename: {secured_img_filename}")

                        img_info['url'] = f"/image/{secured_img_filename}"
                        logger.info(f"[UPLOAD_ROUTE] Сгенерированный URL для изображения: {img_info['url']}")
                    else:
                        logger.warning(f"[UPLOAD_ROUTE] Изображение {img_idx} на странице {page_idx} не имеет 'path'. Данные: {json.dumps(img_info)}")
        
        logger.info(f"Обработка завершена. Всего изображений: {total_images}. Финальные данные для ответа: {json.dumps(result, indent=2)}")
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
    logger.info(f"[SERVE_IMAGE] Запрос на обслуживание изображения. Получен filename: '{filename}'")
    
    # Важно: filename из URL уже должен быть "защищенным", если он был правильно создан в /upload
    # Повторное применение secure_filename здесь не должно ничего менять, если имя уже безопасное.
    # Однако, если по какой-то причине имя в URL не было защищено, это его защитит.
    # Для отладки посмотрим, меняет ли что-то secure_filename.
    s_filename_check = secure_filename(filename)
    if s_filename_check != filename:
        logger.warning(f"[SERVE_IMAGE] Имя файла '{filename}' было изменено secure_filename на '{s_filename_check}'. Это может указывать на проблему в URL.")

    # Используем s_filename_check для построения пути, так как это гарантированно безопасное имя.
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], s_filename_check)
    logger.info(f"[SERVE_IMAGE] UPLOAD_FOLDER: {app.config['UPLOAD_FOLDER']}")
    logger.info(f"[SERVE_IMAGE] Полный путь к файлу для обслуживания: {filepath}")

    # Проверяем существование файла
    if not os.path.exists(filepath):
        logger.warning(f"[SERVE_IMAGE] Файл НЕ НАЙДЕН по пути: {filepath}")
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

# УДАЛЕН: catch-all роут который блокировал корректное отображение реальных изображений
# Теперь полагаемся на корректные markdown ссылки вида /image/<filename>

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

@app.route('/compare')
def compare_results():
    """Показывает страницу сравнения оригинального PDF с результатами OCR."""
    return render_template('compare.html')

@app.route('/pdf_page/<filename>')
def serve_pdf_page(filename):
    """Отдает изображения страниц PDF для сравнения."""
    try:
        pdf_page_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
        if os.path.exists(pdf_page_path):
            return send_file(pdf_page_path, mimetype='image/png')
        else:
            logger.warning(f"PDF страница не найдена: {filename}")
            from flask import abort
            abort(404)
    except Exception as e:
        logger.error(f"Ошибка отдачи PDF страницы {filename}: {e}")
        from flask import abort
        abort(500)


# --- Запуск приложения ---
if __name__ == '__main__':
    # TODO: Вынести настройки в конфигурационный файл или переменные окружения для production
    # Например, использовать Gunicorn + Nginx в production
    app.run(
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('DEBUG', 'False').lower() == 'true'
    )

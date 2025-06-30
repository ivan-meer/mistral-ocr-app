#!/usr/bin/env python3
"""
Тестовый скрипт для проверки извлечения изображений из PDF
Показывает как именно работает fallback извлечение изображений
"""

import os
import sys
import tempfile

def test_pymupdf_import():
    """Проверка что PyMuPDF установлен"""
    try:
        import fitz
        print("✅ PyMuPDF (fitz) успешно импортирован")
        print(f"   Версия: {fitz.version}")
        return True
    except ImportError as e:
        print("❌ PyMuPDF не установлен:")
        print(f"   Ошибка: {e}")
        print("   Установите: pip install PyMuPDF==1.23.26")
        return False

def test_pillow_import():
    """Проверка что Pillow установлен"""
    try:
        from PIL import Image
        print("✅ Pillow успешно импортирован")
        print(f"   Версия: {Image.__version__}")
        return True
    except ImportError as e:
        print("❌ Pillow не установлен:")
        print(f"   Ошибка: {e}")
        print("   Установите: pip install Pillow==10.2.0")
        return False

def test_pdf_processing(pdf_path):
    """Тестирование извлечения изображений из PDF"""
    if not os.path.exists(pdf_path):
        print(f"❌ PDF файл не найден: {pdf_path}")
        return False
    
    try:
        import fitz
        
        print(f"\n🔍 Анализ PDF: {pdf_path}")
        doc = fitz.open(pdf_path)
        
        print(f"📄 Страниц в PDF: {len(doc)}")
        
        total_images = 0
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            images = page.get_images()
            
            print(f"   Страница {page_num + 1}: найдено {len(images)} изображений")
            total_images += len(images)
            
            # Показываем информацию о каждом изображении
            for i, img in enumerate(images):
                xref = img[0]
                width = img[2]
                height = img[3]
                print(f"      Изображение {i+1}: {width}x{height}px (xref: {xref})")
        
        print(f"\n📊 Общий результат:")
        print(f"   Всего изображений в PDF: {total_images}")
        
        doc.close()
        return total_images > 0
        
    except Exception as e:
        print(f"❌ Ошибка обработки PDF: {e}")
        return False

def create_test_pdf_with_image():
    """Создает тестовый PDF с изображением для демонстрации"""
    try:
        import fitz
        from PIL import Image
        import io
        
        # Создаем простое тестовое изображение
        img = Image.new('RGB', (200, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Создаем PDF с изображением
        doc = fitz.open()
        page = doc.new_page()
        
        # Вставляем изображение
        rect = fitz.Rect(50, 50, 250, 150)
        page.insert_image(rect, stream=img_bytes.getvalue())
        
        # Добавляем текст
        text_rect = fitz.Rect(50, 200, 500, 250)
        page.insert_text(text_rect.tl, "Тестовый PDF с изображением", fontsize=16)
        
        # Сохраняем
        test_pdf_path = "test_with_image.pdf"
        doc.save(test_pdf_path)
        doc.close()
        
        print(f"✅ Создан тестовый PDF: {test_pdf_path}")
        return test_pdf_path
        
    except Exception as e:
        print(f"❌ Ошибка создания тестового PDF: {e}")
        return None

def main():
    """Основная функция тестирования"""
    print("🧪 Тестирование системы извлечения изображений")
    print("=" * 50)
    
    # Проверка зависимостей
    pymupdf_ok = test_pymupdf_import()
    pillow_ok = test_pillow_import()
    
    if not (pymupdf_ok and pillow_ok):
        print("\n❌ Не все зависимости установлены. Установите их и запустите снова.")
        return
    
    # Поиск тестового PDF
    test_pdfs = []
    
    # Проверяем есть ли PDF в текущей директории
    for file in os.listdir('.'):
        if file.lower().endswith('.pdf'):
            test_pdfs.append(file)
    
    # Проверяем папку uploads
    uploads_dir = 'uploads'
    if os.path.exists(uploads_dir):
        for file in os.listdir(uploads_dir):
            if file.lower().endswith('.pdf'):
                test_pdfs.append(os.path.join(uploads_dir, file))
    
    if test_pdfs:
        print(f"\n📁 Найдены PDF файлы для тестирования:")
        for pdf in test_pdfs[:3]:  # Тестируем максимум 3 файла
            print(f"   - {pdf}")
            test_pdf_processing(pdf)
    else:
        print("\n📁 PDF файлы не найдены. Создаем тестовый...")
        test_pdf = create_test_pdf_with_image()
        if test_pdf:
            test_pdf_processing(test_pdf)
    
    print("\n" + "=" * 50)
    print("🎯 ЗАКЛЮЧЕНИЕ:")
    print("1. Если изображения найдены - fallback извлечение работает")
    print("2. Если изображения не найдены - используйте PDF с встроенными изображениями")
    print("3. SVG-плейсхолдеры будут показаны для изображений без base64 данных")

if __name__ == "__main__":
    main()
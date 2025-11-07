from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from models import db, Dance, DanceType, DanceFormat, SetType
from werkzeug.utils import secure_filename
import os
import psycopg2
import requests
from parsers import DancePageParser
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import and_, or_
from urllib.parse import urljoin
import filetype

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Конфигурация для загрузки файлов
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dance_files')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'doc', 'docx'}
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
app.config['MAX_IMAGE_SIZE'] = (1200, 1200)  # Максимальный размер изображения
app.config['THUMBNAIL_SIZE'] = (300, 300)    # Размер превью

# Конфигурация базы данных
DB_CONFIG = {
    'postgresql': {
        'uri': 'postgresql://postgres:roy@localhost:5432/scddb',
        'schema': 'scddb'
    },
    'sqlite': {
        'uri': f'sqlite:///{os.path.join(os.path.dirname(__file__), "dances.db")}',
        'schema': None
    }
}

#######################################################
# НАСТРОЙКА БАЗЫ ДАННЫХ
#######################################################

def check_postgres_connection():
    """Проверка подключения к PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="scddb",
            user="postgres",
            password="roy"
        )
        cursor = conn.cursor()
        
        # Проверяем существование таблицы в схеме scddb
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'scddb' 
                AND table_name = 'dance'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            cursor.execute("SELECT COUNT(*) FROM scddb.dance;")
            count = cursor.fetchone()[0]
            print(f"✅ Подключение к PostgreSQL успешно! Записей в таблице dance: {count}")
        else:
            print("✅ Подключение к PostgreSQL успешно! Таблица dance будет создана")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return False

def setup_database():
    """Настройка подключения к базе данных"""
    print("🔗 Проверка подключения к PostgreSQL...")
    if check_postgres_connection():
        app.config['SQLALCHEMY_DATABASE_URI'] = DB_CONFIG['postgresql']['uri']
        app.config['DB_SCHEMA'] = DB_CONFIG['postgresql']['schema']
        print("🎯 Используется PostgreSQL")
        return 'postgresql'
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = DB_CONFIG['sqlite']['uri']
        app.config['DB_SCHEMA'] = DB_CONFIG['sqlite']['schema']
        print("🔄 Используется SQLite (запасной вариант)")
        return 'sqlite'

# НАСТРАИВАЕМ БАЗУ ДАННЫХ ПЕРЕД ИНИЦИАЛИЗАЦИЕЙ SQLAlchemy
db_type = setup_database()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализируем базу данных ПОСЛЕ настройки URI
db.init_app(app)

#######################################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ФАЙЛОВ И ПУТЕЙ
#######################################################

def allowed_file(filename):
    """Проверка разрешенных расширений файлов"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def allowed_image_file(filename):
    """Проверка разрешенных расширений для изображений"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_IMAGE_EXTENSIONS']

def get_dance_files_path(dance_id, dance_name):
    """Создает путь к папке с файлами для конкретного танца"""
    safe_name = secure_filename(dance_name)[:50]
    folder_name = f"{dance_id}_{safe_name}"
    return os.path.join(app.config['UPLOAD_FOLDER'], folder_name)

def ensure_dance_folder(dance_id, dance_name):
    """Создает папку для файлов танца если её нет"""
    dance_path = get_dance_files_path(dance_id, dance_name)
    os.makedirs(dance_path, exist_ok=True)
    return dance_path

def ensure_dance_images_folder(dance_id, dance_name):
    """Создает структуру папок для изображений танца"""
    base_path = get_dance_files_path(dance_id, dance_name)
    images_path = os.path.join(base_path, 'images')
    os.makedirs(images_path, exist_ok=True)
    return images_path

def get_dance_files(dance_id, dance_name):
    """Получение списка файлов для танца (кроме изображений)"""
    dance_path = get_dance_files_path(dance_id, dance_name)
    files = []
    
    if os.path.exists(dance_path):
        for item in os.listdir(dance_path):
            item_path = os.path.join(dance_path, item)
            
            # Пропускаем папку images и сами изображения
            if item == 'images' or item.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg')):
                continue
                
            if os.path.isfile(item_path):
                files.append({
                    'name': item,
                    'size': os.path.getsize(item_path),
                    'upload_time': os.path.getctime(item_path)
                })
    
    # Сортируем по времени загрузки (новые сначала)
    files.sort(key=lambda x: x['upload_time'], reverse=True)
    return files

def get_dance_images(dance_id, dance_name):
    """Получение списка изображений для танца"""
    images_folder = os.path.join(get_dance_files_path(dance_id, dance_name), 'images')
    images = []
    
    if os.path.exists(images_folder):
        for filename in os.listdir(images_folder):
            if not filename.startswith('thumb_') and filename.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg')):
                file_path = os.path.join(images_folder, filename)
                thumb_path = os.path.join(images_folder, f"thumb_{filename}")
                
                if os.path.isfile(file_path):
                    images.append({
                        'filename': filename,
                        'thumbnail': f"thumb_{filename}" if os.path.exists(thumb_path) else filename,
                        'size': os.path.getsize(file_path),
                        'upload_time': os.path.getctime(file_path)
                    })
    
    # Сортируем по времени загрузки (новые сначала)
    images.sort(key=lambda x: x['upload_time'], reverse=True)
    return images

def has_dance_files(dance_id, dance_name):
    """Проверяет наличие файлов у танца (исправленная версия)"""
    try:
        # Проверяем основную структуру папок
        dance_path = get_dance_files_path(dance_id, dance_name)
        
        if not os.path.exists(dance_path):
            return False
        
        # Проверяем наличие любых файлов (кроме папки images)
        for item in os.listdir(dance_path):
            item_path = os.path.join(dance_path, item)
            if item != 'images' and os.path.isfile(item_path):
                print(f"✅ Найден файл: {item_path}")
                return True
        
        # Проверяем наличие изображений
        images_path = os.path.join(dance_path, 'images')
        if os.path.exists(images_path):
            for item in os.listdir(images_path):
                item_path = os.path.join(images_path, item)
                if os.path.isfile(item_path):
                    print(f"✅ Найдено изображение: {item_path}")
                    return True
        
        print(f"❌ Файлы не найдены для танца {dance_id} в пути: {dance_path}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при проверке файлов для танца {dance_id}: {e}")
        return False

def safe_int(value, default=None):
    """Безопасное преобразование в integer"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

#######################################################
# УЛУЧШЕННАЯ СИСТЕМА ЗАГРУЗКИ ИЗОБРАЖЕНИЙ
#######################################################

def is_valid_image(image_data):
    """Улучшенная проверка изображения с поддержкой SVG и BOM"""
    if len(image_data) < 4:  # Минимальный размер для проверки
        return False
        
    # Проверяем бинарные форматы изображений
    image_signatures = {
        b'\xff\xd8\xff': 'jpg',      # JPEG
        b'\x89PNG\r\n\x1a\n': 'png', # PNG
        b'GIF8': 'gif',              # GIF
        b'RIFF': 'webp',             # WebP
        b'BM': 'bmp'                 # BMP
    }
    
    for signature, ext in image_signatures.items():
        if image_data.startswith(signature):
            return True
    
    # Проверяем SVG (текстовый XML формат) с учетом BOM
    try:
        # Пробуем декодировать как UTF-8 с BOM
        image_start = image_data[:200].decode('utf-8-sig')  # utf-8-sig автоматически убирает BOM
        image_start_clean = image_start.strip()
        
        # Проверяем различные варианты начала SVG
        if (image_start_clean.startswith('<?xml') or 
            image_start_clean.startswith('<svg') or 
            '<svg' in image_start_clean or
            'svg' in image_start_clean.lower()):
            return True
            
    except UnicodeDecodeError:
        # Если не удалось декодировать как UTF-8, пробуем без BOM
        try:
            image_start = image_data[:200].decode('utf-8', errors='ignore')
            image_start_clean = image_start.strip()
            
            if (image_start_clean.startswith('<?xml') or 
                image_start_clean.startswith('<svg') or 
                '<svg' in image_start_clean):
                return True
        except:
            pass
    
    # Если сигнатура не распознана, пробуем определить по filetype
    try:
        import filetype
        kind = filetype.guess(image_data)
        if kind and (kind.mime.startswith('image/') or kind.extension == 'svg'):
            return True
    except:
        pass
    
    # Дополнительная проверка для SVG по содержимому
    if b'svg' in image_data[:100].lower():
        return True
    
    return False

def _get_image_extension(image_data, original_url=None):
    """Улучшенное определение расширения с поддержкой SVG"""
    # Сначала проверяем бинарные сигнатуры
    image_signatures = {
        b'\xff\xd8\xff': 'jpg',      # JPEG
        b'\x89PNG\r\n\x1a\n': 'png', # PNG
        b'GIF8': 'gif',              # GIF 87a и 89a
        b'RIFF': 'webp',             # WebP
        b'BM': 'bmp'                 # BMP
    }
    
    for signature, ext in image_signatures.items():
        if image_data.startswith(signature):
            return ext
    
    # Проверяем SVG с учетом BOM
    try:
        # Используем utf-8-sig для автоматического удаления BOM
        image_start = image_data[:200].decode('utf-8-sig').strip()
        if (image_start.startswith('<?xml') or 
            image_start.startswith('<svg') or 
            '<svg' in image_start or
            'svg' in image_start.lower()):
            return 'svg'
    except:
        try:
            image_start = image_data[:200].decode('utf-8', errors='ignore').strip()
            if (image_start.startswith('<?xml') or 
                image_start.startswith('<svg') or 
                '<svg' in image_start):
                return 'svg'
        except:
            pass
    
    # Пробуем определить по URL
    if original_url:
        url_lower = original_url.lower()
        if url_lower.endswith('.svg'):
            return 'svg'
        elif url_lower.endswith('.png'):
            return 'png'
        elif url_lower.endswith('.jpg') or url_lower.endswith('.jpeg'):
            return 'jpg'
        elif url_lower.endswith('.gif'):
            return 'gif'
        elif url_lower.endswith('.webp'):
            return 'webp'
    
    # Пробуем определить по filetype
    try:
        import filetype
        kind = filetype.guess(image_data)
        if kind:
            return kind.extension
    except:
        pass
    
    # Дополнительная проверка по содержимому
    if b'svg' in image_data[:100].lower():
        return 'svg'
    
    return 'svg'  # fallback для SVG

def download_and_process_image(image_url, dance_id, dance_name, image_type='diagram'):
    """Улучшенная загрузка изображения с поддержкой SVG и отладкой"""
    try:
        # Создаем папки для изображений
        images_folder = ensure_dance_images_folder(dance_id, dance_name)
        
        # Загружаем изображение
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/svg+xml,image/*,*/*'
        }
        response = requests.get(image_url, timeout=30, headers=headers)
        response.raise_for_status()
        
        image_data = response.content
        
        print(f"🔍 Получено данных: {len(image_data)} байт")
        print(f"🔍 Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"🔍 Первые 100 байт: {image_data[:100]}")
        
        # Проверяем что это валидное изображение (включая SVG)
        if not is_valid_image(image_data):
            print(f"❌ Невалидное изображение: {image_url}")
            print(f"   Первые 50 байт: {image_data[:50]}")
            
            # Попробуем сохранить как SVG в любом случае, если URL указывает на SVG
            if '.svg' in image_url.lower():
                print("⚠️  Пробуем сохранить как SVG по расширению URL...")
                file_extension = 'svg'
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{image_type}_{timestamp}.{file_extension}"
                
                main_path = os.path.join(images_folder, filename)
                with open(main_path, 'wb') as f:
                    f.write(image_data)
                
                print(f"✅ SVG сохранен принудительно: {filename}")
                
                return {
                    'filename': filename,
                    'thumbnail': None,
                    'original_url': image_url,
                    'type': image_type,
                    'size': len(image_data),
                    'upload_time': datetime.now(),
                    'extension': file_extension
                }
            return None
        
        # Генерируем имя файла
        file_extension = _get_image_extension(image_data, image_url)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{image_type}_{timestamp}.{file_extension}"
        
        # Сохраняем оригинальное изображение
        main_path = os.path.join(images_folder, filename)
        with open(main_path, 'wb') as f:
            f.write(image_data)
        
        print(f"✅ Изображение сохранено ({file_extension}): {filename}")
        
        return {
            'filename': filename,
            'thumbnail': None,  # Превью не создаем для SVG
            'original_url': image_url,
            'type': image_type,
            'size': len(image_data),
            'upload_time': datetime.now(),
            'extension': file_extension
        }
        
    except Exception as e:
        print(f"❌ Ошибка загрузки изображения {image_url}: {e}")
        import traceback
        traceback.print_exc()
        return None

def debug_svg_validation(image_url):
    """Функция для отладки валидации SVG"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/svg+xml,image/*,*/*'
        }
        response = requests.get(image_url, timeout=10, headers=headers)
        response.raise_for_status()
        
        image_data = response.content
        
        print("=" * 50)
        print("🔍 ДЕБАГ SVG ВАЛИДАЦИИ")
        print("=" * 50)
        print(f"URL: {image_url}")
        print(f"Размер: {len(image_data)} байт")
        print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"Первые 200 байт: {image_data[:200]}")
        print(f"Декодировано (utf-8-sig): {image_data[:200].decode('utf-8-sig')}")
        print(f"Декодировано (utf-8): {image_data[:200].decode('utf-8', errors='ignore')}")
        print(f"Содержит 'svg': {'svg' in image_data[:200].decode('utf-8', errors='ignore').lower()}")
        print(f"Содержит 'xml': {'xml' in image_data[:200].decode('utf-8', errors='ignore').lower()}")
        print(f"is_valid_image: {is_valid_image(image_data)}")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Ошибка отладки: {e}")

def process_uploaded_image(image_data, dance_id, dance_name, image_type, original_filename):
    """Обработка загруженного изображения"""
    try:
        # Создаем папки для изображений
        images_folder = ensure_dance_images_folder(dance_id, dance_name)
        
        # Проверяем что это валидное изображение
        if not is_valid_image(image_data):
            return None
        
        # Генерируем имя файла
        file_extension = original_filename.rsplit('.', 1)[-1].lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{image_type}_{timestamp}.{file_extension}"
        
        # Сохраняем основное изображение
        main_path = os.path.join(images_folder, filename)
        with open(main_path, 'wb') as f:
            f.write(image_data)
        
        return {
            'filename': filename,
            'thumbnail': None,
            'type': image_type,
            'size': len(image_data),
            'upload_time': datetime.now()
        }
        
    except Exception as e:
        print(f"❌ Ошибка обработки изображения: {e}")
        return None

def download_dance_images(dance_data, dance_id, dance_name):
    """Загрузка всех изображений для танца с улучшенной классификацией"""
    downloaded_files = []
    
    if not dance_data.get('images'):
        print("ℹ️  Изображения не найдены в данных танца")
        return downloaded_files
    
    print(f"🖼️  Начинаем загрузку {len(dance_data['images'])} изображений...")
    
    for i, image_info in enumerate(dance_data['images']):
        image_url = image_info['url']
        alt_text = image_info.get('alt', '')
        image_type = image_info.get('type', 'diagram')  # Используем тип из парсера
        
        print(f"📥 Загрузка {i+1}/{len(dance_data['images'])}: {image_url}")
        
        # Если это SVG, запускаем отладку
        if '.svg' in image_url.lower():
            print("🔍 Запуск отладки SVG...")
            debug_svg_validation(image_url)
        
        # Загружаем и обрабатываем изображение
        result = download_and_process_image(image_url, dance_id, dance_name, image_type)
        if result:
            result['alt'] = alt_text
            downloaded_files.append(result)
            print(f"✅ Успешно загружено: {result['filename']}")
        else:
            print(f"❌ Не удалось загрузить: {image_url}")
    
    print(f"📊 Итого загружено: {len(downloaded_files)}/{len(dance_data['images'])} изображений")
    return downloaded_files

def update_dance_note_with_images(dance, downloaded_files):
    """Обновление заметки танца с информацией о загруженных изображениях"""
    try:
        image_section = f"\n\n📷 ЗАГРУЖЕННЫЕ ИЗОБРАЖЕНИЯ ({len(downloaded_files)}):"
        
        # Группируем изображения по типам
        images_by_type = {}
        for img in downloaded_files:
            img_type = img.get('type', 'other')
            if img_type not in images_by_type:
                images_by_type[img_type] = []
            images_by_type[img_type].append(img)
        
        # Добавляем информацию по типам
        for img_type, images in images_by_type.items():
            type_display = {
                'diagram': '📐 Диаграммы',
                'music': '🎵 Ноты',
                'author': '👤 Авторы',
                'formation': '🔷 Формации',
                'other': '📷 Изображения'
            }.get(img_type, '📷 Изображения')
            
            image_section += f"\n\n{type_display}:"
            for img in images:
                alt_text = img.get('alt', '')
                if alt_text:
                    image_section += f"\n• {img['filename']} ({alt_text})"
                else:
                    image_section += f"\n• {img['filename']}"
        
        # Обновляем заметку
        if dance.note:
            # Убираем старую секцию изображений если есть
            lines = dance.note.split('\n')
            clean_lines = []
            in_image_section = False
            
            for line in lines:
                if line.strip().startswith('📷 ЗАГРУЖЕННЫЕ ИЗОБРАЖЕНИЯ'):
                    in_image_section = True
                    continue
                if in_image_section and line.strip() and not line.strip().startswith('•') and not line.strip().startswith('📐') and not line.strip().startswith('🎵') and not line.strip().startswith('👤'):
                    in_image_section = False
                if not in_image_section:
                    clean_lines.append(line)
            
            dance.note = '\n'.join(clean_lines).rstrip()
            dance.note += image_section
        else:
            dance.note = "Импортирован автоматически." + image_section
        
        db.session.commit()
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении заметки с изображениями: {e}")
        # Не прерываем выполнение из-за ошибки в заметке

def update_dance_note_with_single_image(dance, image_info):
    """Обновление заметки танца с информацией об одном загруженном изображении"""
    try:
        image_entry = f"\n• {image_info['filename']} ({image_info['type']}"
        if image_info.get('alt'):
            image_entry += f": {image_info['alt']}"
        image_entry += ")"
        
        if dance.note:
            # Проверяем, есть ли уже секция изображений
            if '📷 ЗАГРУЖЕННЫЕ ИЗОБРАЖЕНИЯ' in dance.note:
                # Добавляем к существующей секции
                dance.note += image_entry
            else:
                # Создаем новую секцию
                dance.note += f"\n\n📷 ЗАГРУЖЕННЫЕ ИЗОБРАЖЕНИЯ:{image_entry}"
        else:
            dance.note = f"📷 ЗАГРУЖЕННЫЕ ИЗОБРАЖЕНИЯ:{image_entry}"
        
        db.session.commit()
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении заметки с изображением: {e}")

def remove_image_from_note(dance, filename):
    """Удаление информации об изображении из заметки танца"""
    try:
        if dance.note and '📷 ЗАГРУЖЕННЫЕ ИЗОБРАЖЕНИЯ' in dance.note:
            lines = dance.note.split('\n')
            new_lines = []
            skip_next_empty = False
            
            for line in lines:
                if f"{filename}" in line and ('•' in line or '📷' in line):
                    skip_next_empty = True
                    continue
                if skip_next_empty and line.strip() == '':
                    skip_next_empty = False
                    continue
                new_lines.append(line)
            
            dance.note = '\n'.join(new_lines).rstrip()
            db.session.commit()
            
    except Exception as e:
        print(f"❌ Ошибка при удалении изображения из заметки: {e}")

#######################################################
# КОНТЕКСТНЫЕ ПРОЦЕССОРЫ
#######################################################

@app.context_processor
def utility_processor():
    def format_datetime(timestamp, fmt='%d.%m.%Y %H:%M'):
        """Форматирование timestamp"""
        return datetime.fromtimestamp(timestamp).strftime(fmt)
    
    def has_images(dance_id, dance_name):
        """Проверка наличия изображений у танца"""
        images = get_dance_images(dance_id, dance_name)
        return len(images) > 0
    
    def has_dance_files_in_fs(dance_name):
        """Проверяет наличие файлов в файловой системе для танца"""
        try:
            dance_name_clean = dance_name.replace(' ', '_').replace('/', '_')
            dance_files_path = os.path.join('dance_files', dance_name_clean, 'images')
            
            if os.path.exists(dance_files_path):
                files = [f for f in os.listdir(dance_files_path) 
                        if os.path.isfile(os.path.join(dance_files_path, f))]
                return len(files) > 0
            return False
        except:
            return False
    
    return {
        'get_dance_files': get_dance_files,
        'get_dance_images': get_dance_images,
        'has_images': has_images,
        'format_datetime': format_datetime,
        'db_type': db_type,
        'has_dance_files_in_fs': has_dance_files_in_fs,
        'has_dance_files': has_dance_files  # Добавлена новая функция
    }

#######################################################
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
#######################################################

def check_existing_tables():
    """Проверка существования таблиц в схеме scddb"""
    try:
        with db.engine.connect() as conn:
            # Проверяем существование таблиц в схеме scddb
            result = conn.execute(db.text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'scddb'
            """))
            existing_tables = [row[0] for row in result]
            print(f"📋 Существующие таблицы в схеме scddb: {existing_tables}")
            return existing_tables
    except Exception as e:
        print(f"❌ Ошибка при проверке таблиц: {e}")
        return []

def init_database():
    """Инициализация базы данных с базовыми данными"""
    try:
        with app.app_context():
            if db_type == 'postgresql':
                print("🔧 Инициализация PostgreSQL...")
                try:
                    # Создаем схему если не существует
                    with db.engine.connect() as conn:
                        conn.execute(db.text('CREATE SCHEMA IF NOT EXISTS scddb'))
                        conn.commit()
                    print("✅ Схема scddb создана/проверена")
                    
                    # Устанавливаем схему по умолчанию для этой сессии
                    with db.engine.connect() as conn:
                        conn.execute(db.text('SET search_path TO scddb'))
                        conn.commit()
                        
                except Exception as e:
                    print(f"ℹ️ Информация о схеме: {e}")
            
            # Создаем только таблицы справочников, основную таблицу dance не трогаем
            print("🔄 Создание таблиц справочников...")
            db.create_all()
            print("✅ SQLAlchemy метаданные обновлены")
            
            # Добавляем базовые данные только в справочники
            init_basic_data()
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        import traceback
        traceback.print_exc()

def init_basic_data():
    """Инициализация базовых данных только для справочников"""
    try:
        # Проверяем существующие таблицы
        existing_tables = check_existing_tables()
        
        # Базовые типы сетов
        if 'set_type' in existing_tables:
            basic_set_types = [
                "Longwise set", "Square set", "Triangular set", "Circular set"
            ]
            
            for set_type_name in basic_set_types:
                existing = SetType.query.filter_by(name=set_type_name).first()
                if not existing:
                    set_type = SetType(name=set_type_name)
                    db.session.add(set_type)
                    print(f"✅ Добавлен тип сета: {set_type_name}")
            
            db.session.commit()
        
        # Базовые форматы сетов
        if 'dance_format' in existing_tables:
            dance_formats = [
                '2 couples', '2 trios', '3 couples', '4 couples', '5 couples', '6 couples', '7 couples', 'any', 'other', 'unknown'
            ]
            
            for format_name in dance_formats:
                existing = DanceFormat.query.filter_by(name=format_name).first()
                if not existing:
                    dance_format = DanceFormat(name=format_name)
                    db.session.add(dance_format)
                    print(f"✅ Добавлен формат сета: {format_name}")
            
            db.session.commit()
        
        # Базовые типы танцев
        if 'dance_type' in existing_tables:
            dance_types = [
                ('Reel', 'R'), ('Jig', 'J'), ('Strathspey', 'S'), ('March', 'M'),
                ('Medley', 'D'), ('Polka', 'P'), ('Waltz', 'W'), ('Hornpipe', 'H'),
                ('Quadrille', 'Q'), ('Minuet', 'N')
            ]
            
            for type_name, type_code in dance_types:
                existing = DanceType.query.filter_by(name=type_name).first()
                if not existing:
                    dance_type = DanceType(name=type_name, code=type_code)
                    db.session.add(dance_type)
                    print(f"✅ Добавлен тип танца: {type_name}")
            
            db.session.commit()
        
        print("✅ Базовые типы сетов, форматы и типы танцев проверены/добавлены")
        
        # Статистика - проверяем только справочники
        set_type_count = SetType.query.count()
        dance_format_count = DanceFormat.query.count()
        dance_type_count = DanceType.query.count()
        
        print(f"📊 Записей в таблице set_type: {set_type_count}")
        print(f"📊 Записей в таблице dance_format: {dance_format_count}")
        print(f"📊 Записей в таблице dance_type: {dance_type_count}")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базовых данных: {e}")
        import traceback
        traceback.print_exc()

#######################################################
# ФУНКЦИИ ДЛЯ ФОРМ И ПОИСКА
#######################################################

def get_form_data():
    """Получение данных для форм"""
    return {
        'set_types': SetType.get_all(),
        'dance_formats': DanceFormat.get_all(),
        'dance_types': DanceType.get_all()
    }

def validate_dance_form(form_data):
    """Валидация данных формы танца"""
    errors = []
    
    if not form_data.get('name', '').strip():
        errors.append('Название танца обязательно для заполнения!')
    
    if not safe_int(form_data.get('dance_type')):
        errors.append('Тип танца обязателен для заполнения!')
    
    return errors

def get_search_filters():
    """Получение данных для фильтров поиска"""
    return {
        'dance_types': DanceType.query.order_by(DanceType.id).all(),
        'dance_formats': DanceFormat.query.order_by(DanceFormat.id).all(),
        'set_types': SetType.query.order_by(SetType.id).all(),
        'dance_couples': db.session.query(Dance.dance_couple).distinct().filter(Dance.dance_couple.isnot(None)).order_by(Dance.dance_couple).all()
    }

def build_search_query(filters):
    """Построение запроса поиска с комбинацией условий И/ИЛИ"""
    query = Dance.query
    
    conditions = []
    
    # Поиск по имени (ИЛИ для нескольких слов)
    if filters.get('name'):
        name_terms = [term.strip() for term in filters['name'].split() if term.strip()]
        if name_terms:
            name_conditions = []
            for term in name_terms:
                name_conditions.append(Dance.name.ilike(f'%{term}%'))
            conditions.append(or_(*name_conditions))
    
    # Поиск по автору (ИЛИ для нескольких слов)
    if filters.get('author'):
        author_terms = [term.strip() for term in filters['author'].split() if term.strip()]
        if author_terms:
            author_conditions = []
            for term in author_terms:
                author_conditions.append(Dance.author.ilike(f'%{term}%'))
            conditions.append(or_(*author_conditions))
    
    # Поиск по типу танца (И для нескольких типов)
    if filters.get('dance_types'):
        dance_type_ids = [int(x) for x in filters['dance_types']]
        conditions.append(Dance.dance_type_id.in_(dance_type_ids))
    
    # Поиск по формату сета (И для нескольких форматов)
    if filters.get('dance_formats'):
        format_ids = [int(x) for x in filters['dance_formats']]
        conditions.append(Dance.dance_format_id.in_(format_ids))
    
    # Поиск по типу сета (И для нескольких типов)
    if filters.get('set_types'):
        set_type_ids = [int(x) for x in filters['set_types']]
        conditions.append(Dance.set_type_id.in_(set_type_ids))
    
    # Поиск по танцующим парам (И для нескольких значений)
    if filters.get('dance_couples'):
        couple_values = filters['dance_couples']
        conditions.append(Dance.dance_couple.in_(couple_values))

    # Поиск по описанию (ИЛИ для нескольких слов)
    if filters.get('description'):
        description_terms = [term.strip() for term in filters['description'].split() if term.strip()]
        if description_terms:
            description_conditions = []
            for term in description_terms:
                description_conditions.append(Dance.description.ilike(f'%{term}%'))
            conditions.append(or_(*description_conditions))

    # Поиск по публикации (ИЛИ для нескольких слов)
    if filters.get('published'):
        published_terms = [term.strip() for term in filters['published'].split() if term.strip()]
        if published_terms:
            published_conditions = []
            for term in published_terms:
                published_conditions.append(Dance.published.ilike(f'%{term}%'))
            conditions.append(or_(*published_conditions))
    
    # Поиск по повторам
    if filters.get('count_min'):
        try:
            conditions.append(Dance.count_id >= int(filters['count_min']))
        except (ValueError, TypeError):
            pass
    
    if filters.get('count_max'):
        try:
            conditions.append(Dance.count_id <= int(filters['count_max']))
        except (ValueError, TypeError):
            pass
    
    # Поиск по размеру (тактам)
    if filters.get('size_min'):
        try:
            conditions.append(Dance.size_id >= int(filters['size_min']))
        except (ValueError, TypeError):
            pass
    
    if filters.get('size_max'):
        try:
            conditions.append(Dance.size_id <= int(filters['size_max']))
        except (ValueError, TypeError):
            pass
    
    # ДОБАВЛЕНО: Поиск по наличию описания
    if filters.get('has_description') == 'on':
        conditions.append(Dance.description.isnot(None))
        conditions.append(Dance.description != '')
    
    # ДОБАВЛЕНО: Поиск по наличию файлов (исправленная версия)
    if filters.get('has_files') == 'on':
        print("🔍 Поиск по наличию файлов активирован")
        dances_with_files = []
        all_dances = Dance.query.all()
        print(f"📊 Всего танцев в базе: {len(all_dances)}")
        
        for dance in all_dances:
            has_files = has_dance_files(dance.id, dance.name)
            if has_files:
                dances_with_files.append(dance.id)
                print(f"✅ Танец {dance.id} '{dance.name}' имеет файлы")
        
        print(f"📁 Найдено танцев с файлами: {len(dances_with_files)}")
        
        if dances_with_files:
            conditions.append(Dance.id.in_(dances_with_files))
        else:
            # Если нет танцев с файлами, возвращаем пустой результат
            conditions.append(Dance.id.in_([]))
    
    # Применяем все условия через И
    if conditions:
        query = query.filter(and_(*conditions))
    
    return query

#######################################################
# ОСНОВНЫЕ МАРШРУТЫ ПРИЛОЖЕНИЯ
#######################################################

@app.route('/')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        search = request.args.get('search', '')
        
        # Ограничиваем возможные значения per_page
        if per_page not in [25, 50, 100]:
            per_page = 25
        
        query = Dance.query
        
        if search:
            query = query.filter(
                Dance.name.ilike(f'%{search}%') | 
                Dance.author.ilike(f'%{search}%')
            )
        
        dances = query.order_by(Dance.name).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return render_template('index.html', dances=dances, search=search, per_page=per_page)
        
    except Exception as e:
        print(f"❌ Ошибка в index: {e}")
        # Создаем безопасный объект пагинации для пустого результата
        class EmptyPagination:
            def __init__(self):
                self.items = []
                self.page = 1
                self.per_page = per_page
                self.total = 0
                self.pages = 0
                self.has_prev = False
                self.has_next = False
                self.prev_num = None
                self.next_num = None
                
            def iter_pages(self, *args, **kwargs):
                return []
        
        empty_pagination = EmptyPagination()
        return render_template('index.html', 
                             dances=empty_pagination, 
                             search=search or '', 
                             per_page=per_page)

@app.route('/add', methods=['GET', 'POST'])
def add_dance():
    if request.method == 'POST':
        try:
            errors = validate_dance_form(request.form)
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('add_dance.html', **get_form_data())
            
            # Создаем танец
            dance = Dance(
                name=request.form.get('name', '').strip(),
                author=request.form.get('author', '').strip(),
                dance_type_id=safe_int(request.form.get('dance_type')),
                size_id=safe_int(request.form.get('size_id')),
                count_id=safe_int(request.form.get('count_id')),
                dance_format_id=safe_int(request.form.get('dance_format')),
                dance_couple=request.form.get('dance_couple', '').strip(),
                set_type_id=safe_int(request.form.get('set_type')),
                description=request.form.get('description', '').strip(),
                published=request.form.get('published', '').strip(),
                note=request.form.get('note', '').strip()
            )
            
            db.session.add(dance)
            db.session.commit()
            flash('Танец успешно добавлен!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении танца: {str(e)}', 'danger')
    
    return render_template('add_dance.html', **get_form_data())

@app.route('/dance/<int:dance_id>/edit', methods=['GET', 'POST'])
def edit_dance(dance_id):
    dance = Dance.get_by_id(dance_id)
    
    if request.method == 'POST':
        try:
            errors = validate_dance_form(request.form)
            if errors:
                for error in errors:
                    flash(error, 'danger')
                return render_template('edit_dance.html', dance=dance, **get_form_data())
            
            # Обновляем танец
            dance.name = request.form.get('name', '').strip()
            dance.author = request.form.get('author', '').strip()
            dance.dance_type_id = safe_int(request.form.get('dance_type'))
            dance.size_id = safe_int(request.form.get('size_id'))
            dance.count_id = safe_int(request.form.get('count_id'))
            dance.dance_format_id = safe_int(request.form.get('dance_format'))
            dance.dance_couple = request.form.get('dance_couple', '').strip()
            dance.set_type_id = safe_int(request.form.get('set_type'))
            dance.description = request.form.get('description', '').strip()
            dance.published = request.form.get('published', '').strip()
            dance.note = request.form.get('note', '').strip()
            
            db.session.commit()
            flash('Танец успешно обновлен!', 'success')
            return redirect(url_for('view_dance', dance_id=dance.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении танца: {str(e)}', 'danger')
    
    return render_template('edit_dance.html', dance=dance, **get_form_data())

@app.route('/dance/<int:dance_id>/delete', methods=['POST'])
def delete_dance(dance_id):
    try:
        dance = Dance.get_by_id(dance_id)
        
        # Удаляем связанные файлы
        dance_path = get_dance_files_path(dance_id, dance.name)
        if os.path.exists(dance_path):
            import shutil
            shutil.rmtree(dance_path)
        
        db.session.delete(dance)
        db.session.commit()
        flash('Танец успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении танца: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/dance/<int:dance_id>')
def view_dance(dance_id):
    try:
        dance = Dance.get_by_id(dance_id)
        files = get_dance_files(dance_id, dance.name)
        images = get_dance_images(dance_id, dance.name)
        return render_template('view_dance.html', dance=dance, files=files, images=images)
    except Exception as e:
        flash(f'Ошибка загрузки танца: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/delete-dances', methods=['POST'])
def delete_dances():
    """Массовое удаление танцев"""
    try:
        dance_ids = request.form.getlist('dance_ids')
        if not dance_ids:
            flash('Не выбраны танцы для удаления', 'danger')
            return redirect(url_for('index'))
        
        deleted_count = 0
        for dance_id in dance_ids:
            dance = Dance.query.get(dance_id)
            if dance:
                # Удаляем связанные файлы
                dance_path = get_dance_files_path(dance.id, dance.name)
                if os.path.exists(dance_path):
                    import shutil
                    shutil.rmtree(dance_path)
                
                db.session.delete(dance)
                deleted_count += 1
        
        db.session.commit()
        flash(f'Успешно удалено {deleted_count} танцев', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при массовом удалении: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/dance/<int:dance_id>/delete-single', methods=['POST'])
def delete_single_dance(dance_id):
    """Удаление одного танца (для JS вызова)"""
    try:
        dance = Dance.get_by_id(dance_id)
        dance_name = dance.name
        
        # Удаляем связанные файлы
        dance_path = get_dance_files_path(dance_id, dance_name)
        if os.path.exists(dance_path):
            import shutil
            shutil.rmtree(dance_path)
        
        db.session.delete(dance)
        db.session.commit()
        flash(f'Танец "{dance_name}" успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении танца: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

#######################################################
# МАРШРУТЫ ДЛЯ РАБОТЫ С ФАЙЛАМИ
#######################################################

@app.route('/dance/<int:dance_id>/files')
def dance_files(dance_id):
    """Страница управления файлами танца"""
    dance = Dance.query.get_or_404(dance_id)
    files = get_dance_files(dance_id, dance.name)
    return render_template('dance_files.html', dance=dance, files=files)

@app.route('/dance/<int:dance_id>/upload', methods=['POST'])
def upload_dance_file(dance_id):
    dance = Dance.get_by_id(dance_id)
    
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('dance_files', dance_id=dance_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('dance_files', dance_id=dance_id))
    
    if file and allowed_file(file.filename):
        dance_path = ensure_dance_folder(dance_id, dance.name)
        filename = secure_filename(file.filename)
        file_path = os.path.join(dance_path, filename)
        file.save(file_path)
        flash(f'Файл "{filename}" успешно загружен', 'success')
    else:
        flash('Недопустимый тип файла', 'danger')
    
    return redirect(url_for('dance_files', dance_id=dance_id))

@app.route('/dance/<int:dance_id>/files/<filename>')
def download_dance_file(dance_id, filename):
    dance = Dance.get_by_id(dance_id)
    dance_path = get_dance_files_path(dance_id, dance.name)
    return send_from_directory(dance_path, filename)

@app.route('/dance/<int:dance_id>/files/<filename>/delete', methods=['POST'])
def delete_dance_file(dance_id, filename):
    dance = Dance.get_by_id(dance_id)
    dance_path = get_dance_files_path(dance_id, dance.name)
    file_path = os.path.join(dance_path, filename)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        flash(f'Файл "{filename}" удален', 'success')
    else:
        flash('Файл не найден', 'danger')
    
    return redirect(url_for('dance_files', dance_id=dance_id))

#######################################################
# МАРШРУТЫ ДЛЯ РАБОТЫ С ИЗОБРАЖЕНИЯМИ
#######################################################

@app.route('/dance/<int:dance_id>/images')
def dance_images(dance_id):
    """Страница управления изображениями танца"""
    dance = Dance.get_by_id(dance_id)
    images = get_dance_images(dance_id, dance.name)
    return render_template('dance_images.html', dance=dance, images=images)

@app.route('/dance/<int:dance_id>/upload-image', methods=['POST'])
def upload_dance_image(dance_id):
    """Загрузка изображения для танца"""
    dance = Dance.get_by_id(dance_id)
    
    if 'image' not in request.files:
        flash('Изображение не выбрано', 'danger')
        return redirect(url_for('dance_images', dance_id=dance_id))
    
    file = request.files['image']
    if file.filename == '':
        flash('Изображение не выбрано', 'danger')
        return redirect(url_for('dance_images', dance_id=dance_id))
    
    if file and allowed_image_file(file.filename):
        try:
            # Читаем данные файла
            image_data = file.read()
            
            # Определяем тип изображения из формы
            image_type = request.form.get('image_type', 'diagram')
            alt_text = request.form.get('alt_text', '').strip()
            
            # Обрабатываем и сохраняем изображение
            result = process_uploaded_image(image_data, dance_id, dance.name, image_type, file.filename)
            
            if result:
                # Добавляем alt текст к результату
                result['alt'] = alt_text
                
                # Обновляем заметку танца
                update_dance_note_with_single_image(dance, result)
                
                flash(f'Изображение "{result["filename"]}" успешно загружено!', 'success')
            else:
                flash('Ошибка при обработке изображения', 'danger')
                
        except Exception as e:
            flash(f'Ошибка при загрузке изображения: {str(e)}', 'danger')
    else:
        flash('Недопустимый формат изображения', 'danger')
    
    return redirect(url_for('dance_images', dance_id=dance_id))

@app.route('/dance/<int:dance_id>/image/<filename>')
def serve_dance_image(dance_id, filename):
    """Отдача изображения танца"""
    dance = Dance.get_by_id(dance_id)
    images_folder = os.path.join(get_dance_files_path(dance_id, dance.name), 'images')
    return send_from_directory(images_folder, filename)

@app.route('/dance/<int:dance_id>/image/<filename>/delete', methods=['POST'])
def delete_dance_image(dance_id, filename):
    """Удаление изображения танца"""
    dance = Dance.get_by_id(dance_id)
    images_folder = os.path.join(get_dance_files_path(dance_id, dance.name), 'images')
    
    try:
        # Удаляем основное изображение
        main_path = os.path.join(images_folder, filename)
        if os.path.exists(main_path):
            os.remove(main_path)
        
        # Удаляем превью если существует
        thumb_path = os.path.join(images_folder, f"thumb_{filename}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        # Обновляем заметку танца
        remove_image_from_note(dance, filename)
        
        flash(f'Изображение "{filename}" удалено', 'success')
        
    except Exception as e:
        flash(f'Ошибка при удалении изображения: {str(e)}', 'danger')
    
    return redirect(url_for('dance_images', dance_id=dance_id))

@app.route('/dance/<int:dance_id>/set-primary-image/<filename>', methods=['POST'])
def set_primary_image(dance_id, filename):
    """Установка изображения как основного (для отображения в карточке танца)"""
    dance = Dance.get_by_id(dance_id)
    
    # Здесь можно добавить логику для хранения информации о главном изображении
    # Например, в отдельном поле модели Dance или в заметке
    
    flash(f'Изображение "{filename}" установлено как основное', 'success')
    return redirect(url_for('dance_images', dance_id=dance_id))

#######################################################
# НОВЫЙ МАРШРУТ ДЛЯ ОТДАЧИ ФАЙЛОВ ИЗ DANCE_FILES
#######################################################

@app.route('/dance_files/<int:dance_id>/<path:filename>')
def serve_dance_file(dance_id, filename):
    """Отдача файлов из папки dance_files"""
    try:
        dance = Dance.get_by_id(dance_id)
        dance_folder = get_dance_files_path(dance_id, dance.name)
        
        # Проверяем существование файла
        file_path = os.path.join(dance_folder, filename)
        if not os.path.exists(file_path):
            flash('Файл не найден', 'danger')
            return redirect(url_for('view_dance', dance_id=dance_id))
        
        return send_from_directory(dance_folder, filename)
        
    except Exception as e:
        flash(f'Ошибка при загрузке файла: {str(e)}', 'danger')
        return redirect(url_for('view_dance', dance_id=dance_id))

#######################################################
# МАРШРУТЫ ДЛЯ ПОИСКА
#######################################################

@app.route('/search', methods=['GET', 'POST'])
def advanced_search():
    """Расширенный поиск танцев"""
    filters = {}
    results = []
    total_count = 0
    
    if request.method == 'POST':
        try:
            # Собираем фильтры из формы
            filters = {
                'name': request.form.get('name', '').strip(),
                'author': request.form.get('author', '').strip(),
                'description': request.form.get('description', '').strip(),
                'dance_types': request.form.getlist('dance_types'),
                'dance_formats': request.form.getlist('dance_formats'),
                'set_types': request.form.getlist('set_types'),
                'dance_couples': request.form.getlist('dance_couples'),
                'published': request.form.get('published', '').strip(),
                'count_min': request.form.get('count_min', '').strip(),
                'count_max': request.form.get('count_max', '').strip(),
                'size_min': request.form.get('size_min', '').strip(),
                'size_max': request.form.get('size_max', '').strip(),
                'has_description': request.form.get('has_description'),
                'has_files': request.form.get('has_files')
            }
            
            # Строим запрос
            query = build_search_query(filters)
            
            # Выполняем поиск
            results = query.order_by(Dance.name).all()
            
            total_count = len(results)
            
            if total_count == 0:
                flash('По вашему запросу ничего не найдено', 'info')
            else:
                flash(f'Найдено танцев: {total_count}', 'success')
                
        except Exception as e:
            flash(f'Ошибка при выполнении поиска: {str(e)}', 'danger')
    
    # Получаем данные для фильтров
    search_data = get_search_filters()
    search_data.update({
        'filters': filters,
        'results': results,
        'total_count': total_count
    })
    
    return render_template('search.html', **search_data)

@app.route('/search/results')
def search_results():
    """Быстрый поиск (для использования из других страниц)"""
    query = request.args.get('q', '')
    if query:
        results = Dance.query.filter(
            or_(
                Dance.name.ilike(f'%{query}%'),
                Dance.author.ilike(f'%{query}%'),
                Dance.published.ilike(f'%{query}%')
            )
        ).order_by(Dance.name).all()
        
        return render_template('search_results.html', 
                             results=results, 
                             query=query, 
                             total_count=len(results))
    
    return redirect(url_for('advanced_search'))

#######################################################
# ОБНОВЛЕННЫЙ ИМПОРТ ТАНЦЕВ С ИЗОБРАЖЕНИЯМИ
#######################################################

@app.route('/import/dance', methods=['GET', 'POST'])
def import_dance():
    """Импорт танца из HTML страницы с улучшенной загрузкой изображений"""
    if request.method == 'POST':
        try:
            # Получаем HTML контент
            html_content = request.form.get('html_content')
            url = request.form.get('url')
            download_images = request.form.get('download_images') == 'on'
            image_quality = request.form.get('image_quality', 'high')  # high/medium/low
            
            if url:
                # Загружаем HTML по URL
                response = requests.get(url)
                response.raise_for_status()
                html_content = response.text
            
            if not html_content:
                flash('Необходимо предоставить HTML контент или URL', 'danger')
                return render_template('import_dance.html')
            
            # Настраиваем качество изображений
            if image_quality == 'low':
                app.config['MAX_IMAGE_SIZE'] = (800, 800)
                app.config['THUMBNAIL_SIZE'] = (200, 200)
            elif image_quality == 'medium':
                app.config['MAX_IMAGE_SIZE'] = (1200, 1200)
                app.config['THUMBNAIL_SIZE'] = (300, 300)
            else:  # high
                app.config['MAX_IMAGE_SIZE'] = (1600, 1600)
                app.config['THUMBNAIL_SIZE'] = (400, 400)
            
            # Парсим данные
            parser = DancePageParser(html_content)
            dance_data = parser.parse_dance_data()
            
            # Сохраняем в базу
            dance = save_dance_to_db(dance_data)
            
            # Загружаем изображения если выбрана опция
            if download_images and dance_data.get('images'):
                image_count = len(dance_data['images'])
                flash(f'Найдено {image_count} изображений для загрузки...', 'info')
                
                downloaded_files = download_dance_images(dance_data, dance.id, dance.name)
                
                if downloaded_files:
                    # Обновляем заметку танца с информацией о загруженных изображениях
                    update_dance_note_with_images(dance, downloaded_files)
                    flash(f'Загружено {len(downloaded_files)} изображений для танца!', 'success')
                else:
                    flash('Не удалось загрузить изображения', 'warning')
            
            flash(f'Танец "{dance.name}" успешно импортирован!', 'success')
            return redirect(url_for('view_dance', dance_id=dance.id))
            
        except requests.RequestException as e:
            flash(f'Ошибка при загрузке страницы: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Ошибка при импорте танца: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()
    
    return render_template('import_dance.html')

#######################################################
# ФУНКЦИЯ СОХРАНЕНИЯ ТАНЦА ПРИ ИМПОРТЕ
#######################################################

def save_dance_to_db(dance_data):
    """Сохранение данных танца в базу с красивым форматированием"""
    try:
        # Инициализируем переменные
        dance_type_id = None
        dance_format_id = None
        set_type_id = None
        
        # Получаем или создаем тип танца
        if dance_data['dance_type'] and dance_data['dance_type'] != 'Unknown':
            dance_type = DanceType.query.filter_by(name=dance_data['dance_type']).first()
            if not dance_type:
                dance_type = DanceType(
                    name=dance_data['dance_type'], 
                    code=dance_data['dance_type'][0] if dance_data['dance_type'] else 'U'
                )
                db.session.add(dance_type)
                db.session.commit()
            dance_type_id = dance_type.id
        
        # Получаем формат сета
        if dance_data['couples_count']:
            format_name = f"{dance_data['couples_count']} couples"
            dance_format = DanceFormat.query.filter_by(name=format_name).first()
            if not dance_format:
                dance_format = DanceFormat(name=format_name)
                db.session.add(dance_format)
                db.session.commit()
            dance_format_id = dance_format.id
        
        # Получаем тип сета
        if dance_data['formation']:
            set_type = SetType.query.filter_by(name=dance_data['formation']).first()
            if not set_type:
                set_type = SetType(name=dance_data['formation'])
                db.session.add(set_type)
                db.session.commit()
            set_type_id = set_type.id
        
        # Формируем заметку с красивым форматированием
        note_lines = []
        
        # Заголовок
        note_lines.append("=" * 50)
        note_lines.append("ИНФОРМАЦИЯ О ТАНЦЕ")
        note_lines.append("=" * 50)
        note_lines.append("")
        
        # Основные характеристики
        note_lines.append("🎭 ОСНОВНЫЕ ХАРАКТЕРИСТИКИ")
        note_lines.append("-" * 30)
        if dance_data['meter']:
            note_lines.append(f"• Метр: {dance_data['meter']}")
        if dance_data['bars']:
            note_lines.append(f"• Такты: {dance_data['bars']}")
        if dance_data['progression']:
            note_lines.append(f"• Прогрессия: {dance_data['progression']}")
        if dance_data['repetitions']:
            note_lines.append(f"• Повторения: {dance_data['repetitions']}")
        if dance_data['intensity']:
            note_lines.append(f"• Интенсивность: {dance_data['intensity']}")
        if dance_data['couples_count']:
            note_lines.append(f"• Количество пар: {dance_data['couples_count']}")
        if dance_data['formation']:
            note_lines.append(f"• Формирование: {dance_data['formation']}")
        note_lines.append("")
        
        # Шаги
        if dance_data['steps']:
            note_lines.append("👣 ШАГИ")
            note_lines.append("-" * 30)
            note_lines.append("• " + ", ".join(dance_data['steps']))
            note_lines.append("")
        
        # Формации
        if dance_data['formations_list']:
            note_lines.append("🔷 ФОРМАЦИИ")
            note_lines.append("-" * 30)
            for formation in dance_data['formations_list']:
                note_lines.append(f"• {formation}")
            note_lines.append("")
        
        # Музыка
        if dance_data['recommended_music']:
            note_lines.append("🎵 МУЗЫКА")
            note_lines.append("-" * 30)
            for music in dance_data['recommended_music']:
                note_lines.append(f"• {music}")
            note_lines.append("")
        
        # Публикации
        if dance_data['published_in']:
            note_lines.append("📚 ПУБЛИКАЦИИ")
            note_lines.append("-" * 30)
            for publication in dance_data['published_in']:
                note_lines.append(f"• {publication}")
            note_lines.append("")
        
        # Фигуры
        if dance_data['figures']:
            note_lines.append("💃 ФИГУРЫ ПО ТАКТАМ")
            note_lines.append("-" * 30)
            for figure in dance_data['figures']:
                note_lines.append(f"🎯 {figure['bars']}:")
                # Разбиваем длинное описание на несколько строк если нужно
                description = figure['description']
                if len(description) > 80:
                    # Простой перенос строки для длинного текста
                    words = description.split()
                    lines = []
                    current_line = []
                    for word in words:
                        if len(' '.join(current_line + [word])) <= 80:
                            current_line.append(word)
                        else:
                            lines.append(' '.join(current_line))
                            current_line = [word]
                    if current_line:
                        lines.append(' '.join(current_line))
                    for i, line in enumerate(lines):
                        if i == 0:
                            note_lines.append(f"   {line}")
                        else:
                            note_lines.append(f"   {line}")
                else:
                    note_lines.append(f"   {description}")
                note_lines.append("")
        
        # Дополнительная информация
        if dance_data['extra_info'] and dance_data['extra_info'] != 'Отсутствует':
            note_lines.append("📋 ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ")
            note_lines.append("-" * 30)
            # Разбиваем длинный текст на строки
            extra_lines = dance_data['extra_info'].split('\n')
            for line in extra_lines:
                if line.strip():
                    note_lines.append(f"• {line.strip()}")
            note_lines.append("")
        
        note_lines.append("=" * 50)
        note_lines.append("Конец информации")
        note_lines.append("=" * 50)
        
        # Объединяем все строки
        note = "\n".join(note_lines)
        
        # Создаем танец с правильными значениями для count_id и size_id
        dance = Dance(
            name=dance_data['name'] or 'Неизвестный танец',
            author=dance_data['author'],
            dance_type_id=dance_type_id,
            dance_format_id=dance_format_id,
            set_type_id=set_type_id,
            dance_couple=str(dance_data['couples_count']) if dance_data['couples_count'] else None,
            count_id=dance_data['repetitions'],  # Сохраняем количество повторений
            size_id=dance_data['bars_count'],    # Сохраняем количество тактов
            description=dance_data['description'],
            published=', '.join(dance_data['published_in']) if dance_data['published_in'] else None,
            note=note
        )
        
        db.session.add(dance)
        db.session.commit()
        
        return dance
        
    except Exception as e:
        db.session.rollback()
        raise e

#######################################################
# МАРШРУТЫ ДЛЯ УПРАВЛЕНИЯ СПРАВОЧНИКАМИ
#######################################################

# Маршруты для SetType
@app.route('/set-types')
def manage_set_types():
    """Страница управления типами сетов"""
    set_types = SetType.get_all()
    return render_template('set_types.html', set_types=set_types)

@app.route('/set-types/add', methods=['GET', 'POST'])
def add_set_type():
    """Добавление нового типа сета"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа сета обязательно!', 'danger')
                return render_template('add_set_type.html')
            
            # Проверяем уникальность
            existing = SetType.query.filter_by(name=name).first()
            if existing:
                flash('Тип сета с таким названием уже существует!', 'danger')
                return render_template('add_set_type.html')
            
            set_type = SetType(name=name, description=description)
            db.session.add(set_type)
            db.session.commit()
            
            flash(f'Тип сета "{name}" успешно добавлен!', 'success')
            return redirect(url_for('manage_set_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении типа сета: {str(e)}', 'danger')
    
    return render_template('add_set_type.html')

@app.route('/set-types/<int:set_type_id>/edit', methods=['GET', 'POST'])
def edit_set_type(set_type_id):
    """Редактирование типа сета"""
    set_type = SetType.get_by_id(set_type_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа сета обязательно!', 'danger')
                return render_template('edit_set_type.html', set_type=set_type)
            
            # Проверяем уникальность (исключая текущую запись)
            existing = SetType.query.filter(SetType.name == name, SetType.id != set_type_id).first()
            if existing:
                flash('Тип сета с таким названием уже существует!', 'danger')
                return render_template('edit_set_type.html', set_type=set_type)
            
            set_type.name = name
            set_type.description = description
            db.session.commit()
            
            flash(f'Тип сета "{name}" успешно обновлен!', 'success')
            return redirect(url_for('manage_set_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении типа сета: {str(e)}', 'danger')
    
    return render_template('edit_set_type.html', set_type=set_type)

@app.route('/set-types/<int:set_type_id>/delete', methods=['POST'])
def delete_set_type(set_type_id):
    """Удаление типа сета"""
    try:
        set_type = SetType.get_by_id(set_type_id)
        
        # Проверяем, используется ли тип сета в танцах
        dance_count = Dance.query.filter_by(set_type_id=set_type_id).count()
        if dance_count > 0:
            flash(f'Нельзя удалить тип сета "{set_type.name}" - он используется в {dance_count} танцах!', 'danger')
            return redirect(url_for('manage_set_types'))
        
        db.session.delete(set_type)
        db.session.commit()
        
        flash(f'Тип сета "{set_type.name}" успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении типа сета: {str(e)}', 'danger')
    
    return redirect(url_for('manage_set_types'))

# Маршруты для DanceFormat
@app.route('/dance-formats')
def manage_dance_formats():
    """Страница управления форматами сетов"""
    dance_formats = DanceFormat.get_all()
    return render_template('dance_formats.html', dance_formats=dance_formats)

@app.route('/dance-formats/add', methods=['GET', 'POST'])
def add_dance_format():
    """Добавление нового формата сета"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название формата сета обязательно!', 'danger')
                return render_template('add_dance_format.html')
            
            # Проверяем уникальность
            existing = DanceFormat.query.filter_by(name=name).first()
            if existing:
                flash('Формат сета с таким названием уже существует!', 'danger')
                return render_template('add_dance_format.html')
            
            dance_format = DanceFormat(name=name, description=description)
            db.session.add(dance_format)
            db.session.commit()
            
            flash(f'Формат сета "{name}" успешно добавлен!', 'success')
            return redirect(url_for('manage_dance_formats'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении формата сета: {str(e)}', 'danger')
    
    return render_template('add_dance_format.html')

@app.route('/dance-formats/<int:format_id>/edit', methods=['GET', 'POST'])
def edit_dance_format(format_id):
    """Редактирование формата сета"""
    dance_format = DanceFormat.get_by_id(format_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название формата сета обязательно!', 'danger')
                return render_template('edit_dance_format.html', dance_format=dance_format)
            
            # Проверяем уникальность (исключая текущую запись)
            existing = DanceFormat.query.filter(DanceFormat.name == name, DanceFormat.id != format_id).first()
            if existing:
                flash('Формат сета с таким названием уже существует!', 'danger')
                return render_template('edit_dance_format.html', dance_format=dance_format)
            
            dance_format.name = name
            dance_format.description = description
            db.session.commit()
            
            flash(f'Формат сета "{name}" успешно обновлен!', 'success')
            return redirect(url_for('manage_dance_formats'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении формата сета: {str(e)}', 'danger')
    
    return render_template('edit_dance_format.html', dance_format=dance_format)

@app.route('/dance-formats/<int:format_id>/delete', methods=['POST'])
def delete_dance_format(format_id):
    """Удаление формата сета"""
    try:
        dance_format = DanceFormat.get_by_id(format_id)
        
        # Проверяем, используется ли формат сета в танцах
        dance_count = Dance.query.filter_by(dance_format_id=format_id).count()
        if dance_count > 0:
            flash(f'Нельзя удалить формат сета "{dance_format.name}" - он используется в {dance_count} танцах!', 'danger')
            return redirect(url_for('manage_dance_formats'))
        
        db.session.delete(dance_format)
        db.session.commit()
        
        flash(f'Формат сета "{dance_format.name}" успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении формата сета: {str(e)}', 'danger')
    
    return redirect(url_for('manage_dance_formats'))

# Маршруты для DanceType
@app.route('/dance-types')
def manage_dance_types():
    """Страница управления типами танцев"""
    dance_types = DanceType.get_all()
    return render_template('dance_types.html', dance_types=dance_types)

@app.route('/dance-types/add', methods=['GET', 'POST'])
def add_dance_type():
    """Добавление нового типа танца"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа танца обязательно!', 'danger')
                return render_template('add_dance_type.html')
            
            if not code:
                flash('Код типа танца обязателен!', 'danger')
                return render_template('add_dance_type.html')
            
            # Проверяем уникальность
            existing_name = DanceType.query.filter_by(name=name).first()
            if existing_name:
                flash('Тип танца с таким названием уже существует!', 'danger')
                return render_template('add_dance_type.html')
            
            existing_code = DanceType.query.filter_by(code=code).first()
            if existing_code:
                flash('Тип танца с таким кодом уже существует!', 'danger')
                return render_template('add_dance_type.html')
            
            dance_type = DanceType(name=name, code=code, description=description)
            db.session.add(dance_type)
            db.session.commit()
            
            flash(f'Тип танца "{name}" успешно добавлен!', 'success')
            return redirect(url_for('manage_dance_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении типа танца: {str(e)}', 'danger')
    
    return render_template('add_dance_type.html')

@app.route('/dance-types/<int:type_id>/edit', methods=['GET', 'POST'])
def edit_dance_type(type_id):
    """Редактирование типа танца"""
    dance_type = DanceType.get_by_id(type_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа танца обязательно!', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            if not code:
                flash('Код типа танца обязателен!', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            # Проверяем уникальность (исключая текущую запись)
            existing_name = DanceType.query.filter(DanceType.name == name, DanceType.id != type_id).first()
            if existing_name:
                flash('Тип танца с таким названием уже существует!', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            existing_code = DanceType.query.filter(DanceType.code == code, DanceType.id != type_id).first()
            if existing_code:
                flash('Тип танца с таким кодом уже существует!', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            dance_type.name = name
            dance_type.code = code
            dance_type.description = description
            db.session.commit()
            
            flash(f'Тип танца "{name}" успешно обновлен!', 'success')
            return redirect(url_for('manage_dance_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении типа танца: {str(e)}', 'danger')
    
    return render_template('edit_dance_type.html', dance_type=dance_type)

@app.route('/dance-types/<int:type_id>/delete', methods=['POST'])
def delete_dance_type(type_id):
    """Удаление типа танца"""
    try:
        dance_type = DanceType.get_by_id(type_id)
        
        # Проверяем, используется ли тип танца в танцах
        dance_count = Dance.query.filter_by(dance_type_id=type_id).count()
        if dance_count > 0:
            flash(f'Нельзя удалить тип танца "{dance_type.name}" - он используется в {dance_count} танцах!', 'danger')
            return redirect(url_for('manage_dance_types'))
        
        db.session.delete(dance_type)
        db.session.commit()
        
        flash(f'Тип танца "{dance_type.name}" успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении типа танца: {str(e)}', 'danger')
    
    return redirect(url_for('manage_dance_types'))

#######################################################
# СТАТИСТИКА
#######################################################

@app.route('/stats')
def stats():
    """Статистика базы данных"""
    try:
        total_dances = Dance.query.count()
        total_set_types = SetType.query.count()
        total_dance_formats = DanceFormat.query.count()
        total_dance_types = DanceType.query.count()
        
        # Статистика по типам танцев
        dance_type_stats = db.session.query(
            DanceType.name, 
            db.func.count(Dance.id)
        ).outerjoin(Dance, Dance.dance_type_id == DanceType.id).group_by(DanceType.id, DanceType.name).all()
        
        # Статистика по типам сетов
        set_type_stats = db.session.query(
            SetType.name, 
            db.func.count(Dance.id)
        ).outerjoin(Dance, Dance.set_type_id == SetType.id).group_by(SetType.id, SetType.name).all()
        
        # Статистика по форматам сетов
        dance_format_stats = db.session.query(
            DanceFormat.name, 
            db.func.count(Dance.id)
        ).outerjoin(Dance, Dance.dance_format_id == DanceFormat.id).group_by(DanceFormat.id, DanceFormat.name).all()
        
        return render_template('stats.html',
                            total_dances=total_dances,
                            total_set_types=total_set_types,
                            total_dance_formats=total_dance_formats,
                            total_dance_types=total_dance_types,
                            dance_type_stats=dance_type_stats,
                            set_type_stats=set_type_stats,
                            dance_format_stats=dance_format_stats)
        
    except Exception as e:
        print(f"❌ Ошибка при получении статистики: {e}")
        return render_template('stats.html',
                            total_dances=0,
                            total_set_types=0,
                            total_dance_formats=0,
                            total_dance_types=0,
                            dance_type_stats=[],
                            set_type_stats=[],
                            dance_format_stats=[])

#######################################################
# ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ
#######################################################

@contextmanager
def db_session():
    """Контекстный менеджер для работы с сессией БД"""
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

# Инициализация приложения
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

if __name__ == '__main__':
    print("🚀 Запуск приложения...")
    print(f"📁 Папка для файлов: {app.config['UPLOAD_FOLDER']}")
    print(f"🗄️  Тип базы данных: {db_type}")
    
    # Инициализация базы данных
    init_database()
    
    print("🌐 Приложение запущено по адресу: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
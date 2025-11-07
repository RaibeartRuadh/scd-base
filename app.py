from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
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
import pandas as pd
import chardet
import json
from bs4 import BeautifulSoup
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Конфигурация для загрузки файлов
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dance_files')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'doc', 'docx'}
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
app.config['MAX_IMAGE_SIZE'] = (1200, 1200)  # Максимальный размер изображения
app.config['THUMBNAIL_SIZE'] = (300, 300)    # Размер превью

# Конфигурация для массового импорта
app.config['BATCH_IMPORT_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'batch_imports')
app.config['ALLOWED_BATCH_EXTENSIONS'] = {'csv', 'xlsx', 'xls'}

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
# ФУНКЦИИ ДЛЯ ИЗВЛЕЧЕНИЯ ДАННЫХ С #EXTRAINFO
#######################################################

def get_extrainfo_data(dance_id):
    """
    Извлекает данные с вкладки #extrainfo для указанного танца
    
    Args:
        dance_id (int): ID танца на сайте my.strathspey.org
    
    Returns:
        str: Текст с вкладки #extrainfo или пустая строка при ошибке
    """
    url = f"https://my.strathspey.org/dd/dance/{dance_id}/#extrainfo"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Находим раздел extrainfo
        extrainfo_section = soup.find('div', id='extrainfo')
        
        if not extrainfo_section:
            return ""
        
        # Извлекаем текст из раздела, очищаем от лишних пробелов
        extrainfo_text = extrainfo_section.get_text(separator='\n', strip=True)
        
        return extrainfo_text
        
    except requests.RequestException as e:
        print(f"❌ Ошибка при получении данных для dance_id {dance_id}: {e}")
        return ""
    except Exception as e:
        print(f"❌ Неожиданная ошибка для dance_id {dance_id}: {e}")
        return ""

def parse_dance_with_extrainfo(dance_id):
    """
    Парсит основные данные танца и добавляет данные с #extrainfo в поле note
    
    Args:
        dance_id (int): ID танца на источнике
    
    Returns:
        dict: Данные танца с extrainfo в поле note
    """
    try:
        # Загружаем основную страницу танца
        url = f'https://my.strathspey.org/dd/dance/{dance_id}/'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()
        
        # Парсим основные данные
        parser = DancePageParser(response.text)
        dance_data = parser.parse_dance_data()
        
        if not dance_data:
            return None
        
        # Получаем данные с #extrainfo
        extrainfo_data = get_extrainfo_data(dance_id)
        
        # Сохраняем только данные из #extrainfo в поле note
        if extrainfo_data:
            dance_data['note'] = f"Данные с вкладки #extrainfo:\n\n{extrainfo_data}"
        else:
            dance_data['note'] = "Данные с вкладки #extrainfo не найдены"
        
        # Добавляем URL источника
        dance_data['source_url'] = url
        
        return dance_data
        
    except Exception as e:
        print(f"❌ Ошибка парсинга танца {dance_id}: {e}")
        return None

#######################################################
# МАССОВЫЙ ИМПОРТ С #EXTRAINFO
#######################################################

@app.route('/batch_import', methods=['GET', 'POST'])
def batch_import():
    """Массовый импорт танцев с my.strathspey.org по диапазону ID с данными из #extrainfo"""
    if request.method == 'POST':
        try:
            start_id = int(request.form.get('start_id', 1))
            end_id = int(request.form.get('end_id', 100))
            delay = float(request.form.get('delay', 1.0))
            download_images = request.form.get('download_images') == 'on'
            skip_existing = request.form.get('skip_existing') == 'on'
            
            if start_id > end_id:
                flash('Начальный ID не может быть больше конечного', 'danger')
                return redirect(request.url)
            
            if end_id - start_id > 1000:
                flash('Диапазон слишком большой. Максимум 1000 танцев за один импорт.', 'warning')
                return redirect(request.url)
            
            results = {
                'total': 0,
                'successful': 0,
                'skipped': 0,
                'errors': 0,
                'details': []
            }
            
            # Импорт по диапазону ID
            for dance_id in range(start_id, end_id + 1):
                try:
                    # Создаем новую сессию для каждого танца чтобы избежать проблем с транзакциями
                    from sqlalchemy import create_engine
                    from sqlalchemy.orm import sessionmaker
                    
                    # Проверяем существование танца если включена опция пропуска
                    if skip_existing:
                        existing_dance = Dance.query.filter_by(
                            source_url=f"https://my.strathspey.org/dd/dance/{dance_id}/"
                        ).first()
                        if existing_dance:
                            results['skipped'] += 1
                            results['details'].append({
                                'id': dance_id,
                                'status': 'Пропущен',
                                'message': 'Танец уже существует в базе',
                                'url': f'https://my.strathspey.org/dd/dance/{dance_id}/'
                            })
                            continue
                    
                    # Парсим данные танца с #extrainfo
                    print(f"🔄 Обрабатывается ID {dance_id}")
                    dance_data = parse_dance_with_extrainfo(dance_id)
                    
                    if not dance_data:
                        results['errors'] += 1
                        results['details'].append({
                            'id': dance_id,
                            'status': 'Ошибка',
                            'message': 'Не удалось получить данные танца',
                            'url': f'https://my.strathspey.org/dd/dance/{dance_id}/'
                        })
                        continue
                    
                    if not dance_data.get('name'):
                        results['errors'] += 1
                        results['details'].append({
                            'id': dance_id,
                            'status': 'Ошибка',
                            'message': 'Танец не имеет названия',
                            'url': f'https://my.strathspey.org/dd/dance/{dance_id}/'
                        })
                        continue
                    
                    # Сохраняем в базу в отдельной транзакции
                    try:
                        dance = save_dance_to_db(dance_data)
                        
                        # Загружаем изображения если выбрана опция
                        downloaded_files = []
                        if download_images and dance_data.get('images'):
                            downloaded_files = download_dance_images(dance_data, dance.id, dance.name)
                            if downloaded_files:
                                update_dance_note_with_images(dance, downloaded_files)
                        
                        results['successful'] += 1
                        results['details'].append({
                            'id': dance_id,
                            'status': 'Успешно',
                            'message': f"Танец '{dance.name}' импортирован",
                            'url': dance_data['source_url'],
                            'images_count': len(downloaded_files),
                            'extrainfo_length': len(dance_data.get('note', ''))
                        })
                        
                        print(f"✅ Успешно импортирован ID {dance_id}: {dance.name}")
                        
                    except Exception as e:
                        # Откатываем транзакцию для этого танца
                        db.session.rollback()
                        results['errors'] += 1
                        results['details'].append({
                            'id': dance_id,
                            'status': 'Ошибка БД',
                            'message': f'Ошибка сохранения: {str(e)}',
                            'url': f'https://my.strathspey.org/dd/dance/{dance_id}/'
                        })
                        print(f"❌ Ошибка БД для ID {dance_id}: {e}")
                    
                except requests.RequestException as e:
                    results['errors'] += 1
                    results['details'].append({
                        'id': dance_id,
                        'status': 'Ошибка сети',
                        'message': f'Ошибка сети: {str(e)}',
                        'url': f'https://my.strathspey.org/dd/dance/{dance_id}/'
                    })
                    print(f"❌ Ошибка сети для ID {dance_id}: {e}")
                    
                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({
                        'id': dance_id,
                        'status': 'Ошибка импорта',
                        'message': f'Ошибка импорта: {str(e)}',
                        'url': f'https://my.strathspey.org/dd/dance/{dance_id}/'
                    })
                    print(f"❌ Ошибка импорта для ID {dance_id}: {e}")
                
                finally:
                    results['total'] += 1
                    
                    # Задержка между запросами
                    if delay > 0 and dance_id < end_id:
                        time.sleep(delay)
            
            # Показываем результаты
            flash(f'Массовый импорт завершен. Успешно: {results["successful"]}, Пропущено: {results["skipped"]}, Ошибки: {results["errors"]}', 
                  'success' if results['errors'] == 0 else 'warning')
            
            return render_template('batch_import.html', results=results)
            
        except Exception as e:
            flash(f'Ошибка при запуске массового импорта: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()
    
    return render_template('batch_import.html')

#######################################################
# ОДИНОЧНЫЙ ИМПОРТ С #EXTRAINFO
#######################################################

@app.route('/import/dance', methods=['GET', 'POST'])
def import_dance():
    """Импорт одного танца с данными из #extrainfo"""
    if request.method == 'POST':
        try:
            # Получаем HTML контент или URL
            html_content = request.form.get('html_content')
            url = request.form.get('url')
            download_images = request.form.get('download_images') == 'on'
            
            dance_id = None
            
            if url:
                # Извлекаем ID танца из URL
                try:
                    dance_id = int(url.strip('/').split('/')[-1])
                except (ValueError, IndexError):
                    flash('Неверный URL. Убедитесь, что URL содержит ID танца.', 'danger')
                    return render_template('import_dance.html')
                
                # Парсим данные с #extrainfo
                dance_data = parse_dance_with_extrainfo(dance_id)
            elif html_content:
                # Парсим из HTML контента
                parser = DancePageParser(html_content)
                dance_data = parser.parse_dance_data()
                
                if dance_data:
                    # Пытаемся получить ID из данных или устанавливаем заглушку
                    dance_id = dance_data.get('source_id', 0)
                    # Для HTML контента получаем #extrainfo отдельно если известен ID
                    if dance_id and dance_id > 0:
                        extrainfo_data = get_extrainfo_data(dance_id)
                        if extrainfo_data:
                            dance_data['note'] = f"Данные с вкладки #extrainfo:\n\n{extrainfo_data}"
            else:
                flash('Необходимо предоставить HTML контент или URL', 'danger')
                return render_template('import_dance.html')
            
            if not dance_data:
                flash('Не удалось распарсить данные танца', 'danger')
                return render_template('import_dance.html')
            
            # Сохраняем в базу
            dance = save_dance_to_db(dance_data)
            
            # Загружаем изображения если выбрана опция
            if download_images and dance_data.get('images'):
                downloaded_files = download_dance_images(dance_data, dance.id, dance.name)
                
                if downloaded_files:
                    update_dance_note_with_images(dance, downloaded_files)
                    flash(f'Загружено {len(downloaded_files)} изображений для танца!', 'success')
                else:
                    flash('Не удалось загрузить изображения', 'warning')
            
            flash(f'Танец "{dance.name}" успешно импортирован с данными из #extrainfo!', 'success')
            return redirect(url_for('view_dance', dance_id=dance.id))
            
        except Exception as e:
            flash(f'Ошибка при импорте танца: {str(e)}', 'danger')
            import traceback
            traceback.print_exc()
    
    return render_template('import_dance.html')

#######################################################
# ФУНКЦИЯ СОХРАНЕНИЯ ТАНЦА С #EXTRAINFO
#######################################################

def save_dance_to_db(dance_data):
    """Сохранение данных танца в базу с данными из #extrainfo в поле note"""
    try:
        # Инициализируем переменные
        dance_type_id = None
        dance_format_id = None
        set_type_id = None
        
        # Получаем или создаем тип танца
        if dance_data.get('dance_type') and dance_data['dance_type'] != 'Unknown':
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
        if dance_data.get('couples_count'):
            format_name = f"{dance_data['couples_count']} couples"
            dance_format = DanceFormat.query.filter_by(name=format_name).first()
            if not dance_format:
                dance_format = DanceFormat(name=format_name)
                db.session.add(dance_format)
                db.session.commit()
            dance_format_id = dance_format.id
        
        # Получаем тип сета
        if dance_data.get('formation'):
            set_type = SetType.query.filter_by(name=dance_data['formation']).first()
            if not set_type:
                set_type = SetType(name=dance_data['formation'])
                db.session.add(set_type)
                db.session.commit()
            set_type_id = set_type.id
        
        # Используем данные из #extrainfo для поля note
        note = dance_data.get('note', '')
        
        # Создаем танец
        dance = Dance(
            name=dance_data.get('name', 'Неизвестный танец'),
            author=dance_data.get('author'),
            dance_type_id=dance_type_id,
            dance_format_id=dance_format_id,
            set_type_id=set_type_id,
            dance_couple=str(dance_data.get('couples_count')) if dance_data.get('couples_count') else None,
            count_id=dance_data.get('repetitions'),
            size_id=dance_data.get('bars_count'),
            description=dance_data.get('description'),
            published=', '.join(dance_data.get('published_in', [])) if dance_data.get('published_in') else None,
            note=note,
            source_url=dance_data.get('source_url', '')  # Используем значение по умолчанию
        )
        
        db.session.add(dance)
        db.session.commit()
        
        return dance
        
    except Exception as e:
        db.session.rollback()
        raise e

#######################################################
# РАСШИРЕННЫЙ ПОИСК (ЕДИНЫЙ МАРШРУТ)
#######################################################

@app.route('/search', methods=['GET', 'POST'])
def search():
    """Расширенный поиск танцев с фильтрами - использует search.html"""
    # Инициализируем переменные по умолчанию
    filters = {
        'name': '',
        'author': '',
        'description': '',
        'published': '',
        'size_min': '',
        'size_max': '',
        'count_min': '',
        'count_max': '',
        'dance_types': [],
        'dance_formats': [],
        'set_types': [],
        'dance_couples': [],
        'has_description': '',
        'has_files': ''
    }
    
    if request.method == 'POST':
        try:
            # Собираем фильтры из формы
            filters = {
                'name': request.form.get('name', '').strip(),
                'author': request.form.get('author', '').strip(),
                'description': request.form.get('description', '').strip(),
                'published': request.form.get('published', '').strip(),
                'size_min': request.form.get('size_min', '').strip(),
                'size_max': request.form.get('size_max', '').strip(),
                'count_min': request.form.get('count_min', '').strip(),
                'count_max': request.form.get('count_max', '').strip(),
                'dance_types': request.form.getlist('dance_types'),
                'dance_formats': request.form.getlist('dance_formats'),
                'set_types': request.form.getlist('set_types'),
                'dance_couples': request.form.getlist('dance_couples'),
                'has_description': request.form.get('has_description'),
                'has_files': request.form.get('has_files')
            }
            
            # Строим запрос
            query = Dance.query
            
            # Применяем текстовые фильтры
            if filters['name']:
                query = query.filter(Dance.name.ilike(f'%{filters["name"]}%'))
            
            if filters['author']:
                query = query.filter(Dance.author.ilike(f'%{filters["author"]}%'))
            
            if filters['description']:
                query = query.filter(Dance.description.ilike(f'%{filters["description"]}%'))
            
            if filters['published']:
                query = query.filter(Dance.published.ilike(f'%{filters["published"]}%'))
            
            # Применяем числовые фильтры
            if filters['size_min']:
                query = query.filter(Dance.size_id >= int(filters['size_min']))
            
            if filters['size_max']:
                query = query.filter(Dance.size_id <= int(filters['size_max']))
            
            if filters['count_min']:
                query = query.filter(Dance.count_id >= int(filters['count_min']))
            
            if filters['count_max']:
                query = query.filter(Dance.count_id <= int(filters['count_max']))
            
            # Применяем фильтры по категориям
            if filters['dance_types']:
                query = query.filter(Dance.dance_type_id.in_([int(x) for x in filters['dance_types']]))
            
            if filters['dance_formats']:
                query = query.filter(Dance.dance_format_id.in_([int(x) for x in filters['dance_formats']]))
            
            if filters['set_types']:
                query = query.filter(Dance.set_type_id.in_([int(x) for x in filters['set_types']]))
            
            if filters['dance_couples']:
                query = query.filter(Dance.dance_couple.in_(filters['dance_couples']))
            
            # Фильтр по наличию описания
            if filters.get('has_description') == 'on':
                query = query.filter(
                    Dance.description.isnot(None), 
                    Dance.description != ''
                )
            
            # Фильтр по наличию файлов
            if filters.get('has_files') == 'on':
                dances_with_files = []
                all_dances = Dance.query.all()
                for dance in all_dances:
                    if has_dance_files(dance.id, dance.name):
                        dances_with_files.append(dance.id)
                if dances_with_files:
                    query = query.filter(Dance.id.in_(dances_with_files))
                else:
                    query = query.filter(Dance.id.in_([]))  # Пустой результат
            
            results = query.order_by(Dance.name).all()
            total_count = len(results)
            
            search_filters = get_search_filters()
            return render_template('search.html', 
                                 results=results, 
                                 filters=filters,
                                 total_count=total_count,
                                 **search_filters)
            
        except Exception as e:
            flash(f'Ошибка при выполнении поиска: {str(e)}', 'danger')
            search_filters = get_search_filters()
            return render_template('search.html', filters=filters, **search_filters)
    
    # GET запрос - показать пустую форму поиска
    search_filters = get_search_filters()
    return render_template('search.html', filters=filters, **search_filters)

@app.route('/advanced_search')
def advanced_search():
    """Перенаправление на страницу поиска (для совместимости с base.html)"""
    return redirect(url_for('search'))

def get_search_filters():
    """Получение данных для фильтров поиска"""
    # Получаем уникальные значения для танцующих пар
    dance_couples = db.session.query(Dance.dance_couple).distinct().all()
    dance_couples = [c[0] for c in dance_couples if c[0] is not None]
    dance_couples.sort()
    
    return {
        'dance_types': DanceType.query.order_by(DanceType.name).all(),
        'dance_formats': DanceFormat.query.order_by(DanceFormat.name).all(),
        'set_types': SetType.query.order_by(SetType.name).all(),
        'dance_couples': [(c, c) for c in dance_couples]  # Преобразуем в формат для шаблона
    }

#######################################################
# СТАТИСТИКА
#######################################################

@app.route('/stats')
def stats():
    """Статистика базы данных"""
    try:
        # Основная статистика
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
        
        # Статистика по наличию файлов
        dances_with_files = 0
        dances_with_images = 0
        for dance in Dance.query.all():
            if has_dance_files(dance.id, dance.name):
                dances_with_files += 1
            if has_images(dance.id, dance.name):
                dances_with_images += 1
        
        return render_template('stats.html',
                            total_dances=total_dances,
                            total_set_types=total_set_types,
                            total_dance_formats=total_dance_formats,
                            total_dance_types=total_dance_types,
                            dances_with_files=dances_with_files,
                            dances_with_images=dances_with_images,
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
                            dances_with_files=0,
                            dances_with_images=0,
                            dance_type_stats=[],
                            set_type_stats=[],
                            dance_format_stats=[])

#######################################################
# УПРАВЛЕНИЕ СПРАВОЧНИКАМИ
#######################################################

@app.route('/manage/dance-types')
def manage_dance_types():
    """Управление типами танцев"""
    dance_types = DanceType.query.order_by(DanceType.name).all()
    return render_template('dance_types.html', dance_types=dance_types)

@app.route('/manage/dance-types/add', methods=['GET', 'POST'])
def add_dance_type():
    """Добавление типа танца"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа танца обязательно', 'danger')
                return render_template('add_dance_type.html')
            
            if not code:
                flash('Код типа танца обязателен', 'danger')
                return render_template('add_dance_type.html')
            
            # Проверяем уникальность
            existing = DanceType.query.filter_by(name=name).first()
            if existing:
                flash('Тип танца с таким названием уже существует', 'danger')
                return render_template('add_dance_type.html')
            
            dance_type = DanceType(name=name, code=code, description=description)
            db.session.add(dance_type)
            db.session.commit()
            
            flash(f'Тип танца "{name}" успешно добавлен', 'success')
            return redirect(url_for('manage_dance_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении типа танца: {str(e)}', 'danger')
    
    return render_template('add_dance_type.html')

@app.route('/manage/dance-types/<int:type_id>/edit', methods=['GET', 'POST'])
def edit_dance_type(type_id):
    """Редактирование типа танца"""
    dance_type = DanceType.query.get_or_404(type_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа танца обязательно', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            if not code:
                flash('Код типа танца обязателен', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            # Проверяем уникальность (исключая текущую запись)
            existing = DanceType.query.filter(DanceType.name == name, DanceType.id != type_id).first()
            if existing:
                flash('Тип танца с таким названием уже существует', 'danger')
                return render_template('edit_dance_type.html', dance_type=dance_type)
            
            dance_type.name = name
            dance_type.code = code
            dance_type.description = description
            db.session.commit()
            
            flash(f'Тип танца "{name}" успешно обновлен', 'success')
            return redirect(url_for('manage_dance_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении типа танца: {str(e)}', 'danger')
    
    return render_template('edit_dance_type.html', dance_type=dance_type)

@app.route('/manage/dance-types/<int:type_id>/delete', methods=['POST'])
def delete_dance_type(type_id):
    """Удаление типа танца"""
    try:
        dance_type = DanceType.query.get_or_404(type_id)
        
        # Проверяем использование типа танца
        dance_count = Dance.query.filter_by(dance_type_id=type_id).count()
        if dance_count > 0:
            flash(f'Нельзя удалить тип танца "{dance_type.name}" - он используется в {dance_count} танцах', 'danger')
            return redirect(url_for('manage_dance_types'))
        
        db.session.delete(dance_type)
        db.session.commit()
        
        flash(f'Тип танца "{dance_type.name}" успешно удален', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении типа танца: {str(e)}', 'danger')
    
    return redirect(url_for('manage_dance_types'))

@app.route('/manage/dance-formats')
def manage_dance_formats():
    """Управление форматами танцев"""
    dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
    return render_template('dance_formats.html', dance_formats=dance_formats)

@app.route('/manage/dance-formats/add', methods=['GET', 'POST'])
def add_dance_format():
    """Добавление формата танца"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название формата обязательно', 'danger')
                return render_template('add_dance_format.html')
            
            # Проверяем уникальность
            existing = DanceFormat.query.filter_by(name=name).first()
            if existing:
                flash('Формат с таким названием уже существует', 'danger')
                return render_template('add_dance_format.html')
            
            dance_format = DanceFormat(name=name, description=description)
            db.session.add(dance_format)
            db.session.commit()
            
            flash(f'Формат "{name}" успешно добавлен', 'success')
            return redirect(url_for('manage_dance_formats'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении формата: {str(e)}', 'danger')
    
    return render_template('add_dance_format.html')

@app.route('/manage/dance-formats/<int:format_id>/edit', methods=['GET', 'POST'])
def edit_dance_format(format_id):
    """Редактирование формата танца"""
    dance_format = DanceFormat.query.get_or_404(format_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название формата обязательно', 'danger')
                return render_template('edit_dance_format.html', dance_format=dance_format)
            
            # Проверяем уникальность (исключая текущую запись)
            existing = DanceFormat.query.filter(DanceFormat.name == name, DanceFormat.id != format_id).first()
            if existing:
                flash('Формат с таким названием уже существует', 'danger')
                return render_template('edit_dance_format.html', dance_format=dance_format)
            
            dance_format.name = name
            dance_format.description = description
            db.session.commit()
            
            flash(f'Формат "{name}" успешно обновлен', 'success')
            return redirect(url_for('manage_dance_formats'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении формата: {str(e)}', 'danger')
    
    return render_template('edit_dance_format.html', dance_format=dance_format)

@app.route('/manage/dance-formats/<int:format_id>/delete', methods=['POST'])
def delete_dance_format(format_id):
    """Удаление формата танца"""
    try:
        dance_format = DanceFormat.query.get_or_404(format_id)
        
        # Проверяем использование формата
        dance_count = Dance.query.filter_by(dance_format_id=format_id).count()
        if dance_count > 0:
            flash(f'Нельзя удалить формат "{dance_format.name}" - он используется в {dance_count} танцах', 'danger')
            return redirect(url_for('manage_dance_formats'))
        
        db.session.delete(dance_format)
        db.session.commit()
        
        flash(f'Формат "{dance_format.name}" успешно удален', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении формата: {str(e)}', 'danger')
    
    return redirect(url_for('manage_dance_formats'))

@app.route('/manage/set-types')
def manage_set_types():
    """Управление типами сетов"""
    set_types = SetType.query.order_by(SetType.name).all()
    return render_template('set_types.html', set_types=set_types)


@app.route('/manage/set-types/add', methods=['GET', 'POST'])
def add_set_type():
    """Добавление типа сета"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа сета обязательно', 'danger')
                return render_template('add_set_type.html')
            
            # Проверяем уникальность
            existing = SetType.query.filter_by(name=name).first()
            if existing:
                flash('Тип сета с таким названием уже существует', 'danger')
                return render_template('add_set_type.html')
            
            set_type = SetType(name=name, description=description)
            db.session.add(set_type)
            db.session.commit()
            
            flash(f'Тип сета "{name}" успешно добавлен', 'success')
            return redirect(url_for('manage_set_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении типа сета: {str(e)}', 'danger')
    
    return render_template('add_set_type.html')

@app.route('/manage/set-types/<int:type_id>/edit', methods=['GET', 'POST'])
def edit_set_type(type_id):
    """Редактирование типа сета"""
    set_type = SetType.query.get_or_404(type_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            if not name:
                flash('Название типа сета обязательно', 'danger')
                return render_template('edit_set_type.html', set_type=set_type)
            
            # Проверяем уникальность (исключая текущую запись)
            existing = SetType.query.filter(SetType.name == name, SetType.id != type_id).first()
            if existing:
                flash('Тип сета с таким названием уже существует', 'danger')
                return render_template('edit_set_type.html', set_type=set_type)
            
            set_type.name = name
            set_type.description = description
            db.session.commit()
            
            flash(f'Тип сета "{name}" успешно обновлен', 'success')
            return redirect(url_for('manage_set_types'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении типа сета: {str(e)}', 'danger')
    
    return render_template('edit_set_type.html', set_type=set_type)

@app.route('/manage/set-types/<int:type_id>/delete', methods=['POST'])
def delete_set_type(type_id):
    """Удаление типа сета"""
    try:
        set_type = SetType.query.get_or_404(type_id)
        
        # Проверяем использование типа сета
        dance_count = Dance.query.filter_by(set_type_id=type_id).count()
        if dance_count > 0:
            flash(f'Нельзя удалить тип сета "{set_type.name}" - он используется в {dance_count} танцах', 'danger')
            return redirect(url_for('manage_set_types'))
        
        db.session.delete(set_type)
        db.session.commit()
        
        flash(f'Тип сета "{set_type.name}" успешно удален', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении типа сета: {str(e)}', 'danger')
    
    return redirect(url_for('manage_set_types'))

#######################################################
# УПРАВЛЕНИЕ ФАЙЛАМИ ТАНЦЕВ
#######################################################

@app.route('/dance/<int:dance_id>/files')
def dance_files(dance_id):
    """Страница управления файлами танца"""
    dance = Dance.query.get_or_404(dance_id)
    files = get_dance_files(dance_id, dance.name)
    images = get_dance_images(dance_id, dance.name)
    return render_template('dance_files.html', dance=dance, files=files, images=images)

#######################################################
# МАССОВОЕ УДАЛЕНИЕ ТАНЦЕВ
#######################################################

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
        dance = Dance.query.get_or_404(dance_id)
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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
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
            
            if item == 'images' or item.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg')):
                continue
                
            if os.path.isfile(item_path):
                files.append({
                    'name': item,
                    'size': os.path.getsize(item_path),
                    'upload_time': os.path.getctime(item_path)
                })
    
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
    
    images.sort(key=lambda x: x['upload_time'], reverse=True)
    return images

def has_dance_files(dance_id, dance_name):
    """Проверяет наличие файлов у танца"""
    try:
        dance_path = get_dance_files_path(dance_id, dance_name)
        
        if not os.path.exists(dance_path):
            return False
        
        for item in os.listdir(dance_path):
            item_path = os.path.join(dance_path, item)
            if item != 'images' and os.path.isfile(item_path):
                return True
        
        images_path = os.path.join(dance_path, 'images')
        if os.path.exists(images_path):
            for item in os.listdir(images_path):
                item_path = os.path.join(images_path, item)
                if os.path.isfile(item_path):
                    return True
        
        return False
    except Exception as e:
        print(f"❌ Ошибка при проверке файлов для танца {dance_id}: {e}")
        return False

def has_images(dance_id, dance_name):
    """Проверяет наличие изображений у танца"""
    try:
        images = get_dance_images(dance_id, dance_name)
        return len(images) > 0
    except Exception as e:
        print(f"❌ Ошибка при проверке изображений для танца {dance_id}: {e}")
        return False

def safe_int(value, default=None):
    """Безопасное преобразование в integer"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def download_dance_images(dance_data, dance_id, dance_name):
    """Загрузка изображений для танца"""
    downloaded_files = []
    
    if not dance_data.get('images'):
        return downloaded_files
    
    for image_info in dance_data['images']:
        try:
            image_url = image_info['url']
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(image_url, timeout=30, headers=headers)
            response.raise_for_status()
            
            images_folder = ensure_dance_images_folder(dance_id, dance_name)
            filename = secure_filename(os.path.basename(image_url))
            file_path = os.path.join(images_folder, filename)
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            downloaded_files.append({
                'filename': filename,
                'url': image_url,
                'type': image_info.get('type', 'diagram')
            })
            
        except Exception as e:
            print(f"❌ Ошибка загрузки изображения {image_url}: {e}")
    
    return downloaded_files

def update_dance_note_with_images(dance, downloaded_files):
    """Обновление заметки танца с информацией о загруженных изображениях"""
    try:
        if downloaded_files:
            image_section = f"\n\n📷 Загружено изображений: {len(downloaded_files)}"
            for img in downloaded_files:
                image_section += f"\n• {img['filename']} ({img['type']})"
            
            if dance.note:
                dance.note += image_section
            else:
                dance.note = image_section.lstrip()
            
            db.session.commit()
            
    except Exception as e:
        print(f"❌ Ошибка при обновлении заметки с изображениями: {e}")

#######################################################
# ОСНОВНЫЕ МАРШРУТЫ ПРИЛОЖЕНИЯ
#######################################################

@app.route('/')
def index():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        search = request.args.get('search', '')
        
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
            # Валидация
            if not request.form.get('name', '').strip():
                flash('Название танца обязательно!', 'danger')
                return render_template('add_dance.html', **get_form_data())
            
            if not safe_int(request.form.get('dance_type')):
                flash('Тип танца обязателен!', 'danger')
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

@app.route('/dance/<int:dance_id>')
def view_dance(dance_id):
    try:
        dance = Dance.query.get_or_404(dance_id)
        files = get_dance_files(dance_id, dance.name)
        images = get_dance_images(dance_id, dance.name)
        return render_template('view_dance.html', dance=dance, files=files, images=images)
    except Exception as e:
        flash(f'Ошибка загрузки танца: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/dance/<int:dance_id>/edit', methods=['GET', 'POST'])
def edit_dance(dance_id):
    dance = Dance.query.get_or_404(dance_id)
    
    if request.method == 'POST':
        try:
            # Валидация
            if not request.form.get('name', '').strip():
                flash('Название танца обязательно!', 'danger')
                return render_template('edit_dance.html', dance=dance, **get_form_data())
            
            if not safe_int(request.form.get('dance_type')):
                flash('Тип танца обязателен!', 'danger')
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
        dance = Dance.query.get_or_404(dance_id)
        
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

#######################################################
# УПРАВЛЕНИЕ ФАЙЛАМИ И ИЗОБРАЖЕНИЯМИ
#######################################################

@app.route('/dance/<int:dance_id>/upload', methods=['POST'])
def upload_dance_file(dance_id):
    dance = Dance.query.get_or_404(dance_id)
    
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('view_dance', dance_id=dance_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('view_dance', dance_id=dance_id))
    
    if file and allowed_file(file.filename):
        dance_path = ensure_dance_folder(dance_id, dance.name)
        filename = secure_filename(file.filename)
        file_path = os.path.join(dance_path, filename)
        file.save(file_path)
        flash(f'Файл "{filename}" успешно загружен', 'success')
    else:
        flash('Недопустимый тип файла', 'danger')
    
    return redirect(url_for('view_dance', dance_id=dance_id))

@app.route('/dance/<int:dance_id>/files/<filename>')
def download_dance_file(dance_id, filename):
    dance = Dance.query.get_or_404(dance_id)
    dance_path = get_dance_files_path(dance_id, dance.name)
    return send_from_directory(dance_path, filename)

@app.route('/dance/<int:dance_id>/files/<filename>/delete', methods=['POST'])
def delete_dance_file(dance_id, filename):
    dance = Dance.query.get_or_404(dance_id)
    dance_path = get_dance_files_path(dance_id, dance.name)
    file_path = os.path.join(dance_path, filename)
    
    if os.path.exists(file_path):
        os.remove(file_path)
        flash(f'Файл "{filename}" удален', 'success')
    else:
        flash('Файл не найден', 'danger')
    
    return redirect(url_for('view_dance', dance_id=dance_id))

@app.route('/dance/<int:dance_id>/upload-image', methods=['POST'])
def upload_dance_image(dance_id):
    dance = Dance.query.get_or_404(dance_id)
    
    if 'image' not in request.files:
        flash('Изображение не выбрано', 'danger')
        return redirect(url_for('view_dance', dance_id=dance_id))
    
    file = request.files['image']
    if file.filename == '':
        flash('Изображение не выбрано', 'danger')
        return redirect(url_for('view_dance', dance_id=dance_id))
    
    if file and allowed_image_file(file.filename):
        try:
            images_folder = ensure_dance_images_folder(dance_id, dance.name)
            filename = secure_filename(file.filename)
            file_path = os.path.join(images_folder, filename)
            file.save(file_path)
            flash(f'Изображение "{filename}" успешно загружено', 'success')
        except Exception as e:
            flash(f'Ошибка при загрузке изображения: {str(e)}', 'danger')
    else:
        flash('Недопустимый формат изображения', 'danger')
    
    return redirect(url_for('view_dance', dance_id=dance_id))

@app.route('/dance/<int:dance_id>/image/<filename>')
def serve_dance_image(dance_id, filename):
    dance = Dance.query.get_or_404(dance_id)
    images_folder = os.path.join(get_dance_files_path(dance_id, dance.name), 'images')
    return send_from_directory(images_folder, filename)

@app.route('/dance/<int:dance_id>/image/<filename>/delete', methods=['POST'])
def delete_dance_image(dance_id, filename):
    dance = Dance.query.get_or_404(dance_id)
    images_folder = os.path.join(get_dance_files_path(dance_id, dance.name), 'images')
    
    try:
        main_path = os.path.join(images_folder, filename)
        if os.path.exists(main_path):
            os.remove(main_path)
        
        thumb_path = os.path.join(images_folder, f"thumb_{filename}")
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        flash(f'Изображение "{filename}" удалено', 'success')
        
    except Exception as e:
        flash(f'Ошибка при удалении изображения: {str(e)}', 'danger')
    
    return redirect(url_for('view_dance', dance_id=dance_id))

#######################################################
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ФОРМ
#######################################################

def get_form_data():
    """Получение данных для форм"""
    return {
        'set_types': SetType.query.order_by(SetType.name).all(),
        'dance_formats': DanceFormat.query.order_by(DanceFormat.name).all(),
        'dance_types': DanceType.query.order_by(DanceType.name).all()
    }

#######################################################
# КОНТЕКСТНЫЕ ПРОЦЕССОРЫ
#######################################################

@app.context_processor
def utility_processor():
    def format_datetime(timestamp, fmt='%d.%m.%Y %H:%M'):
        """Форматирование timestamp"""
        return datetime.fromtimestamp(timestamp).strftime(fmt)
    
    def has_images_processor(dance_id, dance_name):
        """Проверка наличия изображений у танца"""
        return has_images(dance_id, dance_name)
    
    def has_dance_files_processor(dance_id, dance_name):
        """Проверяет наличие файлов в файловой системе для танца"""
        return has_dance_files(dance_id, dance_name)
    
    return {
        'get_dance_files': get_dance_files,
        'get_dance_images': get_dance_images,
        'has_images': has_images_processor,
        'format_datetime': format_datetime,
        'db_type': db_type,
        'has_dance_files': has_dance_files_processor
    }

#######################################################
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
#######################################################

def init_database():
    """Инициализация базы данных"""
    try:
        with app.app_context():
            if db_type == 'postgresql':
                print("🔧 Инициализация PostgreSQL...")
                try:
                    with db.engine.connect() as conn:
                        conn.execute(db.text('CREATE SCHEMA IF NOT EXISTS scddb'))
                        conn.commit()
                    print("✅ Схема scddb создана/проверена")
                    
                except Exception as e:
                    print(f"ℹ️ Информация о схеме: {e}")
            
            # УДАЛЯЕМ СУЩЕСТВУЮЩИЕ ТАБЛИЦЫ И СОЗДАЕМ ЗАНОВО
            print("🔄 Удаление старых таблиц...")
            db.drop_all()
            
            print("🔄 Создание новых таблиц...")
            db.create_all()
            print("✅ Таблицы созданы заново")
            
            # Добавляем базовые данные
            init_basic_data()
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        import traceback
        traceback.print_exc()

def init_basic_data():
    """Инициализация базовых данных"""
    try:
        # Базовые типы сетов
        basic_set_types = ["Longwise set", "Square set", "Triangular set", "Circular set"]
        for set_type_name in basic_set_types:
            existing = SetType.query.filter_by(name=set_type_name).first()
            if not existing:
                set_type = SetType(name=set_type_name)
                db.session.add(set_type)
        
        # Базовые форматы сетов
        dance_formats = ['2 couples', '3 couples', '4 couples', '5 couples', '6 couples', 'any', 'other']
        for format_name in dance_formats:
            existing = DanceFormat.query.filter_by(name=format_name).first()
            if not existing:
                dance_format = DanceFormat(name=format_name)
                db.session.add(dance_format)
        
        # Базовые типы танцев
        dance_types = [
            ('Reel', 'R'), ('Jig', 'J'), ('Strathspey', 'S'), ('March', 'M'),
            ('Medley', 'D'), ('Polka', 'P'), ('Waltz', 'W'), ('Hornpipe', 'H')
        ]
        for type_name, type_code in dance_types:
            existing = DanceType.query.filter_by(name=type_name).first()
            if not existing:
                dance_type = DanceType(name=type_name, code=type_code)
                db.session.add(dance_type)
        
        db.session.commit()
        print("✅ Базовые данные добавлены")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базовых данных: {e}")

#######################################################
# ЗАПУСК ПРИЛОЖЕНИЯ
#######################################################

if __name__ == '__main__':
    print("🚀 Запуск приложения...")
    print(f"📁 Папка для файлов: {app.config['UPLOAD_FOLDER']}")
    print(f"📁 Папка для массового импорта: {app.config['BATCH_IMPORT_FOLDER']}")
    print(f"🗄️  Тип базы данных: {db_type}")
    
    # Создаем необходимые папки
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    if not os.path.exists(app.config['BATCH_IMPORT_FOLDER']):
        os.makedirs(app.config['BATCH_IMPORT_FOLDER'])
    
    # Инициализация базы данных
    init_database()
    
    print("🌐 Приложение запущено по адресу: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
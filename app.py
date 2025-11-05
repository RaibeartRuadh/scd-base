from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from models import db, Dance, DanceType, DanceFormat, SetType
from werkzeug.utils import secure_filename
import os
import psycopg2
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import and_, or_

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Конфигурация для загрузки файлов
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dance_files')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'doc', 'docx'}

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

def allowed_file(filename):
    """Проверка разрешенных расширений файлов"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

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

# Настраиваем базу данных
db_type = setup_database()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализируем базу данных
db.init_app(app)

@contextmanager
def db_session():
    """Контекстный менеджер для работы с сессией БД"""
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

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
            print(f"📋 Существующие таблицы в схеме scddб: {existing_tables}")
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

def get_dance_files(dance_id, dance_name):
    """Получение списка файлов для танца"""
    dance_path = get_dance_files_path(dance_id, dance_name)
    files = []
    
    if os.path.exists(dance_path):
        for filename in os.listdir(dance_path):
            file_path = os.path.join(dance_path, filename)
            if os.path.isfile(file_path):
                files.append({
                    'name': filename,
                    'size': os.path.getsize(file_path),
                    'upload_time': os.path.getctime(file_path)
                })
    
    # Сортируем по времени загрузки (новые сначала)
    files.sort(key=lambda x: x['upload_time'], reverse=True)
    return files

def safe_int(value, default=None):
    """Безопасное преобразование в integer"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# Контекстные процессоры
@app.context_processor
def utility_processor():
    def format_datetime(timestamp, fmt='%d.%m.%Y %H:%M'):
        """Форматирование timestamp"""
        return datetime.fromtimestamp(timestamp).strftime(fmt)
    
    return {
        'get_dance_files': get_dance_files,
        'format_datetime': format_datetime,
        'db_type': db_type
    }

# Вспомогательные функции для форм
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

# Функции для поиска
def get_search_filters():
    """Получение данных для фильтров поиска"""
    return {
        'dance_types': DanceType.query.order_by(DanceType.id).all(),  # ИЗМЕНЕНО: сортировка по ID
        'dance_formats': DanceFormat.query.order_by(DanceFormat.id).all(),  # ИЗМЕНЕНО: сортировка по ID
        'set_types': SetType.query.order_by(SetType.id).all(),  # ИЗМЕНЕНО: сортировка по ID
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
    
    # Применяем все условия через И
    if conditions:
        query = query.filter(and_(*conditions))
    
    return query

# Маршруты для поиска
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
                'has_description': request.form.get('has_description'),  # ДОБАВЛЕНО
                'has_files': request.form.get('has_files')  # ДОБАВЛЕНО
            }
            
            # Строим запрос
            query = build_search_query(filters)
            
            # Выполняем поиск
            results = query.order_by(Dance.name).all()
            
            # Применяем фильтр по наличию файлов (после основного запроса)
            if filters.get('has_files') == 'on':
                results = [dance for dance in results if get_dance_files(dance.id, dance.name)]
            
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

# Остальные маршруты (SetType, DanceFormat, DanceType, файлы, основной функционал)

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

# Маршруты для работы с файлами танцев
@app.route('/dance/<int:dance_id>/files')
def dance_files(dance_id):
    dance = Dance.get_by_id(dance_id)
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

# Основные маршруты приложения
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
        return render_template('view_dance.html', dance=dance, files=files)
    except Exception as e:
        flash(f'Ошибка загрузки танца: {str(e)}', 'danger')
        return redirect(url_for('index'))


# Добавить после существующих маршрутов для танцев

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
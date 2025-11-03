from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import os
import psycopg2
from datetime import datetime
from contextlib import contextmanager

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

db = SQLAlchemy(app)

# Базовый класс для моделей с общей логикой
class BaseModel(db.Model):
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    # Убрали created_at для совместимости с существующей базой
    
    @classmethod
    def get_all(cls):
        """Получить все записи"""
        return cls.query.order_by(cls.name).all()
    
    @classmethod
    def get_by_id(cls, id):
        """Получить запись по ID"""
        return cls.query.get_or_404(id)
    
    @classmethod
    def get_or_create(cls, **kwargs):
        """Получить или создать запись"""
        instance = cls.query.filter_by(**kwargs).first()
        if instance:
            return instance, False
        else:
            instance = cls(**kwargs)
            db.session.add(instance)
            db.session.commit()
            return instance, True

# Модель для справочника типов сетов
class SetType(BaseModel):
    __tablename__ = 'set_type'
    
    if db_type == 'postgresql':
        __table_args__ = {'schema': app.config['DB_SCHEMA']}
    
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

# Модель для справочника форматов сетов
class DanceFormat(BaseModel):
    __tablename__ = 'dance_format'
    
    if db_type == 'postgresql':
        __table_args__ = {'schema': app.config['DB_SCHEMA']}
    
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

# Модель для справочника типов танцев
class DanceType(BaseModel):
    __tablename__ = 'dance_type'
    
    if db_type == 'postgresql':
        __table_args__ = {'schema': app.config['DB_SCHEMA']}
    
    name = db.Column(db.String(50), nullable=False, unique=True)
    code = db.Column(db.String(1), nullable=False, unique=True)
    description = db.Column(db.Text)

# Модель данных для танцев
# Модель данных для танцев
class Dance(db.Model):
    __tablename__ = 'dance'
    
    if db_type == 'postgresql':
        __table_args__ = {'schema': app.config['DB_SCHEMA']}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255))
    dance_type_id = db.Column(db.Integer, db.ForeignKey(
        f"{app.config['DB_SCHEMA'] + '.' if db_type == 'postgresql' else ''}dance_type.id"
    ))
    size_id = db.Column(db.Integer)
    count_id = db.Column(db.Integer)
    dance_format_id = db.Column(db.Integer, db.ForeignKey(
        f"{app.config['DB_SCHEMA'] + '.' if db_type == 'postgresql' else ''}dance_format.id"
    ))
    dance_couple = db.Column(db.String(50))
    set_type_id = db.Column(db.Integer, db.ForeignKey(
        f"{app.config['DB_SCHEMA'] + '.' if db_type == 'postgresql' else ''}set_type.id"
    ))
    description = db.Column(db.Text)
    published = db.Column(db.String(255))
    note = db.Column(db.Text)
    
    # Связи
    set_type_rel = db.relationship('SetType', backref='dances')
    dance_format_rel = db.relationship('DanceFormat', backref='dances')
    dance_type_rel = db.relationship('DanceType', backref='dances')
    
    # Добавляем методы, которые были в BaseModel
    @classmethod
    def get_by_id(cls, id):
        """Получить запись по ID"""
        return cls.query.get_or_404(id)
    
    @classmethod
    def get_all(cls):
        """Получить все записи"""
        return cls.query.order_by(cls.name).all()

@contextmanager
def db_session():
    """Контекстный менеджер для работы с сессией БД"""
    try:
        yield db.session
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

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
                except Exception as e:
                    print(f"ℹ️ Информация о схеме: {e}")
            
            # Создаем только таблицы справочников, основную таблицу dance не трогаем
            db.create_all()
            print("✅ SQLAlchemy метаданные обновлены")
            
            # Добавляем базовые данные только в справочники
            init_basic_data()
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

def init_basic_data():
    """Инициализация базовых данных только для справочников"""
    try:
        # Базовые типы сетов
        basic_set_types = [
            "Longwise set", "Square set", "Triangular set", "Circular set",
            "2 Couple set", "3 Couple set", "4 Couple set", "5 Couple set"
        ]
        
        for set_type_name in basic_set_types:
            SetType.get_or_create(name=set_type_name)
        
        # Базовые форматы сетов
        dance_formats = [
            '12 persons', '16 couples', '1 couple', '1 person', '2 couples',
            '2 couples (1x)', '2 couples (Glasgow Highl)', '2 persons', '2 trios',
            '3 couples', '3 couples (1x)', '3 couples (1x,2x)', '3 couples (1x,3x)',
            '3 couples (2x)', '3 couples (2x,3x)', '3 couples (3x)', '3 persons', '3 trios',
            '4 couples', '4 couples (1x)', '4 couples (1x,2x)', '4 couples (1x,3x)',
            '4 couples (1x,4x)', '4 couples (2x,3x)', '4 couples (2x,4x)', '4 couples (3x,4x)',
            '4 couples (4x)', '4 couples (Glasgow Highl)', '4 persons', '4 trios', '4w+2m',
            '5 couples', '5 couples (2x,4x)', '5 couples (4x,5x)', '5 persons',
            '6 couples', '6 couples (2x,4x,6x)', '6 couples (4x,5x,6x)', '6 persons',
            '7 couples', '7 persons', '8 couples', '8 persons', '9 persons',
            'any', 'other', 'unknown'
        ]
        
        for format_name in dance_formats:
            DanceFormat.get_or_create(name=format_name)
        
        # Базовые типы танцев
        dance_types = [
            ('Reel', 'R'), ('Jig', 'J'), ('Strathspey', 'S'), ('March', 'M'),
            ('Medley', 'D'), ('Polka', 'P'), ('Waltz', 'W'), ('Hornpipe', 'H'),
            ('Quadrille', 'Q'), ('Minuet', 'N')
        ]
        
        for type_name, type_code in dance_types:
            DanceType.get_or_create(name=type_name, code=type_code)
        
        print("✅ Базовые типы сетов, форматы и типы танцев добавлены")
        
        # Статистика - проверяем только справочники, основную таблицу не трогаем
        set_type_count = SetType.query.count()
        dance_format_count = DanceFormat.query.count()
        dance_type_count = DanceType.query.count()
        
        print(f"📊 Записей в таблице set_type: {set_type_count}")
        print(f"📊 Записей в таблице dance_format: {dance_format_count}")
        print(f"📊 Записей в таблице dance_type: {dance_type_count}")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации базовых данных: {e}")

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
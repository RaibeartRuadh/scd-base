from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import os
import psycopg2

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'

# Проверяем подключение к PostgreSQL напрямую
def check_postgres_connection():
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
            print(f"✅ Подключение к PostgreSQL успешно!")
            print(f"📊 Таблица dance существует, записей: {count}")
        else:
            print("✅ Подключение к PostgreSQL успешно!")
            print("❌ Таблица dance не существует")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        return False

# Проверяем подключение
print("🔗 Проверка подключения к PostgreSQL...")
if check_postgres_connection():
    # Используем PostgreSQL
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:roy@localhost:5432/scddb'
    print("🎯 Используется PostgreSQL")
else:
    # Используем SQLite как запасной вариант
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "dances.db")}'
    print("🔄 Используется SQLite (запасной вариант)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Модель для справочника типов сетов
class SetType(db.Model):
    __tablename__ = 'set_type'
    __table_args__ = {'schema': 'scddb'}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())

# Модель для справочника форматов сетов
class DanceFormat(db.Model):
    __tablename__ = 'dance_format'
    __table_args__ = {'schema': 'scddb'}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())

# Модель для справочника типов танцев
class DanceType(db.Model):
    __tablename__ = 'dance_type'
    __table_args__ = {'schema': 'scddb'}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    code = db.Column(db.String(1), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())

# Модель данных для танцев
class Dance(db.Model):
    if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']:
        __tablename__ = 'dance'
        __table_args__ = {'schema': 'scddb'}
    else:
        __tablename__ = 'dance'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255))
    dance_type_id = db.Column(db.Integer, db.ForeignKey('scddb.dance_type.id'))
    size_id = db.Column(db.Integer)
    count_id = db.Column(db.Integer)
    dance_format_id = db.Column(db.Integer, db.ForeignKey('scddb.dance_format.id'))
    dance_couple = db.Column(db.String(50))
    set_type_id = db.Column(db.Integer, db.ForeignKey('scddb.set_type.id'))
    description = db.Column(db.Text)
    published = db.Column(db.String(255))
    note = db.Column(db.Text)
    
    # Связь с типом сета
    set_type_rel = db.relationship('SetType', backref='dances')
    # Связь с форматом сета
    dance_format_rel = db.relationship('DanceFormat', backref='dances')
    # Связь с типом танца
    dance_type_rel = db.relationship('DanceType', backref='dances')

def init_database():
    """Инициализация базы данных"""
    try:
        with app.app_context():
            if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI']:
                print("🔧 Инициализация PostgreSQL...")
                
                # Создаем схему если не существует
                try:
                    db.session.execute('CREATE SCHEMA IF NOT EXISTS scddb')
                    db.session.commit()
                    print("✅ Схема scddb создана/проверена")
                except Exception as e:
                    print(f"ℹ️ Схема уже существует: {e}")
                
                # Создаем таблицу set_type если не существует
                try:
                    db.session.execute("""
                        CREATE TABLE IF NOT EXISTS scddb.set_type (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(100) NOT NULL UNIQUE,
                            description TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    db.session.commit()
                    print("✅ Таблица scddb.set_type создана/проверена")
                except Exception as e:
                    print(f"ℹ️ Таблица set_type уже существует: {e}")
                
                # Создаем таблицу dance_format если не существует
                try:
                    db.session.execute("""
                        CREATE TABLE IF NOT EXISTS scddb.dance_format (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(100) NOT NULL UNIQUE,
                            description TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    db.session.commit()
                    print("✅ Таблица scddb.dance_format создана/проверена")
                except Exception as e:
                    print(f"ℹ️ Таблица dance_format уже существует: {e}")
                
                # Создаем таблицу dance_type если не существует
                try:
                    db.session.execute("""
                        CREATE TABLE IF NOT EXISTS scddb.dance_type (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(50) NOT NULL UNIQUE,
                            code VARCHAR(1) NOT NULL UNIQUE,
                            description TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    db.session.commit()
                    print("✅ Таблица scddb.dance_type создана/проверена")
                except Exception as e:
                    print(f"ℹ️ Таблица dance_type уже существует: {e}")
                
                # Создаем таблицу dance если не существует
                try:
                    db.session.execute("""
                        CREATE TABLE IF NOT EXISTS scddb.dance (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(255) NOT NULL,
                            author VARCHAR(255),
                            dance_type_id INTEGER REFERENCES scddb.dance_type(id),
                            size_id INTEGER,
                            count_id INTEGER,
                            dance_format_id INTEGER REFERENCES scddb.dance_format(id),
                            dance_couple VARCHAR(50),
                            set_type_id INTEGER REFERENCES scddb.set_type(id),
                            description TEXT,
                            published VARCHAR(255),
                            note TEXT
                        )
                    """)
                    db.session.commit()
                    print("✅ Таблица scddb.dance создана/проверена")
                except Exception as e:
                    print(f"ℹ️ Таблица dance уже существует: {e}")
            
            # Всегда вызываем create_all для SQLAlchemy
            db.create_all()
            print("✅ SQLAlchemy метаданные обновлены")
            
            # Добавляем базовые типы сетов если их нет
            basic_set_types = [
                "Longwise set",
                "Square set", 
                "Triangular set",
                "Circular set",
                "2 Couple set",
                "3 Couple set",
                "4 Couple set",
                "5 Couple set"
            ]
            
            for set_type_name in basic_set_types:
                existing = SetType.query.filter_by(name=set_type_name).first()
                if not existing:
                    new_set_type = SetType(name=set_type_name)
                    db.session.add(new_set_type)
            
            # Добавляем базовые форматы сетов если их нет
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
                existing = DanceFormat.query.filter_by(name=format_name).first()
                if not existing:
                    new_format = DanceFormat(name=format_name)
                    db.session.add(new_format)
            
            # Добавляем базовые типы танцев если их нет
            dance_types = [
                ('Reel', 'R'),
                ('Jig', 'J'),
                ('Strathspey', 'S'),
                ('March', 'M'),
                ('Medley', 'D'),
                ('Polka', 'P'),
                ('Waltz', 'W'),
                ('Hornpipe', 'H'),
                ('Quadrille', 'Q'),
                ('Minuet', 'N')
            ]
            
            for type_name, type_code in dance_types:
                existing = DanceType.query.filter_by(name=type_name).first()
                if not existing:
                    new_dance_type = DanceType(name=type_name, code=type_code)
                    db.session.add(new_dance_type)
            
            db.session.commit()
            print("✅ Базовые типы сетов, форматы и типы танцев добавлены")
            
            # Проверяем, есть ли уже данные
            dance_count = Dance.query.count()
            set_type_count = SetType.query.count()
            dance_format_count = DanceFormat.query.count()
            dance_type_count = DanceType.query.count()
            print(f"📊 Записей в таблице dance: {dance_count}")
            print(f"📊 Записей в таблице set_type: {set_type_count}")
            print(f"📊 Записей в таблице dance_format: {dance_format_count}")
            print(f"📊 Записей в таблице dance_type: {dance_type_count}")
            
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

def check_table_exists():
    """Проверяет существование таблицы dance"""
    try:
        with app.app_context():
            # Пробуем выполнить простой запрос
            test = Dance.query.first()
            print("✅ Таблица dance доступна")
            return True
    except Exception as e:
        print(f"❌ Таблица dance недоступна: {e}")
        return False

# Остальной код маршрутов остается без изменений...
# [Здесь должен быть весь остальной код маршрутов из предыдущей версии]

# Маршруты для управления типами сетов
@app.route('/set-types')
def manage_set_types():
    """Страница управления типами сетов"""
    set_types = SetType.query.order_by(SetType.name).all()
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
    set_type = SetType.query.get_or_404(set_type_id)
    
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
        set_type = SetType.query.get_or_404(set_type_id)
        
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

# Маршруты для управления форматами сетов
@app.route('/dance-formats')
def manage_dance_formats():
    """Страница управления форматами сетов"""
    dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
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
    dance_format = DanceFormat.query.get_or_404(format_id)
    
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
        dance_format = DanceFormat.query.get_or_404(format_id)
        
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

# Маршруты для управления типами танцев
@app.route('/dance-types')
def manage_dance_types():
    """Страница управления типами танцев"""
    dance_types = DanceType.query.order_by(DanceType.name).all()
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
    dance_type = DanceType.query.get_or_404(type_id)
    
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
        dance_type = DanceType.query.get_or_404(type_id)
        
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
        
        db_type = "PostgreSQL" if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else "SQLite"
        return render_template('index.html', dances=dances, search=search, db_type=db_type, per_page=per_page)
        
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
                             db_type='Unknown', 
                             per_page=per_page)

@app.route('/add', methods=['GET', 'POST'])
def add_dance():
    if request.method == 'POST':
        try:
            # Функция для безопасного преобразования в integer
            def safe_int(value, default=None):
                if value is None or value == '':
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default
            
            # Получаем данные из формы с безопасным преобразованием
            size_id = safe_int(request.form.get('size_id'))
            count_id = safe_int(request.form.get('count_id'))
            set_type_id = safe_int(request.form.get('set_type'))
            dance_format_id = safe_int(request.form.get('dance_format'))
            dance_type_id = safe_int(request.form.get('dance_type'))
            
            dance = Dance(
                name=request.form.get('name', '').strip(),
                author=request.form.get('author', '').strip(),
                dance_type_id=dance_type_id,
                size_id=size_id,
                count_id=count_id,
                dance_format_id=dance_format_id,
                dance_couple=request.form.get('dance_couple', '').strip(),
                set_type_id=set_type_id,
                description=request.form.get('description', '').strip(),
                published=request.form.get('published', '').strip(),
                note=request.form.get('note', '').strip()
            )
            
            # Проверяем обязательные поля
            if not dance.name:
                flash('Название танца обязательно для заполнения!', 'danger')
                set_types = SetType.query.order_by(SetType.name).all()
                dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
                dance_types = DanceType.query.order_by(DanceType.name).all()
                return render_template('add_dance.html', 
                                    set_types=set_types, 
                                    dance_formats=dance_formats,
                                    dance_types=dance_types)
            
            if not dance.dance_type_id:
                flash('Тип танца обязателен для заполнения!', 'danger')
                set_types = SetType.query.order_by(SetType.name).all()
                dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
                dance_types = DanceType.query.order_by(DanceType.name).all()
                return render_template('add_dance.html', 
                                    set_types=set_types, 
                                    dance_formats=dance_formats,
                                    dance_types=dance_types)
            
            db.session.add(dance)
            db.session.commit()
            flash('Танец успешно добавлен!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении танца: {str(e)}', 'danger')
            print(f"❌ Детали ошибки: {e}")
    
    # GET запрос - получаем списки для формы
    set_types = SetType.query.order_by(SetType.name).all()
    dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
    dance_types = DanceType.query.order_by(DanceType.name).all()
    return render_template('add_dance.html', 
                          set_types=set_types, 
                          dance_formats=dance_formats,
                          dance_types=dance_types)

@app.route('/dance/<int:dance_id>/edit', methods=['GET', 'POST'])
def edit_dance(dance_id):
    """Редактирование танца"""
    dance = Dance.query.get_or_404(dance_id)
    
    if request.method == 'POST':
        try:
            # Функция для безопасного преобразования в integer
            def safe_int(value, default=None):
                if value is None or value == '':
                    return default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default
            
            # Получаем данные из формы с безопасным преобразованием
            size_id = safe_int(request.form.get('size_id'))
            count_id = safe_int(request.form.get('count_id'))
            set_type_id = safe_int(request.form.get('set_type'))
            dance_format_id = safe_int(request.form.get('dance_format'))
            dance_type_id = safe_int(request.form.get('dance_type'))
            
            # Обновляем данные танца
            dance.name = request.form.get('name', '').strip()
            dance.author = request.form.get('author', '').strip()
            dance.dance_type_id = dance_type_id
            dance.size_id = size_id
            dance.count_id = count_id
            dance.dance_format_id = dance_format_id
            dance.dance_couple = request.form.get('dance_couple', '').strip()
            dance.set_type_id = set_type_id
            dance.description = request.form.get('description', '').strip()
            dance.published = request.form.get('published', '').strip()
            dance.note = request.form.get('note', '').strip()
            
            # Проверяем обязательные поля
            if not dance.name:
                flash('Название танца обязательно для заполнения!', 'danger')
                set_types = SetType.query.order_by(SetType.name).all()
                dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
                dance_types = DanceType.query.order_by(DanceType.name).all()
                return render_template('edit_dance.html', 
                                    dance=dance,
                                    set_types=set_types, 
                                    dance_formats=dance_formats,
                                    dance_types=dance_types)
            
            if not dance.dance_type_id:
                flash('Тип танца обязателен для заполнения!', 'danger')
                set_types = SetType.query.order_by(SetType.name).all()
                dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
                dance_types = DanceType.query.order_by(DanceType.name).all()
                return render_template('edit_dance.html', 
                                    dance=dance,
                                    set_types=set_types, 
                                    dance_formats=dance_formats,
                                    dance_types=dance_types)
            
            db.session.commit()
            flash('Танец успешно обновлен!', 'success')
            return redirect(url_for('view_dance', dance_id=dance.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при обновлении танца: {str(e)}', 'danger')
            print(f"❌ Детали ошибки: {e}")
    
    # GET запрос - получаем списки для формы
    set_types = SetType.query.order_by(SetType.name).all()
    dance_formats = DanceFormat.query.order_by(DanceFormat.name).all()
    dance_types = DanceType.query.order_by(DanceType.name).all()
    return render_template('edit_dance.html', 
                          dance=dance,
                          set_types=set_types, 
                          dance_formats=dance_formats,
                          dance_types=dance_types)

@app.route('/dance/<int:dance_id>')
def view_dance(dance_id):
    try:
        dance = Dance.query.get_or_404(dance_id)
        return render_template('view_dance.html', dance=dance)
    except Exception as e:
        flash(f'Ошибка загрузки танца: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/delete-dances', methods=['POST'])
def delete_dances():
    """Удаление выбранных танцев"""
    try:
        dance_ids = request.form.getlist('dance_ids')
        
        if not dance_ids:
            flash('Не выбраны танцы для удаления!', 'warning')
            return redirect(url_for('index'))
        
        # Преобразуем ID в числа
        dance_ids = [int(dance_id) for dance_id in dance_ids]
        
        # Находим танцы для удаления (чтобы показать названия в сообщении)
        dances_to_delete = Dance.query.filter(Dance.id.in_(dance_ids)).all()
        dance_names = [dance.name for dance in dances_to_delete]
        
        # Удаляем танцы
        deleted_count = Dance.query.filter(Dance.id.in_(dance_ids)).delete()
        db.session.commit()
        
        if deleted_count == 1:
            flash(f'Танец "{dance_names[0]}" успешно удален!', 'success')
        else:
            flash(f'Успешно удалено {deleted_count} танцев!', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении танцев: {str(e)}', 'danger')
        print(f"❌ Ошибка удаления: {e}")
    
    return redirect(url_for('index'))

@app.route('/dance/<int:dance_id>/delete', methods=['POST'])
def delete_single_dance(dance_id):
    """Удаление одного танца"""
    try:
        dance = Dance.query.get_or_404(dance_id)
        dance_name = dance.name
        
        db.session.delete(dance)
        db.session.commit()
        
        flash(f'Танец "{dance_name}" успешно удален!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении танца: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/debug')
def debug():
    """Страница для отладки"""
    try:
        dances = Dance.query.paginate(page=1, per_page=5, error_out=False)
        return f"""
        <h1>Отладка</h1>
        <p>Тип dances: {type(dances)}</p>
        <p>Атрибуты: {dir(dances)}</p>
        <p>Всего записей: {dances.total}</p>
        <p>Страниц: {dances.pages}</p>
        <p>Текущая страница: {dances.page}</p>
        <p>Записей на странице: {dances.per_page}</p>
        <p><a href="/">На главную</a></p>
        """
    except Exception as e:
        return f"Ошибка: {e}"

@app.route('/init-db')
def init_db_route():
    try:
        init_database()
        flash('База данных инициализирована!', 'success')
    except Exception as e:
        flash(f'Ошибка инициализации БД: {str(e)}', 'danger')
    return redirect(url_for('index'))

@app.route('/check-db')
def check_db():
    """Страница для проверки состояния базы данных"""
    try:
        dance_count = Dance.query.count()
        set_type_count = SetType.query.count()
        dance_format_count = DanceFormat.query.count()
        dance_type_count = DanceType.query.count()
        db_type = "PostgreSQL" if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else "SQLite"
        db_status = f"✅ База данных работает ({db_type})"
        return f"""
        <h1>Проверка базы данных</h1>
        <p>{db_status}</p>
        <p>Записей в таблице dance: {dance_count}</p>
        <p>Записей в таблице set_type: {set_type_count}</p>
        <p>Записей в таблице dance_format: {dance_format_count}</p>
        <p>Записей в таблице dance_type: {dance_type_count}</p>
        <p>Тип БД: {db_type}</p>
        <p><a href="/">Вернуться на главную</a></p>
        """
    except Exception as e:
        return f"""
        <h1>Ошибка базы данных</h1>
        <p>❌ {str(e)}</p>
        <p><a href="/init-db">Попробовать инициализировать БД</a></p>
        """

@app.route('/force-create-tables')
def force_create_tables():
    """Принудительное создание таблиц"""
    try:
        init_database()
        flash('Таблицы созданы/проверены!', 'success')
    except Exception as e:
        flash(f'Ошибка создания таблиц: {str(e)}', 'danger')
    return redirect(url_for('index'))

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Запуск приложения...")
    
    # Проверяем существование таблицы
    if not check_table_exists():
        print("🔧 Таблица не найдена, запускаем инициализацию...")
        init_database()
    else:
        print("✅ Таблица существует")
    
    print("🌐 Откройте в браузере: http://localhost:5000")
    print("🔧 Для проверки БД: http://localhost:5000/check-db")
    print("⚙️ Управление типами сетов: http://localhost:5000/set-types")
    print("⚙️ Управление форматами сетов: http://localhost:5000/dance-formats")
    print("⚙️ Управление типами танцев: http://localhost:5000/dance-types")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
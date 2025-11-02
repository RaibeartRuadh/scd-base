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
        
        # Проверяем существование таблицы
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
    dance_type = db.Column(db.String(1))
    size_id = db.Column(db.Integer)
    count_id = db.Column(db.Integer)
    all_couples = db.Column(db.String(50))
    dance_couple = db.Column(db.String(50))
    set_type_id = db.Column(db.Integer, db.ForeignKey('scddb.set_type.id'))  # Это поле должно быть
    description = db.Column(db.Text)
    published = db.Column(db.String(255))
    note = db.Column(db.Text)
    
    # Связь с типом сета
    set_type_rel = db.relationship('SetType', backref='dances')

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
                
                # Создаем таблицу dance если не существует
                try:
                    db.session.execute("""
                        CREATE TABLE IF NOT EXISTS scddb.dance (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(255) NOT NULL,
                            author VARCHAR(255),
                            dance_type VARCHAR(1),
                            size_id INTEGER,
                            count_id INTEGER,
                            all_couples VARCHAR(50),
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
            
            db.session.commit()
            print("✅ Базовые типы сетов добавлены")
            
            # Проверяем, есть ли уже данные
            dance_count = Dance.query.count()
            set_type_count = SetType.query.count()
            print(f"📊 Записей в таблице dance: {dance_count}")
            print(f"📊 Записей в таблице set_type: {set_type_count}")
            
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
        empty_pagination = type('obj', (object,), {
            'items': [],
            'page': 1,
            'per_page': per_page,
            'total': 0,
            'pages': 0,
            'has_prev': False,
            'has_next': False,
            'prev_num': None,
            'next_num': None,
            'iter_pages': lambda *args: []
        })()
        return render_template('index.html', dances=empty_pagination, search='', db_type='Unknown', per_page=per_page)

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
            
            # Отладочная информация
            print(f"📝 Получены данные формы:")
            print(f"   name: {request.form.get('name')}")
            print(f"   dance_type: {request.form.get('dance_type')}")
            print(f"   set_type: {request.form.get('set_type')}")
            print(f"   set_type_id: {set_type_id}")
            
            dance = Dance(
                name=request.form.get('name', '').strip(),
                author=request.form.get('author', '').strip(),
                dance_type=request.form.get('dance_type', '').strip(),
                size_id=size_id,
                count_id=count_id,
                all_couples=request.form.get('all_couples', '').strip(),
                dance_couple=request.form.get('dance_couple', '').strip(),
                set_type_id=set_type_id,  # Используем set_type_id вместо set_type
                description=request.form.get('description', '').strip(),
                published=request.form.get('published', '').strip(),
                note=request.form.get('note', '').strip()
            )
            
            # Проверяем обязательные поля
            if not dance.name:
                flash('Название танца обязательно для заполнения!', 'danger')
                set_types = SetType.query.order_by(SetType.name).all()
                return render_template('add_dance.html', set_types=set_types)
            
            if not dance.dance_type:
                flash('Тип танца обязателен для заполнения!', 'danger')
                set_types = SetType.query.order_by(SetType.name).all()
                return render_template('add_dance.html', set_types=set_types)
            
            db.session.add(dance)
            db.session.commit()
            flash('Танец успешно добавлен!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении танца: {str(e)}', 'danger')
            print(f"❌ Детали ошибки: {e}")
    
    # GET запрос - получаем список типов сетов для формы
    set_types = SetType.query.order_by(SetType.name).all()
    return render_template('add_dance.html', set_types=set_types)

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
        db_type = "PostgreSQL" if 'postgresql' in app.config['SQLALCHEMY_DATABASE_URI'] else "SQLite"
        db_status = f"✅ База данных работает ({db_type})"
        return f"""
        <h1>Проверка базы данных</h1>
        <p>{db_status}</p>
        <p>Записей в таблице dance: {dance_count}</p>
        <p>Записей в таблице set_type: {set_type_count}</p>
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
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
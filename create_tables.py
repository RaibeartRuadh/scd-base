from app import app, db, Dance
import psycopg2

def create_tables():
    print("🗄️ Создание таблиц в PostgreSQL...")
    
    try:
        # Подключаемся напрямую к PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port="5432", 
            database="scddb",
            user="postgres",
            password="roy"
        )
        cursor = conn.cursor()
        
        # Создаем схему если не существует
        cursor.execute("CREATE SCHEMA IF NOT EXISTS scddb;")
        print("✅ Схема scddb создана/проверена")
        
        # Создаем таблицу dance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scddb.dance (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                author VARCHAR(255),
                dance_type VARCHAR(1),
                size_id INTEGER,
                count_id INTEGER,
                all_couples VARCHAR(50),
                dance_couple VARCHAR(50),
                set_type VARCHAR(50),
                description TEXT,
                published VARCHAR(255),
                note TEXT
            );
        """)
        print("✅ Таблица scddb.dance создана/проверена")
        
        conn.commit()
        conn.close()
        
        # Теперь создаем через SQLAlchemy (для совместимости)
        with app.app_context():
            db.create_all()
            print("✅ SQLAlchemy таблицы созданы")
            
            # Проверяем, что таблица доступна
            count = Dance.query.count()
            print(f"📊 Записей в таблице: {count}")
            
    except Exception as e:
        print(f"❌ Ошибка создания таблиц: {e}")

if __name__ == '__main__':
    create_tables()
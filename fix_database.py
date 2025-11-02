from app import app, db, Dance, SetType
import psycopg2

def check_database_structure():
    """Проверяет текущую структуру таблицы dance"""
    print("🔍 Проверка структуры базы данных...")
    
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="scddb",
            user="postgres",
            password="roy"
        )
        cursor = conn.cursor()
        
        # Проверяем какие столбцы есть в таблице dance
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'scddb' 
            AND table_name = 'dance'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        print("📋 Столбцы таблицы dance:")
        for column in columns:
            print(f"   {column[0]} ({column[1]})")
        
        conn.close()
        return columns
        
    except Exception as e:
        print(f"❌ Ошибка проверки структуры БД: {e}")
        return []

def add_set_type_column():
    """Добавляет столбец set_type_id если его нет"""
    print("🔄 Добавление столбца set_type_id...")
    
    try:
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="scddb",
            user="postgres",
            password="roy"
        )
        cursor = conn.cursor()
        
        # Добавляем столбец set_type_id
        cursor.execute("""
            ALTER TABLE scddb.dance 
            ADD COLUMN IF NOT EXISTS set_type_id INTEGER REFERENCES scddb.set_type(id)
        """)
        
        conn.commit()
        conn.close()
        print("✅ Столбец set_type_id добавлен")
        
    except Exception as e:
        print(f"❌ Ошибка добавления столбца: {e}")

if __name__ == '__main__':
    columns = check_database_structure()
    
    # Проверяем есть ли set_type_id
    has_set_type_id = any('set_type_id' in column for column in columns)
    
    if not has_set_type_id:
        print("❌ Столбец set_type_id не найден, добавляем...")
        add_set_type_column()
    else:
        print("✅ Столбец set_type_id уже существует")
from app import app, db, Dance, SetType
import psycopg2

def update_database_structure():
    """Обновляет структуру базы данных - добавляет столбец set_type_id"""
    print("🔄 Обновление структуры базы данных...")
    
    try:
        with app.app_context():
            # Подключаемся напрямую к PostgreSQL
            conn = psycopg2.connect(
                host="localhost",
                port="5432",
                database="scddb",
                user="postgres",
                password="roy"
            )
            cursor = conn.cursor()
            
            # Проверяем существование столбца set_type_id
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'scddb' 
                AND table_name = 'dance' 
                AND column_name = 'set_type_id'
            """)
            
            set_type_id_exists = cursor.fetchone()
            
            if not set_type_id_exists:
                print("📝 Добавляем столбец set_type_id в таблицу dance...")
                
                # Добавляем столбец set_type_id
                cursor.execute("""
                    ALTER TABLE scddb.dance 
                    ADD COLUMN set_type_id INTEGER REFERENCES scddb.set_type(id)
                """)
                
                # Переносим данные из старого столбца set_type в новый set_type_id
                cursor.execute("""
                    UPDATE scddb.dance 
                    SET set_type_id = (
                        SELECT id FROM scddb.set_type 
                        WHERE name = dance.set_type 
                        LIMIT 1
                    )
                """)
                
                conn.commit()
                print("✅ Столбец set_type_id добавлен и данные перенесены")
            else:
                print("✅ Столбец set_type_id уже существует")
            
            conn.close()
            
    except Exception as e:
        print(f"❌ Ошибка обновления структуры БД: {e}")

if __name__ == '__main__':
    update_database_structure()
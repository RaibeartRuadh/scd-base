import os
import sqlite3
from app import app, db

def check_database():
    print("🔍 Проверка базы данных...")
    
    # Проверяем существует ли файл базы данных
    db_path = os.path.join(os.path.dirname(__file__), 'dances.db')
    print(f"📁 Путь к базе данных: {db_path}")
    print(f"📄 Файл существует: {os.path.exists(db_path)}")
    
    if os.path.exists(db_path):
        print(f"📏 Размер файла: {os.path.getsize(db_path)} байт")
        
        # Пробуем подключиться к SQLite
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Проверяем таблицы
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"📋 Таблицы в базе: {tables}")
            
            # Проверяем таблицу dance
            if tables:
                cursor.execute("SELECT COUNT(*) FROM dance;")
                count = cursor.fetchone()[0]
                print(f"📊 Записей в таблице dance: {count}")
            
            conn.close()
            print("✅ Подключение к SQLite успешно!")
            
        except Exception as e:
            print(f"❌ Ошибка подключения к SQLite: {e}")
    else:
        print("❌ Файл базы данных не найден!")

if __name__ == '__main__':
    check_database()
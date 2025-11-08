# migration.py
from app import app, db
from models import Dance

def add_new_columns():
    """Добавление новых столбцов в таблицу dance"""
    with app.app_context():
        try:
            # Для PostgreSQL
            if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
                with db.engine.connect() as conn:
                    # Добавляем столбцы если их нет
                    conn.execute(db.text("""
                        DO $$ 
                        BEGIN 
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                        WHERE table_schema = 'scddb' 
                                        AND table_name = 'dance' 
                                        AND column_name = 'set_format') THEN
                                ALTER TABLE scddb.dance ADD COLUMN set_format INTEGER;
                            END IF;
                            
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                        WHERE table_schema = 'scddb' 
                                        AND table_name = 'dance' 
                                        AND column_name = 'couples_count') THEN
                                ALTER TABLE scddb.dance ADD COLUMN couples_count INTEGER;
                            END IF;
                        END $$;
                    """))
                    conn.commit()
                print("✅ Столбцы set_format и couples_count добавлены в таблицу dance")
            
        except Exception as e:
            print(f"❌ Ошибка при добавлении столбцов: {e}")

if __name__ == '__main__':
    add_new_columns()
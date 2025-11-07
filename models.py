from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Базовый класс для моделей с общей логикой
class BaseModel(db.Model):
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    
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
    __table_args__ = {'schema': 'scddb'}
    
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

# Модель для справочника форматов сетов
class DanceFormat(BaseModel):
    __tablename__ = 'dance_format'
    __table_args__ = {'schema': 'scddb'}
    
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

# Модель для справочника типов танцев
class DanceType(BaseModel):
    __tablename__ = 'dance_type'
    __table_args__ = {'schema': 'scddb'}
    
    name = db.Column(db.String(50), nullable=False, unique=True)
    code = db.Column(db.String(1), nullable=False, unique=True)
    description = db.Column(db.Text)
#########################################################
# Модель данных для танцев
class Dance(db.Model):
    __tablename__ = 'dance'
    __table_args__ = {'schema': 'scddb'}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255))
    dance_type_id = db.Column(db.Integer, db.ForeignKey('scddb.dance_type.id'))
    size_id = db.Column(db.Integer)
    count_id = db.Column(db.Integer)  # Для хранения повторений
    dance_format_id = db.Column(db.Integer, db.ForeignKey('scddb.dance_format.id'))
    dance_couple = db.Column(db.String(50))
    set_type_id = db.Column(db.Integer, db.ForeignKey('scddb.set_type.id'))
    description = db.Column(db.String(5000))  # Увеличили до 5000
    published = db.Column(db.String(255))
    note = db.Column(db.String(10000))  # Увеличили до 5000


    # Связи
    set_type_rel = db.relationship('SetType', backref='dances')
    dance_format_rel = db.relationship('DanceFormat', backref='dances')
    dance_type_rel = db.relationship('DanceType', backref='dances')
    
    @classmethod
    def get_by_id(cls, id):
        return cls.query.get_or_404(id)
    
    @classmethod
    def get_all(cls):
        return cls.query.order_by(cls.name).all()
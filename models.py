from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class SetType(db.Model):
    __tablename__ = 'set_type'
    __table_args__ = {'schema': 'scddb'}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())

class Dance(db.Model):
    __tablename__ = 'dance'
    __table_args__ = {'schema': 'scddb'}
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255))
    dance_type = db.Column(db.String(1))
    size_id = db.Column(db.Integer)
    count_id = db.Column(db.Integer)
    all_couples = db.Column(db.String(50))
    dance_couple = db.Column(db.String(50))
    set_type_id = db.Column(db.Integer, db.ForeignKey('scddb.set_type.id'))
    description = db.Column(db.Text)
    published = db.Column(db.String(255))
    note = db.Column(db.Text)
    
    # Связь с типом сета
    set_type_rel = db.relationship('SetType', backref='dances')
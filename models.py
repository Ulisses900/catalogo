# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Artista(db.Model):
    __tablename__ = 'artistas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), unique=True, nullable=False)
    tapes = db.relationship('Tape', backref='artista', lazy=True)

class Gravadora(db.Model):
    __tablename__ = 'gravadoras'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), unique=True, nullable=False)
    tapes = db.relationship('Tape', backref='gravadora', lazy=True)

class Etiqueta(db.Model):
    __tablename__ = 'etiquetas'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), unique=True, nullable=False)
    tapes = db.relationship('Tape', backref='etiqueta', lazy=True)

class Tape(db.Model):
    __tablename__ = 'tapes'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(300), nullable=False)
    artista_id = db.Column(db.Integer, db.ForeignKey('artistas.id'), nullable=False)
    gravadora_id = db.Column(db.Integer, db.ForeignKey('gravadoras.id'), nullable=False)
    etiqueta_id = db.Column(db.Integer, db.ForeignKey('etiquetas.id'), nullable=False)
    numero_tape = db.Column(db.String(50), unique=True, nullable=False)
    produtor_musical = db.Column(db.String(200), nullable=True)
    data_cadastro = db.Column(db.DateTime, nullable=True)
    codigo_barras = db.Column(db.String(50), nullable=True)
    quantidade = db.Column(db.Integer, nullable=True)
    preco = db.Column(db.String(20), nullable=True)
    observacao = db.Column(db.Text, nullable=True)

    # flags
    subiu_streaming = db.Column(db.Boolean, default=False)
    nao_pode_subir = db.Column(db.Boolean, default=False)
    digitalizada = db.Column(db.Boolean, default=False)

    faixas = db.relationship('Faixa', backref='tape', lazy=True, cascade='all, delete-orphan')

class Faixa(db.Model):
    __tablename__ = 'faixas'
    id = db.Column(db.Integer, primary_key=True)
    tape_id = db.Column(db.Integer, db.ForeignKey('tapes.id'), nullable=False)
    numero = db.Column(db.String(10), nullable=False)
    lado = db.Column(db.String(5), nullable=True)
    musica = db.Column(db.String(300), nullable=False)
    autor = db.Column(db.String(500), nullable=True)
    editora = db.Column(db.String(200), nullable=True)
    percentual = db.Column(db.String(20), nullable=True)

    __table_args__ = (db.UniqueConstraint('tape_id', 'numero', 'musica', name='uix_faixa_tape'),)
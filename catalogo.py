import os
import logging
from flask import Flask, render_template, request, jsonify, Blueprint, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import case, func, or_, asc, desc
from sqlalchemy.exc import SQLAlchemyError
import csv
import io

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =========================
# CONFIGURAÇÃO DO BANCO (SUPABASE + RENDER)
# =========================
db_url = os.environ.get("DATABASE_URL", "").strip()
logger.info(f"DATABASE_URL original: {db_url}")

# Corrige prefixo antigo (Render às vezes envia postgres://)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

# ⚠️ NÃO trocar porta
# ⚠️ NÃO mexer em sslmode
# ⚠️ NÃO usar 6543

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")

# Engine options (sem sslmode!)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "connect_args": {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30
    }
}

logger.info(f"URL final usada pelo SQLAlchemy: {app.config['SQLALCHEMY_DATABASE_URI']}")

# =========================
# INICIALIZAÇÃO DO DB
# =========================
from models import db, Artista, Gravadora, Etiqueta, Tape, Faixa
db.init_app(app)

# === Blueprint ===
catalogo_bp = Blueprint('catalogo', __name__)

def get_status(tape):
    if tape.subiu_streaming is True:
        return 'on_stream'
    if tape.digitalizada is True:
        return 'digitalizada'
    return 'not_stream'

# === Manipulador de exceções global ===
@app.errorhandler(Exception)
def handle_any_exception(e):
    logger.exception("Erro não tratado:")
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": str(e), "type": e.__class__.__name__}), 500
    return render_template("error.html", error=str(e)), 500

# === Rotas de visualização ===
@catalogo_bp.route('/')
def index():
    return render_template('index.html')

@catalogo_bp.route('/artistas')
def artistas():
    return render_template('artistas.html')

@catalogo_bp.route('/etiquetas')
def etiquetas():
    return render_template('etiquetas.html')

@catalogo_bp.route('/gravadoras')
def gravadoras():
    return render_template('gravadoras.html')

@catalogo_bp.route('/tapes', endpoint='tapes_list')
def tapes():
    return render_template('tapes.html')

@catalogo_bp.route('/tapes/<int:tape_id>/edit')
def tapes_edit(tape_id):
    try:
        tape = Tape.query.get_or_404(tape_id)
        artistas = Artista.query.order_by(Artista.nome).all()
        gravadoras = Gravadora.query.order_by(Gravadora.nome).all()
        etiquetas = Etiqueta.query.order_by(Etiqueta.nome).all()
        tipos_midia = []
        faixas = Faixa.query.filter_by(tape_id=tape.id).order_by(Faixa.lado.asc(), Faixa.numero.asc()).all()
        return render_template(
            'tapes_edit.html',
            tape=tape,
            faixas=faixas,
            artistas=artistas,
            gravadoras=gravadoras,
            etiquetas=etiquetas,
            tipos=tipos_midia
        )
    except Exception as e:
        logger.exception("Erro ao carregar edição de tape")
        return render_template('error.html', error=str(e)), 500

@catalogo_bp.route('/tapes/<int:tape_id>/view', endpoint='tapes_view')
def tapes_view(tape_id):
    try:
        tape = Tape.query.options(
            joinedload(Tape.artista),
            joinedload(Tape.gravadora),
            joinedload(Tape.etiqueta)
        ).get_or_404(tape_id)
        faixas = (Faixa.query
                  .filter_by(tape_id=tape.id)
                  .order_by(Faixa.lado.asc(), Faixa.numero.asc())
                  .all())
        tape.status = get_status(tape)
        return render_template('tapes_view.html', tape=tape, faixas=faixas)
    except Exception as e:
        logger.exception("Erro ao carregar visualização de tape")
        return render_template('error.html', error=str(e)), 500

@catalogo_bp.route('/musicas', endpoint='musicas_list')
def musicas_list():
    return render_template('musicas.html')

@catalogo_bp.route('/musicas/<int:musica_id>/view')
def musicas_view(musica_id):
    try:
        musica = Faixa.query.options(
            joinedload(Faixa.tape).joinedload(Tape.artista),
            joinedload(Faixa.tape).joinedload(Tape.gravadora)
        ).get_or_404(musica_id)
        return render_template('musicas_view.html', musica=musica)
    except Exception as e:
        logger.exception("Erro ao carregar visualização de música")
        return render_template('error.html', error=str(e)), 500

@catalogo_bp.route('/musicas/<int:musica_id>/edit', methods=['GET', 'POST'], endpoint='musicas_edit')
def musicas_edit(musica_id):
    try:
        faixa = Faixa.query.get_or_404(musica_id)
        if request.method == 'POST':
            musica_col = getattr(Faixa, 'musica', None) or getattr(Faixa, 'titulo', None)
            if musica_col is not None:
                setattr(faixa, musica_col.key, request.form.get('musica') or '')
            if hasattr(faixa, 'autor'):
                faixa.autor = request.form.get('autor') or None
            if hasattr(faixa, 'lado'):
                faixa.lado = request.form.get('lado') or None
            if hasattr(faixa, 'numero'):
                num = request.form.get('numero')
                faixa.numero = int(num) if num and num.isdigit() else faixa.numero
            if hasattr(faixa, 'isrc'):
                faixa.isrc = request.form.get('isrc') or None
            db.session.commit()
            return jsonify({"ok": True})
        return render_template('musicas_edit.html', musica=faixa)
    except Exception as e:
        logger.exception("Erro ao editar música")
        return jsonify({"ok": False, "error": str(e)}), 500

# === ROTAS DE API ===

@catalogo_bp.route('/api/search_tapes')
def api_search_tapes():
    try:
        termo = request.args.get('termo', '').strip()
        filtro = request.args.get('filtro', 'todos')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('limit', 30))
        sort_column = request.args.get('sort', 'id')
        sort_order = request.args.get('order', 'asc')

        query = Tape.query.outerjoin(Artista).outerjoin(Gravadora).options(
            joinedload(Tape.artista),
            joinedload(Tape.gravadora),
            joinedload(Tape.etiqueta)
        )

        if filtro == 'on_stream':
            query = query.filter(Tape.subiu_streaming.is_(True))
        elif filtro == 'digitalizada':
            query = query.filter(Tape.digitalizada.is_(True))
        elif filtro == 'nao_pode_subir':
            query = query.filter(Tape.nao_pode_subir.is_(True))
        elif filtro == 'not_stream':
            query = query.filter(Tape.subiu_streaming.isnot(True))

        if termo:
            query = query.filter(
                or_(
                    Tape.titulo.ilike(f'%{termo}%'),
                    Tape.numero_tape.ilike(f'%{termo}%'),
                    Artista.nome.ilike(f'%{termo}%'),
                    Gravadora.nome.ilike(f'%{termo}%')
                )
            )

        sort_map = {
            'id': Tape.id,
            'titulo': Tape.titulo,
            'numero_tape': Tape.numero_tape,
            'artista': Artista.nome,
            'gravadora': Gravadora.nome,
            'status': None
        }

        if sort_column == 'status':
            status_case = case(
                (Tape.subiu_streaming == True, 3),
                (Tape.digitalizada == True, 2),
                (Tape.nao_pode_subir == True, 1),
                else_=0
            )
            if sort_order == 'desc':
                query = query.order_by(status_case.desc())
            else:
                query = query.order_by(status_case.asc())
        else:
            column = sort_map.get(sort_column, Tape.id)
            if column is not None:
                if sort_order == 'desc':
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        tapes_data = []
        for tape in paginated.items:
            tapes_data.append({
                'id': tape.id,
                'titulo': tape.titulo,
                'numero_tape': tape.numero_tape,
                'artista': {'id': tape.artista.id, 'nome': tape.artista.nome} if tape.artista else None,
                'gravadora': {'id': tape.gravadora.id, 'nome': tape.gravadora.nome} if tape.gravadora else None,
                'status': get_status(tape),
                'etiqueta': tape.etiqueta.nome if tape.etiqueta else '',
            })

        return jsonify({
            "ok": True,
            "data": {
                'tapes': tapes_data,
                'total_paginas': paginated.pages,
                'pagina_atual': paginated.page,
                'total_registros': paginated.total
            }
        })
    except SQLAlchemyError as e:
        logger.exception("Erro SQLAlchemy em /api/search_tapes")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        logger.exception("Erro inesperado em /api/search_tapes")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/tapes/<int:tape_id>', methods=['PUT'])
def api_update_tape(tape_id):
    try:
        data = request.get_json(silent=True) or {}
        tape = Tape.query.get_or_404(tape_id)

        def parse_bool(value):
            if value is None:
                return None
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                v = value.strip().lower()
                if v in ("true", "1", "on", "sim", "yes", "y"):
                    return True
                if v in ("false", "0", "off", "nao", "não", "no", "n"):
                    return False
            return bool(value)

        applied = {}

        # Atualiza campos do Tape
        if 'titulo' in data and data['titulo'] is not None:
            tape.titulo = data['titulo']
            applied['titulo'] = tape.titulo
        if 'numero_tape' in data and data['numero_tape'] is not None:
            tape.numero_tape = data['numero_tape']
            applied['numero_tape'] = tape.numero_tape
        if 'artista_id' in data and data['artista_id'] is not None:
            tape.artista_id = data['artista_id']
            applied['artista_id'] = tape.artista_id
        if 'gravadora_id' in data and data['gravadora_id'] is not None:
            tape.gravadora_id = data['gravadora_id']
            applied['gravadora_id'] = tape.gravadora_id
        if 'etiqueta_id' in data and data['etiqueta_id'] is not None:
            tape.etiqueta_id = data['etiqueta_id']
            applied['etiqueta_id'] = tape.etiqueta_id
        if 'tipo_midia_id' in data and data['tipo_midia_id'] is not None:
            tape.tipo_midia_id = data['tipo_midia_id']
            applied['tipo_midia_id'] = tape.tipo_midia_id

        # Booleans
        if 'on_stream' in data and data['on_stream'] is not None:
            tape.subiu_streaming = parse_bool(data['on_stream'])
            applied['subiu_streaming(from_on_stream)'] = tape.subiu_streaming
        elif 'subiu_streaming' in data and data['subiu_streaming'] is not None:
            tape.subiu_streaming = parse_bool(data['subiu_streaming'])
            applied['subiu_streaming'] = tape.subiu_streaming
        elif 'stream' in data and data['stream'] is not None:
            tape.subiu_streaming = parse_bool(data['stream'])
            applied['subiu_streaming(from_stream)'] = tape.subiu_streaming

        if 'digitalizada' in data and data['digitalizada'] is not None:
            tape.digitalizada = parse_bool(data['digitalizada'])
            applied['digitalizada'] = tape.digitalizada
        if 'nao_pode_subir' in data and data['nao_pode_subir'] is not None:
            tape.nao_pode_subir = parse_bool(data['nao_pode_subir'])
            applied['nao_pode_subir'] = tape.nao_pode_subir
        if 'status' in data and data['status'] is not None and hasattr(tape, "status"):
            tape.status = data['status']
            applied['status'] = tape.status

        # Processar faixas
        faixas_enviadas = data.get('faixas', [])
        ids_na_requisicao = {f.get('id') for f in faixas_enviadas if f.get('id')}

        for faixa in list(tape.faixas):
            if faixa.id not in ids_na_requisicao:
                db.session.delete(faixa)

        for idx, faixa_data in enumerate(faixas_enviadas):
            if faixa_data.get('id'):
                faixa = db.session.get(Faixa, faixa_data['id'])
                if faixa:
                    if faixa.tape_id != tape.id:
                        return jsonify({"ok": False, "error": f"Faixa {faixa.id} não pertence ao tape {tape.id}."}), 400
                    if 'numero' in faixa_data and faixa_data['numero'] is not None:
                        try:
                            faixa.numero = int(str(faixa_data['numero']).strip())
                        except (TypeError, ValueError):
                            return jsonify({"ok": False, "error": f"O número da faixa (posição {idx+1}) deve ser inteiro."}), 400
                    if 'lado' in faixa_data and faixa_data['lado'] is not None:
                        faixa.lado = faixa_data['lado']
                    if 'musica' in faixa_data and faixa_data['musica'] is not None:
                        faixa.musica = faixa_data['musica']
                    if 'autor' in faixa_data and faixa_data['autor'] is not None:
                        faixa.autor = faixa_data['autor']
            else:
                numero = faixa_data.get('numero')
                if numero is None:
                    return jsonify({"ok": False, "error": f"O número da faixa (posição {idx+1}) é obrigatório."}), 400
                try:
                    numero = int(str(numero).strip())
                except (TypeError, ValueError):
                    return jsonify({"ok": False, "error": f"O número da faixa (posição {idx+1}) deve ser um número inteiro."}), 400

                nova_faixa = Faixa(
                    tape_id=tape.id,
                    numero=numero,
                    lado=faixa_data.get('lado'),
                    musica=faixa_data.get('musica'),
                    autor=faixa_data.get('autor')
                )
                db.session.add(nova_faixa)

        db.session.commit()

        return jsonify({
            "ok": True,
            "data": {
                "message": "Tape atualizado com sucesso",
                "tape_id": tape.id,
                "applied": applied,
                "subiu_streaming": tape.subiu_streaming
            }
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/tapes/<int:tape_id> PUT")
        return jsonify({"ok": False, "error": "Erro de banco de dados", "details": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/tapes/<int:tape_id> PUT")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/dashboard_data')
def dashboard_data():
    try:
        stats = {
            'on_stream': Tape.query.filter_by(subiu_streaming=True).count(),
            'not_stream': Tape.query.filter_by(nao_pode_subir=True).count(),
            'digitalizada': Tape.query.filter_by(digitalizada=True).count(),
            'nao_subiu': Tape.query.filter(
                Tape.subiu_streaming == False,
                Tape.nao_pode_subir == False,
                Tape.digitalizada == False
            ).count(),
            'total': Tape.query.count()
        }
        return jsonify({
            "ok": True,
            "data": {
                'stats': stats,
                'labels': ['On Stream', 'Not Stream', 'Digitalizada', 'Ainda não subiu']
            }
        })
    except SQLAlchemyError as e:
        logger.exception("Erro SQLAlchemy em /api/dashboard_data")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        logger.exception("Erro inesperado em /api/dashboard_data")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/stats/top_artistas_faixas')
def api_top_artistas_faixas():
    try:
        results = db.session.query(
            Artista.nome,
            func.count(Faixa.id).label('total_faixas')
        ).join(Tape, Tape.artista_id == Artista.id)\
         .join(Faixa, Faixa.tape_id == Tape.id)\
         .group_by(Artista.nome)\
         .order_by(func.count(Faixa.id).desc())\
         .limit(8).all()

        data = [{'nome': r[0], 'qtd': r[1]} for r in results]
        return jsonify({"ok": True, "data": data})
    except SQLAlchemyError as e:
        logger.exception("Erro SQLAlchemy em /api/stats/top_artistas_faixas")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        logger.exception("Erro inesperado em /api/stats/top_artistas_faixas")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/tapes/<int:tape_id>', methods=['GET'])
def api_get_tape(tape_id):
    try:
        tape = Tape.query.options(joinedload(Tape.faixas)).get_or_404(tape_id)

        def faixa_to_dict(f):
            return {
                'id': f.id,
                'faixa': f.numero,
                'lado': f.lado,
                'titulo': f.musica,
                'autor': f.autor,
            }

        payload = {
            'id': tape.id,
            'titulo': tape.titulo,
            'numero_tape': tape.numero_tape,
            'artista_id': tape.artista_id,
            'gravadora_id': tape.gravadora_id,
            'etiqueta_id': tape.etiqueta_id,
            'subiu_streaming': tape.subiu_streaming,
            'digitalizada': tape.digitalizada,
            'nao_pode_subir': tape.nao_pode_subir,
            'status': get_status(tape),
            'produtor_musical': tape.produtor_musical,
            'codigo_barras': tape.codigo_barras,
            'quantidade': tape.quantidade,
            'preco': tape.preco,
            'observacao': tape.observacao,
            'faixas': [faixa_to_dict(f) for f in tape.faixas]
        }
        return jsonify({"ok": True, "data": payload})
    except SQLAlchemyError as e:
        logger.exception("Erro SQLAlchemy em /api/tapes/<int:tape_id> GET")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        logger.exception("Erro inesperado em /api/tapes/<int:tape_id> GET")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/artistas', methods=['GET', 'POST'])
def api_artistas():
    try:
        if request.method == 'GET':
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('limit', 30, type=int)
            termo = request.args.get('termo', '')
            query = Artista.query.order_by(Artista.nome.asc())
            if termo:
                query = query.filter(Artista.nome.ilike(f'%{termo}%'))
            paginated = query.paginate(page=page, per_page=per_page, error_out=False)
            artistas_data = [{'id': a.id, 'nome': a.nome} for a in paginated.items]
            return jsonify({
                "ok": True,
                "data": {
                    'artistas': artistas_data,
                    'total_paginas': paginated.pages,
                    'pagina_atual': paginated.page,
                    'total_registros': paginated.total
                }
            })
        elif request.method == 'POST':
            data = request.get_json()
            novo_artista = Artista(nome=data['nome'])
            db.session.add(novo_artista)
            db.session.commit()
            return jsonify({"ok": True, "data": {'id': novo_artista.id, 'nome': novo_artista.nome}}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/artistas")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/artistas")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/artistas/<int:id>', methods=['PUT', 'DELETE'])
def api_artista(id):
    try:
        artista = Artista.query.get_or_404(id)
        if request.method == 'PUT':
            data = request.get_json()
            artista.nome = data['nome']
            db.session.commit()
            return jsonify({"ok": True, "data": {'id': artista.id, 'nome': artista.nome}})
        elif request.method == 'DELETE':
            db.session.delete(artista)
            db.session.commit()
            return '', 204
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/artistas/<int:id>")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/artistas/<int:id>")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/gravadoras', methods=['GET', 'POST'])
def api_gravadoras():
    try:
        if request.method == 'GET':
            gravadoras = Gravadora.query.all()
            return jsonify({
                "ok": True,
                "data": [{'id': g.id, 'nome': g.nome} for g in gravadoras]
            })
        elif request.method == 'POST':
            data = request.get_json()
            nova_gravadora = Gravadora(nome=data['nome'])
            db.session.add(nova_gravadora)
            db.session.commit()
            return jsonify({"ok": True, "data": {'id': nova_gravadora.id, 'nome': nova_gravadora.nome}}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/gravadoras")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/gravadoras")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/gravadoras/<int:id>', methods=['PUT', 'DELETE'])
def api_gravadora(id):
    try:
        gravadora = Gravadora.query.get_or_404(id)
        if request.method == 'PUT':
            data = request.get_json()
            gravadora.nome = data['nome']
            db.session.commit()
            return jsonify({"ok": True, "data": {'id': gravadora.id, 'nome': gravadora.nome}})
        elif request.method == 'DELETE':
            db.session.delete(gravadora)
            db.session.commit()
            return '', 204
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/gravadoras/<int:id>")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/gravadoras/<int:id>")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/etiquetas', methods=['GET', 'POST'])
def api_etiquetas():
    try:
        if request.method == 'GET':
            etiquetas = Etiqueta.query.all()
            return jsonify({
                "ok": True,
                "data": [{'id': e.id, 'nome': e.nome} for e in etiquetas]
            })
        elif request.method == 'POST':
            data = request.get_json()
            nova_etiqueta = Etiqueta(nome=data['nome'])
            db.session.add(nova_etiqueta)
            db.session.commit()
            return jsonify({"ok": True, "data": {'id': nova_etiqueta.id, 'nome': nova_etiqueta.nome}}), 201
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/etiquetas")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/etiquetas")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/etiquetas/<int:id>', methods=['PUT', 'DELETE'])
def api_etiqueta(id):
    try:
        etiqueta = Etiqueta.query.get_or_404(id)
        if request.method == 'PUT':
            data = request.get_json()
            etiqueta.nome = data['nome']
            db.session.commit()
            return jsonify({"ok": True, "data": {'id': etiqueta.id, 'nome': etiqueta.nome}})
        elif request.method == 'DELETE':
            db.session.delete(etiqueta)
            db.session.commit()
            return '', 204
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/etiquetas/<int:id>")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/etiquetas/<int:id>")
        return jsonify({"ok": False, "error": str(e)}), 500

def _tape_payload(t: Tape):
    return {
        "TapeID": t.id,
        "TituloTape": t.titulo,
        "NumeroTape": t.numero_tape,
        "Artista": t.artista.nome if t.artista else "",
        "Gravadora": t.gravadora.nome if t.gravadora else "",
        "Etiqueta": t.etiqueta.nome if t.etiqueta else "",
        "Produtor": t.produtor_musical or "",
        "StatusOnStream": bool(t.subiu_streaming),
        "StatusNotStream": bool(t.nao_pode_subir),
        "Digitalizada": bool(t.digitalizada),
        "CodigoBarras": t.codigo_barras or "",
        "Quantidade": t.quantidade or "",
        "Preco": t.preco or "",
        "Observacao": t.observacao or "",
    }

@catalogo_bp.route('/api/export/tapes', methods=['GET'])
def api_export_tapes():
    try:
        ids = request.args.get("ids", "").strip()
        export_all = request.args.get("export_all", "false").lower() == "true"

        q = Tape.query.options(
            joinedload(Tape.artista),
            joinedload(Tape.gravadora),
            joinedload(Tape.etiqueta),
            joinedload(Tape.faixas)
        )

        if not export_all and ids:
            ids_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
            q = q.filter(Tape.id.in_(ids_list))

        tapes = q.order_by(Tape.titulo.asc()).all()

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        writer.writerow([
            "TapeID","TituloTape","NumeroTape","Artista","Gravadora","Etiqueta",
            "Produtor","StatusOnStream","StatusNotStream","Digitalizada",
            "CodigoBarras","Quantidade","Preco","Observacao",
            "Faixa#","Lado","Música","Autor"
        ])

        for t in tapes:
            base = _tape_payload(t)
            if t.faixas:
                for f in t.faixas:
                    writer.writerow([
                        base["TapeID"], base["TituloTape"], base["NumeroTape"], base["Artista"], base["Gravadora"], base["Etiqueta"],
                        base["Produtor"], base["StatusOnStream"], base["StatusNotStream"], base["Digitalizada"],
                        base["CodigoBarras"], base["Quantidade"], base["Preco"], base["Observacao"],
                        f.numero, f.lado, f.musica, f.autor
                    ])
            else:
                writer.writerow([
                    base["TapeID"], base["TituloTape"], base["NumeroTape"], base["Artista"], base["Gravadora"], base["Etiqueta"],
                    base["Produtor"], base["StatusOnStream"], base["StatusNotStream"], base["Digitalizada"],
                    base["CodigoBarras"], base["Quantidade"], base["Preco"], base["Observacao"],
                    "", "", "", ""
                ])

        csv_data = output.getvalue()
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="tapes_export.csv"'}
        )
    except Exception as e:
        logger.exception("Erro ao exportar tapes")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/importar_catalogo', methods=['POST'])
def api_importar_catalogo():
    try:
        from importar_catalogo import importar, PARSED_DB_PATH
        data = request.get_json(force=True)
        if data.get("parsed_db_path"):
            import importar_catalogo
            importar_catalogo.PARSED_DB_PATH = data["parsed_db_path"]
        importar()
        return jsonify({"ok": True})
    except ImportError as e:
        logger.exception("Módulo de importação não encontrado")
        return jsonify({"ok": False, "error": "Módulo de importação não encontrado"}), 500
    except Exception as e:
        logger.exception("Erro na importação")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/search_musicas', endpoint='api_search_musicas')
def api_search_musicas():
    try:
        termo = (request.args.get('termo') or '').strip()
        campo = (request.args.get('campo') or 'todos').strip().lower()
        page = int(request.args.get('page') or 1)
        limit = int(request.args.get('limit') or 25)
        sort = (request.args.get('sort') or 'id').strip().lower()
        order = (request.args.get('order') or 'desc').strip().lower()

        if page < 1:
            page = 1
        if limit < 1:
            limit = 25
        if limit > 200:
            limit = 200

        query = Faixa.query.options(
            joinedload(Faixa.tape).joinedload(Tape.artista)
        )

        if termo:
            like = f"%{termo}%"
            musica_col = getattr(Faixa, 'musica', None) or getattr(Faixa, 'titulo', None)
            autor_col = getattr(Faixa, 'autor', None)
            isrc_col  = getattr(Faixa, 'isrc', None)
            tape_titulo_col = getattr(Tape, 'titulo', None)
            tape_numero_col = getattr(Tape, 'numero_tape', None)

            conditions = []

            def add_if(col):
                if col is not None:
                    conditions.append(col.ilike(like))

            if campo == 'musica':
                add_if(musica_col)
                add_if(autor_col)
            elif campo == 'isrc':
                add_if(isrc_col)
            elif campo == 'tape':
                if tape_titulo_col is not None:
                    conditions.append(tape_titulo_col.ilike(like))
                if tape_numero_col is not None:
                    conditions.append(tape_numero_col.ilike(like))
            elif campo == 'artista':
                conditions.append(Artista.nome.ilike(like))
            else:
                add_if(musica_col)
                add_if(autor_col)
                add_if(isrc_col)
                if tape_titulo_col is not None:
                    conditions.append(tape_titulo_col.ilike(like))
                if tape_numero_col is not None:
                    conditions.append(tape_numero_col.ilike(like))
                conditions.append(Artista.nome.ilike(like))

            query = query.join(Faixa.tape).outerjoin(Tape.artista).filter(or_(*conditions))

        # Ordenação
        query = query.join(Faixa.tape).outerjoin(Tape.artista)
        sort_map = {
            'id': Faixa.id,
            'musica': getattr(Faixa, 'musica', None) or getattr(Faixa, 'titulo', Faixa.id),
            'artista': Artista.nome,
            'tape': Tape.titulo,
            'lado': getattr(Faixa, 'lado', Faixa.id),
            'numero': getattr(Faixa, 'numero', Faixa.id),
            'isrc': getattr(Faixa, 'isrc', Faixa.id),
        }
        sort_col = sort_map.get(sort, Faixa.id)
        if order == 'asc':
            query = query.order_by(asc(sort_col))
        else:
            query = query.order_by(desc(sort_col))

        total_registros = query.count()
        total_paginas = max(1, (total_registros + limit - 1) // limit)
        if page > total_paginas:
            page = total_paginas

        itens = query.offset((page - 1) * limit).limit(limit).all()

        def to_dict(f: Faixa):
            musica_val = getattr(f, 'musica', None) or getattr(f, 'titulo', None) or ''
            tape = f.tape
            artista_nome = (tape.artista.nome if tape and tape.artista else None)
            return {
                "id": f.id,
                "musica": musica_val,
                "autor": getattr(f, 'autor', None),
                "lado": getattr(f, 'lado', None),
                "numero": getattr(f, 'numero', None),
                "isrc": getattr(f, 'isrc', None),
                "artista": ({"nome": artista_nome} if artista_nome else None),
                "tape": (
                    {
                        "id": tape.id,
                        "titulo": tape.titulo,
                        "numero_tape": tape.numero_tape
                    } if tape else None
                ),
                "numero_tape": (tape.numero_tape if tape else None),
                "tape_titulo": (tape.titulo if tape else None),
            }

        return jsonify({
            "ok": True,
            "data": {
                "musicas": [to_dict(x) for x in itens],
                "pagina_atual": page,
                "total_paginas": total_paginas,
                "total_registros": total_registros
            }
        })
    except SQLAlchemyError as e:
        logger.exception("Erro SQLAlchemy em /api/search_musicas")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        logger.exception("Erro inesperado em /api/search_musicas")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/musicas/<int:musica_id>', methods=['DELETE'], endpoint='api_delete_musica')
def api_delete_musica(musica_id):
    try:
        faixa = Faixa.query.get_or_404(musica_id)
        db.session.delete(faixa)
        db.session.commit()
        return '', 204
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception("Erro SQLAlchemy em /api/musicas/<int:musica_id> DELETE")
        return jsonify({"ok": False, "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro inesperado em /api/musicas/<int:musica_id> DELETE")
        return jsonify({"ok": False, "error": str(e)}), 500

@catalogo_bp.route('/api/export_musicas', endpoint='api_export_musicas')
def api_export_musicas():
    try:
        q = Faixa.query.options(joinedload(Faixa.tape).joinedload(Tape.artista)).all()
        si = io.StringIO()
        w = csv.writer(si, delimiter=';')
        w.writerow(["id", "musica", "autor", "lado", "numero", "isrc", "tape_id", "tape_titulo", "numero_tape", "artista"])

        for f in q:
            musica_val = getattr(f, 'musica', None) or getattr(f, 'titulo', None) or ''
            tape = f.tape
            artista = (tape.artista.nome if tape and tape.artista else '')
            w.writerow([
                f.id, musica_val, getattr(f, 'autor', ''), getattr(f, 'lado', ''), getattr(f, 'numero', ''),
                getattr(f, 'isrc', ''), tape.id if tape else '', tape.titulo if tape else '', tape.numero_tape if tape else '', artista
            ])

        output = si.getvalue()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=musicas.csv"}
        )
    except Exception as e:
        logger.exception("Erro ao exportar músicas")
        return jsonify({"ok": False, "error": str(e)}), 500

# === Registro do blueprint ===
app.register_blueprint(catalogo_bp)

# === Inicialização do banco de dados (cria tabelas se não existirem) ===
with app.app_context():
    try:
        db.create_all()
        logger.info("Tabelas verificadas/criadas com sucesso.")
    except Exception as e:
        logger.exception("Erro ao criar tabelas:")
        # Não levanta exceção para não impedir o startup, mas loga o erro.

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5005))
    app.run(host='0.0.0.0', port=port, debug=False)
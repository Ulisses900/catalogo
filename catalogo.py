from flask import Flask, render_template, request, jsonify, Blueprint, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import case
from datetime import datetime
from sqlalchemy import func
from sqlalchemy import or_, asc, desc
from werkzeug.exceptions import BadRequest
import os
import csv
import io
from flask import request, jsonify
from sqlalchemy.exc import SQLAlchemyError

# Importa os modelos do arquivo models.py (certifique-se de que está no mesmo diretório)
from models import db, Artista, Gravadora, Etiqueta, Tape, Faixa

app = Flask(__name__)

# Configuração do banco de dados (use o mesmo caminho do seu banco)

# Configuração do banco de dados (use o mesmo caminho do seu banco)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SECRET_KEY'] = '02236d8caf4faa926da6b83aea5b4668f0edd2131bc0025e6f95c253344c32c7'

# Inicializa o SQLAlchemy com a aplicação (o db já vem do models.py, mas precisa ser associado ao app)
db.init_app(app)

# Blueprint
catalogo_bp = Blueprint('catalogo', __name__)

# Função auxiliar para status (inalterada)
def get_status(tape):
    if tape.subiu_streaming is True:
        return 'on_stream'
    if tape.digitalizada is True:
        return 'digitalizada'
    # OFF stream quando "não pode subir" OU quando ainda não subiu (padrão)
    return 'not_stream'

# Rotas de visualização (mantidas iguais, mas os templates podem precisar de ajustes)
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

@catalogo_bp.route('/tapes')
def tapes():
    return render_template('tapes.html')

@catalogo_bp.route('/tapes/<int:tape_id>/edit')
def tapes_edit(tape_id):
    tape = Tape.query.get_or_404(tape_id)
    artistas = Artista.query.order_by(Artista.nome).all()
    gravadoras = Gravadora.query.order_by(Gravadora.nome).all()
    etiquetas = Etiqueta.query.order_by(Etiqueta.nome).all()
    # Como não há mais TipoMidia, removemos a variável 'tipos' do template.
    # Se o template esperar essa variável, você precisará ajustá-lo ou passar uma lista vazia.
    # Aqui vamos passar uma lista vazia para não quebrar o template existente.
    tipos_midia = []  # removido

    faixas = Faixa.query.filter_by(tape_id=tape.id).order_by(Faixa.lado.asc(), Faixa.numero.asc()).all()
    return render_template(
        'tapes_edit.html',
        tape=tape,
        faixas=faixas,
        artistas=artistas,
        gravadoras=gravadoras,
        etiquetas=etiquetas,
        tipos=tipos_midia  # lista vazia; se o template usar, ele não encontrará opções
    )

# ---------- ROTAS DE API ----------

@catalogo_bp.route('/api/search_tapes')
def api_search_tapes():
    termo = request.args.get('termo', '').strip()
    filtro = request.args.get('filtro', 'todos')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('limit', 30))
    sort_column = request.args.get('sort', 'id')
    sort_order = request.args.get('order', 'asc')

    # Query base com joins (usando os modelos importados)
    query = Tape.query.outerjoin(Artista).outerjoin(Gravadora).options(
        joinedload(Tape.artista),
        joinedload(Tape.gravadora),
        joinedload(Tape.etiqueta)
    )

    # Filtros de status
    if filtro == 'on_stream':
        query = query.filter(Tape.subiu_streaming.is_(True))

    elif filtro == 'digitalizada':
        query = query.filter(Tape.digitalizada.is_(True))

    elif filtro == 'nao_pode_subir':
        query = query.filter(Tape.nao_pode_subir.is_(True))

    elif filtro == 'not_stream':
        # OFF stream = não subiu (0 ou NULL)
        query = query.filter(Tape.subiu_streaming.isnot(True))

    elif filtro == 'todos':
        pass

    # Busca por termo
    if termo:
        query = query.filter(
            db.or_(
                Tape.titulo.ilike(f'%{termo}%'),
                Tape.numero_tape.ilike(f'%{termo}%'),
                Artista.nome.ilike(f'%{termo}%'),
                Gravadora.nome.ilike(f'%{termo}%')
            )
        )

    # Mapeamento de ordenação
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
            (Tape.subiu_streaming == True, 3),     # on
            (Tape.digitalizada == True, 2),        # digital
            (Tape.nao_pode_subir == True, 1),      # restrito
            else_=0                                # off
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
            # Se quiser incluir os novos campos do models.py, adicione aqui:
            # 'produtor_musical': tape.produtor_musical,
            # 'codigo_barras': tape.codigo_barras,
            # etc.
        })

    return jsonify({
        'tapes': tapes_data,
        'total_paginas': paginated.pages,
        'pagina_atual': paginated.page,
        'total_registros': paginated.total
    })


@catalogo_bp.route('/api/tapes/<int:tape_id>', methods=['PUT'])
def api_update_tape(tape_id):
    try:
        data = request.get_json(silent=True) or {}
        tape = Tape.query.get_or_404(tape_id)

        print("🟦 [api_update_tape] tape_id:", tape_id)
        print("🟦 [api_update_tape] payload:", data)

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

        # =========================
        # Atualiza campos do Tape (só se veio e não é null)
        # =========================
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

        # Se você tiver tipo_midia_id no model e quiser atualizar:
        if 'tipo_midia_id' in data and data['tipo_midia_id'] is not None:
            tape.tipo_midia_id = data['tipo_midia_id']
            applied['tipo_midia_id'] = tape.tipo_midia_id

        # Booleans (aceita false)
        # Seu front manda: on_stream
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

        # Se seu front manda "status" e você quer salvar:
        if 'status' in data and data['status'] is not None and hasattr(tape, "status"):
            tape.status = data['status']
            applied['status'] = tape.status

        # =========================
        # Processar faixas (compatível com seu payload)
        # payload atual usa: numero, lado, musica, autor, id
        # =========================
        faixas_enviadas = data.get('faixas', [])
        ids_na_requisicao = {f.get('id') for f in faixas_enviadas if f.get('id')}

        # Remove faixas que não vieram na requisição
        for faixa in list(tape.faixas):
            if faixa.id not in ids_na_requisicao:
                db.session.delete(faixa)

        # Atualiza ou cria faixas
        for idx, faixa_data in enumerate(faixas_enviadas):
            if faixa_data.get('id'):
                faixa = db.session.get(Faixa, faixa_data['id'])
                if faixa:
                    # segurança: faixa precisa ser desse tape
                    if faixa.tape_id != tape.id:
                        return jsonify({"error": f"Faixa {faixa.id} não pertence ao tape {tape.id}."}), 400

                    # Só altera se foi enviado e não é null
                    if 'numero' in faixa_data and faixa_data['numero'] is not None:
                        # aceita "01" e converte pra int se seu model for int
                        try:
                            faixa.numero = int(str(faixa_data['numero']).strip())
                        except (TypeError, ValueError):
                            return jsonify({"error": f"O número da faixa (posição {idx+1}) deve ser inteiro."}), 400

                    if 'lado' in faixa_data and faixa_data['lado'] is not None:
                        faixa.lado = faixa_data['lado']

                    if 'musica' in faixa_data and faixa_data['musica'] is not None:
                        faixa.musica = faixa_data['musica']

                    if 'autor' in faixa_data and faixa_data['autor'] is not None:
                        faixa.autor = faixa_data['autor']

            else:
                # Nova faixa: exige número obrigatório
                numero = faixa_data.get('numero')
                if numero is None:
                    return jsonify({"error": f"O número da faixa (posição {idx+1}) é obrigatório."}), 400
                try:
                    numero = int(str(numero).strip())
                except (TypeError, ValueError):
                    return jsonify({"error": f"O número da faixa (posição {idx+1}) deve ser um número inteiro."}), 400

                nova_faixa = Faixa(
                    tape_id=tape.id,
                    numero=numero,
                    lado=faixa_data.get('lado'),
                    musica=faixa_data.get('musica'),
                    autor=faixa_data.get('autor')
                )
                db.session.add(nova_faixa)

        db.session.commit()

        print("✅ [api_update_tape] applied:", applied)

        return jsonify({
            "message": "Tape atualizado com sucesso",
            "tape_id": tape.id,
            "applied": applied,
            "subiu_streaming": tape.subiu_streaming
        }), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": "Erro de banco de dados", "details": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@catalogo_bp.route('/api/dashboard_data')
def dashboard_data():
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
        'stats': stats,
        'labels': ['On Stream', 'Not Stream', 'Digitalizada', 'Ainda não subiu']
    })

@catalogo_bp.route('/api/stats/top_artistas_faixas')
def api_top_artistas_faixas():
    # Consulta: Nome do Artista e Contagem de Faixas vinculadas a ele através dos Tapes
    results = db.session.query(
        Artista.nome,
        func.count(Faixa.id).label('total_faixas')
    ).join(Tape, Tape.artista_id == Artista.id)\
     .join(Faixa, Faixa.tape_id == Tape.id)\
     .group_by(Artista.nome)\
     .order_by(func.count(Faixa.id).desc())\
     .limit(8).all()

    return jsonify([{'nome': r[0], 'qtd': r[1]} for r in results])

@catalogo_bp.route('/api/tapes/<int:tape_id>', methods=['GET'])
def api_get_tape(tape_id):
    tape = Tape.query.options(joinedload(Tape.faixas)).get_or_404(tape_id)

    def faixa_to_dict(f):
        return {
            'id': f.id,
            'faixa': f.numero,
            'lado': f.lado,
            'titulo': f.musica,
            'autor': f.autor,
            # Se quiser incluir editora e percentual:
            # 'editora': f.editora,
            # 'percentual': f.percentual,
        }

    payload = {
        'id': tape.id,
        'titulo': tape.titulo,
        'numero_tape': tape.numero_tape,
        'artista_id': tape.artista_id,
        'gravadora_id': tape.gravadora_id,
        'etiqueta_id': tape.etiqueta_id,
        # 'tipo_midia_id' foi removido – se o front-end esperar esse campo, ele receberá null ou terá que ser ajustado
        'subiu_streaming': tape.subiu_streaming,
        'digitalizada': tape.digitalizada,
        'nao_pode_subir': tape.nao_pode_subir,
        'status': get_status(tape),
        # Outros campos do models.py podem ser adicionados aqui, se necessário
        'produtor_musical': tape.produtor_musical,
        'codigo_barras': tape.codigo_barras,
        'quantidade': tape.quantidade,
        'preco': tape.preco,
        'observacao': tape.observacao,
        'faixas': [faixa_to_dict(f) for f in tape.faixas]
    }
    return jsonify(payload)

# Rotas de API para Artistas, Gravadoras, Etiquetas (mantidas, mas com os modelos corretos)
@catalogo_bp.route('/api/artistas', methods=['GET', 'POST'])
def api_artistas():
    if request.method == 'GET':
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('limit', 30, type=int)
        termo = request.args.get('termo', '')
        query = Artista.query.order_by(Artista.nome.asc())
        if termo:
            query = query.filter(Artista.nome.ilike(f'%{termo}%'))
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        artistas_data = [{'id': a.id, 'nome': a.nome} for a in paginated.items]  # 'funcao' não existe no models.py
        return jsonify({
            'artistas': artistas_data,
            'total_paginas': paginated.pages,
            'pagina_atual': paginated.page,
            'total_registros': paginated.total
        })
    elif request.method == 'POST':
        data = request.get_json()
        novo_artista = Artista(nome=data['nome'])
        db.session.add(novo_artista)
        db.session.commit()
        return jsonify({'id': novo_artista.id, 'nome': novo_artista.nome}), 201

@catalogo_bp.route('/api/artistas/<int:id>', methods=['PUT', 'DELETE'])
def api_artista(id):
    artista = Artista.query.get_or_404(id)
    if request.method == 'PUT':
        data = request.get_json()
        artista.nome = data['nome']
        db.session.commit()
        return jsonify({'id': artista.id, 'nome': artista.nome})
    elif request.method == 'DELETE':
        db.session.delete(artista)
        db.session.commit()
        return '', 204

@catalogo_bp.route('/api/gravadoras', methods=['GET', 'POST'])
def api_gravadoras():
    if request.method == 'GET':
        gravadoras = Gravadora.query.all()
        return jsonify([{'id': g.id, 'nome': g.nome} for g in gravadoras])
    elif request.method == 'POST':
        data = request.get_json()
        nova_gravadora = Gravadora(nome=data['nome'])
        db.session.add(nova_gravadora)
        db.session.commit()
        return jsonify({'id': nova_gravadora.id, 'nome': nova_gravadora.nome}), 201

@catalogo_bp.route('/api/gravadoras/<int:id>', methods=['PUT', 'DELETE'])
def api_gravadora(id):
    gravadora = Gravadora.query.get_or_404(id)
    if request.method == 'PUT':
        data = request.get_json()
        gravadora.nome = data['nome']
        db.session.commit()
        return jsonify({'id': gravadora.id, 'nome': gravadora.nome})
    elif request.method == 'DELETE':
        db.session.delete(gravadora)
        db.session.commit()
        return '', 204

@catalogo_bp.route('/api/etiquetas', methods=['GET', 'POST'])
def api_etiquetas():
    if request.method == 'GET':
        etiquetas = Etiqueta.query.all()
        return jsonify([{'id': e.id, 'nome': e.nome} for e in etiquetas])
    elif request.method == 'POST':
        data = request.get_json()
        nova_etiqueta = Etiqueta(nome=data['nome'])
        db.session.add(nova_etiqueta)
        db.session.commit()
        return jsonify({'id': nova_etiqueta.id, 'nome': nova_etiqueta.nome}), 201

@catalogo_bp.route('/api/etiquetas/<int:id>', methods=['PUT', 'DELETE'])
def api_etiqueta(id):
    etiqueta = Etiqueta.query.get_or_404(id)
    if request.method == 'PUT':
        data = request.get_json()
        etiqueta.nome = data['nome']
        db.session.commit()
        return jsonify({'id': etiqueta.id, 'nome': etiqueta.nome})
    elif request.method == 'DELETE':
        db.session.delete(etiqueta)
        db.session.commit()
        return '', 204


@catalogo_bp.route('/tapes/<int:tape_id>/view', endpoint='tapes_view')
def tapes_view(tape_id):
    tape = Tape.query.options(
        joinedload(Tape.artista),
        joinedload(Tape.gravadora),
        joinedload(Tape.etiqueta)
    ).get_or_404(tape_id)

    faixas = (Faixa.query
              .filter_by(tape_id=tape.id)
              .order_by(Faixa.lado.asc(), Faixa.numero.asc())
              .all())

    print("\n" + "="*40)
    print("SISTEMA DE CATÁLOGO - DEBUG")
    print(f"Tape ID: {tape.id} - Título: {tape.titulo}")
    print(f"Quantidade de faixas encontradas: {len(faixas)}")
    for f in faixas:
        print(f"  -> ID: {f.id} | Música: {f.musica} | Lado: {f.lado} | Nº: {f.numero}")
    print("="*40 + "\n")

    tape.status = get_status(tape)
    return render_template('tapes_view.html', tape=tape, faixas=faixas)

# No seu catalogo.py, altere esta parte:
@catalogo_bp.route('/tapes', endpoint='tapes_list') # Adicionado endpoint='tapes_list'
def tapes():
    return render_template('tapes.html')

# As rotas para /api/midias e /api/agregadoras foram removidas, pois não existem no banco.
# Se o front-end chamá-las, você precisará removê-las do código JS ou criar versões que retornem listas vazias.

# Rota de exportação de tapes (adaptada)
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
        # Campos adicionais
        "CodigoBarras": t.codigo_barras or "",
        "Quantidade": t.quantidade or "",
        "Preco": t.preco or "",
        "Observacao": t.observacao or "",
    }

@catalogo_bp.route('/api/export/tapes', methods=['GET'])
def api_export_tapes():
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

    # Cabeçalho atualizado (sem Agregadora e Midia)
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

# Rota de importação (opcional, mantida mas verifique se o módulo importar_catalogo está adaptado)
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
    except ImportError:
        return jsonify({"ok": False, "erro": "Módulo de importação não encontrado"}), 500
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500
    
# Rotas de musicas
@catalogo_bp.route('/musicas', endpoint='musicas_list')
def musicas_list():
    """Tela principal de músicas (renderiza o HTML)."""
    return render_template('musicas.html')


@catalogo_bp.route('/api/search_musicas', endpoint='api_search_musicas')
def api_search_musicas():
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

    # ✅ Query base (SEM Faixa.artista)
    query = Faixa.query.options(
        joinedload(Faixa.tape).joinedload(Tape.artista)
    )

    # 🔎 Filtro de busca
    if termo:
        like = f"%{termo}%"

        # colunas da Faixa (ajuste se precisar)
        musica_col = getattr(Faixa, 'musica', None) or getattr(Faixa, 'titulo', None)
        autor_col = getattr(Faixa, 'autor', None)
        isrc_col  = getattr(Faixa, 'isrc', None)

        # colunas do Tape
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
            # artista vem do tape
            conditions.append(Artista.nome.ilike(like))

        else:
            # todos
            add_if(musica_col)
            add_if(autor_col)
            add_if(isrc_col)

            if tape_titulo_col is not None:
                conditions.append(tape_titulo_col.ilike(like))
            if tape_numero_col is not None:
                conditions.append(tape_numero_col.ilike(like))

            conditions.append(Artista.nome.ilike(like))

        # precisa join para filtrar por Tape/Artista
        query = query.join(Faixa.tape).outerjoin(Tape.artista).filter(or_(*conditions))

    # ✅ Ordenação
    # obs: tape/artista precisam join antes
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

    # ✅ Paginação
    total_registros = query.count()
    total_paginas = max(1, (total_registros + limit - 1) // limit)
    if page > total_paginas:
        page = total_paginas

    itens = query.offset((page - 1) * limit).limit(limit).all()

    # ✅ Serialização (artista SEMPRE do tape)
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
        "musicas": [to_dict(x) for x in itens],
        "pagina_atual": page,
        "total_paginas": total_paginas,
        "total_registros": total_registros
    })


@catalogo_bp.route('/api/musicas/<int:musica_id>', methods=['DELETE'], endpoint='api_delete_musica')
def api_delete_musica(musica_id):
    """Exclui uma música (faixa) do banco."""
    faixa = Faixa.query.get_or_404(musica_id)
    db.session.delete(faixa)
    db.session.commit()
    return jsonify({"ok": True})


# (Opcional) View simples
@catalogo_bp.route('/musicas/<int:musica_id>/view')
def musicas_view(musica_id):
    # CORREÇÃO: Carregamos a Tape primeiro, e através da Tape carregamos o Artista e Gravadora
    musica = Faixa.query.options(
        joinedload(Faixa.tape).joinedload(Tape.artista),
        joinedload(Faixa.tape).joinedload(Tape.gravadora)
    ).get_or_404(musica_id)
    
    return render_template('musicas_view.html', musica=musica)


# (Opcional) Edit simples (GET/POST)
@catalogo_bp.route('/musicas/<int:musica_id>/edit', methods=['GET', 'POST'], endpoint='musicas_edit')
def musicas_edit(musica_id):
    """Editar música (bem básico)."""
    faixa = Faixa.query.get_or_404(musica_id)

    if request.method == 'POST':
        # Ajuste os campos conforme seu model
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


# (Opcional) Export CSV simples
@catalogo_bp.route('/api/export_musicas', endpoint='api_export_musicas')
def api_export_musicas():
    import csv
    from io import StringIO
    from flask import Response

    q = Faixa.query.options(joinedload(Faixa.tape).joinedload(Tape.artista)).all()

    si = StringIO()
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
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=musicas.csv"})    

# Registro do blueprint
app.register_blueprint(catalogo_bp)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Isso criará as tabelas se não existirem, mas como você já tem o banco, não fará diferença.
        # Dados de exemplo (opcional, ajustado para o models.py)
        if not Artista.query.first():
            print("Adicionando dados de exemplo...")
            artista_ex = Artista(nome="Artista Exemplo")
            gravadora_ex = Gravadora(nome="Gravadora Exemplo")
            etiqueta_ex = Etiqueta(nome="Etiqueta Exemplo")
            db.session.add_all([artista_ex, gravadora_ex, etiqueta_ex])
            db.session.commit()
            tape_ex = Tape(
                titulo="Tape de Exemplo",
                artista=artista_ex,
                gravadora=gravadora_ex,
                etiqueta=etiqueta_ex,
                numero_tape="1234",
                subiu_streaming=True
            )
            db.session.add(tape_ex)
            db.session.commit()


    app.run(host='0.0.0.0', port=5005, debug=True)


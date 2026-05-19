import os
import base64
import hashlib
import hmac
import html
import re
import secrets
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import psycopg
import streamlit as st
from PIL import Image
from psycopg.rows import dict_row
from zoneinfo import ZoneInfo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from database.connection import get_connection, get_conn, reset_connection, SafeConnProxy, run_query
from utils.formatters import formatar_cnpj, formatar_cpf, validar_cnpj, validar_cpf
from utils.security import obter_secret, obter_admin_config, senha_esta_hasheada, gerar_hash_senha, verificar_senha
from utils.validators import validar_upload_imagem


st.set_page_config(page_title="Portal Business Vision", layout="wide")

BASE_DIR = Path(__file__).parent
APP_DATA_DIR = Path.home() / ".businessvision"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

logo_candidates = [
    BASE_DIR / "imagens" / "logo.png",
    BASE_DIR / "imagens" / "Logo.png",
    BASE_DIR / "Logo.png",
    BASE_DIR / "logo.png",
    BASE_DIR.parent / "Logo.png",
    BASE_DIR.parent / "logo.png",
]
logo_path = next((p for p in logo_candidates if p.exists()), None)

APP_TZ = ZoneInfo("America/Santarem")
conn = SafeConnProxy()

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390000
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
CONVITE_EXPIRACAO_HORAS = int(os.getenv("CONVITE_EXPIRACAO_HORAS", "72"))


def autenticar_usuario(usuario, senha):
    user = conn.execute(
        """
        SELECT *
        FROM usuarios
        WHERE usuario = %s AND ativo = TRUE
    """,
        (usuario,),
    ).fetchone()

    if not user:
        return None

    if not verificar_senha(senha, user["senha_hash"]):
        return None

    return user


def autenticar_admin(usuario_digitado, senha_digitada):
    config = obter_admin_config()
    admin_user = config["user"]
    admin_password_hash = config["password_hash"]
    admin_password_plain = config["password_plain"]

    if not admin_user or usuario_digitado != admin_user:
        return False

    if admin_password_hash:
        return verificar_senha(senha_digitada, admin_password_hash)

    if admin_password_plain:
        return hmac.compare_digest(admin_password_plain, senha_digitada or "")

    return False


def obter_cliente_por_usuario(usuario):
    return conn.execute(
        """
        SELECT id, usuario, senha, nome, ativo, cpf, empresa_id, funcao, email
        FROM clientes
        WHERE usuario = %s
        LIMIT 1
        """,
        (usuario,),
    ).fetchone()


def autenticar_cliente(usuario_digitado, senha_digitada):
    cliente = obter_cliente_por_usuario(usuario_digitado)

    if not cliente or not bool(cliente["ativo"]):
        return None

    senha_salva = cliente["senha"] or ""
    autenticado = verificar_senha(senha_digitada, senha_salva)

    if autenticado and not senha_esta_hasheada(senha_salva):
        conn.execute(
            "UPDATE clientes SET senha = %s WHERE id = %s",
            (gerar_hash_senha(senha_digitada), cliente["id"]),
        )
        cliente = obter_cliente_por_usuario(usuario_digitado)

    return cliente if autenticado else None


def obter_atendente_por_usuario(usuario):
    return conn.execute(
        """
        SELECT id, nome, usuario, senha, email, ativo, created_at
        FROM atendentes
        WHERE usuario = %s
        LIMIT 1
        """,
        (usuario,),
    ).fetchone()


def autenticar_atendente(usuario_digitado, senha_digitada):
    atendente = obter_atendente_por_usuario(usuario_digitado)
    if not atendente or not bool(atendente["ativo"]):
        return None

    if verificar_senha(senha_digitada, atendente["senha"] or ""):
        return atendente
    return None


admin_config = obter_admin_config()
admin_user = admin_config["user"]


def carregar_logo():
    try:
        if logo_path and logo_path.exists():
            return Image.open(logo_path)
    except Exception:
        pass
    return None


def carregar_logo_base64():
    try:
        if logo_path and logo_path.exists():
            return base64.b64encode(logo_path.read_bytes()).decode()
    except Exception:
        pass
    return None


logo = carregar_logo()
logo_b64 = carregar_logo_base64()


def agora():
    return datetime.now(APP_TZ)


def agora_str():
    return agora().strftime("%Y-%m-%d %H:%M:%S")


def coluna_existe(nome_tabela, nome_coluna):
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (nome_tabela, nome_coluna),
    ).fetchone()
    return row is not None


def criar_tabelas():
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS empresas (
            id BIGSERIAL PRIMARY KEY,
            cnpj TEXT,
            razao_social TEXT,
            fantasia TEXT,
            cep TEXT,
            logradouro TEXT,
            numero TEXT,
            bairro TEXT,
            cidade TEXT,
            ativo BOOLEAN DEFAULT TRUE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id BIGSERIAL PRIMARY KEY,
            usuario TEXT UNIQUE,
            senha TEXT,
            nome TEXT,
            ativo BOOLEAN DEFAULT TRUE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitacoes (
            id BIGSERIAL PRIMARY KEY,
            cliente TEXT,
            titulo TEXT,
            descricao TEXT,
            prioridade TEXT,
            status TEXT,
            complexidade TEXT,
            resposta TEXT,
            data_criacao TIMESTAMP,
            inicio_atendimento TIMESTAMP,
            fim_atendimento TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS anexos (
            id BIGSERIAL PRIMARY KEY,
            solicitacao_id BIGINT NOT NULL REFERENCES solicitacoes(id) ON DELETE CASCADE,
            nome_arquivo TEXT,
            observacao TEXT,
            imagem BYTEA,
            data_criacao TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessoes_login (
            token TEXT PRIMARY KEY,
            usuario TEXT NOT NULL,
            menu TEXT,
            perfil TEXT,
            data_criacao TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS atendentes (
            id BIGSERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            email TEXT,
            ativo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS convites_cadastro (
            id BIGSERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT NOT NULL,
            empresa_id BIGINT REFERENCES empresas(id),
            tipo_usuario TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pendente',
            observacao TEXT,
            usuario_sugerido TEXT,
            enviado_em TIMESTAMP,
            expiracao_em TIMESTAMP,
            utilizado_em TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    if not coluna_existe("clientes", "cpf"):
        conn.execute("ALTER TABLE clientes ADD COLUMN cpf TEXT")

    if not coluna_existe("clientes", "empresa_id"):
        conn.execute(
            "ALTER TABLE clientes ADD COLUMN empresa_id BIGINT REFERENCES empresas(id)"
        )

    if not coluna_existe("clientes", "funcao"):
        conn.execute("ALTER TABLE clientes ADD COLUMN funcao TEXT")

    if not coluna_existe("clientes", "email"):
        conn.execute("ALTER TABLE clientes ADD COLUMN email TEXT")

    if not coluna_existe("empresas", "ativo"):
        conn.execute("ALTER TABLE empresas ADD COLUMN ativo BOOLEAN DEFAULT TRUE")

    for coluna in [
        "cliente_id",
        "empresa_id",
        "atendente_id",
        "atribuido_em",
        "complexidade",
        "resposta",
        "data_criacao",
        "inicio_atendimento",
        "fim_atendimento",
    ]:
        if not coluna_existe("solicitacoes", coluna):
            if coluna in ["cliente_id", "empresa_id", "atendente_id"]:
                conn.execute(f"ALTER TABLE solicitacoes ADD COLUMN {coluna} BIGINT")
            elif coluna in [
                "data_criacao",
                "inicio_atendimento",
                "fim_atendimento",
                "atribuido_em",
            ]:
                conn.execute(f"ALTER TABLE solicitacoes ADD COLUMN {coluna} TIMESTAMP")
            else:
                conn.execute(f"ALTER TABLE solicitacoes ADD COLUMN {coluna} TEXT")

    if not coluna_existe("sessoes_login", "menu"):
        conn.execute("ALTER TABLE sessoes_login ADD COLUMN menu TEXT")
    if not coluna_existe("sessoes_login", "perfil"):
        conn.execute("ALTER TABLE sessoes_login ADD COLUMN perfil TEXT")

    if not coluna_existe("convites_cadastro", "observacao"):
        conn.execute("ALTER TABLE convites_cadastro ADD COLUMN observacao TEXT")
    if not coluna_existe("convites_cadastro", "usuario_sugerido"):
        conn.execute("ALTER TABLE convites_cadastro ADD COLUMN usuario_sugerido TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projetos_briefing (
            id BIGSERIAL PRIMARY KEY,
            empresa_id BIGINT REFERENCES empresas(id),
            cliente_id BIGINT REFERENCES clientes(id),
            titulo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            objetivo TEXT,
            prioridade TEXT,
            status TEXT DEFAULT 'Em análise',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projetos_etapas (
            id BIGSERIAL PRIMARY KEY,
            projeto_id BIGINT NOT NULL REFERENCES projetos_briefing(id) ON DELETE CASCADE,
            etapa TEXT NOT NULL,
            observacao TEXT,
            data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            visivel_cliente BOOLEAN DEFAULT TRUE
        )
        """
    )

    for coluna in ["objetivo", "prioridade", "atualizado_em"]:
        if not coluna_existe("projetos_briefing", coluna):
            if coluna == "atualizado_em":
                conn.execute(
                    "ALTER TABLE projetos_briefing ADD COLUMN atualizado_em TIMESTAMP"
                )
            else:
                conn.execute(f"ALTER TABLE projetos_briefing ADD COLUMN {coluna} TEXT")


RUN_DB_BOOTSTRAP = os.getenv("RUN_DB_BOOTSTRAP", "false").lower() == "true"
if RUN_DB_BOOTSTRAP:
    criar_tabelas()


def init_state():
    defaults = {
        "logado": False,
        "usuario": "",
        "perfil": "",
        "menu_atual": "Nova Solicitação",
        "titulo": "",
        "descricao": "",
        "mostrar_legenda": False,
        "limpar_campos_nova_solicitacao": False,
        "token_sessao": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def gerar_usuario(nome):
    partes = [p for p in re.split(r"\s+", (nome or "").strip().lower()) if p]
    if not partes:
        return ""
    usuario = f"{partes[0]}_{partes[-1]}" if len(partes) > 1 else partes[0]
    return re.sub(r"[^a-z0-9_]", "", usuario)


def criar_sessao_login(usuario, perfil, menu="Nova Solicitação"):
    token = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO sessoes_login (token, usuario, menu, perfil, data_criacao)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (token)
        DO UPDATE SET
            usuario = EXCLUDED.usuario,
            menu = EXCLUDED.menu,
            perfil = EXCLUDED.perfil,
            data_criacao = EXCLUDED.data_criacao
        """,
        (token, usuario, menu, perfil, agora()),
    )
    return token


def atualizar_menu_sessao(token, menu):
    if not token:
        return
    conn.execute(
        "UPDATE sessoes_login SET menu = %s WHERE token = %s",
        (menu, token),
    )


def obter_sessao(token):
    if not token:
        return None
    return conn.execute(
        "SELECT token, usuario, menu, perfil, data_criacao FROM sessoes_login WHERE token = %s",
        (token,),
    ).fetchone()


def excluir_sessao(token):
    if not token:
        return
    conn.execute("DELETE FROM sessoes_login WHERE token = %s", (token,))


def restaurar_login():
    token = st.query_params.get("token")
    if not token:
        return
    sessao = obter_sessao(token)
    if not sessao:
        return

    usuario = sessao["usuario"]
    perfil = sessao.get("perfil") or ""

    if perfil == "admin":
        usuario_admin = conn.execute(
            "SELECT usuario FROM usuarios WHERE usuario = %s AND perfil = 'admin' AND ativo = TRUE",
            (usuario,),
        ).fetchone()

        if not usuario_admin and usuario != admin_user:
            return
    elif perfil == "cliente":
        cliente = conn.execute(
            "SELECT usuario FROM clientes WHERE usuario = %s AND ativo = TRUE",
            (usuario,),
        ).fetchone()
        if not cliente:
            return
    elif perfil == "atendente":
        atendente = conn.execute(
            "SELECT usuario FROM atendentes WHERE usuario = %s AND ativo = TRUE",
            (usuario,),
        ).fetchone()
        if not atendente:
            return
    else:
        return

    st.session_state.logado = True
    st.session_state.usuario = usuario
    st.session_state.perfil = perfil
    st.session_state.menu_atual = sessao["menu"] or "Nova Solicitação"
    st.session_state.token_sessao = token


def persistir_query_params():
    if st.session_state.get("token_sessao"):
        st.query_params["token"] = st.session_state.token_sessao
    else:
        if "token" in st.query_params:
            del st.query_params["token"]


if not st.session_state.logado:
    restaurar_login()
    persistir_query_params()


def logout():
    token = st.session_state.get("token_sessao")
    excluir_sessao(token)
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()


def limpar_formulario():
    st.session_state.limpar_campos_nova_solicitacao = True
    st.rerun()


def nova_solicitacao():
    st.session_state.titulo = ""
    st.session_state.descricao = ""
    st.session_state.limpar_campos_nova_solicitacao = False
    st.rerun()


def enviar_email_convite(destinatario, nome, link):
    try:
        cfg = st.secrets["email"]

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Convite - Portal Business Vision"
        msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"] = destinatario

        html = f"""
        <html>
            <body style="font-family: Arial; background:#0B1E33; color:#EAF2FF; padding:20px;">
                <h2>Business Vision</h2>
                <p>Olá, {nome}.</p>
                <p>Você recebeu um convite para acessar o portal.</p>

                <a href="{link}" style="
                    display:inline-block;
                    padding:12px 20px;
                    background:#17427A;
                    color:#fff;
                    text-decoration:none;
                    border-radius:8px;
                    margin-top:10px;
                ">
                    Concluir cadastro
                </a>

                <p style="margin-top:20px; font-size:12px;">
                    Caso não funcione, copie o link abaixo:<br>
                    {link}
                </p>
            </body>
        </html>
        """

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_email"], destinatario, msg.as_string())

        return True

    except Exception as e:
        print("Erro envio email:", e)
        return False


def paginar_registros(registros, state_key, page_size=12):
    total = len(registros or [])
    if total <= page_size:
        return registros, 1, 1

    total_paginas = (total + page_size - 1) // page_size
    pagina_atual = int(st.session_state.get(state_key, 1) or 1)
    pagina_atual = max(1, min(pagina_atual, total_paginas))
    st.session_state[state_key] = pagina_atual

    inicio = (pagina_atual - 1) * page_size
    fim = inicio + page_size

    nav1, nav2, nav3 = st.columns([1, 1.3, 1])
    with nav1:
        if st.button(
            "← Anterior",
            key=f"{state_key}_prev",
            use_container_width=True,
            disabled=pagina_atual == 1,
        ):
            st.session_state[state_key] = pagina_atual - 1
            st.rerun()
    with nav2:
        st.caption(f"Página {pagina_atual} de {total_paginas} • {total} registros")
    with nav3:
        if st.button(
            "Próxima →",
            key=f"{state_key}_next",
            use_container_width=True,
            disabled=pagina_atual >= total_paginas,
        ):
            st.session_state[state_key] = pagina_atual + 1
            st.rerun()

    return registros[inicio:fim], pagina_atual, total_paginas


def salvar_etapa_projeto(solicitacao_id, status, titulo, observacao, atendente, visivel_cliente=True):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projeto_etapas 
            (solicitacao_id, status, titulo, observacao, atendente, visivel_cliente, criado_em)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (solicitacao_id, status, titulo, observacao, atendente, visivel_cliente)
        )

def buscar_etapas_projeto(solicitacao_id, cliente=False):
    with get_conn() as conn:
        if cliente:
            return conn.execute(
                """
                SELECT *
                FROM projeto_etapas
                WHERE solicitacao_id = %s
                  AND visivel_cliente = TRUE
                ORDER BY criado_em DESC
                """,
                (solicitacao_id,)
            ).fetchall()

        return conn.execute(
            """
            SELECT *
            FROM projeto_etapas
            WHERE solicitacao_id = %s
            ORDER BY criado_em DESC
            """,
            (solicitacao_id,)
        ).fetchall()
    

def normalizar_status(status):
    status = (status or "").strip()

    mapa = {
        "Pendente": "Em análise",
        "Novo": "Em análise",
        "Iniciado": "Em atendimento",
        "Em andamento": "Em atendimento",

        "Pausado": "Aguardando",
        "Aguardando cliente": "Aguardando",
        "Aguardando Cliente": "Aguardando",
        "Aguardando retorno": "Aguardando",
        "Aguardando": "Aguardando",

        "Resolvido": "Concluído",
        "Finalizado": "Concluído",
        "Finalizada": "Concluído",
        "Concluido": "Concluído",
        "Concluído": "Concluído",

        "Em análise": "Em análise",
        "Em atendimento": "Em atendimento",
    }

    return mapa.get(status, status)

def formatar_status_texto(status):
    return normalizar_status(status)

def status_badge_html(status):
    status = normalizar_status(status)

    cores = {
        "Em análise": "#FF5C7A",
        "Em atendimento": "#5EA8FF",
        "Aguardando": "#F5C451",
        "Concluído": "#43D17A",
    }

    cor = cores.get(status, "#AAB7C4")

    return (
        f'<span style="display:inline-flex;align-items:center;gap:7px;'
        f'padding:4px 9px;border-radius:999px;background:rgba(255,255,255,0.04);'
        f'border:1px solid rgba(120,145,170,0.18);color:{cor};'
        f'font-size:12px;font-weight:800;white-space:nowrap;">'
        f'<svg width="8" height="8" viewBox="0 0 8 8">'
        f'<circle cx="4" cy="4" r="4" fill="{cor}"/></svg>'
        f'{html.escape(status)}</span>'
    )


def obter_atendentes_ativos():
    return conn.execute(
        """
        SELECT id, nome, usuario, email, ativo, created_at
        FROM atendentes
        WHERE ativo = TRUE
        ORDER BY nome, usuario
        """
    ).fetchall()


def obter_todos_atendentes():
    return conn.execute(
        """
        SELECT id, nome, usuario, email, ativo, created_at
        FROM atendentes
        ORDER BY nome, usuario
        """
    ).fetchall()


def obter_clientes_ativos():
    return conn.execute(
        """
        SELECT usuario, nome
        FROM clientes
        WHERE ativo = TRUE
        ORDER BY nome, usuario
        """
    ).fetchall()


def obter_nome_cliente(usuario):
    row = conn.execute(
        "SELECT nome FROM clientes WHERE usuario = %s",
        (usuario,),
    ).fetchone()
    return row["nome"] if row and row["nome"] else usuario


def atualizar_solicitacao(solicitacao_id, novo_status, observacao):
    novo_status = normalizar_status(novo_status)

    atual = conn.execute(
        """
        SELECT inicio_atendimento, fim_atendimento
        FROM solicitacoes
        WHERE id = %s
        """,
        (solicitacao_id,),
    ).fetchone()

    inicio_atendimento = atual["inicio_atendimento"] if atual else None
    fim_atendimento = atual["fim_atendimento"] if atual else None
    agora_atendimento = agora()

    if novo_status == "Em atendimento" and not inicio_atendimento:
        inicio_atendimento = agora_atendimento

    if novo_status == "Concluído":
        fim_atendimento = agora_atendimento

    conn.execute(
        """
        UPDATE solicitacoes
        SET status = %s,
            resposta = %s,
            inicio_atendimento = %s,
            fim_atendimento = %s
        WHERE id = %s
        """,
        (
            novo_status,
            (observacao or "").strip(),
            inicio_atendimento,
            fim_atendimento,
            solicitacao_id,
        ),
    )


def render_anexos_como_arquivo(solicitacao_id, prefixo="anexo"):
    anexos = conn.execute(
        """
        SELECT id, nome_arquivo, observacao, imagem
        FROM anexos
        WHERE solicitacao_id = %s
        ORDER BY id
        """,
        (solicitacao_id,),
    ).fetchall()

    if not anexos:
        return

    st.markdown("**Anexos do cliente:**")
    for anexo in anexos:
        nome_arquivo = anexo["nome_arquivo"] or "arquivo"
        observacao = anexo["observacao"] or "Sem observação"
        ext = Path(nome_arquivo).suffix.lower()
        mime = "image/png"
        if ext in [".jpg", ".jpeg"]:
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"

        with st.expander(f"📎 {nome_arquivo}"):
            st.caption(observacao)
            st.image(anexo["imagem"], use_container_width=True)
            st.download_button(
                label="Baixar arquivo",
                data=anexo["imagem"],
                file_name=nome_arquivo,
                mime=mime,
                key=f"{prefixo}_download_{anexo['id']}",
                use_container_width=False,
            )

@st.cache_data(ttl=30, show_spinner=False)
def obter_solicitacoes_filtradas(
    cliente_id=None,
    cliente_usuario=None,
    empresa_id=None,
    status_filtro="Todos",
    prioridade_filtro="Todas",
    busca="",
    limite=50,
    atendente_usuario=None,
):

    filtros = []
    params = []

    if atendente_usuario:
        atendente = obter_atendente_por_usuario(atendente_usuario)

        if atendente:
            filtros.append("s.atendente_id = %s")
            params.append(atendente["id"])
        else:
            return []

    if cliente_id is not None:
        filtros.append(
            "(s.cliente_id = %s OR (s.cliente_id IS NULL AND s.cliente = %s))"
        )
        params.extend([cliente_id, cliente_usuario or ""])

    elif empresa_id is not None:
        filtros.append("s.empresa_id = %s")
        params.append(empresa_id)

    elif cliente_usuario:
        filtros.append("s.cliente = %s")
        params.append(cliente_usuario)

    if status_filtro != "Todos":
        filtros.append(
            """
            CASE
                WHEN s.status = 'Pendente' THEN 'Em análise'
                WHEN s.status = 'Iniciado' THEN 'Em atendimento'
                WHEN s.status = 'Pausado' THEN 'Aguardando'
                WHEN s.status = 'Resolvido' THEN 'Concluído'
                ELSE s.status
            END = %s
            """
        )
        params.append(status_filtro)

    if prioridade_filtro != "Todas":
        filtros.append("COALESCE(s.prioridade, '') = %s")
        params.append(prioridade_filtro)

    busca = (busca or "").strip()

    if busca:
        filtros.append(
            """
            (
                CAST(s.id AS TEXT) ILIKE %s
                OR s.titulo ILIKE %s
                OR s.descricao ILIKE %s
                OR COALESCE(c.nome, '') ILIKE %s
            )
            """
        )

        termo = f"%{busca}%"

        params.extend([
            termo,
            termo,
            termo,
            termo,
        ])

    where_clause = " AND ".join(filtros) if filtros else "TRUE"

    sql = f"""
        SELECT
            s.id,
            s.cliente,
            s.cliente_id,
            s.empresa_id,
            s.atendente_id,

            a.nome AS atendente_nome,

            c.nome AS cliente_nome,

            s.atribuido_em,
            s.titulo,
            s.descricao,
            s.prioridade,
            s.status,
            s.complexidade,
            s.resposta,
            s.data_criacao,
            s.inicio_atendimento,
            s.fim_atendimento

        FROM solicitacoes s

        LEFT JOIN atendentes a
            ON a.id = s.atendente_id

        LEFT JOIN clientes c
            ON c.id = s.cliente_id

        WHERE {where_clause}

        ORDER BY s.id DESC

        LIMIT %s
    """

    params.append(limite)

    rows = conn.execute(sql, params).fetchall()

    dados = []

    for row in rows:
        item = dict(row)
        item["status"] = normalizar_status(item.get("status"))
        dados.append(item)

    return dados

def normalizar_status_projeto(status):
    mapa = {
        "Novo": "Em análise",
        "Pendente": "Em análise",
        "Em análise": "Em análise",
        "Levantamento": "Levantamento",
        "Proposta": "Proposta",
        "Aprovado": "Aprovado",
        "Em desenvolvimento": "Em desenvolvimento",
        "Pausado": "Pausado",
        "Concluído": "Concluído",
        "Cancelado": "Cancelado",
    }
    return mapa.get(status, status or "Em análise")


def formatar_status_projeto(status):
    status = normalizar_status_projeto(status)

    estilos = {
        "Em análise": "#FF5C7A",
        "Levantamento": "#F5C451",
        "Proposta": "#A78BFA",
        "Aprovado": "#43D17A",
        "Em desenvolvimento": "#5EA8FF",
        "Pausado": "#FF8A4C",
        "Concluído": "#7DD3FC",
        "Cancelado": "#6B7280",
    }

    cor = estilos.get(status, "#AAB7C4")
    status_seguro = html.escape(status)

    return (
        f'<span style="display:inline-flex;align-items:center;gap:7px;'
        f'padding:4px 10px;border-radius:999px;'
        f'background:rgba(255,255,255,0.04);'
        f'border:1px solid rgba(120,145,170,0.18);'
        f'color:{cor};font-size:12px;font-weight:800;white-space:nowrap;">'
        f'<svg width="8" height="8" viewBox="0 0 8 8">'
        f'<circle cx="4" cy="4" r="4" fill="{cor}"></circle>'
        f'</svg>{status_seguro}</span>'
    )


def obter_briefings_filtrados(
    cliente_id=None, empresa_id=None, status_filtro="Todos", busca="", limite=200
):
    filtros = []
    params = []

    if cliente_id is not None:
        filtros.append("p.cliente_id = %s")
        params.append(cliente_id)
    elif empresa_id is not None:
        filtros.append("p.empresa_id = %s")
        params.append(empresa_id)

    if status_filtro != "Todos":
        filtros.append("COALESCE(p.status, 'Em análise') = %s")
        params.append(status_filtro)

    busca = (busca or "").strip()
    if busca:
        if busca.isdigit():
            filtros.append(
                "(CAST(p.id AS TEXT) = %s OR p.titulo ILIKE %s OR p.descricao ILIKE %s)"
            )
            params.extend([busca, f"%{busca}%", f"%{busca}%"])
        else:
            filtros.append(
                "(p.titulo ILIKE %s OR p.descricao ILIKE %s OR COALESCE(c.nome, '') ILIKE %s)"
            )
            params.extend([f"%{busca}%", f"%{busca}%", f"%{busca}%"])

    where_clause = " AND ".join(filtros) if filtros else "TRUE"

    sql = f"""
        SELECT
            p.id,
            p.empresa_id,
            p.cliente_id,
            p.titulo,
            p.descricao,
            p.objetivo,
            p.prioridade,
            p.status,
            p.created_at,
            p.atualizado_em,
            c.nome AS cliente_nome,
            c.usuario AS cliente_usuario,
            e.fantasia AS empresa_nome
        FROM projetos_briefing p
        LEFT JOIN clientes c ON c.id = p.cliente_id
        LEFT JOIN empresas e ON e.id = p.empresa_id
        WHERE {where_clause}
        ORDER BY p.id DESC
        LIMIT %s
    """
    params.append(limite)
    return conn.execute(sql, params).fetchall()


def obter_etapas_projeto(projeto_id, somente_visiveis=False):
    filtro_visibilidade = "AND visivel_cliente = TRUE" if somente_visiveis else ""
    return conn.execute(
        f"""
        SELECT id, projeto_id, etapa, observacao, data_registro, usuario, visivel_cliente
        FROM projetos_etapas
        WHERE projeto_id = %s
        {filtro_visibilidade}
        ORDER BY data_registro ASC, id ASC
        """,
        (projeto_id,),
    ).fetchall()


def render_timeline_projeto(projeto_id, somente_visiveis=False):
    etapas = obter_etapas_projeto(projeto_id, somente_visiveis=somente_visiveis)
    if not etapas:
        st.info("Nenhuma etapa registrada ainda.")
        return

    for etapa in etapas:
        data_txt = "-"
        if etapa.get("data_registro"):
            data_txt = etapa["data_registro"].strftime("%d/%m/%Y %H:%M")
        visibilidade = (
            "Visível ao cliente" if etapa.get("visivel_cliente") else "Interno"
        )
        with st.container(border=True):
            st.write(f"**{etapa['etapa']}**")
            if etapa.get("observacao"):
                st.write(etapa["observacao"])
            st.caption(
                f"Registrado em {data_txt} por {etapa.get('usuario') or '-'} • {visibilidade}"
            )


def agrupar_solicitacoes_por_cliente(solicitacoes):
    grupos = defaultdict(list)
    for item in solicitacoes:
        chave = (item.get("cliente_id"), item.get("cliente"))
        grupos[chave].append(item)
    return grupos


def montar_url_convite(token_convite):
    base_url = os.getenv("APP_BASE_URL", "").strip()
    if not base_url:
        try:
            qp = st.query_params.to_dict()
            qp["invite"] = token_convite
            if "token" in qp:
                del qp["token"]
            query = "&".join([f"{k}={quote_plus(str(v))}" for k, v in qp.items()])
            return f"?{query}"
        except Exception:
            return f"?invite={token_convite}"

    separador = "&" if "?" in base_url else "?"
    return f"{base_url}{separador}invite={quote_plus(token_convite)}"


def gerar_token_convite():
    return secrets.token_urlsafe(24)


def convite_expirado(convite):
    expiracao = convite.get("expiracao_em")
    if not expiracao:
        return False
    if expiracao.tzinfo is None:
        return expiracao < agora().replace(tzinfo=None)
    return expiracao < agora()


def obter_convite_por_token(token):
    convite = conn.execute(
        """
        SELECT c.*, e.fantasia AS empresa_nome
        FROM convites_cadastro c
        LEFT JOIN empresas e ON e.id = c.empresa_id
        WHERE c.token = %s
        LIMIT 1
        """,
        (token,),
    ).fetchone()

    if (
        convite
        and convite["status"] in ("pendente", "enviado")
        and convite_expirado(convite)
    ):
        conn.execute(
            "UPDATE convites_cadastro SET status = 'expirado' WHERE id = %s",
            (convite["id"],),
        )
        convite = conn.execute(
            """
            SELECT c.*, e.fantasia AS empresa_nome
            FROM convites_cadastro c
            LEFT JOIN empresas e ON e.id = c.empresa_id
            WHERE c.token = %s
            LIMIT 1
            """,
            (token,),
        ).fetchone()
    return convite


def criar_convite(nome, email, empresa_id, tipo_usuario, observacao=""):
    token = gerar_token_convite()
    usuario_sugerido = gerar_usuario(nome)
    enviado_em = agora()
    expiracao_em = agora() + timedelta(hours=CONVITE_EXPIRACAO_HORAS)

    convite = conn.execute(
        """
        INSERT INTO convites_cadastro
        (nome, email, empresa_id, tipo_usuario, token, status, observacao, usuario_sugerido, enviado_em, expiracao_em)
        VALUES (%s, %s, %s, %s, %s, 'enviado', %s, %s, %s, %s)
        RETURNING id
        """,
        (
            nome.strip(),
            email.strip().lower(),
            empresa_id,
            tipo_usuario,
            token,
            observacao.strip(),
            usuario_sugerido,
            enviado_em,
            expiracao_em,
        ),
    ).fetchone()
    return convite["id"], token


def reenviar_convite(convite_id):
    token = gerar_token_convite()
    enviado_em = agora()
    expiracao_em = agora() + timedelta(hours=CONVITE_EXPIRACAO_HORAS)

    conn.execute(
        """
        UPDATE convites_cadastro
        SET token = %s,
            status = 'enviado',
            enviado_em = %s,
            expiracao_em = %s
        WHERE id = %s
        """,
        (token, enviado_em, expiracao_em, convite_id),
    )
    return token


def concluir_convite(
    convite, nome, usuario, senha, cpf="", funcao="", email="", nome_atendente=""
):
    tipo = convite["tipo_usuario"]

    if tipo == "cliente":
        existe = conn.execute(
            "SELECT 1 FROM clientes WHERE usuario = %s",
            (usuario,),
        ).fetchone()
        if existe:
            raise ValueError("Já existe um cliente com esse usuário.")

        conn.execute(
            """
            INSERT INTO clientes (usuario, senha, nome, ativo, cpf, empresa_id, funcao, email)
            VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s)
            """,
            (
                usuario,
                gerar_hash_senha(senha),
                nome,
                cpf,
                convite["empresa_id"],
                funcao,
                email.strip().lower(),
            ),
        )
    else:
        existe = conn.execute(
            "SELECT 1 FROM atendentes WHERE usuario = %s",
            (usuario,),
        ).fetchone()
        if existe:
            raise ValueError("Já existe um atendente com esse usuário.")

        conn.execute(
            """
            INSERT INTO atendentes (nome, usuario, senha, email, ativo)
            VALUES (%s, %s, %s, %s, TRUE)
            """,
            (
                nome_atendente or nome,
                usuario,
                gerar_hash_senha(senha),
                email.strip().lower(),
            ),
        )

    conn.execute(
        """
        UPDATE convites_cadastro
        SET status = 'concluido',
            utilizado_em = %s
        WHERE id = %s
        """,
        (agora(), convite["id"]),
    )


def aplicar_estilo_login():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #061C33 0%, #0B3A63 100%);
        }

        section[data-testid="stSidebar"] {
            display: none;
        }

        .block-container {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }

        .stTextInput label, .stSelectbox label {
            color: #dfeaf5 !important;
            font-weight: 600 !important;
        }

        .stTextInput > div > div > input {
            background-color: rgba(255,255,255,0.06) !important;
            color: white !important;
            border: 1px solid rgba(173, 216, 255, 0.22) !important;
            border-radius: 10px !important;
        }

        .stButton > button {
            width: 100%;
            border-radius: 12px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_tela_convite(token_convite):
    aplicar_estilo_login()
    convite = obter_convite_por_token(token_convite)

    col1, col2, col3 = st.columns([1.1, 1, 1.1])
    with col2:
        if logo_b64:
            st.markdown(
                f"""
                <div style='display:flex; justify-content:center; margin-bottom:18px;'>
                    <img src='data:image/png;base64,{logo_b64}' width='140'>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "<div style='text-align:center; color:white; font-size:26px; font-weight:700;'>BUSINESS VISION</div>",
            unsafe_allow_html=True,
        )

        if not convite:
            st.error("Convite inválido.")
            st.stop()

        if convite["status"] == "concluido":
            st.success("Este convite já foi utilizado.")
            st.stop()

        if convite["status"] in ("cancelado", "expirado") or convite_expirado(convite):
            st.error("Este convite expirou ou foi cancelado.")
            st.stop()

        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:15px; margin-top:6px; margin-bottom:20px;'>Concluir cadastro</div>",
            unsafe_allow_html=True,
        )

        st.info(
            f"Convite para {convite['nome']} • Perfil: {convite['tipo_usuario'].capitalize()}"
            + (
                f" • Empresa: {convite['empresa_nome']}"
                if convite.get("empresa_nome")
                else ""
            )
        )

        email = st.text_input("E-mail", value=convite["email"], disabled=True)
        nome = st.text_input("Nome completo", value=convite["nome"])
        usuario = st.text_input(
            "Usuário",
            value=convite.get("usuario_sugerido") or gerar_usuario(convite["nome"]),
        )
        senha = st.text_input("Senha", type="password")
        confirmar_senha = st.text_input("Confirmar senha", type="password")

        cpf = ""
        funcao = ""
        if convite["tipo_usuario"] == "cliente":
            cpf = st.text_input("CPF")
            funcao = st.text_input("Função")
        else:
            funcao = st.text_input("Função / Cargo")

        if st.button("Concluir cadastro"):
            if not nome.strip() or not usuario.strip() or not senha.strip():
                st.error("Preencha nome, usuário e senha.")
            elif senha != confirmar_senha:
                st.error("As senhas não conferem.")
            elif len(senha.strip()) < 6:
                st.error("A senha deve ter pelo menos 6 caracteres.")
            else:
                try:
                    concluir_convite(
                        convite=convite,
                        nome=nome.strip(),
                        usuario=usuario.strip(),
                        senha=senha.strip(),
                        cpf=cpf.strip(),
                        funcao=funcao.strip(),
                        email=email.strip(),
                        nome_atendente=nome.strip(),
                    )
                    st.success(
                        "Cadastro concluído com sucesso. Agora você já pode acessar o portal."
                    )
                except ValueError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Erro ao concluir cadastro: {exc}")
        st.stop()


invite_token = st.query_params.get("invite")
if invite_token:
    render_tela_convite(invite_token)


if not st.session_state.logado:
    aplicar_estilo_login()

    col1, col2, col3 = st.columns([1.2, 1, 1.2])
    with col2:
        if logo_b64:
            st.markdown(
                f"""
                <div style='display:flex; justify-content:center; margin-bottom:18px;'>
                    <img src='data:image/png;base64,{logo_b64}' width='140'>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "<div style='text-align:center; color:white; font-size:26px; font-weight:700;'>BUSINESS VISION</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:15px; margin-top:5px;'>PORTAL DO CLIENTE</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:13px; margin-bottom:20px;'>Acesse sua conta</div>",
            unsafe_allow_html=True,
        )

        usuario_input = st.text_input("Usuário", placeholder="Digite seu usuário")
        senha_input = st.text_input(
            "Senha", type="password", placeholder="Digite sua senha"
        )

        if st.button("ENTRAR →"):
            usuario_digitado = usuario_input.strip()
            senha_digitada = senha_input.strip()

            if not usuario_digitado or not senha_digitada:
                st.error("Informe usuário e senha.")

            else:
                user = autenticar_usuario(usuario_digitado, senha_digitada)

                if user:
                    perfil_usuario = user["perfil"] or "cliente"
                    menu_inicial = (
                        "Demandas Solicitadas"
                        if perfil_usuario == "atendente"
                        else "Nova Solicitação"
                    )

                    token = criar_sessao_login(
                        usuario_digitado, perfil_usuario, menu_inicial
                    )

                    st.session_state.logado = True
                    st.session_state.usuario = usuario_digitado
                    st.session_state.perfil = perfil_usuario
                    st.session_state.menu_atual = menu_inicial
                    st.session_state.token_sessao = token

                    persistir_query_params()
                    st.rerun()

                elif autenticar_admin(usuario_digitado, senha_digitada):
                    token = criar_sessao_login(
                        usuario_digitado, "admin", "Nova Solicitação"
                    )

                    st.session_state.logado = True
                    st.session_state.usuario = usuario_digitado
                    st.session_state.perfil = "admin"
                    st.session_state.menu_atual = "Nova Solicitação"
                    st.session_state.token_sessao = token

                    persistir_query_params()
                    st.rerun()

                else:
                    cliente = autenticar_cliente(usuario_digitado, senha_digitada)
                    if cliente:
                        token = criar_sessao_login(
                            usuario_digitado, "cliente", "Nova Solicitação"
                        )

                        st.session_state.logado = True
                        st.session_state.usuario = usuario_digitado
                        st.session_state.perfil = "cliente"
                        st.session_state.menu_atual = "Nova Solicitação"
                        st.session_state.token_sessao = token

                        persistir_query_params()
                        st.rerun()

                    else:
                        atendente = autenticar_atendente(
                            usuario_digitado, senha_digitada
                        )
                        if atendente:
                            token = criar_sessao_login(
                                usuario_digitado, "atendente", "Demandas Solicitadas"
                            )

                            st.session_state.logado = True
                            st.session_state.usuario = usuario_digitado
                            st.session_state.perfil = "atendente"
                            st.session_state.menu_atual = "Demandas Solicitadas"
                            st.session_state.token_sessao = token

                            persistir_query_params()
                            st.rerun()
                        else:
                            st.error("Usuário ou senha inválidos.")
    st.stop()

def aplicar_design_portal():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #020b16 0%, #04111f 100%);
            color: #EAF2FF;
        }

        [data-testid="stHeader"] {
            background: transparent;
        }

        .block-container {
            padding-top: 1.15rem;
            padding-bottom: 1.8rem;
            max-width: 1380px;
        }

        section[data-testid="stSidebar"] {
            min-width: 300px !important;
            max-width: 300px !important;
            width: 300px !important;
            background: linear-gradient(180deg, #03101d 0%, #051424 100%);
            border-right: 1px solid rgba(120,145,170,0.12);
            transition: all 0.3s ease-in-out !important;
        }

        section[data-testid="stSidebar"] > div {
            min-width: 300px !important;
            max-width: 300px !important;
            width: 300px !important;
            padding-left: 18px !important;
            padding-right: 18px !important;
        }

        section[data-testid="stSidebar"] * {
            color: #EAF2FF !important;
        }

        section[data-testid="stSidebar"] .stButton > button {
            width: 100%;
            min-height: 42px;
            border-radius: 12px;
            font-weight: 700;
            font-size: 13px !important;
            text-align: left !important;
            justify-content: flex-start !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding-left: 12px !important;
            padding-right: 10px !important;
            margin-bottom: 8px;
        }

        section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
            background: transparent !important;
            border: 1px solid transparent !important;
            color: #B9C8D9 !important;
        }

        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: rgba(38,79,150,0.72) !important;
            border: 1px solid rgba(120,166,255,0.15) !important;
            color: #FFFFFF !important;
        }

        section[data-testid="stSidebar"] > div {
            display: flex !important;
            flex-direction: column !important;
            min-height: 100vh !important;
        }

        .bv-sidebar-spacer {
            flex: 1;
        }

        .stTextInput > div > div > input,
        .stTextArea textarea,
        .stSelectbox > div > div,
        .stNumberInput input {
            background: rgba(255,255,255,0.03) !important;
            color: #EAF2FF !important;
            border: 1px solid rgba(120,145,170,0.18) !important;
            border-radius: 10px !important;
            box-shadow: none !important;
        }

        .stButton > button {
            width: 100%;
            border-radius: 12px;
            font-weight: 700;
            border: 1px solid rgba(84,138,226,0.28);
            background: linear-gradient(180deg, #17427A 0%, #10335F 100%);
            color: #FFFFFF;
            box-shadow: none;
        }

        .bv-sidebar-top {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 4px 0 22px 0;
            width: 100%;
        }

        .bv-sidebar-logo {
            width: 42px;
            height: 42px;
            object-fit: contain;
            flex-shrink: 0;
        }

        .bv-sidebar-title {
            font-size: 16px;
            font-weight: 800;
            color: #F7FBFF;
            line-height: 1.2;
            white-space: normal;
        }

        .bv-menu-heading {
            font-size: 11px;
            letter-spacing: .08em;
            font-weight: 800;
            color: #7F93A8 !important;
            margin: 8px 0 10px 0;
            text-transform: uppercase;
        }

        .bv-menu-icon-wrap {
            width: 42px;
            min-width: 42px;
            height: 42px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #B9C8D9;
            border-radius: 12px;
            margin-bottom: 8px;
        }

        .bv-menu-icon-wrap.active {
            background: rgba(38,79,150,0.72);
            color: #FFFFFF;
            border: 1px solid rgba(120,166,255,0.15);
        }

        .bv-sidebar-divider {
            height: 1px;
            background: rgba(120,145,170,0.16);
            margin: 18px 0 18px 0;
        }

        .bv-user-card {
            display: flex;
            align-items: center;
            gap: 12px;
            width: 100%;
            margin-top: 14px;
            margin-bottom: 14px;
            overflow: hidden;
        }

        .bv-user-avatar {
            width: 42px;
            height: 42px;
            min-width: 42px;
            border-radius: 50%;
            background: #2B59C3;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #FFFFFF;
            font-weight: 800;
            font-size: 13px;
            flex-shrink: 0;
        }

        .bv-user-meta {
            min-width: 0;
            overflow: hidden;
        }

        .bv-user-label {
            font-size: 11px;
            color: #8FA5BC !important;
            line-height: 1.2;
            margin-bottom: 3px;
        }

        .bv-user-name {
            font-size: 13px;
            font-weight: 800;
            color: #EAF2FF;
            line-height: 1.25;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 190px;
        }

        .bv-kpi-card {
            background: rgba(255,255,255,0.035);
            border: 1px solid rgba(120,145,170,0.18);
            border-radius: 16px;
            padding: 18px 20px;
            min-height: 112px;
            margin-bottom: 12px;
        }

        .bv-kpi-label {
            color: #9AA8B5 !important;
            font-size: 12px;
            font-weight: 800;
            margin-bottom: 8px;
        }

        .bv-kpi-value {
            color: #FFFFFF !important;
            font-size: 30px;
            font-weight: 900;
            line-height: 1;
        }

        .bv-section-card {
            background: rgba(255,255,255,0.025);
            border: 1px solid rgba(120,145,170,0.14);
            border-radius: 18px;
            padding: 20px 22px;
            margin-bottom: 20px;
        }

        .bv-title-divider {
            border: 1px solid rgba(120,145,170,0.12);
            margin-top: 0;
            margin-bottom: 20px;
        }

        @media (max-width: 900px) {
            section[data-testid="stSidebar"] {
                min-width: 270px !important;
                max-width: 270px !important;
                width: 270px !important;
            }

            section[data-testid="stSidebar"] > div {
                min-width: 270px !important;
                max-width: 270px !important;
                width: 270px !important;
            }

            .bv-user-name {
                max-width: 160px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def svg_menu_icon(kind):
    icons = {
        "dashboard": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="3.5" y="3.5" width="7" height="7" rx="1.2" stroke="currentColor" stroke-width="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.2" stroke="currentColor" stroke-width="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.2" stroke="currentColor" stroke-width="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.2" stroke="currentColor" stroke-width="1.8"/></svg>',
        "demandas": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="5" y="3.5" width="14" height="17" rx="2" stroke="currentColor" stroke-width="1.8"/><line x1="8" y1="8" x2="16" y2="8" stroke="currentColor" stroke-width="1.8"/><line x1="8" y1="12" x2="16" y2="12" stroke="currentColor" stroke-width="1.8"/></svg>',
        "nova": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><line x1="12" y1="5" x2="12" y2="19" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="5" y1="12" x2="19" y2="12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
        "clientes": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="9" cy="8" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M3 19c0-3.2 2.9-5.3 6-5.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="17" cy="8" r="3" stroke="currentColor" stroke-width="1.8"/><path d="M21 19c0-3.2-2.9-5.3-6-5.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
        "atendentes": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="7" r="3.2" stroke="currentColor" stroke-width="1.8"/><path d="M5 19c0-3.6 3.3-5.8 7-5.8s7 2.2 7 5.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
        "cadastros": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M4 7.5h16M7 4.5v6M17 4.5v6M6.5 20h11a2 2 0 0 0 2-2v-8.5a2 2 0 0 0-2-2h-11a2 2 0 0 0-2 2V18a2 2 0 0 0 2 2Z" stroke="currentColor" stroke-width="1.8"/><path d="M9 14h6M12 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
        "projetos": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M6 4h8l4 4v12H6V4Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 4v5h5" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M9 13h6M9 16h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
        "swap": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M8 7H19M19 7L15.5 3.5M19 7L15.5 10.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 17H5M5 17L8.5 13.5M5 17L8.5 20.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    }
    return icons.get(kind, icons["demandas"])


def sla_limite(prioridade):
    prioridade = (prioridade or "").strip()
    if prioridade == "Alta":
        return 24
    if prioridade == "Média":
        return 48
    return 72


def registrar_historico_solicitacao(solicitacao_id, status, observacao):
    conn.execute(
        """
        INSERT INTO solicitacoes_historico
        (solicitacao_id, status, observacao, usuario, data_registro)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            solicitacao_id,
            status,
            (observacao or "").strip(),
            st.session_state.usuario,
            agora(),
        ),
    )


def obter_historico_solicitacao(solicitacao_id):
    return conn.execute(
        """
        SELECT id, status, observacao, usuario, data_registro
        FROM solicitacoes_historico
        WHERE solicitacao_id = %s
        ORDER BY data_registro ASC, id ASC
        """,
        (solicitacao_id,),
    ).fetchall()


def render_historico_solicitacao(solicitacao_id):
    historico = obter_historico_solicitacao(solicitacao_id)

    if not historico:
        st.info("Nenhum registro de acompanhamento ainda.")
        return

    st.markdown("**Linha do tempo do atendimento:**")

    for item in historico:
        data_txt = (
            item["data_registro"].strftime("%d/%m/%Y")
            if item.get("data_registro")
            else "-"
        )
        hora_txt = (
            item["data_registro"].strftime("%H:%M") if item.get("data_registro") else ""
        )

        status = item.get("status") or "-"
        observacao = item.get("observacao") or "-"
        usuario = item.get("usuario") or "-"

        if status == "Concluído":
            cor = "#2F80ED"
        elif status == "Aguardando cliente":
            cor = "#F2C94C"
        elif status == "Em atendimento":
            cor = "#27AE60"
        else:
            cor = "#9AA8B5"

        st.markdown(
            f"""
            <div style="
                display:grid;
                grid-template-columns: 120px 22px 1fr;
                gap:12px;
                margin-bottom:14px;
                align-items:start;
            ">
                <div style="font-size:12px;color:#9AA8B5;text-align:right;padding-top:2px;">
                    <b>{data_txt}</b><br>
                    {hora_txt}
                </div>

                <div style="display:flex;flex-direction:column;align-items:center;">
                    <div style="
                        width:14px;
                        height:14px;
                        border-radius:50%;
                        background:{cor};
                        border:2px solid rgba(255,255,255,0.35);
                        margin-top:3px;
                    "></div>
                    <div style="
                        width:2px;
                        min-height:54px;
                        background:rgba(154,168,181,0.25);
                        margin-top:4px;
                    "></div>
                </div>

                <div style="
                    border:1px solid rgba(120,145,170,0.18);
                    background:rgba(255,255,255,0.025);
                    border-radius:12px;
                    padding:10px 12px;
                ">
                    <div style="font-weight:700;color:#EAF2FF;margin-bottom:4px;">
                        {html.escape(status)}
                    </div>
                    <div style="font-size:13px;color:#D7E2EE;line-height:1.45;">
                        {html.escape(observacao)}
                    </div>
                    <div style="font-size:11px;color:#8FA5BC;margin-top:6px;">
                        Registrado por {html.escape(usuario)}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_sidebar_menu(menu_options, current_menu, logo_b64):
    icon_map = {
        "Dashboard": "dashboard",
        "Demandas Solicitadas": "demandas",
        "Nova Solicitação": "nova",
        "Solicitação de Projeto": "projetos",
        "Novo Projeto": "projetos",
        "Cadastro de Clientes": "clientes",
        "Cadastro de Atendentes": "atendentes",
        "Painel de Cadastros": "cadastros",
    }

    if logo_b64:
        st.markdown(
            f'<div class="bv-sidebar-top"><img class="bv-sidebar-logo" src="data:image/png;base64,{logo_b64}"><div class="bv-sidebar-title">Portal Business Vision</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="bv-menu-heading">Menu</div>', unsafe_allow_html=True)

    for item in menu_options:
        is_active = item == current_menu
        col_icon, col_button = st.columns([0.18, 0.82], vertical_alignment="center")

        with col_icon:
            st.markdown(
                f'<div class="bv-menu-icon-wrap{" active" if is_active else ""}">{svg_menu_icon(icon_map.get(item, "demandas"))}</div>',
                unsafe_allow_html=True,
            )

        with col_button:
            if st.button(
                item,
                key=f"menu_btn_{item}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.menu_atual = item
                atualizar_menu_sessao(st.session_state.get("token_sessao"), item)
                persistir_query_params()
                st.rerun()


aplicar_design_portal()

header_logo_col, header_title_col = st.columns([0.8, 8])

with header_logo_col:
    if logo_b64:
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; height:72px;">
                <img src="data:image/png;base64,{logo_b64}" style="max-width:72px; max-height:72px;">
            </div>
            """,
            unsafe_allow_html=True,
        )

with header_title_col:
    st.markdown(
        "<h1 style='margin-bottom:0;'>Portal Business Vision</h1>",
        unsafe_allow_html=True,
    )

st.markdown(
    "<hr style='border:1px solid rgba(120,145,170,0.12); margin-top:0;'>",
    unsafe_allow_html=True,
)
st.caption("Gestão de demandas e acompanhamento em tempo real")

menu_options_admin = [
    "Dashboard",
    "Nova Solicitação",
    "Demandas Solicitadas",
    "Novo Projeto",
    "Painel de Cadastros",
    "Cadastro de Clientes",
    "Cadastro de Atendentes",
]
menu_options_cliente = [
    "Nova Solicitação",
    "Demandas Solicitadas",
    "Novo Projeto",
]
menu_options_atendente = ["Dashboard",
                          "Nova Solicitação",
                          "Demandas Solicitadas", 
                          "Novo Projeto",
                          ]

perfil_atual = st.session_state.get("perfil")
if perfil_atual == "admin":
    menu_options = menu_options_admin
elif perfil_atual == "atendente":
    menu_options = menu_options_atendente
else:
    menu_options = menu_options_cliente

selected_menu_qp = st.query_params.get("menu")
if selected_menu_qp in menu_options:
    st.session_state.menu_atual = selected_menu_qp

if st.session_state.get("menu_atual") not in menu_options:
    st.session_state.menu_atual = menu_options[0]

menu = st.session_state.menu_atual
atualizar_menu_sessao(st.session_state.get("token_sessao"), menu)
persistir_query_params()

with st.sidebar:
    render_sidebar_menu(menu_options=menu_options, current_menu=menu, logo_b64=logo_b64)
    st.markdown('<div class="bv-sidebar-spacer"></div>', unsafe_allow_html=True)
    st.markdown('<div class="bv-sidebar-divider"></div>', unsafe_allow_html=True)

    nome_usuario = (st.session_state.usuario or "").replace("_", " ").strip()
    partes_nome_usuario = [p for p in nome_usuario.split() if p]
    if len(partes_nome_usuario) >= 2:
        iniciais = (partes_nome_usuario[0][0] + partes_nome_usuario[1][0]).upper()
    elif len(partes_nome_usuario) == 1:
        iniciais = partes_nome_usuario[0][0].upper()
    else:
        iniciais = "US"

    st.markdown(
        f"""
        <div class="bv-user-card">
            <div class="bv-user-avatar">{iniciais}</div>
            <div class="bv-user-meta">
                <div class="bv-user-label">Usuário atual</div>
                <div class="bv-user-name">{html.escape(st.session_state.usuario)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_swap_i, col_swap_b = st.columns([0.18, 0.82], vertical_alignment="center")
    with col_swap_i:
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:center;height:38px;color:#DCE7F4;">{svg_menu_icon("swap")}</div>',
            unsafe_allow_html=True,
        )
    with col_swap_b:
        if st.button(
            "Trocar usuário", key="trocar_usuario_menu", use_container_width=True
        ):
            logout()


if menu == "Nova Solicitação":
    st.markdown("### 📌 Abrir nova solicitação")

    st.caption(
        """
    Descreva sua necessidade com detalhes e, se possível, anexe evidências.
    Isso agiliza a análise e reduz o tempo de atendimento.
    """
    )
    if st.session_state.get("limpar_campos_nova_solicitacao", False):
        st.session_state["titulo"] = ""
        st.session_state["descricao"] = ""
        st.session_state.limpar_campos_nova_solicitacao = False

    if perfil_atual == "admin":
        clientes_ativos = obter_clientes_ativos()
        if clientes_ativos:
            lista_clientes = [
                f"{row['nome']} ({row['usuario']})" for row in clientes_ativos
            ]
            mapa_clientes = {
                f"{row['nome']} ({row['usuario']})": row["usuario"]
                for row in clientes_ativos
            }
            cliente_escolhido = st.selectbox("Cliente", lista_clientes)
            cliente_usuario = mapa_clientes[cliente_escolhido]
            cliente_info = obter_cliente_por_usuario(cliente_usuario)
        else:
            st.warning("Não há clientes ativos cadastrados.")
            st.stop()
    else:
        cliente_usuario = st.session_state.usuario
        cliente_info = obter_cliente_por_usuario(cliente_usuario)
        st.text_input(
            "Cliente", value=obter_nome_cliente(cliente_usuario), disabled=True
        )

    titulo = st.text_input("Título", key="titulo")
    descricao = st.text_area("Descrição", key="descricao")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

    complexidade = (
        st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])
        if perfil_atual == "admin"
        else ""
    )

    st.subheader("Anexos de evidência")
    arquivos = st.file_uploader(
        "Selecione os arquivos",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="anexos_upload",
    )

    observacoes_anexos = []
    if arquivos:
        for idx, arq in enumerate(arquivos, start=1):
            st.caption(f"Arquivo {idx}: {arq.name}")
            obs = st.text_input(f"Observação do arquivo {idx}", key=f"obs_img_{idx}")
            observacoes_anexos.append(obs)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        enviar = st.button("Enviar", use_container_width=True)
    with col_b:
        limpar = st.button("LIMPAR", use_container_width=True)
    with col_c:
        nova = st.button("NOVA", use_container_width=True)

    if limpar:
        limpar_formulario()

    if nova:
        nova_solicitacao()

    if enviar:
        cliente_id = cliente_info["id"] if cliente_info else None
        empresa_id = cliente_info["empresa_id"] if cliente_info else None
        titulo_limpo = titulo.strip()
        descricao_limpa = descricao.strip()

        if not cliente_info or not cliente_id:
            st.error("Não foi possível identificar o cliente da solicitação.")
        elif empresa_id is None:
            st.error("O cliente selecionado não está vinculado a nenhuma empresa.")
        elif not titulo_limpo or not descricao_limpa:
            st.warning("Preencha título e descrição antes de enviar.")
        else:
            uploads_invalidos = []
            for arquivo in (arquivos or []):
                ok, mensagem = validar_upload_imagem(arquivo)
                if not ok:
                    uploads_invalidos.append(mensagem)

            if uploads_invalidos:
                for mensagem in uploads_invalidos:
                    st.error(mensagem)
            else:
                duplicado = conn.execute(
                    """
                    SELECT id
                    FROM solicitacoes
                    WHERE cliente_id = %s
                      AND titulo = %s
                      AND descricao = %s
                      AND status IN ('Pendente', 'Iniciado', 'Pausado', 'Em análise', 'Em atendimento', 'Aguardando')
                    LIMIT 1
                    """,
                    (cliente_id, titulo_limpo, descricao_limpa),
                ).fetchone()

                if duplicado is not None:
                    st.warning(
                        f"Esta solicitação já foi solicitada antes e ainda está em andamento. ID #{duplicado['id']}"
                    )
                else:
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO solicitacoes
                                (
                                    cliente,
                                    cliente_id,
                                    empresa_id,
                                    titulo,
                                    descricao,
                                    prioridade,
                                    status,
                                    complexidade,
                                    resposta,
                                    data_criacao
                                )
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                RETURNING id
                                """,
                                (
                                    cliente_usuario,
                                    cliente_id,
                                    empresa_id,
                                    titulo_limpo,
                                    descricao_limpa,
                                    prioridade,
                                    "Em análise",
                                    complexidade,
                                    "",
                                    agora(),
                                ),
                            )
                            solicitacao_id = cur.fetchone()["id"]

                            for idx, arq in enumerate(arquivos or []):
                                cur.execute(
                                    """
                                    INSERT INTO anexos (solicitacao_id, nome_arquivo, observacao, imagem, data_criacao)
                                    VALUES (%s, %s, %s, %s, %s)
                                    """,
                                    (
                                        solicitacao_id,
                                        arq.name,
                                        (
                                            observacoes_anexos[idx]
                                            if idx < len(observacoes_anexos)
                                            else ""
                                        ),
                                        arq.getvalue(),
                                        agora(),
                                    ),
                                )

                        st.session_state.limpar_campos_nova_solicitacao = True
                        st.success("Solicitação enviada com sucesso.")
                        st.rerun()
                    except psycopg.Error as e:
                        st.error(f"Erro ao gravar solicitação: {e}")


elif menu == "Demandas Solicitadas":
    st.header("Demandas Solicitadas")
    st.caption(
        """
    Acompanhe aqui todas as suas solicitações, status de atendimento e respostas da equipe.
    """
    )

    col_legenda1, col_legenda2 = st.columns([8, 1])
    with col_legenda2:
        if st.button("📌 Legenda", use_container_width=True):
            st.session_state.mostrar_legenda = not st.session_state.get(
                "mostrar_legenda", False
            )

    if st.session_state.get("mostrar_legenda", False):
        st.info("🔴 Em análise\n\n🔘 Em atendimento\n\n🟡 Aguardando\n\n🟢 Concluído")

    f1, f2, f3 = st.columns([1.2, 1.2, 2.2])
    with f1:
        status_filtro = st.selectbox(
            "Filtrar por status",
            [
                "Todos",
                "Em análise",
                "Em atendimento",
                "Aguardando",
                "Concluído",
            ],
            index=0,
            key="filtro_status_demandas",
        )
    with f2:
        prioridade_filtro = st.selectbox(
            "Filtrar por prioridade",
            ["Todas", "Alta", "Média", "Baixa"],
            index=0,
            key="filtro_prioridade_demandas",
        )
    with f3:
        busca_filtro = st.text_input(
            "Buscar por ID ou título",
            placeholder="Ex.: 125 ou erro no relatório",
            key="busca_demandas",
        )

    st.caption(
        "Listagem otimizada para reduzir consultas repetidas e melhorar o tempo de resposta."
    )

    clientes_mapa = {}
    atendentes_ativos = obter_atendentes_ativos() if perfil_atual == "admin" else []

    if perfil_atual == "admin":
        clientes = conn.execute(
            """
            SELECT id, usuario, nome, empresa_id
            FROM clientes
            WHERE ativo = TRUE
            ORDER BY nome, usuario
            """
        ).fetchall()
        clientes_mapa = {(cli["id"], cli["usuario"]): cli for cli in clientes if cli}
        todas_solicitacoes = obter_solicitacoes_filtradas(
            status_filtro=status_filtro,
            prioridade_filtro=prioridade_filtro,
            busca=busca_filtro,
            limite=300,
        )
        grupos_solicitacoes = agrupar_solicitacoes_por_cliente(todas_solicitacoes)
        clientes_iteracao = [
            clientes_mapa[chave]
            for chave in clientes_mapa
            if chave in grupos_solicitacoes
        ]
    elif perfil_atual == "atendente":
        dados_cli = obter_solicitacoes_filtradas(
            status_filtro=status_filtro,
            prioridade_filtro=prioridade_filtro,
            busca=busca_filtro,
            limite=200,
            atendente_usuario=st.session_state.usuario,
        )
        clientes_iteracao = []
        grupos_solicitacoes = {"_atendente": dados_cli}
    else:
        cliente_logado = obter_cliente_por_usuario(st.session_state.usuario)
        clientes_iteracao = [cliente_logado] if cliente_logado else []
        grupos_solicitacoes = {}

    encontrou_resultado = False

    if perfil_atual == "admin":
        clientes_iteracao, _, _ = paginar_registros(
            clientes_iteracao, state_key="pagina_demandas_clientes", page_size=8
        )

    if perfil_atual == "atendente":
        df_cli = pd.DataFrame(grupos_solicitacoes.get("_atendente", []))
        if df_cli.empty:
            st.info("Nenhuma solicitação encontrada com os filtros aplicados.")
        else:
            encontrou_resultado = True
            for _, row in df_cli.iterrows():
                status_atual = normalizar_status(row["status"])
                solicitacao_id = int(row["id"])

                data_criacao = row.get("data_criacao")
                horas_aberta = 0

                if data_criacao:
                    try:
                        if data_criacao.tzinfo is None:
                            data_base = data_criacao.replace(tzinfo=APP_TZ)
                        else:
                            data_base = data_criacao
                        horas_aberta = (agora() - data_base).total_seconds() / 3600
                    except Exception:
                        horas_aberta = 0

                cor_fundo = "rgba(255,255,255,0.02)"
                borda = "rgba(120,145,170,0.18)"

                if status_atual != "Concluído":
                    if horas_aberta >= 48:
                        cor_fundo = "rgba(160, 40, 40, 0.28)"
                        borda = "rgba(255, 90, 90, 0.55)"
                    elif horas_aberta >= 24:
                        cor_fundo = "rgba(170, 130, 25, 0.28)"
                        borda = "rgba(255, 200, 80, 0.55)"

                st.markdown(
                    f"""
                    <div style="
                        background:{cor_fundo};
                        border:1px solid {borda};
                        border-radius:14px;
                        padding:14px 16px;
                        margin-bottom:10px;
                    ">
                        <div style="display:grid; grid-template-columns: 80px 1fr 160px 180px; gap:12px; align-items:center;">
                            <div><b>#{solicitacao_id}</b></div>
                            <div><b>{html.escape(str(row['titulo']))}</b></div>
                            <div>Prioridade: <b>{html.escape(str(row['prioridade']))}</b></div>
                            <div>Status: {status_badge_html(status_atual)}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                with st.expander(
                    f"Ver detalhes da solicitação #{solicitacao_id}", expanded=False
                ):
                    st.write("**Descrição:**")
                    st.write(row["descricao"] or "-")

                    if data_criacao:
                        st.caption(
                            f"Aberta em: {data_criacao.strftime('%d/%m/%Y %H:%M')} • {horas_aberta:.1f}h em aberto"
                        )

                    render_anexos_como_arquivo(
                        solicitacao_id,
                        prefixo=f"admin_{solicitacao_id}",
                    )

                    render_historico_solicitacao(solicitacao_id)

                    obs_key = f"obs_{solicitacao_id}"
                    if obs_key not in st.session_state:
                        st.session_state[obs_key] = (
                            row["resposta"] if row["resposta"] else ""
                        )

                    st.text_area(
                        "Observações",
                        key=obs_key,
                        height=90,
                        placeholder="Digite aqui a observação para o cliente...",
                    )

                    nome_atendente_atual = row.get("atendente_nome") or "Não atribuído"
                    st.caption(f"Atendente atual: {nome_atendente_atual}")

                    if atendentes_ativos:
                        opcoes_atendentes = {
                            atendente["nome"]: atendente["id"]
                            for atendente in atendentes_ativos
                        }
                        nomes_atendentes = list(opcoes_atendentes.keys())

                        indice_atendente = 0
                        if row.get("atendente_id"):
                            for idx_at, atendente in enumerate(atendentes_ativos):
                                if atendente["id"] == row.get("atendente_id"):
                                    indice_atendente = idx_at
                                    break

                        ac_at1, ac_at2 = st.columns([2.4, 1])
                        with ac_at1:
                            atendente_sel = st.selectbox(
                                "Atendente responsável",
                                nomes_atendentes,
                                index=indice_atendente,
                                key=f"atendente_{solicitacao_id}",
                            )
                        with ac_at2:
                            st.write("")
                            st.write("")
                            if st.button(
                                "Atribuir",
                                key=f"atribuir_atendente_{solicitacao_id}",
                                use_container_width=True,
                            ):
                                conn.execute(
                                    """
                                    UPDATE solicitacoes
                                    SET atendente_id = %s,
                                        atribuido_em = %s
                                    WHERE id = %s
                                    """,
                                    (
                                        opcoes_atendentes[atendente_sel],
                                        agora(),
                                        solicitacao_id,
                                    ),
                                )
                                st.success("Atendente atribuído.")
                                st.rerun()
                    else:
                        st.info("Nenhum atendente ativo cadastrado.")

                    ac1, ac2, ac3 = st.columns([1.2, 1.2, 3])

                    if status_atual == "Em análise":
                        with ac1:
                            if st.button(
                                "INICIAR",
                                key=f"iniciar_{solicitacao_id}",
                                use_container_width=True,
                            ):
                                observacao_inicio = st.session_state.get(obs_key, "")

                                atualizar_solicitacao(
                                    solicitacao_id,
                                    "Em atendimento",
                                    observacao_inicio,
                                )

                                registrar_historico_solicitacao(
                                    solicitacao_id,
                                    "Em atendimento",
                                    f"Atendimento iniciado pelo atendente {st.session_state.usuario}. {observacao_inicio}",
                                )

                                st.rerun()

                    elif status_atual == "Em atendimento":

                        with ac1:
                            if st.button(
                                "AGUARDAR CLIENTE",
                                key=f"aguardar_{solicitacao_id}",
                                use_container_width=True,
                            ):
                                atualizar_solicitacao(
                                    solicitacao_id,
                                    "Aguardando",
                                    st.session_state[obs_key],
                                )

                                registrar_historico_solicitacao(
                                    solicitacao_id,
                                    "Aguardando",
                                    st.session_state[obs_key],
                                )

                                st.rerun()

                        with ac2:
                            if st.button(
                                "FINALIZAR",
                                key=f"finalizar_{solicitacao_id}",
                                use_container_width=True,
                            ):
                                atualizar_solicitacao(
                                    solicitacao_id,
                                    "Concluído",
                                    st.session_state[obs_key],
                                )

                                registrar_historico_solicitacao(
                                    solicitacao_id,
                                    "Concluído",
                                    st.session_state[obs_key],
                                )

                                st.rerun()

                    elif status_atual == "Aguardando":

                        with ac1:
                            if st.button(
                                "RETOMAR",
                                key=f"retomar_{solicitacao_id}",
                                use_container_width=True,
                            ):
                                observacao_retomada = st.session_state.get(obs_key, "")

                                atualizar_solicitacao(
                                    solicitacao_id,
                                    "Em atendimento",
                                    observacao_retomada,
                                )

                                registrar_historico_solicitacao(
                                    solicitacao_id,
                                    "Em atendimento",
                                    f"Atendimento retomado pelo atendente {st.session_state.usuario}. {observacao_retomada}",
                                )

                                st.rerun()

                        with ac2:
                            if st.button(
                                "FINALIZAR",
                                key=f"finalizar_pausado_{solicitacao_id}",
                                use_container_width=True,
                            ):
                                atualizar_solicitacao(
                                    solicitacao_id,
                                    "Concluído",
                                    st.session_state[obs_key],
                                )

                                registrar_historico_solicitacao(
                                    solicitacao_id,
                                    "Concluído",
                                    st.session_state[obs_key],
                                )

                                st.rerun()
                    else:
                        st.success("Demanda concluída.")
    else:
        for cli in clientes_iteracao:
            if not cli:
                continue

            if perfil_atual == "admin":
                dados_cli = grupos_solicitacoes.get((cli["id"], cli["usuario"]), [])
            else:
                dados_cli = obter_solicitacoes_filtradas(
                    cliente_id=cli["id"],
                    cliente_usuario=cli["usuario"],
                    empresa_id=None,
                    status_filtro=status_filtro,
                    prioridade_filtro=prioridade_filtro,
                    busca=busca_filtro,
                    limite=50,
                )

            if not dados_cli:
                continue

            encontrou_resultado = True
            nome_exibicao = cli["nome"] or cli["usuario"]
            st.subheader(f"Cliente: {nome_exibicao} ({cli['usuario']})")

            df_cli = pd.DataFrame(dados_cli)

            if perfil_atual != "admin":
                df_exibicao = df_cli.copy()
                df_exibicao["status"] = df_exibicao["status"].apply(
                    formatar_status_texto
                )
                df_exibicao["observacoes"] = df_exibicao["resposta"].fillna("")
                df_exibicao = df_exibicao[
                    [
                        "id",
                        "titulo",
                        "prioridade",
                        "status",
                        "observacoes",
                        "data_criacao",
                    ]
                ]
                df_exibicao.columns = [
                    "ID",
                    "Título",
                    "Prioridade",
                    "Status",
                    "Observações",
                    "Data",
                ]
                st.dataframe(df_exibicao, use_container_width=True)

                for _, row in df_cli.iterrows():
                    anexo_id = int(row["id"])
                    with st.expander(f"Anexos da solicitação #{anexo_id}"):
                        render_anexos_como_arquivo(
                            anexo_id, prefixo=f"cliente_{anexo_id}"
                        )

            else:
                for _, row in df_cli.iterrows():
                    status_atual = normalizar_status(row["status"])
                    solicitacao_id = int(row["id"])

                    data_criacao = row.get("data_criacao")
                    horas_aberta = 0

                    if data_criacao:
                        try:
                            if data_criacao.tzinfo is None:
                                data_base = data_criacao.replace(tzinfo=APP_TZ)
                            else:
                                data_base = data_criacao
                            horas_aberta = (agora() - data_base).total_seconds() / 3600
                        except Exception:
                            horas_aberta = 0

                    cor_fundo = "rgba(255,255,255,0.02)"
                    borda = "rgba(120,145,170,0.18)"

                    if status_atual != "Concluído":
                        if horas_aberta >= 48:
                            cor_fundo = "rgba(160, 40, 40, 0.28)"
                            borda = "rgba(255, 90, 90, 0.55)"
                        elif horas_aberta >= 24:
                            cor_fundo = "rgba(170, 130, 25, 0.28)"
                            borda = "rgba(255, 200, 80, 0.55)"

                    st.markdown(
                        f"""
                        <div style="
                            background:{cor_fundo};
                            border:1px solid {borda};
                            border-radius:14px;
                            padding:14px 16px;
                            margin-bottom:10px;
                        ">
                            <div style="display:grid; grid-template-columns: 80px 1fr 160px 180px; gap:12px; align-items:center;">
                                <div><b>#{solicitacao_id}</b></div>
                                <div><b>{html.escape(str(row['titulo']))}</b></div>
                                <div>Prioridade: <b>{html.escape(str(row['prioridade']))}</b></div>
                                <div>Status: {status_badge_html(status_atual)}</div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    with st.expander(
                        f"Ver detalhes da solicitação #{solicitacao_id}", expanded=False
                    ):
                        st.write("**Descrição:**")
                        st.write(row["descricao"] or "-")

                        if data_criacao:
                            st.caption(
                                f"Aberta em: {data_criacao.strftime('%d/%m/%Y %H:%M')} • {horas_aberta:.1f}h em aberto"
                            )

                        render_anexos_como_arquivo(
                            solicitacao_id,
                            prefixo=f"admin_{solicitacao_id}",
                        )

                        render_historico_solicitacao(solicitacao_id)

                        obs_key = f"obs_{solicitacao_id}"
                        if obs_key not in st.session_state:
                            st.session_state[obs_key] = (
                                row["resposta"] if row["resposta"] else ""
                            )

                        st.text_area(
                            "Observações",
                            key=obs_key,
                            height=90,
                            placeholder="Digite aqui a observação para o cliente...",
                        )

                        nome_atendente_atual = (
                            row.get("atendente_nome") or "Não atribuído"
                        )
                        st.caption(f"Atendente atual: {nome_atendente_atual}")

                        if atendentes_ativos:
                            opcoes_atendentes = {
                                atendente["nome"]: atendente["id"]
                                for atendente in atendentes_ativos
                            }
                            nomes_atendentes = list(opcoes_atendentes.keys())

                            indice_atendente = 0
                            if row.get("atendente_id"):
                                for idx_at, atendente in enumerate(atendentes_ativos):
                                    if atendente["id"] == row.get("atendente_id"):
                                        indice_atendente = idx_at
                                        break

                            ac_at1, ac_at2 = st.columns([2.4, 1])
                            with ac_at1:
                                atendente_sel = st.selectbox(
                                    "Atendente responsável",
                                    nomes_atendentes,
                                    index=indice_atendente,
                                    key=f"atendente_{solicitacao_id}",
                                )
                            with ac_at2:
                                st.write("")
                                st.write("")
                                if st.button(
                                    "Atribuir",
                                    key=f"atribuir_atendente_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    conn.execute(
                                        """
                                        UPDATE solicitacoes
                                        SET atendente_id = %s,
                                            atribuido_em = %s
                                        WHERE id = %s
                                        """,
                                        (
                                            opcoes_atendentes[atendente_sel],
                                            agora(),
                                            solicitacao_id,
                                        ),
                                    )
                                    st.success("Atendente atribuído.")
                                    st.rerun()
                        else:
                            st.info("Nenhum atendente ativo cadastrado.")

                        ac1, ac2, ac3 = st.columns([1.2, 1.2, 3])

                        if status_atual == "Em análise":
                            with ac1:
                                if st.button(
                                    "INICIAR",
                                    key=f"iniciar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Em atendimento",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()

                        elif status_atual == "Em atendimento":
                            with ac1:
                                if st.button(
                                    "AGUARDAR CLIENTE",
                                    key=f"aguardar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Aguardando",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()
                            with ac2:
                                if st.button(
                                    "FINALIZAR",
                                    key=f"finalizar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Concluído",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()

                        elif status_atual == "Aguardando":
                            with ac1:
                                if st.button(
                                    "RETOMAR",
                                    key=f"retomar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Em atendimento",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()
                            with ac2:
                                if st.button(
                                    "FINALIZAR",
                                    key=f"finalizar_aguardando_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Concluído",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()
                        else:
                            st.success("Demanda concluída.")

    if not encontrou_resultado and perfil_atual != "atendente":
        st.info("Nenhuma solicitação encontrada com os filtros aplicados.")


elif menu == "Novo Projeto":
    st.header("Novo Projeto")
    st.caption(
        "Descreva o projeto que você precisa. Nossa equipe irá analisar e retornar com a melhor solução."
    )

    status_opcoes_projeto = [
        "Todos",
        "Em análise",
        "Levantamento",
        "Proposta",
        "Aprovado",
        "Em desenvolvimento",
        "Pausado",
        "Concluído",
        "Cancelado",
    ]

    if "projeto_aberto_id" not in st.session_state:
        st.session_state.projeto_aberto_id = None

    if perfil_atual in ["admin", "cliente"]:
        with st.expander(
            "Nova solicitação de projeto",
            expanded=perfil_atual == "cliente",
        ):
            if perfil_atual == "admin":
                clientes_ativos = conn.execute(
                    """
                    SELECT c.id, c.usuario, c.nome, c.empresa_id, e.fantasia AS empresa
                    FROM clientes c
                    LEFT JOIN empresas e ON e.id = c.empresa_id
                    WHERE c.ativo = TRUE
                    ORDER BY c.nome, c.usuario
                    """
                ).fetchall()

                if clientes_ativos:
                    lista_clientes = [
                        f"{row['nome']} ({row['usuario']}) • {row.get('empresa') or 'Sem empresa'}"
                        for row in clientes_ativos
                    ]
                    mapa_clientes = {
                        f"{row['nome']} ({row['usuario']}) • {row.get('empresa') or 'Sem empresa'}": row
                        for row in clientes_ativos
                    }
                    cliente_escolhido = st.selectbox(
                        "Cliente", lista_clientes, key="briefing_cliente_admin"
                    )
                    cliente_briefing = mapa_clientes[cliente_escolhido]
                else:
                    cliente_briefing = None
                    st.warning("Não há clientes ativos cadastrados.")
            else:
                cliente_briefing = obter_cliente_por_usuario(st.session_state.usuario)
                st.text_input(
                    "Cliente",
                    value=obter_nome_cliente(st.session_state.usuario),
                    disabled=True,
                    key="briefing_cliente_logado",
                )

            titulo_projeto = st.text_input("Título do projeto", key="briefing_titulo")
            objetivo_projeto = st.text_input("Objetivo principal", key="briefing_objetivo")
            descricao_projeto = st.text_area(
                "Descreva o que precisa",
                key="briefing_descricao",
                placeholder="Explique o problema, processo atual, resultado esperado, relatórios/sistemas envolvidos e prazos desejados.",
                height=140,
            )
            prioridade_projeto = st.selectbox(
                "Prioridade",
                ["Alta", "Média", "Baixa"],
                index=1,
                key="briefing_prioridade",
            )

            if st.button("Enviar briefing", key="enviar_briefing", use_container_width=True):
                if not cliente_briefing or not cliente_briefing.get("id"):
                    st.error("Não foi possível identificar o cliente.")
                elif not cliente_briefing.get("empresa_id"):
                    st.error("O cliente precisa estar vinculado a uma empresa.")
                elif not titulo_projeto.strip() or not descricao_projeto.strip():
                    st.error("Preencha título e descrição do projeto.")
                else:
                    projeto = conn.execute(
                        """
                        INSERT INTO projetos_briefing
                        (empresa_id, cliente_id, titulo, descricao, objetivo, prioridade, status, created_at, atualizado_em)
                        VALUES (%s, %s, %s, %s, %s, %s, 'Em análise', %s, %s)
                        RETURNING id
                        """,
                        (
                            cliente_briefing["empresa_id"],
                            cliente_briefing["id"],
                            titulo_projeto.strip(),
                            descricao_projeto.strip(),
                            objetivo_projeto.strip(),
                            prioridade_projeto,
                            agora(),
                            agora(),
                        ),
                    ).fetchone()

                    conn.execute(
                        """
                        INSERT INTO projetos_etapas
                        (projeto_id, etapa, observacao, usuario, visivel_cliente, data_registro)
                        VALUES (%s, %s, %s, %s, TRUE, %s)
                        """,
                        (
                            projeto["id"],
                            "Briefing recebido",
                            "Solicitação de projeto registrada e encaminhada para análise inicial.",
                            st.session_state.usuario,
                            agora(),
                        ),
                    )

                    st.success(f"Briefing #{projeto['id']} enviado com sucesso.")
                    st.rerun()

    f1, f2 = st.columns([1.2, 2.8])
    with f1:
        status_filtro_projeto = st.selectbox(
            "Filtrar por status",
            status_opcoes_projeto,
            index=0,
            key="filtro_status_briefing",
        )
    with f2:
        busca_projeto = st.text_input(
            "Buscar por ID, título, descrição ou cliente",
            key="busca_briefing",
        )

    if perfil_atual == "admin":
        projetos = obter_briefings_filtrados(
            status_filtro=status_filtro_projeto,
            busca=busca_projeto,
            limite=300,
        )
    elif perfil_atual == "cliente":
        cliente_logado = obter_cliente_por_usuario(st.session_state.usuario)
        projetos = obter_briefings_filtrados(
            cliente_id=cliente_logado["id"] if cliente_logado else None,
            status_filtro=status_filtro_projeto,
            busca=busca_projeto,
            limite=100,
        )
    else:
        projetos = []
        st.info("Perfil de atendente não possui acesso ao Novo Projeto.")

    if not projetos:
        st.info("Nenhum briefing encontrado com os filtros aplicados.")
    else:
        projetos, _, _ = paginar_registros(
            projetos,
            "pagina_briefing_projetos",
            page_size=8,
        )

        for projeto in projetos:
            projeto_id = int(projeto["id"])
            status_atual = normalizar_status_projeto(projeto.get("status"))
            status_html = formatar_status_projeto(status_atual)

            data_txt = "-"
            if projeto.get("created_at"):
                data_txt = projeto["created_at"].strftime("%d/%m/%Y %H:%M")

            descricao_curta = projeto.get("descricao") or ""
            if len(descricao_curta) > 180:
                descricao_curta = descricao_curta[:180] + "..."

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([0.7, 3.2, 1.5, 1.8])

                with c1:
                    st.markdown(f"**#{projeto_id}**")

                with c2:
                    st.markdown(f"**{html.escape(str(projeto.get('titulo') or '-'))}**")
                    st.caption(descricao_curta)

                    if projeto.get("objetivo"):
                        st.caption(f"Objetivo: {projeto.get('objetivo')}")

                with c3:
                    st.markdown(
                        f"Prioridade: **{html.escape(str(projeto.get('prioridade') or '-'))}**"
                    )

                    if perfil_atual == "admin":
                        st.caption(
                            f"Cliente: {projeto.get('cliente_nome') or projeto.get('cliente_usuario') or '-'}"
                        )

                with c4:
                    st.markdown(
                        f"""
                        <div style="font-size:14px;color:#EAF2FF;margin-bottom:8px;">
                            Status: {status_html}
                        </div>
                        <div style="font-size:12px;color:#8FA5BC;">
                            {data_txt}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                abrir = st.button(
                    "Abrir detalhes" if st.session_state.projeto_aberto_id != projeto_id else "Fechar detalhes",
                    key=f"abrir_projeto_{projeto_id}",
                    use_container_width=True,
                )

                if abrir:
                    if st.session_state.projeto_aberto_id == projeto_id:
                        st.session_state.projeto_aberto_id = None
                    else:
                        st.session_state.projeto_aberto_id = projeto_id
                    st.rerun()

                if st.session_state.projeto_aberto_id == projeto_id:
                    st.markdown("---")
                    st.markdown("**Timeline do briefing**")

                    render_timeline_projeto(
                        projeto_id,
                        somente_visiveis=(perfil_atual != "admin"),
                    )

                    if perfil_atual == "admin":
                        st.markdown("**Atualização administrativa**")

                        a1, a2 = st.columns([1.2, 2.8])

                        with a1:
                            status_sem_todos = status_opcoes_projeto[1:]
                            idx_status = (
                                status_sem_todos.index(status_atual)
                                if status_atual in status_sem_todos
                                else 0
                            )

                            novo_status_projeto = st.selectbox(
                                "Status",
                                status_sem_todos,
                                index=idx_status,
                                key=f"status_projeto_{projeto_id}",
                            )

                            visivel_cliente = st.checkbox(
                                "Visível para o cliente",
                                value=True,
                                key=f"visivel_etapa_{projeto_id}",
                            )

                        with a2:
                            nova_etapa = st.text_input(
                                "Etapa / título do registro",
                                key=f"etapa_projeto_{projeto_id}",
                                placeholder="Ex.: Levantamento técnico realizado",
                            )

                            obs_etapa = st.text_area(
                                "Observação da etapa",
                                key=f"obs_projeto_{projeto_id}",
                                height=90,
                                placeholder="Registro técnico/comercial do andamento.",
                            )

                        b1, b2 = st.columns([1.2, 3])

                        with b1:
                            if st.button(
                                "Salvar etapa",
                                key=f"salvar_etapa_{projeto_id}",
                                use_container_width=True,
                            ):
                                if (
                                    not nova_etapa.strip()
                                    and not obs_etapa.strip()
                                    and novo_status_projeto == status_atual
                                ):
                                    st.error("Informe uma etapa, observação ou altere o status.")
                                else:
                                    etapa_final = (
                                        nova_etapa.strip()
                                        or f"Status atualizado para {novo_status_projeto}"
                                    )

                                    conn.execute(
                                        """
                                        INSERT INTO projetos_etapas
                                        (projeto_id, etapa, observacao, usuario, visivel_cliente, data_registro)
                                        VALUES (%s, %s, %s, %s, %s, %s)
                                        """,
                                        (
                                            projeto_id,
                                            etapa_final,
                                            obs_etapa.strip(),
                                            st.session_state.usuario,
                                            visivel_cliente,
                                            agora(),
                                        ),
                                    )

                                    conn.execute(
                                        """
                                        UPDATE projetos_briefing
                                        SET status = %s,
                                            atualizado_em = %s
                                        WHERE id = %s
                                        """,
                                        (
                                            novo_status_projeto,
                                            agora(),
                                            projeto_id,
                                        ),
                                    )

                                    st.success("Etapa registrada com sucesso.")
                                    st.rerun()

elif menu == "Dashboard" and perfil_atual == "admin":
    st.markdown("### Dashboard Executivo")
    st.caption(
        "Visão operacional para medir produtividade, identificar atrasos, acompanhar SLA e priorizar atendimentos."
    )

    def sla_limite(prioridade):
        prioridade = (prioridade or "").strip()
        if prioridade == "Alta":
            return 24
        if prioridade == "Média":
            return 48
        return 72

    dados = conn.execute(
        """
        SELECT
            s.id,
            s.cliente,
            c.nome AS cliente_nome,
            e.fantasia AS empresa_nome,
            s.titulo,
            s.descricao,
            s.prioridade,
            s.status,
            s.complexidade,
            s.resposta,
            s.data_criacao,
            s.inicio_atendimento,
            s.fim_atendimento,
            a.nome AS atendente_nome
        FROM solicitacoes s
        LEFT JOIN clientes c ON c.id = s.cliente_id
        LEFT JOIN empresas e ON e.id = s.empresa_id
        LEFT JOIN atendentes a ON a.id = s.atendente_id
        ORDER BY s.data_criacao DESC NULLS LAST, s.id DESC
        """
    ).fetchall()

    if not dados:
        st.info("Nenhuma solicitação registrada ainda.")
        st.stop()

    df = pd.DataFrame(dados)

    df["status_norm"] = df["status"].apply(normalizar_status)
    df["data_criacao"] = pd.to_datetime(df["data_criacao"], errors="coerce")
    df["inicio_atendimento"] = pd.to_datetime(df["inicio_atendimento"], errors="coerce")
    df["fim_atendimento"] = pd.to_datetime(df["fim_atendimento"], errors="coerce")

    agora_ref = pd.Timestamp(agora()).tz_localize(None)

    df["horas_aberta"] = (
        (agora_ref - df["data_criacao"]).dt.total_seconds() / 3600
    ).fillna(0)

    df["sla_limite"] = df["prioridade"].apply(sla_limite)

    df_ativas = df[df["status_norm"] != "Concluído"].copy()
    df_concluidas = df[df["status_norm"] == "Concluído"].copy()

    if not df_concluidas.empty:
        df_concluidas["tempo_horas"] = (
            df_concluidas["fim_atendimento"] - df_concluidas["data_criacao"]
        ).dt.total_seconds() / 3600

        tempo_medio = df_concluidas["tempo_horas"].mean()
        total_concluidas = len(df_concluidas)

        df_concluidas["dentro_sla"] = (
            df_concluidas["tempo_horas"] <= df_concluidas["sla_limite"]
        )

        sla_percentual = df_concluidas["dentro_sla"].mean() * 100
    else:
        tempo_medio = 0
        total_concluidas = 0
        sla_percentual = 0

    if not df_ativas.empty:
        df_ativas["tempo_horas"] = df_ativas["horas_aberta"]
        df_ativas["atrasada"] = df_ativas["tempo_horas"] > df_ativas["sla_limite"]
        total_atrasadas = int(df_ativas["atrasada"].sum())
        criticas_24h = len(df_ativas[df_ativas["horas_aberta"] >= 24])
        criticas_48h = len(df_ativas[df_ativas["horas_aberta"] >= 48])
        sem_atendente = len(df_ativas[df_ativas["atendente_nome"].isna()])
    else:
        total_atrasadas = 0
        criticas_24h = 0
        criticas_48h = 0
        sem_atendente = 0

    total = len(df)
    ativas = len(df_ativas)
    
    status_operacao = "ESTÁVEL"
    status_cor = "#43D17A"

    if criticas_48h > 0:
        status_operacao = "CRÍTICO"
        status_cor = "#FF5C7A"
    elif criticas_24h > 0:
        status_operacao = "ATENÇÃO"
        status_cor = "#F5C451"

    st.markdown(
        f'<div style="background:rgba(255,255,255,0.035);border:1px solid rgba(120,145,170,0.16);border-radius:22px;padding:24px 28px;margin-bottom:26px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:24px;">'
        f'<div>'
        f'<div style="color:#8FA5BC;font-size:11px;font-weight:700;letter-spacing:.08em;margin-bottom:10px;">STATUS OPERACIONAL</div>'
        f'<div style="display:flex;align-items:center;gap:14px;">'
        f'<div style="width:16px;height:16px;border-radius:50%;background:{status_cor};box-shadow:0 0 18px {status_cor};"></div>'
        f'<div style="color:#FFFFFF;font-size:34px;font-weight:900;line-height:1;">{status_operacao}</div>'
        f'</div>'
        f'</div>'
        f'<div style="display:flex;gap:42px;flex-wrap:wrap;">'
        f'<div><div style="color:#8FA5BC;font-size:11px;margin-bottom:6px;">SLA GLOBAL</div><div style="color:#FFFFFF;font-size:26px;font-weight:800;">{sla_percentual:.0f}%</div></div>'
        f'<div><div style="color:#8FA5BC;font-size:11px;margin-bottom:6px;">DEMANDAS ATIVAS</div><div style="color:#FFFFFF;font-size:26px;font-weight:800;">{ativas}</div></div>'
        f'<div><div style="color:#8FA5BC;font-size:11px;margin-bottom:6px;">ATRASADAS</div><div style="color:#FF5C7A;font-size:26px;font-weight:800;">{total_atrasadas}</div></div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("#### Produtividade")

    cards_produtividade = [
        ("Concluídas", total_concluidas, "Demandas finalizadas"),
        ("Tempo médio (h)", f"{tempo_medio:.1f}", "Tempo médio de resolução"),
        ("SLA cumprido", f"{sla_percentual:.0f}%", "Percentual dentro do prazo"),
        ("Atrasadas", total_atrasadas, "Demandas fora do SLA"),
    ]

    cols_produtividade = st.columns(4)

    for col, (titulo, valor, footer) in zip(cols_produtividade, cards_produtividade):
        with col:
            st.markdown(
                f"""
                <div class="bv-kpi-card">
                    <div class="bv-kpi-label">{titulo}</div>
                    <div class="bv-kpi-value">{valor}</div>
                    <div class="bv-kpi-footer">{footer}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div style="font-size:20px;font-weight:800;color:#EAF2FF;margin:22px 0 18px 0;">
            Operação atual
        </div>
        """,
        unsafe_allow_html=True,
    )

    cards = [
        ("Total", total, "Demandas registradas"),
        ("Ativas", ativas, "Em andamento"),
        ("+24h", criticas_24h, "Atenção operacional"),
        ("+48h", criticas_48h, "Risco crítico"),
        ("Sem atendente", sem_atendente, "Necessitam atribuição"),
        ("Finalizadas", total_concluidas, "Demandas concluídas"),
    ]

    cols = st.columns(6)

    for col, (titulo, valor, footer) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="bv-kpi-card">
                    <div class="bv-kpi-label">{titulo}</div>
                    <div class="bv-kpi-value">{valor}</div>
                    <div class="bv-kpi-footer">{footer}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("""
            <style>
            .bv-kpi-card {
                background: linear-gradient(
                    180deg,
                    rgba(255,255,255,0.045) 0%,
                    rgba(255,255,255,0.02) 100%
                );

                border: 1px solid rgba(120,145,170,0.16);
                border-radius: 18px;

                padding: 22px;
                min-height: 125px;

                backdrop-filter: blur(10px);

                transition: all .18s ease;
            }

            .bv-kpi-card:hover {
                transform: translateY(-2px);
                border: 1px solid rgba(120,166,255,0.28);
            }

            .bv-kpi-title {
                color: #8FA5BC;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: .02em;
                margin-bottom: 12px;
            }

            .bv-kpi-value {
                color: #FFFFFF;
                font-size: 34px;
                font-weight: 800;
                line-height: 1;
            }

            .bv-kpi-footer {
                color: #7D91A5;
                font-size: 11px;
                margin-top: 12px;
            }
            </style>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Performance da Equipe")

    if df_concluidas.empty:
        st.info("Ainda não há demandas concluídas suficientes para gerar ranking de atendentes.")
    else:
        ranking_atendentes = df_concluidas.copy()
        ranking_atendentes["atendente_nome"] = ranking_atendentes["atendente_nome"].fillna("Não atribuído")

        ranking_atendentes = (
            ranking_atendentes
            .groupby("atendente_nome")
            .agg(
                concluidas=("id", "count"),
                tempo_medio_horas=("tempo_horas", "mean"),
                sla_percentual=("dentro_sla", "mean"),
            )
            .reset_index()
        )

        ranking_atendentes["sla_percentual"] = ranking_atendentes["sla_percentual"] * 100

        ranking_atendentes = ranking_atendentes.sort_values(
            by=["sla_percentual", "concluidas"],
            ascending=[False, False],
        )

        ranking_exibicao = ranking_atendentes.copy()
        ranking_exibicao["SLA"] = ranking_exibicao["sla_percentual"].map(lambda x: f"{x:.0f}%")
        ranking_exibicao["Tempo médio (h)"] = ranking_exibicao["tempo_medio_horas"].map(lambda x: f"{x:.1f}")
        ranking_exibicao = ranking_exibicao.rename(
            columns={
                "atendente_nome": "Atendente",
                "concluidas": "Concluídas",
            }
        )

        for posicao, row_rank in ranking_exibicao.iterrows():
            posicao_rank = posicao + 1

            atendente = html.escape(str(row_rank["Atendente"]))
            concluidas = row_rank["Concluídas"]
            sla = row_rank["SLA"]
            tempo = row_rank["Tempo médio (h)"]

            if posicao_rank == 1:
                destaque = "#F5C451"
                label = "TOP 1"
            elif posicao_rank == 2:
                destaque = "#B8C2CC"
                label = "TOP 2"
            elif posicao_rank == 3:
                destaque = "#C78B5A"
                label = "TOP 3"
            else:
                destaque = "#5EA8FF"
                label = f"#{posicao_rank}"

            ranking_html = (
                f'<div style="display:grid;grid-template-columns:72px 1fr 120px 120px 140px;'
                f'gap:14px;align-items:center;background:rgba(255,255,255,0.035);'
                f'border:1px solid rgba(120,145,170,0.16);border-left:4px solid {destaque};'
                f'border-radius:16px;padding:14px 16px;margin-bottom:10px;">'
                f'<div style="color:{destaque};font-size:15px;font-weight:900;">{label}</div>'
                f'<div style="color:#FFFFFF;font-size:15px;font-weight:800;">{atendente}</div>'
                f'<div style="color:#D8E2EE;font-size:12px;">Concluídas<br><b style="font-size:18px;color:#FFFFFF;">{concluidas}</b></div>'
                f'<div style="color:#D8E2EE;font-size:12px;">SLA<br><b style="font-size:18px;color:{destaque};">{sla}</b></div>'
                f'<div style="color:#D8E2EE;font-size:12px;">Tempo médio<br><b style="font-size:18px;color:#FFFFFF;">{tempo}h</b></div>'
                f'</div>'
            )

            st.markdown(ranking_html, unsafe_allow_html=True)

    st.markdown("---")

    fila = df_ativas.copy()
    fila = fila.sort_values(
        by=["horas_aberta"],
        ascending=False,
    )

    st.markdown("#### Demandas críticas por SLA")

    if fila.empty:
        st.success("Nenhuma demanda crítica no momento.")
    else:
        for _, row in fila.iterrows():
            status_atual = normalizar_status(row.get("status_norm"))
            cliente_nome = str(row.get("cliente_nome") or row.get("cliente") or "-")
            prioridade = str(row.get("prioridade") or "-")
            atendente_nome = str(row.get("atendente_nome") or "Não atribuído")
            horas_abertas = float(row.get("horas_aberta") or 0)
            titulo = html.escape(str(row.get("titulo") or "-"))

            card_html = (
                f'<div style="background:linear-gradient(90deg,rgba(70,10,20,0.55) 0%,rgba(40,10,20,0.45) 100%);'
                f'border:1px solid rgba(255,70,90,0.55);border-radius:14px;padding:14px 16px;margin-bottom:12px;">'
                f'<div style="font-size:15px;font-weight:800;color:#FFFFFF;margin-bottom:8px;">'
                f'#{int(row["id"])} • {titulo}</div>'
                f'<div style="color:#D8E2EE;font-size:13px;line-height:1.7;">'
                f'Cliente: {html.escape(cliente_nome)} '
                f'• Prioridade: <b>{html.escape(prioridade)}</b> '
                f'• Status: {status_badge_html(status_atual)}'
                f'<br>'
                f'Aberta há: <b>{horas_abertas:.1f}h</b> '
                f'• Atendente: <b>{html.escape(atendente_nome)}</b>'
                f'</div></div>'
            )

            st.markdown(card_html, unsafe_allow_html=True)

    g1, g2 = st.columns(2)

    with g1:
        st.markdown("#### Solicitações por status")
        status_df = df.groupby("status_norm")["id"].count().reset_index()
        status_df.columns = ["Status", "Quantidade"]
        st.bar_chart(status_df.set_index("Status"))

    with g2:
        st.markdown("#### Solicitações por prioridade")
        prioridade_df = df.groupby("prioridade")["id"].count().reset_index()
        prioridade_df.columns = ["Prioridade", "Quantidade"]
        st.bar_chart(prioridade_df.set_index("Prioridade"))

    t1, t2 = st.columns(2)

    with t1:
        st.markdown("#### Demandas ativas por atendente")
        atendente_df = df_ativas.copy()
        if atendente_df.empty:
            st.info("Nenhuma demanda ativa.")
        else:
            atendente_df["atendente_nome"] = atendente_df["atendente_nome"].fillna(
                "Não atribuído"
            )
            atendente_df = (
                atendente_df.groupby("atendente_nome")["id"]
                .count()
                .reset_index()
                .sort_values("id", ascending=False)
            )
            atendente_df.columns = ["Atendente", "Demandas ativas"]
            st.dataframe(atendente_df, use_container_width=True, hide_index=True)

    with t2:
        st.markdown("#### Clientes com mais demandas ativas")
        clientes_df = df_ativas.copy()
        if clientes_df.empty:
            st.info("Nenhuma demanda ativa.")
        else:
            clientes_df["cliente_exibicao"] = clientes_df["cliente_nome"].fillna(
                clientes_df["cliente"]
            )
            clientes_df = (
                clientes_df.groupby("cliente_exibicao")["id"]
                .count()
                .reset_index()
                .sort_values("id", ascending=False)
                .head(10)
            )
            clientes_df.columns = ["Cliente", "Demandas ativas"]
            st.dataframe(clientes_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    st.markdown("#### Resumo executivo")
    if total_atrasadas > 0:
        st.warning(
            f"Existem {total_atrasadas} demandas fora do SLA. Priorize a fila crítica antes de iniciar novas demandas."
        )
    elif ativas > 0:
        st.info(
            "Não há demandas vencidas no momento. Mantenha foco nas demandas com maior tempo em aberto."
        )
    else:
        st.success("Não há fila ativa no momento.")

elif menu == "Cadastro de Clientes" and perfil_atual == "admin":
    st.header("Cadastro de Clientes")

    with st.expander("Cadastro de Empresa", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            cnpj = st.text_input("CNPJ")
            razao_social = st.text_input("Razão Social")
            fantasia = st.text_input("Nome Fantasia")
            cep = st.text_input("CEP")
        with c2:
            logradouro = st.text_input("Logradouro")
            numero = st.text_input("Número")
            bairro = st.text_input("Bairro")
            cidade = st.text_input("Cidade")

        if st.button("Cadastrar Empresa"):
            if not fantasia.strip() or not razao_social.strip():
                st.error("Preencha pelo menos Razão Social e Nome Fantasia.")
            else:
                conn.execute(
                    """
                    INSERT INTO empresas
                    (cnpj, razao_social, fantasia, cep, logradouro, numero, bairro, cidade, ativo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    """,
                    (
                        formatar_cnpj(cnpj.strip()),
                        razao_social.strip(),
                        fantasia.strip(),
                        cep.strip(),
                        logradouro.strip(),
                        numero.strip(),
                        bairro.strip(),
                        cidade.strip(),
                    ),
                )
                st.success("Empresa cadastrada com sucesso.")
                st.rerun()

    with st.expander("Cadastro de Usuário", expanded=True):
        nome_completo = st.text_input("Nome completo")
        cpf = st.text_input("CPF")
        email = st.text_input("E-mail")

        empresas = conn.execute(
            "SELECT id, fantasia FROM empresas WHERE ativo = TRUE ORDER BY fantasia"
        ).fetchall()

        if empresas:
            labels_empresas = [row["fantasia"] for row in empresas]
            mapa_empresas = {row["fantasia"]: row["id"] for row in empresas}
            empresa_sel = st.selectbox("Empresa", labels_empresas)
            empresa_id = mapa_empresas[empresa_sel]
        else:
            empresa_id = None
            st.warning("Cadastre pelo menos uma empresa antes de criar usuários.")

        sugestao_usuario = gerar_usuario(nome_completo) if nome_completo.strip() else ""
        usuario = st.text_input("Usuário", value=sugestao_usuario)
        senha = st.text_input("Senha", type="password")
        funcao = st.text_input("Função")
        ativo = st.checkbox("Ativo", value=True)

        if st.button("Cadastrar Usuário"):
            if not empresa_id:
                st.error("É necessário cadastrar uma empresa primeiro.")
            elif (
                not nome_completo.strip()
                or not cpf.strip()
                or not usuario.strip()
                or not senha.strip()
            ):
                st.error("Preencha os campos obrigatórios.")
            else:
                existe = conn.execute(
                    "SELECT 1 FROM clientes WHERE usuario = %s", (usuario.strip(),)
                ).fetchone()

                if existe:
                    st.error("Usuário já existe. Informe outro usuário.")
                else:
                    conn.execute(
                        """
                        INSERT INTO clientes (usuario, senha, nome, ativo, cpf, empresa_id, funcao, email)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            usuario.strip(),
                            gerar_hash_senha(senha.strip()),
                            nome_completo.strip(),
                            ativo,
                            formatar_cpf(cpf.strip()),
                            empresa_id,
                            funcao.strip(),
                            email.strip().lower(),
                        ),
                    )
                    st.success(f"Usuário {usuario.strip()} cadastrado com sucesso.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Clientes cadastrados")

    if "cliente_editando_id" not in st.session_state:
        st.session_state.cliente_editando_id = None

    clientes = conn.execute(
        """
        SELECT
            c.id,
            c.usuario,
            c.nome,
            c.ativo,
            c.cpf,
            c.funcao,
            c.email,
            c.empresa_id,
            e.fantasia AS empresa
        FROM clientes c
        LEFT JOIN empresas e ON e.id = c.empresa_id
        ORDER BY c.nome
        """
    ).fetchall()

    empresas_ativas = conn.execute(
        "SELECT id, fantasia FROM empresas WHERE ativo = TRUE ORDER BY fantasia"
    ).fetchall()
    mapa_empresas_id_nome = {row["id"]: row["fantasia"] for row in empresas_ativas}
    labels_empresas = [row["fantasia"] for row in empresas_ativas]

    if clientes:
        clientes, _, _ = paginar_registros(
            clientes, "pagina_clientes_cadastro", page_size=10
        )
        for cli in clientes:
            id_cli = cli["id"]
            with st.container(border=True):
                col1, col2, col3, col4, col5 = st.columns([2, 2.5, 2, 1.2, 3.5])

                with col1:
                    st.write(f"**{cli['usuario']}**")
                    st.caption(cli["nome"] or "")

                with col2:
                    st.write(cli["empresa"] or "Sem empresa")
                    st.caption(cli["funcao"] or "")
                    st.caption(cli["email"] or "")

                with col3:
                    st.write(f"CPF: {cli['cpf'] or ''}")

                with col4:
                    status_cliente = "Ativo" if bool(cli["ativo"]) else "Inativo"
                    st.write(status_cliente)

                with col5:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if bool(cli["ativo"]):
                            if st.button(
                                "Inativar",
                                key=f"inativar_{id_cli}",
                                use_container_width=True,
                            ):
                                conn.execute(
                                    "UPDATE clientes SET ativo = FALSE WHERE id = %s",
                                    (id_cli,),
                                )
                                st.rerun()
                        else:
                            if st.button(
                                "Ativar",
                                key=f"ativar_{id_cli}",
                                use_container_width=True,
                            ):
                                conn.execute(
                                    "UPDATE clientes SET ativo = TRUE WHERE id = %s",
                                    (id_cli,),
                                )
                                st.rerun()

                    with b2:
                        if st.button(
                            "Excluir", key=f"excluir_{id_cli}", use_container_width=True
                        ):
                            tem_solicitacao = conn.execute(
                                "SELECT 1 FROM solicitacoes WHERE cliente = %s LIMIT 1",
                                (cli["usuario"],),
                            ).fetchone()

                            if tem_solicitacao:
                                st.warning(
                                    f"O cliente {cli['usuario']} possui solicitações. Inative ao invés de excluir."
                                )
                            else:
                                conn.execute(
                                    "DELETE FROM clientes WHERE id = %s", (id_cli,)
                                )
                                st.success(f"Cliente {cli['usuario']} excluído.")
                                st.rerun()

                    with b3:
                        if st.button(
                            "Alterar", key=f"alterar_{id_cli}", use_container_width=True
                        ):
                            st.session_state.cliente_editando_id = id_cli
                            st.rerun()

                if st.session_state.cliente_editando_id == id_cli:
                    st.markdown("**Alteração de cadastro**")
                    e1, e2, e3 = st.columns(3)

                    with e1:
                        novo_nome = st.text_input(
                            "Nome completo",
                            value=cli["nome"] or "",
                            key=f"edit_nome_{id_cli}",
                        )
                        novo_cpf = st.text_input(
                            "CPF", value=cli["cpf"] or "", key=f"edit_cpf_{id_cli}"
                        )
                    with e2:
                        novo_usuario = st.text_input(
                            "Usuário",
                            value=cli["usuario"] or "",
                            key=f"edit_usuario_{id_cli}",
                        )
                        nova_funcao = st.text_input(
                            "Função",
                            value=cli["funcao"] or "",
                            key=f"edit_funcao_{id_cli}",
                        )
                    with e3:
                        novo_email = st.text_input(
                            "E-mail",
                            value=cli["email"] or "",
                            key=f"edit_email_{id_cli}",
                        )
                        empresa_atual_nome = mapa_empresas_id_nome.get(
                            cli["empresa_id"]
                        )
                        if labels_empresas:
                            idx_empresa = (
                                labels_empresas.index(empresa_atual_nome)
                                if empresa_atual_nome in labels_empresas
                                else 0
                            )
                            empresa_edit_nome = st.selectbox(
                                "Empresa",
                                labels_empresas,
                                index=idx_empresa,
                                key=f"edit_empresa_{id_cli}",
                            )
                            nova_empresa_id = next(
                                row["id"]
                                for row in empresas_ativas
                                if row["fantasia"] == empresa_edit_nome
                            )
                        else:
                            st.warning("Não há empresas ativas para vincular.")
                            nova_empresa_id = cli["empresa_id"]

                        nova_senha = st.text_input(
                            "Nova senha (opcional)",
                            type="password",
                            key=f"edit_senha_{id_cli}",
                        )

                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button(
                            "Salvar alteração",
                            key=f"salvar_alteracao_{id_cli}",
                            use_container_width=True,
                        ):
                            if (
                                not novo_nome.strip()
                                or not novo_cpf.strip()
                                or not novo_usuario.strip()
                            ):
                                st.error("Preencha nome, CPF e usuário.")
                            else:
                                usuario_existente = conn.execute(
                                    "SELECT 1 FROM clientes WHERE usuario = %s AND id <> %s",
                                    (novo_usuario.strip(), id_cli),
                                ).fetchone()

                                if usuario_existente:
                                    st.error(
                                        "Já existe outro cliente com esse usuário."
                                    )
                                else:
                                    if nova_senha.strip():
                                        conn.execute(
                                            """
                                            UPDATE clientes
                                            SET nome = %s, cpf = %s, usuario = %s, funcao = %s, empresa_id = %s, senha = %s, email = %s
                                            WHERE id = %s
                                            """,
                                            (
                                                novo_nome.strip(),
                                                formatar_cpf(novo_cpf.strip()),
                                                novo_usuario.strip(),
                                                nova_funcao.strip(),
                                                nova_empresa_id,
                                                gerar_hash_senha(nova_senha.strip()),
                                                novo_email.strip().lower(),
                                                id_cli,
                                            ),
                                        )
                                    else:
                                        conn.execute(
                                            """
                                            UPDATE clientes
                                            SET nome = %s, cpf = %s, usuario = %s, funcao = %s, empresa_id = %s, email = %s
                                            WHERE id = %s
                                            """,
                                            (
                                                novo_nome.strip(),
                                                formatar_cpf(novo_cpf.strip()),
                                                novo_usuario.strip(),
                                                nova_funcao.strip(),
                                                nova_empresa_id,
                                                novo_email.strip().lower(),
                                                id_cli,
                                            ),
                                        )

                                    conn.execute(
                                        "UPDATE solicitacoes SET cliente = %s WHERE cliente = %s",
                                        (novo_usuario.strip(), cli["usuario"]),
                                    )
                                    st.session_state.cliente_editando_id = None
                                    st.success("Cadastro atualizado com sucesso.")
                                    st.rerun()
                    with a2:
                        if st.button(
                            "Cancelar alteração",
                            key=f"cancelar_alteracao_{id_cli}",
                            use_container_width=True,
                        ):
                            st.session_state.cliente_editando_id = None
                            st.rerun()
    else:
        st.info("Nenhum cliente cadastrado ainda.")


elif menu == "Cadastro de Atendentes" and perfil_atual == "admin":
    st.header("Cadastro de Atendentes")

    with st.expander("Novo atendente", expanded=True):
        nome_atendente = st.text_input("Nome do atendente")
        usuario_atendente = st.text_input(
            "Usuário do atendente",
            value=gerar_usuario(nome_atendente) if nome_atendente.strip() else "",
            key="novo_atendente_usuario",
        )
        email_atendente = st.text_input("E-mail", key="novo_atendente_email")
        senha_atendente = st.text_input(
            "Senha", type="password", key="novo_atendente_senha"
        )
        ativo_atendente = st.checkbox("Ativo", value=True, key="novo_atendente_ativo")

        if st.button("Cadastrar Atendente"):
            if (
                not nome_atendente.strip()
                or not usuario_atendente.strip()
                or not senha_atendente.strip()
            ):
                st.error("Preencha nome, usuário e senha.")
            else:
                existe = conn.execute(
                    "SELECT 1 FROM atendentes WHERE usuario = %s",
                    (usuario_atendente.strip(),),
                ).fetchone()
                if existe:
                    st.error("Já existe um atendente com esse usuário.")
                else:
                    conn.execute(
                        """
                        INSERT INTO atendentes (nome, usuario, senha, email, ativo)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            nome_atendente.strip(),
                            usuario_atendente.strip(),
                            gerar_hash_senha(senha_atendente.strip()),
                            email_atendente.strip().lower(),
                            ativo_atendente,
                        ),
                    )
                    st.success("Atendente cadastrado com sucesso.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Atendentes cadastrados")

    if "atendente_editando_id" not in st.session_state:
        st.session_state.atendente_editando_id = None

    atendentes = obter_todos_atendentes()

    if atendentes:
        atendentes, _, _ = paginar_registros(
            atendentes, "pagina_atendentes_cadastro", page_size=10
        )
        for atendente in atendentes:
            atendente_id = atendente["id"]
            with st.container(border=True):
                col1, col2, col3 = st.columns([2.2, 2.4, 3.4])

                with col1:
                    st.write(f"**{atendente['usuario']}**")
                    st.caption(atendente["nome"] or "")

                with col2:
                    st.write(atendente["email"] or "Sem e-mail")
                    st.write("Ativo" if bool(atendente["ativo"]) else "Inativo")

                with col3:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if bool(atendente["ativo"]):
                            if st.button(
                                "Inativar",
                                key=f"inativar_atendente_{atendente_id}",
                                use_container_width=True,
                            ):
                                conn.execute(
                                    "UPDATE atendentes SET ativo = FALSE WHERE id = %s",
                                    (atendente_id,),
                                )
                                st.rerun()
                        else:
                            if st.button(
                                "Ativar",
                                key=f"ativar_atendente_{atendente_id}",
                                use_container_width=True,
                            ):
                                conn.execute(
                                    "UPDATE atendentes SET ativo = TRUE WHERE id = %s",
                                    (atendente_id,),
                                )
                                st.rerun()

                    with b2:
                        if st.button(
                            "Excluir",
                            key=f"excluir_atendente_{atendente_id}",
                            use_container_width=True,
                        ):
                            possui_vinculo = conn.execute(
                                "SELECT 1 FROM solicitacoes WHERE atendente_id = %s LIMIT 1",
                                (atendente_id,),
                            ).fetchone()

                            if possui_vinculo:
                                st.warning(
                                    "Este atendente já está vinculado a solicitações. Inative ao invés de excluir."
                                )
                            else:
                                conn.execute(
                                    "DELETE FROM atendentes WHERE id = %s",
                                    (atendente_id,),
                                )
                                st.success("Atendente excluído.")
                                st.rerun()

                    with b3:
                        if st.button(
                            "Alterar",
                            key=f"alterar_atendente_{atendente_id}",
                            use_container_width=True,
                        ):
                            st.session_state.atendente_editando_id = atendente_id
                            st.rerun()

                if st.session_state.atendente_editando_id == atendente_id:
                    ed1, ed2 = st.columns(2)

                    with ed1:
                        novo_nome_at = st.text_input(
                            "Nome",
                            value=atendente["nome"] or "",
                            key=f"edit_at_nome_{atendente_id}",
                        )
                        novo_usuario_at = st.text_input(
                            "Usuário",
                            value=atendente["usuario"] or "",
                            key=f"edit_at_usuario_{atendente_id}",
                        )

                    with ed2:
                        novo_email_at = st.text_input(
                            "E-mail",
                            value=atendente["email"] or "",
                            key=f"edit_at_email_{atendente_id}",
                        )
                        nova_senha_at = st.text_input(
                            "Nova senha (opcional)",
                            type="password",
                            key=f"edit_at_senha_{atendente_id}",
                        )

                    a1, a2 = st.columns(2)
                    with a1:
                        if st.button(
                            "Salvar alteração",
                            key=f"salvar_atendente_{atendente_id}",
                            use_container_width=True,
                        ):
                            if not novo_nome_at.strip() or not novo_usuario_at.strip():
                                st.error("Preencha nome e usuário.")
                            else:
                                usuario_existente = conn.execute(
                                    "SELECT 1 FROM atendentes WHERE usuario = %s AND id <> %s",
                                    (novo_usuario_at.strip(), atendente_id),
                                ).fetchone()

                                if usuario_existente:
                                    st.error(
                                        "Já existe outro atendente com esse usuário."
                                    )
                                else:
                                    if nova_senha_at.strip():
                                        conn.execute(
                                            """
                                            UPDATE atendentes
                                            SET nome = %s, usuario = %s, email = %s, senha = %s
                                            WHERE id = %s
                                            """,
                                            (
                                                novo_nome_at.strip(),
                                                novo_usuario_at.strip(),
                                                novo_email_at.strip().lower(),
                                                gerar_hash_senha(nova_senha_at.strip()),
                                                atendente_id,
                                            ),
                                        )
                                    else:
                                        conn.execute(
                                            """
                                            UPDATE atendentes
                                            SET nome = %s, usuario = %s, email = %s
                                            WHERE id = %s
                                            """,
                                            (
                                                novo_nome_at.strip(),
                                                novo_usuario_at.strip(),
                                                novo_email_at.strip().lower(),
                                                atendente_id,
                                            ),
                                        )

                                    st.session_state.atendente_editando_id = None
                                    st.success("Atendente atualizado com sucesso.")
                                    st.rerun()
                    with a2:
                        if st.button(
                            "Cancelar alteração",
                            key=f"cancelar_atendente_{atendente_id}",
                            use_container_width=True,
                        ):
                            st.session_state.atendente_editando_id = None
                            st.rerun()
    else:
        st.info("Nenhum atendente cadastrado ainda.")


elif menu == "Painel de Cadastros" and perfil_atual == "admin":
    st.header("Painel de Cadastros")
    st.caption(
        "Pré-cadastro por convite com geração de link para conclusão pelo cliente ou atendente."
    )

    tab1, tab2, tab3 = st.tabs(["Novo convite", "Pendentes / enviados", "Concluídos"])

    with tab1:
        empresas = conn.execute(
            "SELECT id, fantasia FROM empresas WHERE ativo = TRUE ORDER BY fantasia"
        ).fetchall()
        nome_convite = st.text_input("Nome", key="convite_nome")
        email_convite = st.text_input("E-mail", key="convite_email")
        tipo_convite = st.selectbox(
            "Tipo de usuário", ["cliente", "atendente"], key="convite_tipo"
        )
        obs_convite = st.text_area("Observação", key="convite_obs")
        empresa_id_convite = None

        if empresas:
            opcoes = ["Selecione"] + [row["fantasia"] for row in empresas]
            empresa_nome = st.selectbox("Empresa", opcoes, key="convite_empresa")
            if empresa_nome != "Selecione":
                empresa_id_convite = next(
                    row["id"] for row in empresas if row["fantasia"] == empresa_nome
                )
        else:
            st.warning(
                "Cadastre ao menos uma empresa ativa para usar o painel de convites."
            )

        if st.button("Gerar convite e link", key="criar_convite_btn"):
            if not nome_convite.strip() or not email_convite.strip():
                st.error("Preencha nome e e-mail.")
            elif tipo_convite == "cliente" and not empresa_id_convite:
                st.error("Selecione a empresa do cliente.")
            else:
                convite_id, token = criar_convite(
                    nome=nome_convite,
                    email=email_convite,
                    empresa_id=empresa_id_convite,
                    tipo_usuario=tipo_convite,
                    observacao=obs_convite,
                )
                link = montar_url_convite(token)
                st.success("Convite criado com sucesso.")
                st.code(link, language="text")
                st.session_state["ultimo_link_convite"] = link

        ultimo_link = st.session_state.get("ultimo_link_convite")
        if ultimo_link:
            st.caption("Último link gerado")
            st.code(ultimo_link, language="text")

    with tab2:
        convites = conn.execute(
            """
            SELECT c.*, e.fantasia AS empresa_nome
            FROM convites_cadastro c
            LEFT JOIN empresas e ON e.id = c.empresa_id
            WHERE c.status IN ('pendente', 'enviado', 'expirado')
            ORDER BY c.created_at DESC
            """
        ).fetchall()

        if not convites:
            st.info("Nenhum convite pendente/enviado.")
        else:
            for convite in convites:
                link = montar_url_convite(convite["token"])
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2.4, 1.6, 1.4, 3.2])
                    with c1:
                        st.write(f"**{convite['nome']}**")
                        st.caption(convite["email"])
                    with c2:
                        st.write(convite["tipo_usuario"].capitalize())
                        st.caption(convite.get("empresa_nome") or "Sem empresa")
                    with c3:
                        st.write(convite["status"].capitalize())
                        exp = (
                            convite["expiracao_em"].strftime("%d/%m/%Y %H:%M")
                            if convite["expiracao_em"]
                            else "-"
                        )
                        st.caption(f"Expira em {exp}")
                    with c4:
                        a1, a2, a3 = st.columns(3)
                        with a1:
                            if st.button(
                                "Reenviar",
                                key=f"reenviar_convite_{convite['id']}",
                                use_container_width=True,
                            ):
                                novo_token = reenviar_convite(convite["id"])
                                st.session_state[f"link_convite_{convite['id']}"] = (
                                    montar_url_convite(novo_token)
                                )
                                st.success("Convite renovado com novo link.")
                                st.rerun()
                        with a2:
                            if st.button(
                                "Cancelar",
                                key=f"cancelar_convite_{convite['id']}",
                                use_container_width=True,
                            ):
                                conn.execute(
                                    "UPDATE convites_cadastro SET status = 'cancelado' WHERE id = %s",
                                    (convite["id"],),
                                )
                                st.success("Convite cancelado.")
                                st.rerun()
                        with a3:
                            st.code(
                                st.session_state.get(
                                    f"link_convite_{convite['id']}", link
                                ),
                                language="text",
                            )

    with tab3:
        concluidos = conn.execute(
            """
            SELECT c.*, e.fantasia AS empresa_nome
            FROM convites_cadastro c
            LEFT JOIN empresas e ON e.id = c.empresa_id
            WHERE c.status = 'concluido'
            ORDER BY c.utilizado_em DESC NULLS LAST, c.created_at DESC
            """
        ).fetchall()
        if not concluidos:
            st.info("Nenhum cadastro concluído ainda.")
        else:
            for convite in concluidos:
                with st.container(border=True):
                    st.write(f"**{convite['nome']}** • {convite['email']}")
                    st.caption(
                        f"Tipo: {convite['tipo_usuario'].capitalize()} • "
                        f"Empresa: {convite.get('empresa_nome') or 'Sem empresa'} • "
                        f"Concluído em: {convite['utilizado_em'].strftime('%d/%m/%Y %H:%M') if convite['utilizado_em'] else '-'}"
                    )

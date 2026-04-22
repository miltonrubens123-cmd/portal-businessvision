import os
import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
import psycopg
from zoneinfo import ZoneInfo
from psycopg.rows import dict_row


@st.cache_resource
def get_connection():
    database_url = None

    if "database" in st.secrets and "url" in st.secrets["database"]:
        database_url = st.secrets["database"]["url"]
    else:
        database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL não configurado.")

    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
    )


def get_conn():
    """
    Retorna uma conexão válida.
    Se a conexão cacheada caiu ou expirou, limpa o cache e reconecta.
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return conn
    except Exception:
        get_connection.clear()
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return conn


class SafeConnProxy:
    def execute(self, *args, **kwargs):
        return get_conn().execute(*args, **kwargs)

    def cursor(self, *args, **kwargs):
        return get_conn().cursor(*args, **kwargs)


def run_query(sql, params=None, fetchone=False, fetchall=False):
    with get_conn().cursor() as cur:
        cur.execute(sql, params or ())
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        return None


# ----------------------------
# CONFIGURAÇÃO INICIAL
# ----------------------------
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

conn = SafeConnProxy()  # proxy com reconexão automática


# ----------------------------
# SEGURANÇA / AUTENTICAÇÃO
# ----------------------------
PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390000
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))


def obter_secret(path, default=None):
    try:
        cursor = st.secrets
        for key in path:
            cursor = cursor[key]
        return cursor
    except Exception:
        return default


def obter_admin_config():
    admin_user = (
        obter_secret(["admin", "user"])
        or os.getenv("ADMIN_USER")
        or ""
    ).strip()

    admin_password_hash = (
        obter_secret(["admin", "password_hash"])
        or os.getenv("ADMIN_PASSWORD_HASH")
        or ""
    ).strip()

    admin_password_plain = (
        obter_secret(["admin", "password"])
        or os.getenv("ADMIN_PASSWORD")
        or ""
    ).strip()

    return {
        "user": admin_user,
        "password_hash": admin_password_hash,
        "password_plain": admin_password_plain,
    }


def senha_esta_hasheada(valor):
    return isinstance(valor, str) and valor.startswith(f"{PASSWORD_SCHEME}$")


def gerar_hash_senha(senha):
    if not isinstance(senha, str) or not senha.strip():
        raise ValueError("Senha inválida para geração de hash.")

    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${dk.hex()}"


def verificar_senha(senha_informada, senha_armazenada):
    if not senha_armazenada or not isinstance(senha_armazenada, str):
        return False

    if senha_esta_hasheada(senha_armazenada):
        try:
            _, iteracoes, salt, hash_salvo = senha_armazenada.split("$", 3)
            dk = hashlib.pbkdf2_hmac(
                "sha256",
                (senha_informada or "").encode("utf-8"),
                salt.encode("utf-8"),
                int(iteracoes),
            )
            return hmac.compare_digest(dk.hex(), hash_salvo)
        except Exception:
            return False

    return hmac.compare_digest(senha_armazenada, senha_informada or "")


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
        SELECT id, usuario, senha, nome, ativo, cpf, empresa_id, funcao
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


def validar_upload_imagem(arquivo):
    nome = (arquivo.name or "").lower()
    ext_permitidas = {".png", ".jpg", ".jpeg"}
    ext = Path(nome).suffix.lower()

    if ext not in ext_permitidas:
        return False, "Tipo de arquivo inválido. Envie apenas PNG, JPG ou JPEG."

    tamanho = len(arquivo.getvalue())
    limite = MAX_UPLOAD_MB * 1024 * 1024
    if tamanho > limite:
        return (
            False,
            f"O arquivo {arquivo.name} excede o limite de {MAX_UPLOAD_MB} MB.",
        )

    return True, ""


admin_config = obter_admin_config()
admin_user = admin_config["user"]



# ----------------------------
# LOGO
# ----------------------------
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


# ----------------------------
# DATA/HORA
# ----------------------------
def agora():
    return datetime.now(APP_TZ)


def agora_str():
    return agora().strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------
# BANCO
# ----------------------------
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

    if not coluna_existe("clientes", "cpf"):
        conn.execute("ALTER TABLE clientes ADD COLUMN cpf TEXT")

    if not coluna_existe("clientes", "empresa_id"):
        conn.execute(
            "ALTER TABLE clientes ADD COLUMN empresa_id BIGINT REFERENCES empresas(id)"
        )

    if not coluna_existe("clientes", "funcao"):
        conn.execute("ALTER TABLE clientes ADD COLUMN funcao TEXT")

    if not coluna_existe("empresas", "ativo"):
        conn.execute("ALTER TABLE empresas ADD COLUMN ativo BOOLEAN DEFAULT TRUE")

    for coluna in [
        "complexidade",
        "resposta",
        "data_criacao",
        "inicio_atendimento",
        "fim_atendimento",
    ]:
        if not coluna_existe("solicitacoes", coluna):
            if coluna in ["data_criacao", "inicio_atendimento", "fim_atendimento"]:
                conn.execute(f"ALTER TABLE solicitacoes ADD COLUMN {coluna} TIMESTAMP")
            else:
                conn.execute(f"ALTER TABLE solicitacoes ADD COLUMN {coluna} TEXT")

    if not coluna_existe("solicitacoes", "atendente_id"):
        conn.execute(
            "ALTER TABLE solicitacoes ADD COLUMN atendente_id BIGINT REFERENCES atendentes(id)"
        )

    if not coluna_existe("solicitacoes", "atribuido_em"):
        conn.execute("ALTER TABLE solicitacoes ADD COLUMN atribuido_em TIMESTAMP")

    if not coluna_existe("sessoes_login", "menu"):
        conn.execute("ALTER TABLE sessoes_login ADD COLUMN menu TEXT")


# Executa bootstrap de schema apenas se explicitamente habilitado.
# Em produção, deixe desabilitado para evitar DDL e consultas ao information_schema em todo rerun.
RUN_DB_BOOTSTRAP = os.getenv("RUN_DB_BOOTSTRAP", "false").lower() == "true"
if RUN_DB_BOOTSTRAP:
    criar_tabelas()


# ----------------------------
# SESSION STATE
# ----------------------------
def init_state():
    defaults = {
        "logado": False,
        "usuario": "",
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


# ----------------------------
# FUNÇÕES AUXILIARES
# ----------------------------
def gerar_usuario(nome):
    partes = [p for p in re.split(r"\s+", nome.strip().lower()) if p]
    if not partes:
        return ""
    usuario = f"{partes[0]}_{partes[-1]}" if len(partes) > 1 else partes[0]
    return re.sub(r"[^a-z0-9_]", "", usuario)


def criar_sessao_login(usuario, menu="Nova Solicitação"):
    token = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO sessoes_login (token, usuario, menu, data_criacao)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (token)
        DO UPDATE SET
            usuario = EXCLUDED.usuario,
            menu = EXCLUDED.menu,
            data_criacao = EXCLUDED.data_criacao
        """,
        (token, usuario, menu, agora()),
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
        "SELECT token, usuario, menu, data_criacao FROM sessoes_login WHERE token = %s",
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
    if usuario != admin_user:
        cliente = conn.execute(
            "SELECT usuario FROM clientes WHERE usuario = %s AND ativo = TRUE",
            (usuario,),
        ).fetchone()
        if not cliente:
            return

    st.session_state.logado = True
    st.session_state.usuario = usuario
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


def normalizar_status(status):
    mapa = {
        "Pendente": "Em análise",
        "Iniciado": "Em atendimento",
        "Pausado": "Aguardando cliente",
        "Resolvido": "Concluído",
        "Em análise": "Em análise",
        "Em atendimento": "Em atendimento",
        "Aguardando cliente": "Aguardando cliente",
        "Concluído": "Concluído",
    }
    return mapa.get(status, status)


def formatar_status_texto(status):
    status = normalizar_status(status)
    status_map = {
        "Em análise": "🔴 Em análise",
        "Em atendimento": "🟢 Em atendimento",
        "Aguardando cliente": "🟡 Aguardando cliente",
        "Concluído": "🔵 Concluído",
    }
    return status_map.get(status, status)

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


def obter_nome_atendente(atendente_id):
    if not atendente_id:
        return ""
    row = conn.execute(
        "SELECT nome FROM atendentes WHERE id = %s",
        (atendente_id,),
    ).fetchone()
    return row["nome"] if row and row["nome"] else ""


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


def obter_solicitacoes_filtradas(
    cliente_id=None,
    cliente_usuario=None,
    empresa_id=None,
    status_filtro="Todos",
    prioridade_filtro="Todas",
    busca="",
    limite=50,
):
    filtros = []
    params = []

    if cliente_id is not None:
        filtros.append("(s.cliente_id = %s OR (s.cliente_id IS NULL AND s.s.cliente = %s))")
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
                WHEN s.status = 'Pausado' THEN 'Aguardando cliente'
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
        if busca.isdigit():
            filtros.append("(CAST(s.id AS TEXT) = %s OR s.s.titulo ILIKE %s)")
            params.append(busca)
            params.append(f"%{busca}%")
        else:
            filtros.append("s.titulo ILIKE %s")
            params.append(f"%{busca}%")

    where_clause = " AND ".join(filtros) if filtros else "TRUE"

    sql = f"""
        SELECT
            s.id,
            s.cliente,
            s.cliente_id,
            s.empresa_id,
            s.atendente_id,
            a.nome AS atendente_nome,
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
        LEFT JOIN atendentes a ON a.id = s.atendente_id
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
            height: 100vh;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }

        .login-wrapper {
            width: 100%;
            max-width: 420px;
        }

        .stTextInput label {
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


# ----------------------------
# LOGIN
# ----------------------------
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
            elif autenticar_admin(usuario_digitado, senha_digitada):
                token = criar_sessao_login(usuario_digitado, "Nova Solicitação")
                st.session_state.logado = True
                st.session_state.usuario = usuario_digitado
                st.session_state.menu_atual = "Nova Solicitação"
                st.session_state.token_sessao = token
                persistir_query_params()
                st.rerun()
            else:
                cliente = autenticar_cliente(usuario_digitado, senha_digitada)

                if cliente:
                    token = criar_sessao_login(usuario_digitado, "Nova Solicitação")
                    st.session_state.logado = True
                    st.session_state.usuario = usuario_digitado
                    st.session_state.menu_atual = "Nova Solicitação"
                    st.session_state.token_sessao = token
                    persistir_query_params()
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")

        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()


# ----------------------------
# APP LOGADO
# ----------------------------
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

st.markdown("<hr style='border:1px solid #333; margin-top:0;'>", unsafe_allow_html=True)
st.caption("Gestão de demandas e acompanhamento em tempo real")


# ----------------------------
# MENU
# ----------------------------
menu_options_admin = [
    "Nova Solicitação",
    "Demandas Solicitadas",
    "Dashboard",
    "Cadastro de Clientes",
    "Cadastro de Atendentes",
]
menu_options_cliente = ["Nova Solicitação", "Demandas Solicitadas"]
menu_options = (
    menu_options_admin
    if st.session_state.usuario == admin_user
    else menu_options_cliente
)

try:
    default_idx = menu_options.index(
        st.session_state.get("menu_atual", "Nova Solicitação")
    )
except ValueError:
    default_idx = 0

menu = st.sidebar.selectbox("Menu", menu_options, index=default_idx, key="menu_select")
st.session_state.menu_atual = menu
atualizar_menu_sessao(st.session_state.get("token_sessao"), menu)
persistir_query_params()

st.sidebar.markdown("---")
st.sidebar.markdown(f"👤 Usuário: **{st.session_state.usuario}**")
if st.sidebar.button("Trocar usuário"):
    logout()


# ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
if menu == "Nova Solicitação":
    st.header("Nova Solicitação")

    if st.session_state.get("limpar_campos_nova_solicitacao", False):
        st.session_state["titulo"] = ""
        st.session_state["descricao"] = ""
        st.session_state.limpar_campos_nova_solicitacao = False

    if st.session_state.usuario == admin_user:
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
        st.text_input("Cliente", value=obter_nome_cliente(cliente_usuario), disabled=True)

    titulo = st.text_input("Título", key="titulo")
    descricao = st.text_area("Descrição", key="descricao")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

    if st.session_state.usuario == admin_user:
        complexidade = st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])
    else:
        complexidade = ""

    st.subheader("Anexos de evidência")
    arquivos = st.file_uploader(
        "Envie pelo menos 1 imagem",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="anexos_upload",
    )

    observacoes_anexos = []
    if arquivos:
        for idx, arq in enumerate(arquivos, start=1):
            st.caption(f"Arquivo {idx}: {arq.name}")
            obs = st.text_input(f"Observação da imagem {idx}", key=f"obs_img_{idx}")
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
        elif not arquivos or len(arquivos) == 0:
            st.error("É obrigatório enviar pelo menos uma imagem.")
        else:
            uploads_invalidos = []
            for arquivo in arquivos:
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
                      AND status IN ('Pendente', 'Iniciado', 'Pausado', 'Em análise', 'Em atendimento', 'Aguardando cliente')
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

                            for idx, arq in enumerate(arquivos):
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


# ----------------------------
# DEMANDAS SOLICITADAS
# ----------------------------
elif menu == "Demandas Solicitadas":
    st.header("Demandas Solicitadas")

    col_legenda1, col_legenda2 = st.columns([8, 1])

    with col_legenda2:
        if st.button("📌 Legenda", use_container_width=True):
            st.session_state.mostrar_legenda = not st.session_state.get(
                "mostrar_legenda", False
            )

    if st.session_state.get("mostrar_legenda", False):
        st.info(
            """
🔴 Em análise  
🟢 Em atendimento  
🟡 Aguardando cliente  
🔵 Concluído
            """
        )

    f1, f2, f3 = st.columns([1.2, 1.2, 2.2])
    with f1:
        status_filtro = st.selectbox(
            "Filtrar por status",
            ["Todos", "Em análise", "Em atendimento", "Aguardando cliente", "Concluído"],
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

    st.caption("Exibindo no máximo 50 registros por cliente para preservar performance.")

    if st.session_state.usuario == admin_user:
        clientes = conn.execute(
            """
            SELECT id, usuario, nome, empresa_id
            FROM clientes
            WHERE ativo = TRUE
            ORDER BY nome, usuario
            """
        ).fetchall()
    else:
        cliente_logado = obter_cliente_por_usuario(st.session_state.usuario)
        clientes = [cliente_logado] if cliente_logado else []

    encontrou_resultado = False

    for cli in clientes:
        if not cli:
            continue

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

        if st.session_state.usuario != admin_user:
            df_exibicao = df_cli.copy()
            df_exibicao["status"] = df_exibicao["status"].apply(formatar_status_texto)
            df_exibicao["observacoes"] = df_exibicao["resposta"].fillna("")
            df_exibicao = df_exibicao[
                ["id", "titulo", "prioridade", "status", "observacoes", "data_criacao"]
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

                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([0.7, 2.5, 1.2, 1.4, 1.5])

                    with c1:
                        st.write(f"**#{solicitacao_id}**")
                    with c2:
                        st.write(f"**{row['titulo']}**")
                        st.caption(row["descricao"])
                    with c3:
                        st.write(f"Prioridade: **{row['prioridade']}**")
                    with c4:
                        st.write(f"Status: **{formatar_status_texto(status_atual)}**")
                    with c5:
                        if row["complexidade"]:
                            st.write(f"Complexidade: **{row['complexidade']}**")

                    with st.expander(f"Anexos da solicitação #{solicitacao_id}"):
                        render_anexos_como_arquivo(
                            solicitacao_id, prefixo=f"admin_{solicitacao_id}"
                        )

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

                    atendentes_ativos = obter_atendentes_ativos()
                    nome_atendente_atual = row.get("atendente_nome") or "Não atribuído"
                    st.caption(f"Atendente atual: {nome_atendente_atual}")

                    if atendentes_ativos:
                        opcoes_atendentes = {
                            atendente["nome"]: atendente["id"] for atendente in atendentes_ativos
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

                    ac1, ac2, ac3, ac4 = st.columns([1.2, 1.2, 1, 3.6])

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
                                    "Aguardando cliente",
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

                    elif status_atual == "Aguardando cliente":
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

                    meta1, meta2, meta3, meta4 = st.columns(4)
                    with meta1:
                        st.caption(
                            f"Criado em: {row['data_criacao'].strftime('%Y-%m-%d %H:%M:%S') if row['data_criacao'] else ''}"
                        )
                    with meta2:
                        st.caption(
                            f"Início: {row['inicio_atendimento'].strftime('%Y-%m-%d %H:%M:%S') if row['inicio_atendimento'] else ''}"
                        )
                    with meta3:
                        st.caption(
                            f"Fim: {row['fim_atendimento'].strftime('%Y-%m-%d %H:%M:%S') if row['fim_atendimento'] else ''}"
                        )
                    with meta4:
                        st.caption(
                            f"Atribuído em: {row['atribuido_em'].strftime('%Y-%m-%d %H:%M:%S') if row.get('atribuido_em') else ''}"
                        )

    if not encontrou_resultado:
        st.info("Nenhuma solicitação encontrada com os filtros aplicados.")


# ----------------------------
# DASHBOARD
# ----------------------------
elif menu == "Dashboard" and st.session_state.usuario == admin_user:
    st.header("Dashboard")

    if logo:
        st.image(logo, width=100)

    st.markdown("<hr>", unsafe_allow_html=True)

    dados = conn.execute(
        """
        SELECT
            id,
            cliente,
            titulo,
            descricao,
            prioridade,
            status,
            complexidade,
            resposta,
            data_criacao,
            inicio_atendimento,
            fim_atendimento
        FROM solicitacoes
        """
    ).fetchall()

    colunas = [
        "ID",
        "Cliente",
        "Título",
        "Descrição",
        "Prioridade",
        "Status",
        "Complexidade",
        "Resposta",
        "Data",
        "Início",
        "Fim",
    ]
    df = (
        pd.DataFrame([tuple(r.values()) for r in dados], columns=colunas)
        if dados
        else pd.DataFrame(columns=colunas)
    )

    if not df.empty:
        df["Status"] = df["Status"].apply(normalizar_status)

    total = len(df)
    finalizadas = len(df[df["Status"].apply(normalizar_status) == "Concluído"])
    pendentes_iniciadas = len(
        df[df["Status"].isin(["Em análise", "Iniciado", "Pausado"])]
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Solicitações", total)
    col2.metric("Finalizadas", finalizadas)
    col3.metric("Pendentes/Iniciadas", pendentes_iniciadas)

    st.subheader("Solicitações por Prioridade")
    if not df.empty:
        resumo = df.groupby("Prioridade")["ID"].count().reset_index()
        resumo.columns = ["Prioridade", "Quantidade"]
        st.bar_chart(resumo.set_index("Prioridade"))
    else:
        st.info("Nenhuma solicitação registrada ainda.")

    st.subheader("Tempo médio de atendimento")
    if not df.empty:
        df_tempo = df.copy()
        df_tempo = df_tempo[
            df_tempo["Início"].notna()
            & df_tempo["Fim"].notna()
            & (df_tempo["Início"] != "")
            & (df_tempo["Fim"] != "")
        ].copy()

        if not df_tempo.empty:
            df_tempo["Início"] = pd.to_datetime(df_tempo["Início"], errors="coerce")
            df_tempo["Fim"] = pd.to_datetime(df_tempo["Fim"], errors="coerce")
            df_tempo["Horas"] = (
                df_tempo["Fim"] - df_tempo["Início"]
            ).dt.total_seconds() / 3600
            media_horas = df_tempo["Horas"].dropna().mean()

            if pd.notna(media_horas):
                st.metric("Tempo médio (horas)", f"{media_horas:.2f}")
            else:
                st.info("Ainda não há dados suficientes para calcular o tempo médio.")
        else:
            st.info("Ainda não há dados suficientes para calcular o tempo médio.")
    else:
        st.info("Ainda não há dados suficientes para calcular o tempo médio.")


# ----------------------------
# CADASTRO DE CLIENTES E EMPRESAS
# ----------------------------
elif menu == "Cadastro de Clientes" and st.session_state.usuario == admin_user:
    st.header("Cadastro de Clientes")

    with st.expander("🏢 Cadastro de Empresa", expanded=False):
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
                        cnpj.strip(),
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

    with st.expander("👤 Cadastro de Usuário", expanded=True):
        nome_completo = st.text_input("Nome completo")
        cpf = st.text_input("CPF")

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
                    "SELECT 1 FROM clientes WHERE usuario = %s",
                    (usuario.strip(),),
                ).fetchone()

                if existe:
                    st.error("Usuário já existe. Informe outro usuário.")
                else:
                    conn.execute(
                        """
                        INSERT INTO clientes (usuario, senha, nome, ativo, cpf, empresa_id, funcao)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            usuario.strip(),
                            gerar_hash_senha(senha.strip()),
                            nome_completo.strip(),
                            ativo,
                            cpf.strip(),
                            empresa_id,
                            funcao.strip(),
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

                with col3:
                    st.write(f"CPF: {cli['cpf'] or ''}")

                with col4:
                    status_cliente = "🟢 Ativo" if bool(cli["ativo"]) else "🔴 Inativo"
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
                                "SELECT 1 FROM solicitacoes WHERE s.cliente = %s LIMIT 1",
                                (cli["usuario"],),
                            ).fetchone()

                            if tem_solicitacao:
                                st.warning(
                                    f"O cliente {cli['usuario']} possui solicitações. Inative ao invés de excluir."
                                )
                            else:
                                conn.execute(
                                    "DELETE FROM clientes WHERE id = %s",
                                    (id_cli,),
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
                                            SET nome = %s, cpf = %s, usuario = %s, funcao = %s, s.empresa_id = %s, senha = %s
                                            WHERE id = %s
                                            """,
                                            (
                                                novo_nome.strip(),
                                                novo_cpf.strip(),
                                                novo_usuario.strip(),
                                                nova_funcao.strip(),
                                                nova_empresa_id,
                                                gerar_hash_senha(nova_senha.strip()),
                                                id_cli,
                                            ),
                                        )
                                    else:
                                        conn.execute(
                                            """
                                            UPDATE clientes
                                            SET nome = %s, cpf = %s, usuario = %s, funcao = %s, s.empresa_id = %s
                                            WHERE id = %s
                                            """,
                                            (
                                                novo_nome.strip(),
                                                novo_cpf.strip(),
                                                novo_usuario.strip(),
                                                nova_funcao.strip(),
                                                nova_empresa_id,
                                                id_cli,
                                            ),
                                        )

                                    conn.execute(
                                        "UPDATE solicitacoes SET s.cliente = %s WHERE s.cliente = %s",
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


# ----------------------------
# CADASTRO DE ATENDENTES
# ----------------------------
elif menu == "Cadastro de Atendentes" and st.session_state.usuario == admin_user:
    st.header("Cadastro de Atendentes")

    with st.expander("🛠️ Novo atendente", expanded=True):
        nome_atendente = st.text_input("Nome do atendente")
        usuario_atendente = st.text_input(
            "Usuário do atendente",
            value=gerar_usuario(nome_atendente) if nome_atendente.strip() else "",
            key="novo_atendente_usuario",
        )
        email_atendente = st.text_input("E-mail", key="novo_atendente_email")
        senha_atendente = st.text_input("Senha", type="password", key="novo_atendente_senha")
        ativo_atendente = st.checkbox("Ativo", value=True, key="novo_atendente_ativo")

        if st.button("Cadastrar Atendente"):
            if not nome_atendente.strip() or not usuario_atendente.strip() or not senha_atendente.strip():
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
                            email_atendente.strip(),
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
        for atendente in atendentes:
            atendente_id = atendente["id"]
            with st.container(border=True):
                col1, col2, col3 = st.columns([2.2, 2.4, 3.4])

                with col1:
                    st.write(f"**{atendente['usuario']}**")
                    st.caption(atendente["nome"] or "")

                with col2:
                    st.write(atendente["email"] or "Sem e-mail")
                    st.caption("🟢 Ativo" if bool(atendente["ativo"]) else "🔴 Inativo")

                with col3:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if bool(atendente["ativo"]):
                            if st.button("Inativar", key=f"inativar_atendente_{atendente_id}", use_container_width=True):
                                conn.execute(
                                    "UPDATE atendentes SET ativo = FALSE WHERE id = %s",
                                    (atendente_id,),
                                )
                                st.rerun()
                        else:
                            if st.button("Ativar", key=f"ativar_atendente_{atendente_id}", use_container_width=True):
                                conn.execute(
                                    "UPDATE atendentes SET ativo = TRUE WHERE id = %s",
                                    (atendente_id,),
                                )
                                st.rerun()

                    with b2:
                        if st.button("Excluir", key=f"excluir_atendente_{atendente_id}", use_container_width=True):
                            possui_vinculo = conn.execute(
                                "SELECT 1 FROM solicitacoes WHERE atendente_id = %s LIMIT 1",
                                (atendente_id,),
                            ).fetchone()

                            if possui_vinculo:
                                st.warning("Este atendente já está vinculado a solicitações. Inative ao invés de excluir.")
                            else:
                                conn.execute(
                                    "DELETE FROM atendentes WHERE id = %s",
                                    (atendente_id,),
                                )
                                st.success("Atendente excluído.")
                                st.rerun()

                    with b3:
                        if st.button("Alterar", key=f"alterar_atendente_{atendente_id}", use_container_width=True):
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
                        if st.button("Salvar alteração", key=f"salvar_atendente_{atendente_id}", use_container_width=True):
                            if not novo_nome_at.strip() or not novo_usuario_at.strip():
                                st.error("Preencha nome e usuário.")
                            else:
                                usuario_existente = conn.execute(
                                    "SELECT 1 FROM atendentes WHERE usuario = %s AND id <> %s",
                                    (novo_usuario_at.strip(), atendente_id),
                                ).fetchone()

                                if usuario_existente:
                                    st.error("Já existe outro atendente com esse usuário.")
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
                                                novo_email_at.strip(),
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
                                                novo_email_at.strip(),
                                                atendente_id,
                                            ),
                                        )

                                    st.session_state.atendente_editando_id = None
                                    st.success("Atendente atualizado com sucesso.")
                                    st.rerun()

                    with a2:
                        if st.button("Cancelar alteração", key=f"cancelar_atendente_{atendente_id}", use_container_width=True):
                            st.session_state.atendente_editando_id = None
                            st.rerun()
    else:
        st.info("Nenhum atendente cadastrado ainda.")

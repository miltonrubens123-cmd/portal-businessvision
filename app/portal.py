import streamlit as st
import sqlite3
from datetime import datetime
from pathlib import Path
from PIL import Image
import pandas as pd
from zoneinfo import ZoneInfo
import secrets

# ----------------------------
# CONFIGURAÇÃO INICIAL
# ----------------------------
st.set_page_config(page_title="Portal Business Vision", layout="wide")

BASE_DIR = Path(__file__).parent
db_path = BASE_DIR / "dados.db"
logo_path = BASE_DIR / "imagens" / "logo.png"

admin_user = "admin_business"
admin_pass = "M@ionese123"
APP_TZ = ZoneInfo("America/Santarem")


# ----------------------------
# CONEXÃO COM BANCO
# ----------------------------
@st.cache_resource
def get_connection():
    return sqlite3.connect(db_path, check_same_thread=False)


conn = get_connection()


# ----------------------------
# LOGO
# ----------------------------
def carregar_logo():
    try:
        if logo_path.exists():
            return Image.open(logo_path)
    except Exception:
        return None
    return None


logo = carregar_logo()


# ----------------------------
# DATA/HORA
# ----------------------------
def agora_str():
    return datetime.now(APP_TZ).strftime("%Y-%m-%d %H:%M")


# ----------------------------
# CRIAR TABELAS
# ----------------------------
def criar_tabelas():
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE,
                senha TEXT,
                nome TEXT,
                ativo INTEGER DEFAULT 1
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS solicitacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente TEXT,
                titulo TEXT,
                descricao TEXT,
                prioridade TEXT,
                status TEXT,
                complexidade TEXT,
                resposta TEXT,
                data_criacao TEXT,
                inicio_atendimento TEXT,
                fim_atendimento TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessoes_login (
                token TEXT PRIMARY KEY,
                usuario TEXT NOT NULL,
                data_criacao TEXT
            )
            """
        )

        colunas_clientes = {
            row[1] for row in conn.execute("PRAGMA table_info(clientes)").fetchall()
        }

        if "ativo" not in colunas_clientes:
            conn.execute("ALTER TABLE clientes ADD COLUMN ativo INTEGER DEFAULT 1")

        colunas_solicitacoes = {
            row[1] for row in conn.execute("PRAGMA table_info(solicitacoes)").fetchall()
        }

        if "complexidade" not in colunas_solicitacoes:
            conn.execute("ALTER TABLE solicitacoes ADD COLUMN complexidade TEXT")

        if "resposta" not in colunas_solicitacoes:
            conn.execute("ALTER TABLE solicitacoes ADD COLUMN resposta TEXT")

        if "data_criacao" not in colunas_solicitacoes:
            conn.execute("ALTER TABLE solicitacoes ADD COLUMN data_criacao TEXT")

        if "inicio_atendimento" not in colunas_solicitacoes:
            conn.execute("ALTER TABLE solicitacoes ADD COLUMN inicio_atendimento TEXT")

        if "fim_atendimento" not in colunas_solicitacoes:
            conn.execute("ALTER TABLE solicitacoes ADD COLUMN fim_atendimento TEXT")


# ----------------------------
# SESSION STATE
# ----------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False

if "usuario" not in st.session_state:
    st.session_state.usuario = ""

if "titulo" not in st.session_state:
    st.session_state.titulo = ""

if "descricao" not in st.session_state:
    st.session_state.descricao = ""

if "mostrar_legenda" not in st.session_state:
    st.session_state.mostrar_legenda = False

if "limpar_campos_nova_solicitacao" not in st.session_state:
    st.session_state.limpar_campos_nova_solicitacao = False

if "menu_atual" not in st.session_state:
    st.session_state.menu_atual = "Nova Solicitação"

if "auth_token" not in st.session_state:
    st.session_state.auth_token = ""


# ----------------------------
# FUNÇÕES AUXILIARES
# ----------------------------
def criar_sessao_login(usuario):
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessoes_login (token, usuario, data_criacao) VALUES (?, ?, ?)",
            (token, usuario, agora_str()),
        )
    st.session_state.auth_token = token
    st.query_params["token"] = token
    st.query_params["menu"] = st.session_state.get("menu_atual", "Nova Solicitação")


def obter_usuario_por_token(token):
    if not token:
        return None
    with conn:
        cur = conn.cursor()
        resultado = cur.execute(
            "SELECT usuario FROM sessoes_login WHERE token = ?",
            (token,),
        ).fetchone()
    return resultado[0] if resultado else None


def restaurar_sessao_por_query_params():
    token = st.query_params.get("token", "")
    menu = st.query_params.get("menu", "")

    if menu:
        st.session_state.menu_atual = menu

    if st.session_state.get("logado"):
        if st.session_state.get("auth_token"):
            st.query_params["token"] = st.session_state.auth_token
        st.query_params["menu"] = st.session_state.get("menu_atual", "Nova Solicitação")
        return

    if token:
        usuario = obter_usuario_por_token(token)
        if usuario:
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.session_state.auth_token = token


def atualizar_menu_query_param(menu):
    st.session_state.menu_atual = menu
    st.query_params["menu"] = menu
    if st.session_state.get("auth_token"):
        st.query_params["token"] = st.session_state.auth_token

def logout():
    token = st.session_state.get("auth_token", "")
    if token:
        with conn:
            conn.execute("DELETE FROM sessoes_login WHERE token = ?", (token,))

    st.query_params.clear()
    st.session_state.clear()
    st.rerun()


def limpar_formulario():
    st.session_state.limpar_campos_nova_solicitacao = True
    st.rerun()


def nova_solicitacao():
    usuario = st.session_state.usuario
    logado = st.session_state.logado

    st.session_state.clear()
    st.session_state.usuario = usuario
    st.session_state.logado = logado
    st.session_state.titulo = ""
    st.session_state.descricao = ""
    st.session_state.mostrar_legenda = False
    st.session_state.limpar_campos_nova_solicitacao = False
    st.rerun()


def formatar_status(status):
    status_map = {
        "Pendente": "🔴",
        "Iniciado": "🟢",
        "Pausado": "🟡",
        "Resolvido": "🔵",
    }
    return status_map.get(status, "⚪")


def aplicar_estilo_login():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #06213d 0%, #0a3760 100%);
        }

        section[data-testid="stSidebar"] {
            display: none;
        }

        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }

        .login-box {
            background: rgba(32, 74, 114, 0.92);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 24px;
            padding: 28px 26px 22px 26px;
            box-shadow: 0 18px 40px rgba(0,0,0,0.35);
            backdrop-filter: blur(6px);
            margin-top: 40px;
        }

        .login-title {
            text-align: center;
            color: #ffffff;
            font-size: 20px;
            font-weight: 700;
            margin-top: 8px;
            margin-bottom: 2px;
        }

        .login-subtitle {
            text-align: center;
            color: #c7d7e6;
            font-size: 13px;
            margin-bottom: 18px;
        }

        .login-footer {
            text-align: center;
            color: #c7d7e6;
            font-size: 12px;
            margin-top: 10px;
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
            height: 48px !important;
        }

        .stTextInput > div > div > input::placeholder {
            color: #c7d7e6 !important;
        }

        .stButton > button {
            width: 100%;
            height: 48px;
            border-radius: 12px;
            border: none;
            background: linear-gradient(90deg, #18b7d9 0%, #2c73d2 100%);
            color: white;
            font-size: 16px;
            font-weight: 700;
        }

        .stButton > button:hover {
            border: none;
            color: white;
            filter: brightness(1.05);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def formatar_status_texto(status):
    status_map = {
        "Pendente": "🔴 Pendente",
        "Iniciado": "🟢 Iniciado",
        "Pausado": "🟡 Pausado",
        "Resolvido": "🔵 Resolvido",
    }
    return status_map.get(status, status)


def obter_clientes_ativos():
    with conn:
        cur = conn.cursor()
        return cur.execute(
            "SELECT usuario FROM clientes WHERE ativo=1 ORDER BY usuario"
        ).fetchall()


def obter_nome_cliente(usuario):
    with conn:
        cur = conn.cursor()
        resultado = cur.execute(
            "SELECT nome FROM clientes WHERE usuario=?",
            (usuario,),
        ).fetchone()
    return resultado[0] if resultado else usuario


def atualizar_solicitacao(solicitacao_id, novo_status, observacao):
    with conn:
        cur = conn.cursor()
        atual = cur.execute(
            """
            SELECT inicio_atendimento, fim_atendimento
            FROM solicitacoes
            WHERE id = ?
            """,
            (solicitacao_id,),
        ).fetchone()

    inicio_atendimento = atual[0] if atual else None
    fim_atendimento = atual[1] if atual else None
    agora = agora_str()

    if novo_status == "Iniciado" and not inicio_atendimento:
        inicio_atendimento = agora

    if novo_status == "Resolvido":
        fim_atendimento = agora

    with conn:
        conn.execute(
            """
            UPDATE solicitacoes
            SET status = ?,
                resposta = ?,
                inicio_atendimento = ?,
                fim_atendimento = ?
            WHERE id = ?
            """,
            (
                novo_status,
                observacao.strip(),
                inicio_atendimento,
                fim_atendimento,
                solicitacao_id,
            ),
        )


def obter_nome_exibicao(usuario):
    if usuario == admin_user:
        return "Administrador"

    with conn:
        cur = conn.cursor()
        resultado = cur.execute(
            "SELECT nome FROM clientes WHERE usuario = ?",
            (usuario,),
        ).fetchone()

    return resultado[0] if resultado else usuario


def carregar_logo():
    try:
        if logo_path.exists():
            return Image.open(logo_path)
    except Exception as e:
        st.warning(f"Erro ao carregar logo: {e}")
    return None


# ----------------------------
# LOGIN
# ----------------------------
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
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }

        .login-box {
            background: rgba(35, 78, 115, 0.95);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 18px 40px rgba(0,0,0,0.35);
            margin-top: 60px;
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
            height: 48px !important;
        }

        .stButton > button {
            width: 100%;
            height: 48px;
            border-radius: 12px;
            border: none;
            background: linear-gradient(90deg, #19B5D8 0%, #2B74D1 100%);
            color: white;
            font-size: 16px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


restaurar_sessao_por_query_params()

if not st.session_state.logado:
    aplicar_estilo_login()

    col1, col2, col3 = st.columns([1.2, 1, 1.2])

    with col2:
        st.markdown('<div class="login-box">', unsafe_allow_html=True)

        # ----------------------------
        # LOGO CENTRALIZADA
        # ----------------------------
        col_logo1, col_logo2, col_logo3 = st.columns([1, 1, 1])

        with col_logo2:
            if logo:
                st.image(logo, width=130)
            else:
                st.markdown(
                    "<div style='text-align:center; font-size:26px; font-weight:700; color:white;'>BUSINESS VISION</div>",
                    unsafe_allow_html=True,
                )

        # ESPAÇO
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # TÍTULO
        st.markdown(
            "<div style='text-align:center; color:white; font-size:26px; font-weight:700;'>BUSINESS VISION</div>",
            unsafe_allow_html=True,
        )

        # SUBTÍTULO
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:15px; margin-top:5px;'>PORTAL DO CLIENTE</div>",
            unsafe_allow_html=True,
        )

        # TEXTO
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:13px; margin-bottom:20px;'>Acesse sua conta</div>",
            unsafe_allow_html=True,
        )

        # INPUTS
        usuario_input = st.text_input("Usuário", placeholder="Digite seu usuário")
        senha_input = st.text_input(
            "Senha", type="password", placeholder="Digite sua senha"
        )

        # BOTÃO
        if st.button("ENTRAR →"):
            if (
                usuario_input.strip() == admin_user
                and senha_input.strip() == admin_pass
            ):
                st.session_state.logado = True
                st.session_state.usuario = admin_user
                criar_sessao_login(admin_user)
                st.rerun()
            else:
                with conn:
                    cur = conn.cursor()
                    cliente = cur.execute(
                        """
                        SELECT usuario
                        FROM clientes
                        WHERE usuario = ?
                          AND senha = ?
                          AND ativo = 1
                        """,
                        (usuario_input.strip(), senha_input.strip()),
                    ).fetchone()

                if cliente:
                    st.session_state.logado = True
                    st.session_state.usuario = usuario_input.strip()
                    criar_sessao_login(usuario_input.strip())
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")

        # RODAPÉ
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:12px; margin-top:15px;'>Business Vision • Gestão de Demandas</div>",
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

# ----------------------------
# APP LOGADO
# ----------------------------
col1, col2 = st.columns([1, 6])

with col1:
    if logo:
        st.image(logo, width=80)

with col2:
    st.markdown(
        "<h1 style='margin-bottom:0;'>Portal Business Vision</h1>"
        "<hr style='border:1px solid #333; margin-top:0;'>",
        unsafe_allow_html=True,
    )

st.caption("Gestão de demandas e acompanhamento em tempo real")


# ----------------------------
# MENU
# ----------------------------
if st.session_state.usuario == admin_user:
    opcoes_menu = [
        "Nova Solicitação",
        "Demandas Solicitadas",
        "Dashboard",
        "Cadastro de Clientes",
    ]
else:
    opcoes_menu = [
        "Nova Solicitação",
        "Demandas Solicitadas",
    ]

menu_padrao = st.session_state.get("menu_atual", opcoes_menu[0])
if menu_padrao not in opcoes_menu:
    menu_padrao = opcoes_menu[0]

menu = st.sidebar.selectbox(
    "Menu",
    opcoes_menu,
    index=opcoes_menu.index(menu_padrao),
)
atualizar_menu_query_param(menu)

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
            lista_clientes = [c[0] for c in clientes_ativos]
            cliente_nome = st.selectbox("Cliente", lista_clientes)
        else:
            st.warning("Não há clientes ativos cadastrados.")
            st.stop()
    else:
        cliente_nome = st.session_state.usuario
        st.text_input("Cliente", value=cliente_nome, disabled=True)

    titulo = st.text_input("Título", key="titulo")
    descricao = st.text_area("Descrição", key="descricao")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

    if st.session_state.usuario == admin_user:
        complexidade = st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])
    else:
        complexidade = ""

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
        titulo_limpo = titulo.strip()
        descricao_limpa = descricao.strip()
        duplicado = None

        if not titulo_limpo or not descricao_limpa:
            st.warning("Preencha título e descrição antes de enviar.")
        else:
            with conn:
                cur = conn.cursor()
                duplicado = cur.execute(
                    """
                    SELECT id
                    FROM solicitacoes
                    WHERE cliente = ?
                      AND titulo = ?
                      AND descricao = ?
                      AND status IN ('Pendente', 'Iniciado', 'Pausado')
                    LIMIT 1
                    """,
                    (cliente_nome, titulo_limpo, descricao_limpa),
                ).fetchone()

            if duplicado is not None:
                st.warning(
                    f"Esta solicitação já foi solicitada antes e ainda está em andamento. ID #{duplicado[0]}"
                )
            else:
                try:
                    with conn:
                        conn.execute(
                            """
                            INSERT INTO solicitacoes
                            (
                                cliente,
                                titulo,
                                descricao,
                                prioridade,
                                status,
                                complexidade,
                                resposta,
                                data_criacao
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                cliente_nome,
                                titulo_limpo,
                                descricao_limpa,
                                prioridade,
                                "Pendente",
                                complexidade,
                                "",
                                agora_str(),
                            ),
                        )

                    st.session_state.limpar_campos_nova_solicitacao = True
                    st.success("Solicitação enviada com sucesso.")
                    st.rerun()

                except sqlite3.OperationalError as e:
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
🔴 Pendente  
🟢 Iniciado  
🟡 Pausado  
🔵 Resolvido
            """
        )

    with conn:
        cur = conn.cursor()

        if st.session_state.usuario == admin_user:
            clientes = [
                u[0]
                for u in cur.execute(
                    "SELECT usuario FROM clientes WHERE ativo=1 ORDER BY usuario"
                ).fetchall()
            ]
        else:
            clientes = [st.session_state.usuario]

        for cli in clientes:
            nome_exibicao = obter_nome_cliente(cli)
            st.subheader(f"Cliente: {nome_exibicao} ({cli})")

            dados_cli = cur.execute(
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
                WHERE cliente = ?
                ORDER BY id DESC
                """,
                (cli,),
            ).fetchall()

            if not dados_cli:
                st.info("Nenhuma solicitação para este cliente.")
                continue

            df_cli = pd.DataFrame(
                dados_cli,
                columns=[
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
                ],
            )

            if st.session_state.usuario != admin_user:
                df_exibicao = df_cli.copy()
                df_exibicao["Status"] = df_exibicao["Status"].apply(
                    formatar_status_texto
                )
                df_exibicao["Observações"] = df_exibicao["Resposta"].fillna("")
                df_exibicao = df_exibicao[
                    ["ID", "Título", "Prioridade", "Status", "Observações", "Data"]
                ]
                st.dataframe(df_exibicao, use_container_width=True)
            else:
                for _, row in df_cli.iterrows():
                    status_atual = row["Status"]
                    solicitacao_id = int(row["ID"])

                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([0.7, 2.5, 1.2, 1.2, 1.6])

                        with c1:
                            st.write(f"**#{solicitacao_id}**")

                        with c2:
                            st.write(f"**{row['Título']}**")
                            st.caption(row["Descrição"])

                        with c3:
                            st.write(f"Prioridade: **{row['Prioridade']}**")

                        with c4:
                            st.write(
                                f"Status: **{formatar_status_texto(status_atual)}**"
                            )

                        with c5:
                            if row["Complexidade"]:
                                st.write(f"Complexidade: **{row['Complexidade']}**")

                        obs_key = f"obs_{solicitacao_id}"
                        if obs_key not in st.session_state:
                            st.session_state[obs_key] = (
                                row["Resposta"] if row["Resposta"] else ""
                            )

                        st.text_area(
                            "Observações",
                            key=obs_key,
                            height=90,
                            placeholder="Digite aqui a observação para o cliente...",
                        )

                        ac1, ac2, ac3, ac4 = st.columns([1, 1, 1, 4])

                        if status_atual == "Pendente":
                            with ac1:
                                if st.button(
                                    "INICIAR",
                                    key=f"iniciar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Iniciado",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()

                        elif status_atual == "Iniciado":
                            with ac1:
                                if st.button(
                                    "PAUSAR",
                                    key=f"pausar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Pausado",
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
                                        "Resolvido",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()

                        elif status_atual == "Pausado":
                            with ac1:
                                if st.button(
                                    "INICIAR",
                                    key=f"reiniciar_{solicitacao_id}",
                                    use_container_width=True,
                                ):
                                    atualizar_solicitacao(
                                        solicitacao_id,
                                        "Iniciado",
                                        st.session_state[obs_key],
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
                                        "Resolvido",
                                        st.session_state[obs_key],
                                    )
                                    st.rerun()

                        else:
                            st.success("Demanda finalizada.")

                        meta1, meta2, meta3 = st.columns(3)
                        with meta1:
                            st.caption(f"Criado em: {row['Data'] or ''}")
                        with meta2:
                            st.caption(f"Início: {row['Início'] or ''}")
                        with meta3:
                            st.caption(f"Fim: {row['Fim'] or ''}")

# ----------------------------
# DASHBOARD
# ----------------------------
elif menu == "Dashboard" and st.session_state.usuario == admin_user:
    st.header("Dashboard")

    if logo:
        st.image(logo, width=100)

    st.markdown("<hr>", unsafe_allow_html=True)

    with conn:
        cur = conn.cursor()
        dados = cur.execute(
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
        pd.DataFrame(dados, columns=colunas) if dados else pd.DataFrame(columns=colunas)
    )

    total = len(df)
    finalizadas = len(df[df["Status"] == "Resolvido"])
    pendentes_iniciadas = len(
        df[df["Status"].isin(["Pendente", "Iniciado", "Pausado"])]
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
# CADASTRO DE CLIENTES
# ----------------------------
elif menu == "Cadastro de Clientes" and st.session_state.usuario == admin_user:
    st.header("Cadastro de Clientes")

    novo_usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    nome = st.text_input("Nome")
    ativo = st.checkbox("Ativo", value=True)

    if st.button("Cadastrar"):
        if novo_usuario.strip() and senha.strip() and nome.strip():
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO clientes (usuario, senha, nome, ativo)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            novo_usuario.strip(),
                            senha.strip(),
                            nome.strip(),
                            int(ativo),
                        ),
                    )
                st.success(f"Cliente {novo_usuario.strip()} cadastrado com sucesso.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Usuário já existe. Escolha outro.")
        else:
            st.error("Preencha todos os campos.")

    st.markdown("---")
    st.subheader("Clientes cadastrados")

    with conn:
        cur = conn.cursor()
        clientes = cur.execute(
            """
            SELECT id, usuario, nome, ativo
            FROM clientes
            ORDER BY nome
            """
        ).fetchall()

    if clientes:
        for cli in clientes:
            id_cli, usuario, nome_cli, ativo_cli = cli

            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 3, 1.5, 2.5])

                with col1:
                    st.write(f"**{usuario}**")

                with col2:
                    st.write(nome_cli)

                with col3:
                    status_cliente = "🟢 Ativo" if ativo_cli == 1 else "🔴 Inativo"
                    st.write(status_cliente)

                with col4:
                    b1, b2 = st.columns(2)

                    with b1:
                        if ativo_cli == 1:
                            if st.button(
                                "Inativar",
                                key=f"inativar_{id_cli}",
                                use_container_width=True,
                            ):
                                with conn:
                                    conn.execute(
                                        "UPDATE clientes SET ativo = 0 WHERE id = ?",
                                        (id_cli,),
                                    )
                                st.rerun()
                        else:
                            if st.button(
                                "Ativar",
                                key=f"ativar_{id_cli}",
                                use_container_width=True,
                            ):
                                with conn:
                                    conn.execute(
                                        "UPDATE clientes SET ativo = 1 WHERE id = ?",
                                        (id_cli,),
                                    )
                                st.rerun()

                    with b2:
                        if st.button(
                            "Excluir", key=f"excluir_{id_cli}", use_container_width=True
                        ):
                            with conn:
                                cur = conn.cursor()
                                tem_solicitacao = cur.execute(
                                    "SELECT 1 FROM solicitacoes WHERE cliente = ? LIMIT 1",
                                    (usuario,),
                                ).fetchone()

                            if tem_solicitacao:
                                st.warning(
                                    f"O cliente {usuario} possui solicitações. Inative ao invés de excluir."
                                )
                            else:
                                with conn:
                                    conn.execute(
                                        "DELETE FROM clientes WHERE id = ?",
                                        (id_cli,),
                                    )
                                st.success(f"Cliente {usuario} excluído.")
                                st.rerun()
    else:
        st.info("Nenhum cliente cadastrado ainda.")

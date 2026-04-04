import streamlit as st
import sqlite3
from datetime import datetime
from pathlib import Path
from PIL import Image
import pandas as pd

# ----------------------------
# CONFIGURAÇÃO INICIAL
# ----------------------------
st.set_page_config(page_title="Portal Business Vision", layout="wide")

BASE_DIR = Path(__file__).parent
db_path = BASE_DIR / "dados.db"
logo_path = BASE_DIR / "imagens" / "logo.png"

admin_user = "admin_business"
admin_pass = "M@ionese123"


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


criar_tabelas()


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

if "enviado" not in st.session_state:
    st.session_state.enviado = False


# ----------------------------
# FUNÇÕES AUXILIARES
# ----------------------------
def logout():
    st.session_state.clear()
    st.rerun()


def limpar_formulario():
    st.session_state.titulo = ""
    st.session_state.descricao = ""
    st.session_state.enviado = False
    st.rerun()


def nova_solicitacao():
    usuario = st.session_state.usuario
    logado = st.session_state.logado

    st.session_state.clear()
    st.session_state.usuario = usuario
    st.session_state.logado = logado
    st.session_state.titulo = ""
    st.session_state.descricao = ""
    st.session_state.enviado = False
    st.rerun()


def formatar_status(status):
    status_map = {
        "Pendente": "🔴 Pendente",
        "Iniciado": "🟢 Iniciado",
        "Atrasado": "⚫ Atrasado",
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


# ----------------------------
# LOGIN
# ----------------------------
if not st.session_state.logado:
    st.title("Login - Portal Business Vision")

    usuario_input = st.text_input("Usuário")
    senha_input = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if usuario_input.strip() == admin_user and senha_input.strip() == admin_pass:
            st.session_state.logado = True
            st.session_state.usuario = admin_user
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
                st.rerun()
            else:
                st.error("Usuário ou senha inválidos.")

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
    menu = st.sidebar.selectbox(
        "Menu",
        [
            "Nova Solicitação",
            "Demandas Solicitadas",
            "Dashboard",
            "Cadastro de Clientes",
        ],
    )
else:
    menu = st.sidebar.selectbox(
        "Menu",
        [
            "Nova Solicitação",
            "Demandas Solicitadas",
        ],
    )

st.sidebar.markdown("---")
st.sidebar.markdown(f"👤 Usuário: **{st.session_state.usuario}**")

if st.sidebar.button("Trocar usuário"):
    logout()


# ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
if menu == "Nova Solicitação":
    st.header("Nova Solicitação")

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
        if not titulo.strip() or not descricao.strip():
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
                      AND status IN ('Pendente', 'Iniciado', 'Atrasado')
                    """,
                    (cliente_nome, titulo.strip(), descricao.strip()),
                ).fetchone()

            if duplicado:
                st.warning(
                    "Esta solicitação já foi solicitada antes e ainda está em andamento."
                )
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")

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
                            titulo.strip(),
                            descricao.strip(),
                            prioridade,
                            "Pendente",
                            complexidade,
                            "",
                            now,
                        ),
                    )

                st.success("Solicitação enviada com sucesso.")
                st.session_state.enviado = True


# ----------------------------
# DEMANDAS SOLICITADAS
# ----------------------------
elif menu == "Demandas Solicitadas":
    st.header("Demandas Solicitadas")

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

            if dados_cli:
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

                df_exibicao = df_cli.copy()
                df_exibicao["Status"] = df_exibicao["Status"].apply(formatar_status)

                if st.session_state.usuario != admin_user:
                    df_exibicao = df_exibicao[
                        ["ID", "Título", "Prioridade", "Status", "Data"]
                    ]
                else:
                    df_exibicao = df_exibicao[
                        ["ID", "Título", "Prioridade", "Status", "Complexidade", "Data"]
                    ]

                st.dataframe(df_exibicao, use_container_width=True)
            else:
                st.info("Nenhuma solicitação para este cliente.")


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
        df[df["Status"].isin(["Pendente", "Iniciado", "Atrasado"])]
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
        df_clientes = pd.DataFrame(
            clientes,
            columns=["ID", "Usuário", "Nome", "Ativo"],
        )
        df_clientes["Ativo"] = df_clientes["Ativo"].apply(
            lambda x: "Sim" if x == 1 else "Não"
        )
        st.dataframe(df_clientes, use_container_width=True)
    else:
        st.info("Nenhum cliente cadastrado ainda.")

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

# Caminho da logo
logo_path = "imagens/logo.png"
logo = Image.open(logo_path)

# Conexão com banco
db_path = Path(__file__).parent / "dados.db"
conn = sqlite3.connect(db_path, check_same_thread=False)

# ----------------------------
# CRIAR TABELAS
# ----------------------------
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

# ----------------------------
# LOGIN
# ----------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = ""

admin_user = "admin_business"
admin_pass = "M@ionese123"

if not st.session_state.logado:
    st.title("Login - Portal Business Vision")
    usuario_input = st.text_input("Usuário")
    senha_input = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        # Admin
        if usuario_input == admin_user and senha_input == admin_pass:
            st.session_state.logado = True
            st.session_state.usuario = admin_user
        else:
            # Cliente
            cur = conn.cursor()
            cliente = cur.execute(
                "SELECT usuario FROM clientes WHERE usuario=? AND senha=? AND ativo=1",
                (usuario_input, senha_input),
            ).fetchone()
            if cliente:
                st.session_state.logado = True
                st.session_state.usuario = usuario_input
            else:
                st.error("Usuário ou senha inválidos.")

# ----------------------------
# APP LOGADO
# ----------------------------
if st.session_state.logado:
    # Cabeçalho
    col1, col2 = st.columns([1, 6])
    with col1:
        st.image(logo, width=80)
    with col2:
        st.markdown(
            "<h1 style='margin-bottom:0px;'>Portal Business Vision</h1>"
            "<hr style='border:1px solid #333; margin-top:0px;'>",
            unsafe_allow_html=True,
        )
    st.caption("Gestão de demandas e acompanhamento em tempo real")

    # Menu
    if st.session_state.usuario == admin_user:
        menu = st.sidebar.selectbox(
            "Menu",
            [
                "Nova Solicitação",
                "Dashboard",
                "Demandas Solicitadas",
                "Cadastro de Clientes",
            ],
        )
    else:
        menu = st.sidebar.selectbox(
            "Menu", ["Nova Solicitação", "Demandas Solicitadas"]
        )

    # ----------------------------
    # NOVA SOLICITAÇÃO
    # ----------------------------
    if menu == "Nova Solicitação":
        st.header("Nova Solicitação")
        cliente_nome = st.session_state.usuario
        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição")
        prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

        # Complexidade apenas para admin
        if st.session_state.usuario == admin_user:
            complexidade = st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])
        else:
            complexidade = ""

        if st.button("Enviar"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            with conn:
                conn.execute(
                    """
                    INSERT INTO solicitacoes
                    (cliente, titulo, descricao, prioridade, status, complexidade, resposta, data_criacao)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        cliente_nome,
                        titulo,
                        descricao,
                        prioridade,
                        "Pendente",
                        complexidade,
                        "",
                        now,
                    ),
                )
            st.success("Solicitação enviada com sucesso!")

    # ----------------------------
    # DASHBOARD
    # ----------------------------
    elif menu == "Dashboard" and st.session_state.usuario == admin_user:
        st.header("Dashboard")
        st.image(logo, width=100)
        st.markdown("<hr>", unsafe_allow_html=True)

        cur = conn.cursor()
        dados = cur.execute("SELECT * FROM solicitacoes").fetchall()
        df = (
            pd.DataFrame(
                dados,
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
            if dados
            else pd.DataFrame(
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
                ]
            )
        )

        # Cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Solicitações", len(df))
        col2.metric("Finalizadas", len(df[df["Status"] == "Resolvido"]))
        col3.metric(
            "Pendentes/Iniciadas",
            len(df[df["Status"].isin(["Pendente", "Iniciado", "Atrasado"])]),
        )

        # Gráfico de prioridade
        st.subheader("Solicitações por Prioridade")
        if not df.empty:
            resumo = df.groupby("Prioridade")["ID"].count().reset_index()
            resumo.columns = ["Prioridade", "Quantidade"]
            st.bar_chart(resumo.set_index("Prioridade"))
        else:
            st.write("Nenhuma solicitação registrada ainda.")

    # ----------------------------
    # DEMANDAS SOLICITADAS
    # ----------------------------
    elif menu == "Demandas Solicitadas":
        st.header("Demandas Solicitadas")
        cur = conn.cursor()
        clientes = (
            [st.session_state.usuario]
            if st.session_state.usuario != admin_user
            else [
                u[0]
                for u in cur.execute(
                    "SELECT usuario FROM clientes WHERE ativo=1"
                ).fetchall()
            ]
        )

        for cli in clientes:
            st.subheader(f"Cliente: {cli}")
            dados_cli = cur.execute(
                "SELECT * FROM solicitacoes WHERE cliente=?", (cli,)
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
                status_color = {
                    "Pendente": "🔴",
                    "Iniciado": "🟢",
                    "Atrasado": "⚫",
                    "Resolvido": "🔵",
                }
                df_cli["Status Color"] = df_cli["Status"].map(status_color)
                st.table(df_cli[["ID", "Título", "Prioridade", "Status Color", "Data"]])
            else:
                st.info("Nenhuma solicitação para este cliente.")

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
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO clientes (usuario, senha, nome, ativo) VALUES (?, ?, ?, ?)",
                        (novo_usuario, senha, nome, int(ativo)),
                    )
                st.success(f"Cliente {novo_usuario} cadastrado com sucesso!")
            except sqlite3.IntegrityError:
                st.error("Usuário já existe, escolha outro.")

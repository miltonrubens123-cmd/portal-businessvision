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

# Caminho relativo ao repositório
logo_path = "imagens/logo.png"
logo = Image.open(logo_path)

# Conexão com banco
conn = sqlite3.connect(Path(__file__).parent / "dados.db", check_same_thread=False)
c = conn.cursor()

# ----------------------------
# CRIAR TABELAS SE NÃO EXISTIREM
# ----------------------------
c.execute(
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

c.execute(
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
conn.commit()

# ----------------------------
# LOGIN SIMPLES
# ----------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = ""

# Exemplo de admin padrão
admin_user = "admin_business"
admin_pass = "M@ionese123"

if not st.session_state.logado:
    st.title("Login - Portal Business Vision")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if usuario == admin_user and senha == admin_pass:
            st.session_state.logado = True
            st.session_state.usuario = usuario
        else:
            cliente = c.execute(
                "SELECT * FROM clientes WHERE usuario=? AND senha=? AND ativo=1",
                (usuario, senha),
            ).fetchone()
            if cliente:
                st.session_state.logado = True
                st.session_state.usuario = usuario
            else:
                st.error("Usuário ou senha inválidos.")

if st.session_state.logado:
    # ----------------------------
    # CABEÇALHO
    # ----------------------------
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

    # ----------------------------
    # MENU LATERAL
    # ----------------------------
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
        cliente = (
            st.session_state.usuario
            if st.session_state.usuario != admin_user
            else st.selectbox(
                "Solicitante (Cliente)",
                [
                    c[1]
                    for c in c.execute(
                        "SELECT usuario FROM clientes WHERE ativo=1"
                    ).fetchall()
                ],
            )
        )
        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição")
        prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])
        if st.session_state.usuario == admin_user:
            complexidade = st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])
        else:
            complexidade = ""

        if st.button("Enviar"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute(
                """
                INSERT INTO solicitacoes (cliente, titulo, descricao, prioridade, status, complexidade, resposta, data_criacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    cliente,
                    titulo,
                    descricao,
                    prioridade,
                    "Pendente",
                    complexidade,
                    "",
                    now,
                ),
            )
            conn.commit()
            st.success("Solicitação enviada com sucesso!")

    # ----------------------------
    # DASHBOARD (Admin)
    # ----------------------------
    elif menu == "Dashboard" and st.session_state.usuario == admin_user:
        st.header("Dashboard")

        dados = c.execute("SELECT * FROM solicitacoes").fetchall()
        if dados:
            df = pd.DataFrame(
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
            # Cards simples
            st.subheader("Resumo Geral")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total de Solicitações", len(df))
            col2.metric("Finalizadas", len(df[df["Status"] == "Resolvido"]))
            col3.metric(
                "Pendentes/Iniciadas",
                len(df[df["Status"].isin(["Pendente", "Iniciado", "Atrasado"])]),
            )

            st.subheader("Solicitações por Prioridade")
            resumo = df.groupby("Prioridade")["ID"].count().reset_index()
            resumo.columns = ["Prioridade", "Quantidade"]
            st.bar_chart(resumo.set_index("Prioridade"))

            st.subheader("Tempo médio de atendimento (minutos)")
            df["Data_dt"] = pd.to_datetime(df["Data"])
            df["Início_dt"] = pd.to_datetime(df["Início"])
            df["Fim_dt"] = pd.to_datetime(df["Fim"])
            df["Duracao"] = (df["Fim_dt"] - df["Início_dt"]).dt.total_seconds() / 60
            st.write(df["Duracao"].mean())

    # ----------------------------
    # DEMANDAS SOLICITADAS
    # ----------------------------
    elif menu == "Demandas Solicitadas":
        st.header("Demandas Solicitadas")
        if st.session_state.usuario == admin_user:
            clientes = [
                c[1]
                for c in c.execute(
                    "SELECT usuario FROM clientes WHERE ativo=1"
                ).fetchall()
            ]
        else:
            clientes = [st.session_state.usuario]

        for cli in clientes:
            st.subheader(f"Cliente: {cli}")
            dados = c.execute(
                "SELECT * FROM solicitacoes WHERE cliente=?", (cli,)
            ).fetchall()
            if dados:
                df = pd.DataFrame(
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
                # Mapear cores
                status_color = {
                    "Pendente": "🔴",
                    "Iniciado": "🟢",
                    "Atrasado": "⚫",
                    "Resolvido": "🔵",
                }
                df["Status Color"] = df["Status"].map(status_color)
                st.table(df[["ID", "Título", "Prioridade", "Status Color", "Data"]])
            else:
                st.info("Nenhuma solicitação para este cliente.")

    # ----------------------------
    # CADASTRO DE CLIENTES (Admin)
    # ----------------------------
    elif menu == "Cadastro de Clientes" and st.session_state.usuario == admin_user:
        st.header("Cadastro de Clientes")
        novo_usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        nome = st.text_input("Nome")
        ativo = st.checkbox("Ativo", value=True)

        if st.button("Cadastrar"):
            c.execute(
                "INSERT INTO clientes (usuario, senha, nome, ativo) VALUES (?, ?, ?, ?)",
                (novo_usuario, senha, nome, int(ativo)),
            )

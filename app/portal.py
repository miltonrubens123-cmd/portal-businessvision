import streamlit as st
import sqlite3
from datetime import datetime
from PIL import Image

# --------------------------
# Configurações da página
# --------------------------
st.set_page_config(
    page_title="Portal Business Vision", layout="wide", initial_sidebar_state="expanded"
)

# --------------------------
# Banco de dados
# --------------------------
conn = sqlite3.connect("dados.db", check_same_thread=False)
c = conn.cursor()

# Tabela de solicitações
c.execute(
    """
CREATE TABLE IF NOT EXISTS solicitacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT,
    titulo TEXT,
    descricao TEXT,
    prioridade TEXT,
    status TEXT,
    resposta TEXT,
    data_criacao TEXT
)
"""
)
conn.commit()

# Tabela de empresas (login)
c.execute(
    """
CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE,
    senha TEXT
)
"""
)
conn.commit()

# --------------------------
# Cabeçalho com logo
# --------------------------
logo = Image.open("imagens/logo.png")
col1, col2 = st.columns([1, 6])
with col1:
    st.image(logo, width=80)
with col2:
    st.markdown(
        "<h1 style='margin-bottom:0'>Portal Business Vision</h1>",
        unsafe_allow_html=True,
    )
st.markdown("<hr style='border:1px solid #ccc'>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:gray; font-size:14px;'>Gestão de demandas e acompanhamento em tempo real</p>",
    unsafe_allow_html=True,
)

# --------------------------
# Menu lateral
# --------------------------
st.sidebar.image("app/logo_empresa.png", width=60)
st.sidebar.markdown("<h3>Portal Business Vision</h3>", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border:1px solid #ccc'>", unsafe_allow_html=True)

menu = st.sidebar.radio(
    label="Menu", options=["Login Cliente", "Nova Solicitação", "Painel Admin"]
)

# --------------------------
# Login Cliente
# --------------------------
if menu == "Login Cliente":
    st.header("Acesso Cliente")
    nome_cliente = st.text_input("Empresa")
    senha_cliente = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        valida = c.execute(
            "SELECT * FROM empresas WHERE nome=? AND senha=?",
            (nome_cliente, senha_cliente),
        ).fetchone()
        if valida:
            st.success(f"Bem-vindo(a), {nome_cliente}!")

            # Mostrar solicitações apenas deste cliente
            dados = c.execute(
                "SELECT * FROM solicitacoes WHERE cliente=?", (nome_cliente,)
            ).fetchall()
            if not dados:
                st.info("Nenhuma solicitação encontrada.")
            else:
                for d in dados:
                    st.markdown(f"### #{d[0]} - {d[2]}")
                    st.write(f"Prioridade: {d[4]}")
                    st.write(f"Status: {d[5]}")
                    st.write(f"Última atualização / Observações: {d[6]}")

        else:
            st.error("Empresa ou senha inválida.")

# --------------------------
# Nova Solicitação
# --------------------------
elif menu == "Nova Solicitação":
    st.header("Nova Solicitação")

    empresas = [e[0] for e in c.execute("SELECT nome FROM empresas").fetchall()]
    if not empresas:
        st.warning("Nenhuma empresa cadastrada. Admin precisa cadastrar primeiro.")
    else:
        cliente = st.selectbox("Selecione sua empresa", empresas)
        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição")
        prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

        if st.button("Enviar"):
            c.execute(
                """
            INSERT INTO solicitacoes (cliente, titulo, descricao, prioridade, status, resposta, data_criacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    cliente,
                    titulo,
                    descricao,
                    prioridade,
                    "Backlog",
                    "",
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            conn.commit()
            st.success("Solicitação enviada com sucesso!")

# --------------------------
# Painel Admin
# --------------------------
elif menu == "Painel Admin":
    st.header("Painel Admin")

    nome_admin = st.text_input("Admin: empresa (para criar login)")
    senha_admin = st.text_input("Senha", type="password")
    if st.button("Cadastrar Empresa"):
        try:
            c.execute(
                "INSERT INTO empresas (nome, senha) VALUES (?, ?)",
                (nome_admin, senha_admin),
            )
            conn.commit()
            st.success(f"Empresa {nome_admin} cadastrada!")
        except sqlite3.IntegrityError:
            st.warning("Empresa já cadastrada.")

    st.markdown("---")
    st.subheader("Solicitações gerais")
    dados = c.execute("SELECT * FROM solicitacoes").fetchall()
    if dados:
        total_alta = len([d for d in dados if d[4] == "Alta"])
        total_media = len([d for d in dados if d[4] == "Média"])
        total_baixa = len([d for d in dados if d[4] == "Baixa"])
        col1, col2, col3 = st.columns(3)
        col1.metric("Alta", total_alta)
        col2.metric("Média", total_media)
        col3.metric("Baixa", total_baixa)

        st.markdown("---")
        for d in dados:
            st.markdown(f"### #{d[0]} - {d[2]}")
            st.write(f"Cliente: {d[1]}")
            st.write(f"Prioridade: {d[4]}")
            st.write(f"Status: {d[5]}")
            novo_status = st.selectbox(
                f"Alterar status {d[0]}",
                ["Backlog", "Pendente", "Em andamento", "Em validação", "Finalizado"],
                key=f"status{d[0]}",
            )
            resposta = st.text_area(
                "Observações / Atualização", value=d[6], key=f"resp{d[0]}"
            )
            if st.button(f"Salvar {d[0]}"):
                c.execute(
                    "UPDATE solicitacoes SET status=?, resposta=? WHERE id=?",
                    (novo_status, resposta, d[0]),
                )
                conn.commit()
                st.success("Atualizado!")
    else:
        st.info("Nenhuma solicitação registrada.")

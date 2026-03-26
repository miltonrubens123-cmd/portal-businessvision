import streamlit as st
import sqlite3
from datetime import datetime

# Conexão com banco
conn = sqlite3.connect("dados.db", check_same_thread=False)
c = conn.cursor()

# Criar tabela
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

st.title("🚀 Portal Business Vision")
st.caption("Gestão de solicitações e acompanhamento em tempo real")

st.set_page_config(page_title="Portal Business Vision", layout="wide")


menu = st.sidebar.selectbox("Menu", ["Nova Solicitação", "Painel", "Cliente"])

# 🔹 FORMULÁRIO
if menu == "Nova Solicitação":
    st.header("📥 Nova Solicitação")

    cliente = st.text_input("Cliente")
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

# 🔹 PAINEL INTERNO
elif menu == "Painel":
    st.header("📊 Gestão de Demandas")

    dados = c.execute("SELECT * FROM solicitacoes").fetchall()

    for d in dados:
        st.subheader(f"#{d[0]} - {d[2]}")
        st.write(f"Cliente: {d[1]}")
        st.write(f"Prioridade: {d[4]}")
        st.write(f"Status: {d[5]}")

        novo_status = st.selectbox(
            f"Alterar status {d[0]}",
            ["Pendente", "Em andamento", "Em validação", "Finalizado"],
            key=f"status{d[0]}",
        )
        resposta = st.text_area("Atualização", value=d[6], key=f"resp{d[0]}")

        if st.button(f"Salvar {d[0]}"):
            c.execute(
                """
            UPDATE solicitacoes SET status=?, resposta=? WHERE id=?
            """,
                (novo_status, resposta, d[0]),
            )
            conn.commit()
            st.success("Atualizado!")

# 🔹 VISÃO CLIENTE
elif menu == "Cliente":
    st.header("👤 Consulta do Cliente")

    cliente_busca = st.text_input("Digite seu nome ou empresa")

if cliente_busca:
    dados = c.execute(
        "SELECT * FROM solicitacoes WHERE cliente=?", (cliente_busca,)
    ).fetchall()

    if not dados:
        st.warning("Nenhuma solicitação encontrada.")

    for d in dados:
        st.subheader(f"#{d[0]} - {d[2]}")
        st.write(f"Status: {d[5]}")
        st.write(f"Atualização: {d[6]}")

    if cliente_busca:
        dados = c.execute(
            "SELECT * FROM solicitacoes WHERE cliente=?", (cliente_busca,)
        ).fetchall()

        for d in dados:
            st.subheader(f"#{d[0]} - {d[2]}")
            st.write(f"Status: {d[5]}")
            st.write(f"Atualização: {d[6]}")

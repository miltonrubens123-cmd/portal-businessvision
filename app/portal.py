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

# Caminho correto relativo ao repositório
logo_path = "imagens/logo.png"
logo = Image.open(logo_path)


# Exibir no sidebar
st.sidebar.image(logo, width=120)

# Conexão com banco
conn = sqlite3.connect(Path(__file__).parent / "dados.db", check_same_thread=False)
c = conn.cursor()

# Criar tabela se não existir
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

# ----------------------------
# CABEÇALHO
# ----------------------------
st.image(logo, width=100)
st.title("Portal Business Vision")
st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Gestão de demandas e acompanhamento em tempo real")

# ----------------------------
# MENU LATERAL
# ----------------------------
menu = st.sidebar.selectbox("Menu", ["Nova Solicitação", "Painel", "Cliente"])

# ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
if menu == "Nova Solicitação":
    st.header("Nova Solicitação")
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

# ----------------------------
# PAINEL ADMIN
# ----------------------------
elif menu == "Painel":
    st.header("Painel de Demandas")

    # Buscar dados do banco
    dados = c.execute("SELECT * FROM solicitacoes").fetchall()
    if not dados:
        st.info("Nenhuma solicitação registrada.")
    else:
        df = pd.DataFrame(
            dados,
            columns=[
                "ID",
                "Cliente",
                "Título",
                "Descrição",
                "Prioridade",
                "Status",
                "Resposta",
                "Data",
            ],
        )

        # Dashboard resumido
        st.subheader("Resumo por Prioridade")
        resumo = df.groupby("Prioridade")["ID"].count().reset_index()
        resumo.columns = ["Prioridade", "Quantidade"]
        st.bar_chart(resumo.set_index("Prioridade"))

        st.markdown("---")
        st.subheader("Solicitações Detalhadas")
        for d in dados:
            st.markdown(f"**#{d[0]} - {d[2]}**")
            st.write(f"Cliente: {d[1]}")
            st.write(f"Prioridade: {d[4]}")
            st.write(f"Status: {d[5]}")
            resposta = st.text_area(
                "Atualização/Observação", value=d[6], key=f"resp{d[0]}"
            )
            novo_status = st.selectbox(
                "Alterar status",
                ["Pendente", "Em andamento", "Em validação", "Finalizado"],
                index=["Pendente", "Em andamento", "Em validação", "Finalizado"].index(
                    d[5]
                ),
                key=f"status{d[0]}",
            )
            if st.button(f"Salvar {d[0]}"):
                c.execute(
                    "UPDATE solicitacoes SET status=?, resposta=? WHERE id=?",
                    (novo_status, resposta, d[0]),
                )
                conn.commit()
                st.success("Atualizado!")

# ----------------------------
# VISÃO CLIENTE
# ----------------------------
elif menu == "Cliente":
    st.header("Consulta de Solicitações")
    cliente_busca = st.text_input("Digite seu nome ou empresa")

    if cliente_busca:
        dados = c.execute(
            "SELECT * FROM solicitacoes WHERE cliente=?", (cliente_busca,)
        ).fetchall()
        if not dados:
            st.warning("Nenhuma solicitação encontrada.")
        else:
            for d in dados:
                st.markdown(f"**#{d[0]} - {d[2]}**")
                st.write(f"Status: {d[5]}")
                st.write(f"Atualização: {d[6]}")

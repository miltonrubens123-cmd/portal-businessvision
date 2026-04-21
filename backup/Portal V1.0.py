# PORTAL BUSINESS VISION - POSTGRES (NEON) - VERSÃO CORRIGIDA

import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import psycopg
from zoneinfo import ZoneInfo
from psycopg.rows import dict_row

# ----------------------------
# CONEXÃO (CORRIGIDA)
# ----------------------------
def get_connection():
    if "database" in st.secrets and "url" in st.secrets["database"]:
        database_url = st.secrets["database"]["url"]
        st.info("Origem da conexão: st.secrets[database][url]")
    else:
        database_url = os.getenv("DATABASE_URL")
        st.info("Origem da conexão: variável de ambiente DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL não configurado.")

    try:
        conn = psycopg.connect(
            database_url,
            row_factory=dict_row,
            autocommit=True,
        )
        st.success("Conexão com o banco realizada com sucesso.")
        return conn

    except Exception as e:
        # CORREÇÃO: agora mostra o erro real
        raise RuntimeError(
            f"Falha ao conectar no Postgres/Neon. Tipo: {type(e).__name__}. Detalhe: {e}"
        )

conn = get_connection()

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(page_title="Portal Business Vision", layout="wide")

admin_user = "admin_business"
admin_pass = "M@ionese123"
APP_TZ = ZoneInfo("America/Santarem")

# ----------------------------
# UTIL
# ----------------------------
def agora():
    return datetime.now(APP_TZ)

# ----------------------------
# LOGIN
# ----------------------------
if "logado" not in st.session_state:
    st.session_state.logado = False

if not st.session_state.logado:
    st.title("Portal Business Vision")

    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if usuario == admin_user and senha == admin_pass:
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()

        row = conn.execute(
            "SELECT usuario FROM clientes WHERE usuario = %s AND senha = %s AND ativo = TRUE",
            (usuario, senha),
        ).fetchone()

        if row:
            st.session_state.logado = True
            st.session_state.usuario = usuario
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")

    st.stop()

# ----------------------------
# MENU
# ----------------------------
menu = st.sidebar.selectbox("Menu", ["Nova Solicitação", "Demandas"])

# ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
if menu == "Nova Solicitação":
    st.header("Nova Solicitação")

    titulo = st.text_input("Título")
    descricao = st.text_area("Descrição")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

    if st.button("Enviar"):
        if not titulo or not descricao:
            st.warning("Preencha os campos")
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO solicitacoes (
                        cliente,
                        titulo,
                        descricao,
                        prioridade,
                        status,
                        data_criacao
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        st.session_state.usuario,
                        titulo,
                        descricao,
                        prioridade,
                        "Pendente",
                        agora(),
                    ),
                )
                solicitacao_id = cur.fetchone()["id"]

            st.success(f"Solicitação enviada #{solicitacao_id}")

# ----------------------------
# LISTAGEM
# ----------------------------
elif menu == "Demandas":
    st.header("Demandas")

    dados = conn.execute(
        """
        SELECT id, titulo, prioridade, status, data_criacao
        FROM solicitacoes
        WHERE cliente = %s
        ORDER BY id DESC
        """,
        (st.session_state.usuario,),
    ).fetchall()

    if dados:
        df = pd.DataFrame(dados)
        st.dataframe(df)
    else:
        st.info("Nenhuma solicitação encontrada")

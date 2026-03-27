import streamlit as st
import sqlite3
from datetime import datetime
from pathlib import Path
from PIL import Image
import pandas as pd
import hashlib

# ----------------------------
# CONFIGURAÇÃO INICIAL
# ----------------------------
st.set_page_config(page_title="Portal Business Vision", layout="wide")

# Caminho relativo da logo
logo_path = "imagens/logo.png"
logo = Image.open(logo_path)

# Cabeçalho com logo e título alinhados
col1, col2 = st.columns([1, 6])
with col1:
    st.image(logo, width=80)
with col2:
    st.markdown(
        "<h1 style='margin-bottom:0px;'>Portal Business Vision</h1>"
        "<hr style='border:1px solid #333; margin-top:0px;'>",
        unsafe_allow_html=True,
    )
st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Gestão de demandas e acompanhamento em tempo real")

# ----------------------------
# BANCO DE DADOS
# ----------------------------
conn = sqlite3.connect(Path(__file__).parent / "dados.db", check_same_thread=False)
c = conn.cursor()

# Tabela de solicitações
c.execute(
    """
CREATE TABLE IF NOT EXISTS solicitacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT,
    solicitante TEXT,
    titulo TEXT,
    descricao TEXT,
    prioridade TEXT,
    status TEXT,
    resposta TEXT,
    complexidade TEXT,
    data_criacao TEXT,
    inicio_atendimento TEXT,
    fim_atendimento TEXT
)
"""
)
conn.commit()

# Tabela de clientes
c.execute(
    """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE,
    usuario TEXT UNIQUE,
    senha_hash TEXT
)
"""
)
conn.commit()


# ----------------------------
# AUTENTICAÇÃO
# ----------------------------
def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


if "logado" not in st.session_state:
    st.session_state.logado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = ""

# Login admin ou clientes
if not st.session_state.logado:
    st.subheader("Login")
    usuario_input = st.text_input("Usuário")
    senha_input = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        # Admin fixo
        if usuario_input == "admin_business" and senha_input == "M@ionese123":
            st.session_state.logado = True
            st.session_state.usuario = "admin_business"
        else:
            # Verifica clientes
            senha_h = hash_senha(senha_input)
            res = c.execute(
                "SELECT * FROM clientes WHERE usuario=? AND senha_hash=?",
                (usuario_input, senha_h),
            ).fetchone()
            if res:
                st.session_state.logado = True
                st.session_state.usuario = usuario_input
            else:
                st.error("Usuário ou senha incorretos.")
    st.stop()

# ----------------------------
# MENU LATERAL
# ----------------------------
menu_items = ["Nova Solicitação", "Painel", "Cliente"]
if st.session_state.usuario == "admin_business":
    menu_items.append("Cadastro Cliente")

menu = st.sidebar.selectbox("Menu", menu_items)

# ----------------------------
# CADASTRO CLIENTE (ADMIN)
# ----------------------------
if menu == "Cadastro Cliente" and st.session_state.usuario == "admin_business":
    st.header("Cadastro de Clientes")
    nome = st.text_input("Nome da Empresa")
    usuario = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")
    if st.button("Cadastrar"):
        try:
            senha_h = hash_senha(senha)
            c.execute(
                "INSERT INTO clientes (nome, usuario, senha_hash) VALUES (?, ?, ?)",
                (nome, usuario, senha_h),
            )
            conn.commit()
            st.success("Cliente cadastrado com sucesso!")
        except sqlite3.IntegrityError:
            st.error("Usuário ou empresa já cadastrada.")

# ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
elif menu == "Nova Solicitação":
    st.header("Nova Solicitação")
    # Cliente logado define automaticamente o solicitante
    cliente_nome = st.session_state.usuario
    solicitante = st.text_input("Solicitante")
    titulo = st.text_input("Título")
    descricao = st.text_area("Descrição")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])
    complexidade = st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])

    if st.button("Enviar"):
        c.execute(
            """
            INSERT INTO solicitacoes 
            (cliente, solicitante, titulo, descricao, prioridade, status, resposta, complexidade, data_criacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                cliente_nome,
                solicitante,
                titulo,
                descricao,
                prioridade,
                "Backlog",
                "",
                complexidade,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        conn.commit()
        st.success("Solicitação enviada com sucesso!")

# ----------------------------
# PAINEL ADMIN
# ----------------------------
elif menu == "Painel" and st.session_state.usuario == "admin_business":
    st.header("Painel de Demandas")

    dados = c.execute("SELECT * FROM solicitacoes").fetchall()
    if not dados:
        st.info("Nenhuma solicitação registrada.")
    else:
        df = pd.DataFrame(
            dados,
            columns=[
                "ID",
                "Cliente",
                "Solicitante",
                "Título",
                "Descrição",
                "Prioridade",
                "Status",
                "Resposta",
                "Complexidade",
                "Data Criação",
                "Início Atendimento",
                "Fim Atendimento",
            ],
        )

        # Indicadores gerais
        st.subheader("Resumo Geral")
        total = len(df)
        finalizadas = len(df[df["Status"] == "Finalizado"])
        pendentes = len(df[df["Status"].isin(["Pendente", "Em andamento"])])
        st.metric("Total de Solicitações", total)
        st.metric("Finalizadas", finalizadas)
        st.metric("Pendentes", pendentes)

        # Pendentes por prioridade
        st.subheader("Pendentes por Prioridade")
        pendencias = df[df["Status"].isin(["Pendente", "Em andamento"])]
        resumo = pendencias.groupby("Prioridade")["ID"].count().reset_index()
        resumo.columns = ["Prioridade", "Quantidade"]
        st.bar_chart(resumo.set_index("Prioridade"))

        # Tempo médio por solicitação
        df["Data Criação"] = pd.to_datetime(df["Data Criação"])
        df["Início Atendimento"] = pd.to_datetime(df["Início Atendimento"])
        df["Fim Atendimento"] = pd.to_datetime(df["Fim Atendimento"])
        df["Tempo Atendimento"] = (
            df["Fim Atendimento"] - df["Início Atendimento"]
        ).dt.total_seconds() / 60
        tempo_medio = (
            df["Tempo Atendimento"].mean()
            if not df["Tempo Atendimento"].isna().all()
            else 0
        )
        st.write(f"Tempo médio por solicitação: {tempo_medio:.2f} minutos")

        st.markdown("---")
        st.subheader("Solicitações Detalhadas")
        for _, d in df.iterrows():
            st.markdown(f"**#{d['ID']} - {d['Título']}**")
            st.write(f"Solicitante: {d['Solicitante']}")
            st.write(f"Data e hora da criação: {d['Data Criação']}")
            st.write(
                f"Prioridade: {d['Prioridade']} | Status: {d['Status']} | Complexidade: {d['Complexidade']}"
            )
            resposta = st.text_area(
                "Atualização/Observação", value=d["Resposta"], key=f"resp{d['ID']}"
            )
            novo_status = st.selectbox(
                "Alterar status",
                ["Pendente", "Em andamento", "Em validação", "Finalizado"],
                index=["Pendente", "Em andamento", "Em validação", "Finalizado"].index(
                    d["Status"]
                ),
                key=f"status{d['ID']}",
            )
            if st.button(f"Salvar {d['ID']}"):
                if d["Início Atendimento"] is pd.NaT:
                    inicio = datetime.now().strftime("%Y-%m-%d %H:%M")
                else:
                    inicio = d["Início Atendimento"].strftime("%Y-%m-%d %H:%M")
                fim = (
                    datetime.now().strftime("%Y-%m-%d %H:%M")
                    if novo_status == "Finalizado"
                    else None
                )
                c.execute(
                    """
                    UPDATE solicitacoes SET status=?, resposta=?, inicio_atendimento=?, fim_atendimento=?
                    WHERE id=?
                """,
                    (novo_status, resposta, inicio, fim, d["ID"]),
                )
                conn.commit()
                st.success("Atualizado!")

# ----------------------------
# VISÃO CLIENTE
# ----------------------------
elif menu == "Cliente" and st.session_state.usuario != "admin_business":
    st.header("Consulta de Solicitações")
    cliente_busca = st.session_state.usuario  # pega automaticamente o cliente logado
    dados = c.execute(
        "SELECT * FROM solicitacoes WHERE cliente=?", (cliente_busca,)
    ).fetchall()
    if not dados:
        st.warning("Nenhuma solicitação encontrada.")
    else:
        for d in dados:
            st.markdown(f"**#{d[0]} - {d[3]}**")
            st.write(f"Data/Hora da Solicitação: {d[9]}")
            st.write(f"Complexidade: {d[8]} | Prioridade: {d[5]}")
            st.write(f"Status: {d[6]}")
            st.write(f"Resposta: {d[7]}")
            st.markdown("---")

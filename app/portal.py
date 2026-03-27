import streamlit as st
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
import pandas as pd

# ----------------------------
# CONFIGURAÇÃO INICIAL
# ----------------------------
st.set_page_config(page_title="Portal Business Vision", layout="wide")

# Caminho do logo
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
st.caption("Gestão de demandas e acompanhamento em tempo real")

# ----------------------------
# CONEXÃO COM BANCO
# ----------------------------
db_path = Path(__file__).parent / "dados.db"
conn = sqlite3.connect(db_path, check_same_thread=False)
c = conn.cursor()

# ----------------------------
# CRIAR TABELAS SE NÃO EXISTIREM
# ----------------------------
c.execute(
    """
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    usuario TEXT UNIQUE,
    senha TEXT,
    ativo INTEGER DEFAULT 1
)
"""
)

c.execute(
    """
CREATE TABLE IF NOT EXISTS solicitacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    solicitante TEXT,
    titulo TEXT,
    descricao TEXT,
    prioridade TEXT,
    status TEXT,
    resposta TEXT,
    complexidade TEXT,
    prazo INTEGER,
    data_inicio TEXT,
    data_fim TEXT,
    data_criacao TEXT,
    FOREIGN KEY(cliente_id) REFERENCES clientes(id)
)
"""
)
conn.commit()

# ----------------------------
# LOGIN ADMIN / CLIENTE
# ----------------------------
st.session_state.setdefault("logado", False)
st.session_state.setdefault("usuario", "")

if not st.session_state.logado:
    st.subheader("Login")
    usuario_input = st.text_input("Usuário")
    senha_input = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if usuario_input == "admin_business" and senha_input == "M@ionese123":
            st.session_state.logado = True
            st.session_state.usuario = "admin"
        else:
            c.execute(
                "SELECT id, nome FROM clientes WHERE usuario=? AND senha=? AND ativo=1",
                (usuario_input, senha_input),
            )
            cliente = c.fetchone()
            if cliente:
                st.session_state.logado = True
                st.session_state.usuario = "cliente"
                st.session_state.cliente_id = cliente[0]
                st.session_state.cliente_nome = cliente[1]
            else:
                st.error("Usuário ou senha inválidos")

if st.session_state.logado:
    # ----------------------------
    # MENU LATERAL
    # ----------------------------
    menu_itens = ["Nova Solicitação", "Demandas Solicitadas", "Dashboard"]
    if st.session_state.usuario == "admin":
        menu_itens.append("Cadastro Clientes")
    menu = st.sidebar.selectbox("Menu", menu_itens)

    # ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
if menu == "Nova Solicitação":
    st.header("Nova Solicitação")

    if st.session_state.usuario == "admin":
        # Admin seleciona cliente ativo
        with conn:
            clientes_ativos = c.execute(
                "SELECT id, nome FROM clientes WHERE ativo=1"
            ).fetchall()
        if clientes_ativos:
            cliente_id = st.selectbox(
                "Selecione Cliente", [f"{c[0]} - {c[1]}" for c in clientes_ativos]
            )
            cliente_id = int(cliente_id.split(" - ")[0])
        else:
            st.warning("Não há clientes ativos cadastrados.")
            cliente_id = None
        solicitante = st.text_input("Nome do Solicitante")
        complexidade = st.selectbox("Complexidade", ["Leve", "Média", "Complexa"])
        prazo = st.number_input(
            "Prazo (em horas)", min_value=1, max_value=168, value=24
        )
    else:
        # Cliente logado
        cliente_id = st.session_state.cliente_id
        solicitante = st.session_state.cliente_nome
        complexidade = ""
        prazo = None

    titulo = st.text_input("Título")
    descricao = st.text_area("Descrição")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

    if st.button("Enviar"):
        if cliente_id is None:
            st.error("Não é possível enviar solicitação sem cliente selecionado.")
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            with conn:
                c.execute(
                    """
                INSERT INTO solicitacoes
                (cliente_id, solicitante, titulo, descricao, prioridade, status, resposta, complexidade, prazo, data_inicio, data_fim, data_criacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        cliente_id,
                        solicitante,
                        titulo,
                        descricao,
                        prioridade,
                        "Pendente",
                        "",
                        complexidade,
                        prazo,
                        now,
                        None,
                        now,
                    ),
                )
            st.success("Solicitação enviada com sucesso!")

    # ----------------------------
    # DEMANDAS SOLICITADAS (CLIENTE)
    # ----------------------------
    elif menu == "Demandas Solicitadas":
        st.header("Demandas Solicitadas")
        if st.session_state.usuario == "cliente":
            cliente_id = st.session_state.cliente_id
            dados = c.execute(
                "SELECT id, titulo, prioridade, status, data_criacao, prazo, complexidade FROM solicitacoes WHERE cliente_id=?",
                (cliente_id,),
            ).fetchall()
        else:  # admin pode ver geral
            dados = c.execute(
                "SELECT s.id, s.titulo, s.prioridade, s.status, s.data_criacao, s.prazo, s.complexidade, cl.nome "
                "FROM solicitacoes s JOIN clientes cl ON s.cliente_id=cl.id"
            ).fetchall()

        if not dados:
            st.info("Nenhuma solicitação encontrada.")
        else:
            # Tabela com cores
            status_color = {
                "Pendente": "🔴",
                "Em andamento": "🟡",
                "Atrasado": "⚫",
                "Resolvido": "🟢",
            }
            table_rows = []
            for d in dados:
                if st.session_state.usuario == "cliente":
                    status_display = status_color.get(d[3], d[3])
                    table_rows.append(
                        [
                            d[0],
                            st.session_state.cliente_nome,
                            d[1],
                            d[2],
                            status_display,
                        ]
                    )
                else:
                    status_display = status_color.get(d[3], d[3])
                    table_rows.append([d[0], d[7], d[1], d[2], status_display])
            df = pd.DataFrame(
                table_rows,
                columns=["ID", "Solicitante", "Título", "Prioridade", "Status"],
            )
            st.table(df)
            st.markdown(
                "**Legenda:** 🔴 Pendente | 🟡 Em andamento | ⚫ Atrasado | 🟢 Resolvido"
            )

    # ----------------------------
    # DASHBOARD (Admin)
    # ----------------------------
    elif menu == "Dashboard" and st.session_state.usuario == "admin":
        st.header("Dashboard de Gestão")
        c.execute("SELECT * FROM solicitacoes")
        dados = c.fetchall()
        if dados:
            df = pd.DataFrame(
                dados,
                columns=[
                    "ID",
                    "Cliente_id",
                    "Solicitante",
                    "Título",
                    "Descrição",
                    "Prioridade",
                    "Status",
                    "Resposta",
                    "Complexidade",
                    "Prazo",
                    "Data_Inicio",
                    "Data_Fim",
                    "Data_Criacao",
                ],
            )
            # Quantidade total
            total = len(df)
            finalizadas = len(df[df["Status"] == "Resolvido"])
            pendentes = len(df[df["Status"] == "Pendente"])
            andamento = len(df[df["Status"] == "Em andamento"])
            st.metric("Total de Solicitações", total)
            st.metric("Finalizadas", finalizadas)
            st.metric("Pendentes", pendentes)
            st.metric("Em andamento", andamento)
            st.markdown("---")
            # Gráfico de prioridade
            st.subheader("Solicitações por Prioridade")
            st.bar_chart(df.groupby("Prioridade")["ID"].count())
            # Tempo médio
            df["Data_Inicio"] = pd.to_datetime(df["Data_Inicio"])
            df["Data_Fim"] = pd.to_datetime(df["Data_Fim"])
            df["Duracao"] = (
                df["Data_Fim"] - df["Data_Inicio"]
            ).dt.total_seconds() / 3600
            st.metric(
                "Tempo Médio de Atendimento (h)",
                round(
                    df["Duracao"].mean() if not df["Duracao"].isnull().all() else 0, 2
                ),
            )

    # ----------------------------
    # CADASTRO CLIENTES (Admin)
    # ----------------------------
    elif menu == "Cadastro Clientes" and st.session_state.usuario == "admin":
        st.header("Cadastro de Clientes")
        nome = st.text_input("Nome da Empresa")
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        ativo = st.checkbox("Ativo", value=True)
        if st.button("Cadastrar"):
            c.execute(
                "INSERT INTO clientes (nome, usuario, senha, ativo) VALUES (?,?,?,?)",
                (nome, usuario, senha, 1 if ativo else 0),
            )
            conn.commit()
            st.success("Cliente cadastrado com sucesso!")

import streamlit as st
import sqlite3
from datetime import datetime
from collections import Counter

# ==========================
# Conexão com banco de dados
# ==========================
conn = sqlite3.connect("dados.db", check_same_thread=False)
c = conn.cursor()

# Criar tabela de solicitações
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

# Criar tabela de usuários/empresas
c.execute(
    """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa TEXT UNIQUE,
    senha TEXT
)
"""
)
conn.commit()

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Portal Business Vision", layout="wide")
st.title("🚀 Portal Business Vision")
st.caption("Gestão de demandas e acompanhamento em tempo real")

# ==========================
# Menu lateral
# ==========================
menu = st.sidebar.selectbox("Menu", ["Nova Solicitação", "Painel", "Cliente", "Admin"])

# ==========================
# 🔹 ADMIN - Cadastro de empresas
# ==========================
if menu == "Admin":
    st.header("⚙️ Administração - Cadastrar Empresas")

    st.subheader("Login de administrador")
    admin_senha = st.text_input("Senha admin", type="password")

    if admin_senha == "admin123":  # Senha fixa para teste, pode melhorar depois
        st.success("Acesso autorizado!")

        st.subheader("Cadastrar nova empresa/usuário")
        nova_empresa = st.text_input("Nome da empresa")
        nova_senha = st.text_input("Senha da empresa", type="password")

        if st.button("Cadastrar Empresa"):
            if nova_empresa and nova_senha:
                try:
                    c.execute(
                        "INSERT INTO usuarios (empresa, senha) VALUES (?, ?)",
                        (nova_empresa, nova_senha),
                    )
                    conn.commit()
                    st.success(f"Empresa '{nova_empresa}' cadastrada com sucesso!")
                except:
                    st.error("Empresa já cadastrada ou erro no cadastro.")

        st.subheader("Empresas cadastradas")
        dados_empresas = c.execute("SELECT empresa FROM usuarios").fetchall()
        for e in dados_empresas:
            st.write(f"- {e[0]}")
    else:
        st.warning("Senha incorreta.")

# ==========================
# 🔹 NOVA SOLICITAÇÃO
# ==========================
elif menu == "Nova Solicitação":
    st.header("📥 Nova Solicitação")

    cliente = st.text_input("Cliente")
    titulo = st.text_input("Título")
    descricao = st.text_area("Descrição")
    prioridade = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])

    if st.button("Enviar"):
        if cliente and titulo and descricao:
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
        else:
            st.error("Preencha todos os campos!")

# ==========================
# 🔹 PAINEL - Dashboard interno
# ==========================
elif menu == "Painel":
    st.header("📊 Painel de Demandas")

    dados = c.execute("SELECT * FROM solicitacoes").fetchall()

    if dados:
        # Dashboard de prioridades
        prioridades = [d[4] for d in dados]
        contagem = Counter(prioridades)
        st.subheader("📈 Demandas por Prioridade")
        st.write(f"- Alta: {contagem.get('Alta',0)}")
        st.write(f"- Média: {contagem.get('Média',0)}")
        st.write(f"- Baixa: {contagem.get('Baixa',0)}")

        # Listagem detalhada
        st.subheader("Detalhamento das solicitações")
        for d in dados:
            st.markdown(f"### #{d[0]} - {d[2]}")
            st.write(f"Cliente: {d[1]}")
            st.write(f"Prioridade: {d[4]}")
            st.write(f"Status atual: {d[5]}")
            resposta = st.text_area(
                "Observações / Atualizações", value=d[6], key=f"resp{d[0]}"
            )
            novo_status = st.selectbox(
                "Alterar status",
                ["Pendente", "Em andamento", "Em validação", "Finalizado"],
                index=(
                    ["Pendente", "Em andamento", "Em validação", "Finalizado"].index(
                        d[5]
                    )
                    if d[5]
                    in ["Pendente", "Em andamento", "Em validação", "Finalizado"]
                    else 0
                ),
                key=f"status{d[0]}",
            )
            if st.button(f"Salvar {d[0]}"):
                c.execute(
                    "UPDATE solicitacoes SET status=?, resposta=? WHERE id=?",
                    (novo_status, resposta, d[0]),
                )
                conn.commit()
                st.success("Atualizado com sucesso!")

    else:
        st.info("Nenhuma solicitação cadastrada ainda.")

# ==========================
# 🔹 VISÃO CLIENTE
# ==========================
elif menu == "Cliente":
    st.header("👤 Consulta de Solicitações")

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

import base64
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from zoneinfo import ZoneInfo


# ----------------------------
# CONFIGURAÇÃO INICIAL
# ----------------------------
st.set_page_config(page_title='Portal Business Vision', layout='wide')

BASE_DIR = Path(__file__).parent
APP_DATA_DIR = Path.home() / '.businessvision'
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

db_path = APP_DATA_DIR / 'dados.db'

logo_candidates = [
    BASE_DIR / 'imagens' / 'logo.png',
    BASE_DIR / 'Logo.png',
    BASE_DIR / 'logo.png',
]
logo_path = next((p for p in logo_candidates if p.exists()), logo_candidates[0])

admin_user = 'admin_business'
admin_pass = 'M@ionese123'
APP_TZ = ZoneInfo('America/Santarem')


# ----------------------------
# CONEXÃO COM BANCO
# ----------------------------
@st.cache_resource
def get_connection():
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


conn = get_connection()


# ----------------------------
# LOGO
# ----------------------------
def carregar_logo():
    try:
        if logo_path.exists():
            return Image.open(logo_path)
    except Exception:
        pass
    return None


def logo_base64():
    try:
        if logo_path.exists():
            return base64.b64encode(logo_path.read_bytes()).decode()
    except Exception:
        pass
    return None


logo = carregar_logo()


# ----------------------------
# DATA/HORA
# ----------------------------
def agora_str():
    return datetime.now(APP_TZ).strftime('%Y-%m-%d %H:%M:%S')


# ----------------------------
# BANCO
# ----------------------------
def coluna_existe(nome_tabela, nome_coluna):
    colunas = {row['name'] for row in conn.execute(f'PRAGMA table_info({nome_tabela})').fetchall()}
    return nome_coluna in colunas


def criar_tabelas():
    with conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT,
                razao_social TEXT,
                fantasia TEXT,
                cep TEXT,
                logradouro TEXT,
                numero TEXT,
                bairro TEXT,
                cidade TEXT,
                ativo INTEGER DEFAULT 1
            )
            '''
        )

        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE,
                senha TEXT,
                nome TEXT,
                ativo INTEGER DEFAULT 1
            )
            '''
        )

        conn.execute(
            '''
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
            '''
        )

        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS anexos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                solicitacao_id INTEGER NOT NULL,
                nome_arquivo TEXT,
                observacao TEXT,
                imagem BLOB,
                data_criacao TEXT,
                FOREIGN KEY (solicitacao_id) REFERENCES solicitacoes(id) ON DELETE CASCADE
            )
            '''
        )

        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS sessoes_login (
                token TEXT PRIMARY KEY,
                usuario TEXT NOT NULL,
                menu TEXT,
                data_criacao TEXT
            )
            '''
        )

        if not coluna_existe('clientes', 'cpf'):
            conn.execute('ALTER TABLE clientes ADD COLUMN cpf TEXT')

        if not coluna_existe('clientes', 'empresa_id'):
            conn.execute('ALTER TABLE clientes ADD COLUMN empresa_id INTEGER')

        if not coluna_existe('clientes', 'funcao'):
            conn.execute('ALTER TABLE clientes ADD COLUMN funcao TEXT')

        if not coluna_existe('empresas', 'ativo'):
            conn.execute('ALTER TABLE empresas ADD COLUMN ativo INTEGER DEFAULT 1')

        for coluna in ['complexidade', 'resposta', 'data_criacao', 'inicio_atendimento', 'fim_atendimento']:
            if not coluna_existe('solicitacoes', coluna):
                conn.execute(f'ALTER TABLE solicitacoes ADD COLUMN {coluna} TEXT')

        if not coluna_existe('sessoes_login', 'menu'):
            conn.execute('ALTER TABLE sessoes_login ADD COLUMN menu TEXT')


criar_tabelas()


# ----------------------------
# SESSION STATE
# ----------------------------
def init_state():
    defaults = {
        'logado': False,
        'usuario': '',
        'menu_atual': 'Nova Solicitação',
        'titulo': '',
        'descricao': '',
        'mostrar_legenda': False,
        'limpar_campos_nova_solicitacao': False,
        'token_sessao': None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ----------------------------
# FUNÇÕES AUXILIARES
# ----------------------------
def gerar_usuario(nome):
    partes = [p for p in re.split(r'\s+', nome.strip().lower()) if p]
    if not partes:
        return ''
    usuario = f'{partes[0]}_{partes[-1]}' if len(partes) > 1 else partes[0]
    return re.sub(r'[^a-z0-9_]', '', usuario)


def criar_sessao_login(usuario, menu='Nova Solicitação'):
    token = str(uuid.uuid4())
    with conn:
        conn.execute(
            '''
            INSERT OR REPLACE INTO sessoes_login (token, usuario, menu, data_criacao)
            VALUES (?, ?, ?, ?)
            ''',
            (token, usuario, menu, agora_str()),
        )
    return token


def atualizar_menu_sessao(token, menu):
    if not token:
        return
    with conn:
        conn.execute('UPDATE sessoes_login SET menu = ? WHERE token = ?', (menu, token))


def obter_sessao(token):
    if not token:
        return None
    return conn.execute(
        'SELECT token, usuario, menu, data_criacao FROM sessoes_login WHERE token = ?',
        (token,),
    ).fetchone()


def excluir_sessao(token):
    if not token:
        return
    with conn:
        conn.execute('DELETE FROM sessoes_login WHERE token = ?', (token,))


def restaurar_login():
    token = st.query_params.get('token')
    if not token:
        return
    sessao = obter_sessao(token)
    if not sessao:
        return

    usuario = sessao['usuario']
    if usuario != admin_user:
        cliente = conn.execute(
            'SELECT usuario FROM clientes WHERE usuario = ? AND ativo = 1',
            (usuario,),
        ).fetchone()
        if not cliente:
            return

    st.session_state.logado = True
    st.session_state.usuario = usuario
    st.session_state.menu_atual = sessao['menu'] or 'Nova Solicitação'
    st.session_state.token_sessao = token


def persistir_query_params():
    if st.session_state.get('token_sessao'):
        st.query_params['token'] = st.session_state.token_sessao
    else:
        if 'token' in st.query_params:
            del st.query_params['token']


if not st.session_state.logado:
    restaurar_login()
    persistir_query_params()


def logout():
    token = st.session_state.get('token_sessao')
    excluir_sessao(token)
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()


def limpar_formulario():
    st.session_state.limpar_campos_nova_solicitacao = True
    st.rerun()


def nova_solicitacao():
    st.session_state.titulo = ''
    st.session_state.descricao = ''
    st.session_state.limpar_campos_nova_solicitacao = False
    st.rerun()


def formatar_status_texto(status):
    status_map = {
        'Pendente': '🔴 Pendente',
        'Iniciado': '🟢 Iniciado',
        'Pausado': '🟡 Pausado',
        'Resolvido': '🔵 Resolvido',
    }
    return status_map.get(status, status)


def obter_clientes_ativos():
    return conn.execute(
        '''
        SELECT usuario, nome
        FROM clientes
        WHERE ativo = 1
        ORDER BY nome, usuario
        '''
    ).fetchall()


def obter_nome_cliente(usuario):
    row = conn.execute('SELECT nome FROM clientes WHERE usuario = ?', (usuario,)).fetchone()
    return row['nome'] if row and row['nome'] else usuario


def atualizar_solicitacao(solicitacao_id, novo_status, observacao):
    atual = conn.execute(
        '''
        SELECT inicio_atendimento, fim_atendimento
        FROM solicitacoes
        WHERE id = ?
        ''',
        (solicitacao_id,),
    ).fetchone()

    inicio_atendimento = atual['inicio_atendimento'] if atual else None
    fim_atendimento = atual['fim_atendimento'] if atual else None
    agora = agora_str()

    if novo_status == 'Iniciado' and not inicio_atendimento:
        inicio_atendimento = agora

    if novo_status == 'Resolvido':
        fim_atendimento = agora

    with conn:
        conn.execute(
            '''
            UPDATE solicitacoes
            SET status = ?,
                resposta = ?,
                inicio_atendimento = ?,
                fim_atendimento = ?
            WHERE id = ?
            ''',
            (novo_status, (observacao or '').strip(), inicio_atendimento, fim_atendimento, solicitacao_id),
        )


def aplicar_estilo_login():
    st.markdown(
        '''
        <style>
        .stApp {
            background: linear-gradient(180deg, #061C33 0%, #0B3A63 100%);
        }
        section[data-testid="stSidebar"] {
            display: none;
        }
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }
        .login-box {
            background: rgba(35, 78, 115, 0.95);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 18px 40px rgba(0,0,0,0.35);
            margin-top: 40px;
        }
        .stTextInput label, .stTextArea label, .stSelectbox label, .stFileUploader label {
            color: #dfeaf5 !important;
            font-weight: 600 !important;
        }
        .stTextInput > div > div > input,
        .stTextArea textarea {
            background-color: rgba(255,255,255,0.06) !important;
            color: white !important;
            border: 1px solid rgba(173, 216, 255, 0.22) !important;
            border-radius: 10px !important;
        }
        .stButton > button {
            width: 100%;
            border-radius: 12px;
            font-weight: 700;
        }
        </style>
        ''',
        unsafe_allow_html=True,
    )


# ----------------------------
# LOGIN
# ----------------------------
if not st.session_state.logado:
    aplicar_estilo_login()

    col1, col2, col3 = st.columns([1.2, 1, 1.2])

    with col2:
        st.markdown('<div class="login-box">', unsafe_allow_html=True)

        encoded_logo = logo_base64()
        if encoded_logo:
            st.markdown(
                f"""
                <div style='display:flex; justify-content:center; margin-bottom:18px;'>
                    <img src='data:image/png;base64,{encoded_logo}' width='140'>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            "<div style='text-align:center; color:white; font-size:26px; font-weight:700;'>BUSINESS VISION</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:15px; margin-top:5px;'>PORTAL DO CLIENTE</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:13px; margin-bottom:20px;'>Acesse sua conta</div>",
            unsafe_allow_html=True,
        )

        usuario_input = st.text_input('Usuário', placeholder='Digite seu usuário')
        senha_input = st.text_input('Senha', type='password', placeholder='Digite sua senha')

        if st.button('ENTRAR →'):
            usuario_digitado = usuario_input.strip()
            senha_digitada = senha_input.strip()

            if usuario_digitado == admin_user and senha_digitada == admin_pass:
                token = criar_sessao_login(admin_user, 'Nova Solicitação')
                st.session_state.logado = True
                st.session_state.usuario = admin_user
                st.session_state.menu_atual = 'Nova Solicitação'
                st.session_state.token_sessao = token
                persistir_query_params()
                st.rerun()
            else:
                cliente = conn.execute(
                    '''
                    SELECT usuario
                    FROM clientes
                    WHERE usuario = ?
                      AND senha = ?
                      AND ativo = 1
                    ''',
                    (usuario_digitado, senha_digitada),
                ).fetchone()

                if cliente:
                    token = criar_sessao_login(usuario_digitado, 'Nova Solicitação')
                    st.session_state.logado = True
                    st.session_state.usuario = usuario_digitado
                    st.session_state.menu_atual = 'Nova Solicitação'
                    st.session_state.token_sessao = token
                    persistir_query_params()
                    st.rerun()
                else:
                    st.error('Usuário ou senha inválidos.')

        st.markdown(
            "<div style='text-align:center; color:#c7d7e6; font-size:12px; margin-top:15px;'>Business Vision • Gestão de Demandas</div>",
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    st.stop()


# ----------------------------
# APP LOGADO
# ----------------------------
col1, col2 = st.columns([0.6, 8])

with col1:
    if logo:
        st.image(logo, width=60)

with col2:
    st.markdown("<h1 style='margin-bottom:0;'>Portal Business Vision</h1>", unsafe_allow_html=True)

st.markdown("<hr style='border:1px solid #333; margin-top:0;'>", unsafe_allow_html=True)
st.caption('Gestão de demandas e acompanhamento em tempo real')


# ----------------------------
# MENU
# ----------------------------
menu_options_admin = ['Nova Solicitação', 'Demandas Solicitadas', 'Dashboard', 'Cadastro de Clientes']
menu_options_cliente = ['Nova Solicitação', 'Demandas Solicitadas']
menu_options = menu_options_admin if st.session_state.usuario == admin_user else menu_options_cliente

try:
    default_idx = menu_options.index(st.session_state.get('menu_atual', 'Nova Solicitação'))
except ValueError:
    default_idx = 0

menu = st.sidebar.selectbox('Menu', menu_options, index=default_idx, key='menu_select')
st.session_state.menu_atual = menu
atualizar_menu_sessao(st.session_state.get('token_sessao'), menu)
persistir_query_params()

st.sidebar.markdown('---')
st.sidebar.markdown(f"👤 Usuário: **{st.session_state.usuario}**")
if st.sidebar.button('Trocar usuário'):
    logout()


# ----------------------------
# NOVA SOLICITAÇÃO
# ----------------------------
if menu == 'Nova Solicitação':
    st.header('Nova Solicitação')

    if st.session_state.get('limpar_campos_nova_solicitacao', False):
        st.session_state['titulo'] = ''
        st.session_state['descricao'] = ''
        st.session_state.limpar_campos_nova_solicitacao = False

    if st.session_state.usuario == admin_user:
        clientes_ativos = obter_clientes_ativos()
        if clientes_ativos:
            lista_clientes = [f"{row['nome']} ({row['usuario']})" for row in clientes_ativos]
            mapa_clientes = {f"{row['nome']} ({row['usuario']})": row['usuario'] for row in clientes_ativos}
            cliente_escolhido = st.selectbox('Cliente', lista_clientes)
            cliente_nome = mapa_clientes[cliente_escolhido]
        else:
            st.warning('Não há clientes ativos cadastrados.')
            st.stop()
    else:
        cliente_nome = st.session_state.usuario
        st.text_input('Cliente', value=obter_nome_cliente(cliente_nome), disabled=True)

    titulo = st.text_input('Título', key='titulo')
    descricao = st.text_area('Descrição', key='descricao')
    prioridade = st.selectbox('Prioridade', ['Alta', 'Média', 'Baixa'])

    if st.session_state.usuario == admin_user:
        complexidade = st.selectbox('Complexidade', ['Leve', 'Média', 'Complexa'])
    else:
        complexidade = ''

    st.subheader('Anexos de evidência')
    arquivos = st.file_uploader(
        'Envie pelo menos 1 imagem',
        type=['png', 'jpg', 'jpeg'],
        accept_multiple_files=True,
        key='anexos_upload',
    )

    observacoes_anexos = []
    if arquivos:
        for idx, arq in enumerate(arquivos, start=1):
            st.caption(f'Arquivo {idx}: {arq.name}')
            obs = st.text_input(f'Observação da imagem {idx}', key=f'obs_img_{idx}')
            observacoes_anexos.append(obs)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        enviar = st.button('Enviar', use_container_width=True)
    with col_b:
        limpar = st.button('LIMPAR', use_container_width=True)
    with col_c:
        nova = st.button('NOVA', use_container_width=True)

    if limpar:
        limpar_formulario()

    if nova:
        nova_solicitacao()

    if enviar:
        titulo_limpo = titulo.strip()
        descricao_limpa = descricao.strip()

        if not titulo_limpo or not descricao_limpa:
            st.warning('Preencha título e descrição antes de enviar.')
        elif not arquivos or len(arquivos) == 0:
            st.error('É obrigatório enviar pelo menos uma imagem.')
        else:
            duplicado = conn.execute(
                '''
                SELECT id
                FROM solicitacoes
                WHERE cliente = ?
                  AND titulo = ?
                  AND descricao = ?
                  AND status IN ('Pendente', 'Iniciado', 'Pausado')
                LIMIT 1
                ''',
                (cliente_nome, titulo_limpo, descricao_limpa),
            ).fetchone()

            if duplicado is not None:
                st.warning(
                    f"Esta solicitação já foi solicitada antes e ainda está em andamento. ID #{duplicado['id']}"
                )
            else:
                try:
                    with conn:
                        cur = conn.cursor()
                        cur.execute(
                            '''
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
                            ''',
                            (
                                cliente_nome,
                                titulo_limpo,
                                descricao_limpa,
                                prioridade,
                                'Pendente',
                                complexidade,
                                '',
                                agora_str(),
                            ),
                        )
                        solicitacao_id = cur.lastrowid

                        for idx, arq in enumerate(arquivos):
                            cur.execute(
                                '''
                                INSERT INTO anexos (solicitacao_id, nome_arquivo, observacao, imagem, data_criacao)
                                VALUES (?, ?, ?, ?, ?)
                                ''',
                                (
                                    solicitacao_id,
                                    arq.name,
                                    observacoes_anexos[idx] if idx < len(observacoes_anexos) else '',
                                    arq.getvalue(),
                                    agora_str(),
                                ),
                            )

                    st.session_state.limpar_campos_nova_solicitacao = True
                    st.success('Solicitação enviada com sucesso.')
                    st.rerun()

                except sqlite3.Error as e:
                    st.error(f'Erro ao gravar solicitação: {e}')


# ----------------------------
# DEMANDAS SOLICITADAS
# ----------------------------
elif menu == 'Demandas Solicitadas':
    st.header('Demandas Solicitadas')

    col_legenda1, col_legenda2 = st.columns([8, 1])

    with col_legenda2:
        if st.button('📌 Legenda', use_container_width=True):
            st.session_state.mostrar_legenda = not st.session_state.get('mostrar_legenda', False)

    if st.session_state.get('mostrar_legenda', False):
        st.info(
            '''
🔴 Pendente  
🟢 Iniciado  
🟡 Pausado  
🔵 Resolvido
            '''
        )

    if st.session_state.usuario == admin_user:
        clientes = [row['usuario'] for row in conn.execute(
            'SELECT usuario FROM clientes WHERE ativo = 1 ORDER BY nome, usuario'
        ).fetchall()]
    else:
        clientes = [st.session_state.usuario]

    for cli in clientes:
        nome_exibicao = obter_nome_cliente(cli)
        st.subheader(f'Cliente: {nome_exibicao} ({cli})')

        dados_cli = conn.execute(
            '''
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
            ''',
            (cli,),
        ).fetchall()

        if not dados_cli:
            st.info('Nenhuma solicitação para este cliente.')
            continue

        df_cli = pd.DataFrame([dict(r) for r in dados_cli])

        if st.session_state.usuario != admin_user:
            df_exibicao = df_cli.copy()
            df_exibicao['status'] = df_exibicao['status'].apply(formatar_status_texto)
            df_exibicao['observacoes'] = df_exibicao['resposta'].fillna('')
            df_exibicao = df_exibicao[['id', 'titulo', 'prioridade', 'status', 'observacoes', 'data_criacao']]
            df_exibicao.columns = ['ID', 'Título', 'Prioridade', 'Status', 'Observações', 'Data']
            st.dataframe(df_exibicao, use_container_width=True)

            for _, row in df_cli.iterrows():
                anexos = conn.execute(
                    '''
                    SELECT nome_arquivo, observacao, imagem
                    FROM anexos
                    WHERE solicitacao_id = ?
                    ORDER BY id
                    ''',
                    (int(row['id']),),
                ).fetchall()

                if anexos:
                    with st.expander(f"Ver anexos da solicitação #{int(row['id'])}"):
                        cols = st.columns(min(3, max(1, len(anexos))))
                        for i, anexo in enumerate(anexos):
                            with cols[i % len(cols)]:
                                st.image(
                                    anexo['imagem'],
                                    caption=anexo['observacao'] or anexo['nome_arquivo'],
                                    use_container_width=True,
                                )
        else:
            for _, row in df_cli.iterrows():
                status_atual = row['status']
                solicitacao_id = int(row['id'])

                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([0.7, 2.5, 1.2, 1.2, 1.6])

                    with c1:
                        st.write(f'**#{solicitacao_id}**')
                    with c2:
                        st.write(f"**{row['titulo']}**")
                        st.caption(row['descricao'])
                    with c3:
                        st.write(f"Prioridade: **{row['prioridade']}**")
                    with c4:
                        st.write(f"Status: **{formatar_status_texto(status_atual)}**")
                    with c5:
                        if row['complexidade']:
                            st.write(f"Complexidade: **{row['complexidade']}**")

                    anexos = conn.execute(
                        '''
                        SELECT nome_arquivo, observacao, imagem
                        FROM anexos
                        WHERE solicitacao_id = ?
                        ORDER BY id
                        ''',
                        (solicitacao_id,),
                    ).fetchall()

                    if anexos:
                        st.markdown('**Anexos do cliente:**')
                        cols = st.columns(min(3, max(1, len(anexos))))
                        for i, anexo in enumerate(anexos):
                            with cols[i % len(cols)]:
                                st.image(
                                    anexo['imagem'],
                                    caption=anexo['observacao'] or anexo['nome_arquivo'],
                                    use_container_width=True,
                                )

                    obs_key = f'obs_{solicitacao_id}'
                    if obs_key not in st.session_state:
                        st.session_state[obs_key] = row['resposta'] if row['resposta'] else ''

                    st.text_area(
                        'Observações',
                        key=obs_key,
                        height=90,
                        placeholder='Digite aqui a observação para o cliente...',
                    )

                    ac1, ac2, ac3, ac4 = st.columns([1, 1, 1, 4])

                    if status_atual == 'Pendente':
                        with ac1:
                            if st.button('INICIAR', key=f'iniciar_{solicitacao_id}', use_container_width=True):
                                atualizar_solicitacao(solicitacao_id, 'Iniciado', st.session_state[obs_key])
                                st.rerun()

                    elif status_atual == 'Iniciado':
                        with ac1:
                            if st.button('PAUSAR', key=f'pausar_{solicitacao_id}', use_container_width=True):
                                atualizar_solicitacao(solicitacao_id, 'Pausado', st.session_state[obs_key])
                                st.rerun()
                        with ac2:
                            if st.button('FINALIZAR', key=f'finalizar_{solicitacao_id}', use_container_width=True):
                                atualizar_solicitacao(solicitacao_id, 'Resolvido', st.session_state[obs_key])
                                st.rerun()

                    elif status_atual == 'Pausado':
                        with ac1:
                            if st.button('INICIAR', key=f'reiniciar_{solicitacao_id}', use_container_width=True):
                                atualizar_solicitacao(solicitacao_id, 'Iniciado', st.session_state[obs_key])
                                st.rerun()
                        with ac2:
                            if st.button('FINALIZAR', key=f'finalizar_pausado_{solicitacao_id}', use_container_width=True):
                                atualizar_solicitacao(solicitacao_id, 'Resolvido', st.session_state[obs_key])
                                st.rerun()
                    else:
                        st.success('Demanda finalizada.')

                    meta1, meta2, meta3 = st.columns(3)
                    with meta1:
                        st.caption(f"Criado em: {row['data_criacao'] or ''}")
                    with meta2:
                        st.caption(f"Início: {row['inicio_atendimento'] or ''}")
                    with meta3:
                        st.caption(f"Fim: {row['fim_atendimento'] or ''}")


# ----------------------------
# DASHBOARD
# ----------------------------
elif menu == 'Dashboard' and st.session_state.usuario == admin_user:
    st.header('Dashboard')

    if logo:
        st.image(logo, width=100)

    st.markdown('<hr>', unsafe_allow_html=True)

    dados = conn.execute(
        '''
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
        '''
    ).fetchall()

    colunas = ['ID', 'Cliente', 'Título', 'Descrição', 'Prioridade', 'Status', 'Complexidade', 'Resposta', 'Data', 'Início', 'Fim']
    df = pd.DataFrame([tuple(r) for r in dados], columns=colunas) if dados else pd.DataFrame(columns=colunas)

    total = len(df)
    finalizadas = len(df[df['Status'] == 'Resolvido'])
    pendentes_iniciadas = len(df[df['Status'].isin(['Pendente', 'Iniciado', 'Pausado'])])

    col1, col2, col3 = st.columns(3)
    col1.metric('Total de Solicitações', total)
    col2.metric('Finalizadas', finalizadas)
    col3.metric('Pendentes/Iniciadas', pendentes_iniciadas)

    st.subheader('Solicitações por Prioridade')
    if not df.empty:
        resumo = df.groupby('Prioridade')['ID'].count().reset_index()
        resumo.columns = ['Prioridade', 'Quantidade']
        st.bar_chart(resumo.set_index('Prioridade'))
    else:
        st.info('Nenhuma solicitação registrada ainda.')

    st.subheader('Tempo médio de atendimento')
    if not df.empty:
        df_tempo = df.copy()
        df_tempo = df_tempo[
            df_tempo['Início'].notna()
            & df_tempo['Fim'].notna()
            & (df_tempo['Início'] != '')
            & (df_tempo['Fim'] != '')
        ].copy()

        if not df_tempo.empty:
            df_tempo['Início'] = pd.to_datetime(df_tempo['Início'], errors='coerce')
            df_tempo['Fim'] = pd.to_datetime(df_tempo['Fim'], errors='coerce')
            df_tempo['Horas'] = (df_tempo['Fim'] - df_tempo['Início']).dt.total_seconds() / 3600
            media_horas = df_tempo['Horas'].dropna().mean()

            if pd.notna(media_horas):
                st.metric('Tempo médio (horas)', f'{media_horas:.2f}')
            else:
                st.info('Ainda não há dados suficientes para calcular o tempo médio.')
        else:
            st.info('Ainda não há dados suficientes para calcular o tempo médio.')
    else:
        st.info('Ainda não há dados suficientes para calcular o tempo médio.')


# ----------------------------
# CADASTRO DE CLIENTES E EMPRESAS
# ----------------------------
elif menu == 'Cadastro de Clientes' and st.session_state.usuario == admin_user:
    st.header('Cadastro de Clientes')

    st.subheader('Cadastro de Empresa')
    c1, c2 = st.columns(2)
    with c1:
        cnpj = st.text_input('CNPJ')
        razao_social = st.text_input('Razão Social')
        fantasia = st.text_input('Nome Fantasia')
        cep = st.text_input('CEP')
    with c2:
        logradouro = st.text_input('Logradouro')
        numero = st.text_input('Número')
        bairro = st.text_input('Bairro')
        cidade = st.text_input('Cidade')

    if st.button('Cadastrar Empresa'):
        if not fantasia.strip() or not razao_social.strip():
            st.error('Preencha pelo menos Razão Social e Nome Fantasia.')
        else:
            with conn:
                conn.execute(
                    '''
                    INSERT INTO empresas
                    (cnpj, razao_social, fantasia, cep, logradouro, numero, bairro, cidade, ativo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ''',
                    (
                        cnpj.strip(),
                        razao_social.strip(),
                        fantasia.strip(),
                        cep.strip(),
                        logradouro.strip(),
                        numero.strip(),
                        bairro.strip(),
                        cidade.strip(),
                    ),
                )
            st.success('Empresa cadastrada com sucesso.')
            st.rerun()

    st.markdown('---')
    st.subheader('Cadastro de Usuário')
    nome_completo = st.text_input('Nome completo')
    cpf = st.text_input('CPF')

    empresas = conn.execute(
        'SELECT id, fantasia FROM empresas WHERE ativo = 1 ORDER BY fantasia'
    ).fetchall()

    if empresas:
        labels_empresas = [row['fantasia'] for row in empresas]
        mapa_empresas = {row['fantasia']: row['id'] for row in empresas}
        empresa_sel = st.selectbox('Empresa', labels_empresas)
        empresa_id = mapa_empresas[empresa_sel]
    else:
        empresa_id = None
        st.warning('Cadastre pelo menos uma empresa antes de criar usuários.')

    sugestao_usuario = gerar_usuario(nome_completo) if nome_completo.strip() else ''
    usuario = st.text_input('Usuário', value=sugestao_usuario)
    senha = st.text_input('Senha', type='password')
    funcao = st.text_input('Função')
    ativo = st.checkbox('Ativo', value=True)

    if st.button('Cadastrar Usuário'):
        if not empresa_id:
            st.error('É necessário cadastrar uma empresa primeiro.')
        elif not nome_completo.strip() or not cpf.strip() or not usuario.strip() or not senha.strip():
            st.error('Preencha os campos obrigatórios.')
        else:
            existe = conn.execute('SELECT 1 FROM clientes WHERE usuario = ?', (usuario.strip(),)).fetchone()

            if existe:
                st.error('Usuário já existe. Informe outro usuário.')
            else:
                with conn:
                    conn.execute(
                        '''
                        INSERT INTO clientes (usuario, senha, nome, ativo, cpf, empresa_id, funcao)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            usuario.strip(),
                            senha.strip(),
                            nome_completo.strip(),
                            int(ativo),
                            cpf.strip(),
                            empresa_id,
                            funcao.strip(),
                        ),
                    )
                st.success(f'Usuário {usuario.strip()} cadastrado com sucesso.')
                st.rerun()

    st.markdown('---')
    st.subheader('Clientes cadastrados')

    clientes = conn.execute(
        '''
        SELECT
            c.id,
            c.usuario,
            c.nome,
            c.ativo,
            c.cpf,
            c.funcao,
            e.fantasia AS empresa
        FROM clientes c
        LEFT JOIN empresas e ON e.id = c.empresa_id
        ORDER BY c.nome
        '''
    ).fetchall()

    if clientes:
        for cli in clientes:
            id_cli = cli['id']
            with st.container(border=True):
                col1, col2, col3, col4, col5 = st.columns([2, 2.5, 2, 1.2, 2.5])

                with col1:
                    st.write(f"**{cli['usuario']}**")
                    st.caption(cli['nome'] or '')

                with col2:
                    st.write(cli['empresa'] or 'Sem empresa')
                    st.caption(cli['funcao'] or '')

                with col3:
                    st.write(f"CPF: {cli['cpf'] or ''}")

                with col4:
                    status_cliente = '🟢 Ativo' if cli['ativo'] == 1 else '🔴 Inativo'
                    st.write(status_cliente)

                with col5:
                    b1, b2 = st.columns(2)
                    with b1:
                        if cli['ativo'] == 1:
                            if st.button('Inativar', key=f'inativar_{id_cli}', use_container_width=True):
                                with conn:
                                    conn.execute('UPDATE clientes SET ativo = 0 WHERE id = ?', (id_cli,))
                                st.rerun()
                        else:
                            if st.button('Ativar', key=f'ativar_{id_cli}', use_container_width=True):
                                with conn:
                                    conn.execute('UPDATE clientes SET ativo = 1 WHERE id = ?', (id_cli,))
                                st.rerun()

                    with b2:
                        if st.button('Excluir', key=f'excluir_{id_cli}', use_container_width=True):
                            tem_solicitacao = conn.execute(
                                'SELECT 1 FROM solicitacoes WHERE cliente = ? LIMIT 1',
                                (cli['usuario'],),
                            ).fetchone()

                            if tem_solicitacao:
                                st.warning(
                                    f"O cliente {cli['usuario']} possui solicitações. Inative ao invés de excluir."
                                )
                            else:
                                with conn:
                                    conn.execute('DELETE FROM clientes WHERE id = ?', (id_cli,))
                                st.success(f"Cliente {cli['usuario']} excluído.")
                                st.rerun()
    else:
        st.info('Nenhum cliente cadastrado ainda.')

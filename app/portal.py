# === PATCH EXECUTIVO DE VISUAL (APLICAR NO SEU PORTAL.py) ===

def aplicar_estilo_app():
    import streamlit as st
    st.markdown("""
    <style>

    .stApp {
        background: linear-gradient(180deg, #0B1220 0%, #0F1B2E 100%);
    }

    section[data-testid="stSidebar"] {
        background: #0A1628;
        border-right: 1px solid #1E293B;
    }

    section[data-testid="stSidebar"] * {
        color: #CBD5E1 !important;
    }

    .block-container {
        padding-top: 2rem;
    }

    h1, h2, h3 {
        color: #E2E8F0;
    }

    p, span, label {
        color: #94A3B8;
    }

    div[data-testid="stVerticalBlock"] > div {
        background: #111C2E;
        border: 1px solid #1F2A3C;
        border-radius: 12px;
        padding: 16px;
    }

    .stButton > button {
        background: #1D4ED8;
        color: white;
        border-radius: 10px;
        font-weight: 600;
        border: none;
    }

    .stButton > button:hover {
        background: #1E40AF;
    }

    .stTextInput input, .stTextArea textarea, .stSelectbox div {
        background: #0F172A !important;
        color: #E2E8F0 !important;
        border: 1px solid #1F2A3C !important;
        border-radius: 8px !important;
    }

    </style>
    """, unsafe_allow_html=True)


# === ONDE USAR ===
# Depois do login, no início do app logado:

# aplicar_estilo_app()


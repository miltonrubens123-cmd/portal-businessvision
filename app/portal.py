# (TRECHO PRINCIPAL AJUSTADO)

def render_status_badge(status):
    status = normalizar_status(status)

    styles = {
        "Em análise": {
            "bg": "#EAF2FF",
            "border": "#C7D7FE",
            "text": "#1E3A5F",
            "icon": "#315E9E",
            "svg": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><path d="M12 7V12L15 14" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        },
        "Em atendimento": {
            "bg": "#E8F7F4",
            "border": "#BFE7DD",
            "text": "#0F4C45",
            "icon": "#148777",
            "svg": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 3L4 7V12C4 17 7.5 20.5 12 21C16.5 20.5 20 17 20 12V7L12 3Z" stroke="currentColor" stroke-width="2"/></svg>',
        },
        "Aguardando cliente": {
            "bg": "#FFF6E8",
            "border": "#F2D7A6",
            "text": "#6B4E16",
            "icon": "#C58A1C",
            "svg": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 8V12" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="16" r="1" fill="currentColor"/></svg>',
        },
        "Concluído": {
            "bg": "#EDF7ED",
            "border": "#CBE7CB",
            "text": "#1F5A2E",
            "icon": "#2F8F46",
            "svg": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17L4 12" stroke="currentColor" stroke-width="2"/></svg>',
        },
    }

    s = styles.get(status, styles["Em análise"])

    return f'''
    <div style="
        display:inline-flex;
        align-items:center;
        gap:6px;
        padding:4px 10px;
        border-radius:999px;
        background:{s['bg']};
        border:1px solid {s['border']};
        color:{s['text']};
        font-size:12px;
        font-weight:600;">
        <span style="display:flex;color:{s['icon']}">{s['svg']}</span>
        <span>{status}</span>
    </div>
    '''

# USO CORRETO (EXEMPLO)
# st.markdown(render_status_badge(status_atual), unsafe_allow_html=True)

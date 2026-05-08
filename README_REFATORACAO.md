# Business Vision — Refatoração Fase 1

Esta versão inicia a separação em camadas sem alterar a lógica operacional principal do portal.

## Como executar

```bash
streamlit run app.py
```

## O que foi separado nesta fase

- `database/connection.py`: conexão PostgreSQL/Neon e proxy seguro.
- `utils/security.py`: hash, validação de senha e leitura de credenciais admin.
- `utils/formatters.py`: formatação e validação de CPF/CNPJ.
- `utils/validators.py`: validação de upload de imagem.
- `config/settings.py`: constantes globais para próximas fases.

## Arquivos principais

- `app.py`: portal principal ajustado para importar módulos separados.
- `portal_original_backup.py`: cópia integral do arquivo original enviado.

## Próxima fase recomendada

Separar autenticação, sessão e menu lateral:

- `services/auth_service.py`
- `utils/session.py`
- `components/sidebar.py`
- `pages/login.py`

Depois disso, separar as páginas grandes: demandas, dashboard, clientes, atendentes, projetos e convites.

@echo off
REM ----------------------------
REM Rodar Portal Business Vision - Automático
REM ----------------------------

REM Nome do ambiente virtual
set VENV_DIR=venv

REM Verifica se o ambiente virtual existe
IF NOT EXIST %VENV_DIR% (
    echo Criando ambiente virtual...
    python -m venv %VENV_DIR%
)

REM Ativa o ambiente virtual
echo Ativando ambiente virtual...
call %VENV_DIR%\Scripts\activate

REM Atualiza pip e instala dependências
echo Instalando/atualizando pacotes...
python -m pip install --upgrade pip
IF EXIST requirements.txt (
    pip install -r requirements.txt
)

REM Roda o Streamlit
echo Rodando o Portal Business Vision...
python -m streamlit run app\portal.py

pause

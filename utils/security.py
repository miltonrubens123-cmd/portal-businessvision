import os
import hashlib
import hmac
import secrets

import streamlit as st

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 390000


def obter_secret(path, default=None):
    try:
        cursor = st.secrets
        for key in path:
            cursor = cursor[key]
        return cursor
    except Exception:
        return default


def obter_admin_config():
    admin_user = (
        obter_secret(["admin", "user"]) or os.getenv("ADMIN_USER") or ""
    ).strip()

    admin_password_hash = (
        obter_secret(["admin", "password_hash"])
        or os.getenv("ADMIN_PASSWORD_HASH")
        or ""
    ).strip()

    admin_password_plain = (
        obter_secret(["admin", "password"]) or os.getenv("ADMIN_PASSWORD") or ""
    ).strip()

    return {
        "user": admin_user,
        "password_hash": admin_password_hash,
        "password_plain": admin_password_plain,
    }


def senha_esta_hasheada(valor):
    return isinstance(valor, str) and valor.startswith(f"{PASSWORD_SCHEME}$")


def gerar_hash_senha(senha):
    if not isinstance(senha, str) or not senha.strip():
        raise ValueError("Senha inválida para geração de hash.")

    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    return f"{PASSWORD_SCHEME}${PASSWORD_ITERATIONS}${salt}${dk.hex()}"


def verificar_senha(senha_informada, senha_armazenada):
    if not senha_armazenada or not isinstance(senha_armazenada, str):
        return False

    if senha_esta_hasheada(senha_armazenada):
        try:
            _, iteracoes, salt, hash_salvo = senha_armazenada.split("$", 3)
            dk = hashlib.pbkdf2_hmac(
                "sha256",
                (senha_informada or "").encode("utf-8"),
                salt.encode("utf-8"),
                int(iteracoes),
            )
            return hmac.compare_digest(dk.hex(), hash_salvo)
        except Exception:
            return False

    return hmac.compare_digest(senha_armazenada, senha_informada or "")

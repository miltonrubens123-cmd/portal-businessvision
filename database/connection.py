import os
import psycopg
import streamlit as st

from psycopg.rows import dict_row


@st.cache_resource
def get_connection():
    database_url = None

    try:
        if "database" in st.secrets:
            database_url = st.secrets["database"]["url"]
    except Exception:
        pass

    if not database_url:
        database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL não configurada.")

    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
    )


def get_conn():
    return get_connection()


def reset_connection():
    get_connection.clear()
    return get_connection()


class SafeConnProxy:
    def execute(self, *args, **kwargs):
        try:
            return get_conn().execute(*args, **kwargs)
        except Exception:
            return reset_connection().execute(*args, **kwargs)

    def cursor(self, *args, **kwargs):
        try:
            return get_conn().cursor(*args, **kwargs)
        except Exception:
            return reset_connection().cursor(*args, **kwargs)


def run_query(sql, params=None, fetchone=False, fetchall=False):
    with get_conn().cursor() as cur:
        cur.execute(sql, params or ())

        if fetchone:
            return cur.fetchone()

        if fetchall:
            return cur.fetchall()

        return None


conn = SafeConnProxy()
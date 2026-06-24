from typing import Optional

import psycopg2
import psycopg2.extras

from src.config import settings


def get_age_conn():
    """
    Retorna conexão psycopg2 configurada para AGE.
    Sempre fechar após uso (context manager recomendado).
    """
    conn = psycopg2.connect(settings.graph_db_url)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("LOAD 'age';")
        cur.execute('SET search_path = ag_catalog, "$user", public;')
    return conn


def execute_cypher(cypher: str, params: Optional[dict] = None) -> list[dict]:
    """
    Executa uma query Cypher no revenue_graph e retorna rows como lista de dicts.
    Roda de forma síncrona — use asyncio.to_thread() para chamar de código async.
    """
    conn = get_age_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(cypher, params or {})
            conn.commit()
            try:
                return [dict(row) for row in cur.fetchall()]
            except psycopg2.ProgrammingError:
                return []
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

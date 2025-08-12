# backend/routers/insert_specialty_json.py
from __future__ import annotations

import logging
import re
import uuid
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlmodel import Session

from backend.database import engine, get_db

logger = logging.getLogger(__name__)

# Public router export
specialty_router = APIRouter(prefix="", tags=["specialty-diag"])
router = specialty_router  # for main.py include
__all__ = ["router", "specialty_router"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def exec_one(db: Session, sql: str, **params):
    """Execute a SQL statement and return the first row (or None)."""
    return db.exec(text(sql), params=params).first()

def exec_all(db: Session, sql: str, **params):
    """Execute a SQL statement and return all rows (list)."""
    return db.exec(text(sql), params=params).all()

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _ok_ident(x: str) -> bool:
    return bool(_IDENT_RE.match(x))

# ---------------------------------------------------------------------------
# Pings / Connection info
# ---------------------------------------------------------------------------

@specialty_router.get("/_ping-specialty")
def _ping_specialty():
    """Router health check."""
    logger.info("🟢 _ping-specialty endpoint hit")
    return {"ok": True, "message": "Specialty router is alive"}

@specialty_router.get("/_ping-specialty-db")
def _ping_specialty_db(db: Session = Depends(get_db)):
    """DB liveness check (SELECT 1)."""
    logger.info("🟢 _ping-specialty-db endpoint hit")
    result = exec_one(db, "SELECT 1")
    return {"ok": True, "db_result": result[0] if result else None}

@specialty_router.get("/_db-conn-info")
def _db_conn_info():
    """Show SQLAlchemy connection target (masked)."""
    url = engine.url
    return {
        "ok": True,
        "driver": url.drivername,
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
    }

@specialty_router.get("/_db-where-am-i")
def _db_where_am_i(db: Session = Depends(get_db)):
    """Server identity and search_path."""
    row = exec_one(db, """
        SELECT current_database() AS database,
               current_user       AS role,
               current_schema()   AS current_schema,
               current_setting('search_path') AS search_path
    """)
    return {"ok": True, **dict(row._mapping)}

# ---------------------------------------------------------------------------
# Schema / tables
# ---------------------------------------------------------------------------

@specialty_router.get("/_db-schemas")
def _db_schemas(db: Session = Depends(get_db)):
    """List non-system schemas."""
    rows = exec_all(db, """
        SELECT nspname AS schema
        FROM pg_namespace
        WHERE nspname NOT IN ('pg_catalog','information_schema')
        ORDER BY nspname
    """)
    return {"ok": True, "schemas": [r[0] for r in rows]}

@specialty_router.get("/_db-tables-in")
def _db_tables_in(schema: str = Query("public"), db: Session = Depends(get_db)):
    """List tables in a specific schema."""
    rows = exec_all(db, """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :schema
        ORDER BY table_name
    """, schema=schema)
    return {"ok": True, "schema": schema, "tables": [r[0] for r in rows]}

@specialty_router.get("/_db-describe-table")
def _db_describe_table(
    schema: str = Query("public"),
    table: str = Query(...),
    db: Session = Depends(get_db)
):
    """Describe columns for a given table."""
    if not (_ok_ident(schema) and _ok_ident(table)):
        return {"ok": False, "error": "invalid schema/table name"}
    rows = exec_all(db, """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = :schema AND table_name = :table
        ORDER BY ordinal_position
    """, schema=schema, table=table)
    return {
        "ok": True,
        "schema": schema,
        "table": table,
        "columns": [dict(r._mapping) for r in rows]
    }

# ---------------------------------------------------------------------------
# Qualified count / first-row peek
# ---------------------------------------------------------------------------

@specialty_router.get("/_db-count-qual")
def _db_count_qual(
    schema: str = Query("public"),
    table: str = Query(...),
    db: Session = Depends(get_db),
):
    """SELECT COUNT(*) from "schema"."table"."""
    if not (_ok_ident(schema) and _ok_ident(table)):
        return {"ok": False, "error": "invalid schema/table name"}
    row = exec_one(db, f'SELECT COUNT(*) FROM "{schema}"."{table}"')
    return {"ok": True, "schema": schema, "table": table, "count": row[0] if row else 0}

@specialty_router.get("/_db-first-row-qual")
def _db_first_row_qual(
    schema: str = Query("public"),
    table: str = Query(...),
    db: Session = Depends(get_db),
):
    """SELECT * LIMIT 1 from "schema"."table"."""
    if not (_ok_ident(schema) and _ok_ident(table)):
        return {"ok": False, "error": "invalid schema/table name"}
    row = exec_one(db, f'SELECT * FROM "{schema}"."{table}" LIMIT 1')
    return {"ok": True, "schema": schema, "table": table,
            "row": (dict(row._mapping) if row else None)}

# ---------------------------------------------------------------------------
# Specialty probes
# ---------------------------------------------------------------------------

@specialty_router.get("/_specialty-exists")
def _specialty_exists(db: Session = Depends(get_db)):
    """Does public.specialty exist?"""
    row = exec_one(db, "SELECT to_regclass('public.specialty') IS NOT NULL AS exists")
    return {"ok": True, "exists": bool(row[0])}

@specialty_router.get("/_db-pk")
def _db_pk(schema: str = Query("public"),
           table: str = Query(...),
           db: Session = Depends(get_db)):
    """Return primary key column names for a table."""
    rowset = exec_all(db, """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
        WHERE i.indisprimary
          AND n.nspname = :schema
          AND c.relname  = :table
        ORDER BY a.attnum
    """, schema=schema, table=table)
    cols: List[str] = [r[0] for r in rowset]
    return {"ok": True, "schema": schema, "table": table, "pk_columns": cols}

@specialty_router.get("/_specialty-peek")
def _specialty_peek(limit: int = Query(3, ge=1, le=50), db: Session = Depends(get_db)):
    """Return first N rows from public.specialty (no ORDER BY)."""
    try:
        rows = exec_all(db, """
            SELECT * FROM public.specialty
            LIMIT :limit
        """, limit=limit)
        return {"ok": True, "count": len(rows), "rows": [dict(r._mapping) for r in rows]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@specialty_router.get("/_specialty-peek-ordered")
def _specialty_peek_ordered(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Return first N rows ordered by PK (if present)."""
    pk = exec_all(db, """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
        WHERE i.indisprimary
          AND n.nspname = 'public'
          AND c.relname  = 'specialty'
        ORDER BY a.attnum
    """)
    order_clause = ""
    if pk:
        cols = ", ".join([f'"{r[0]}"' for r in pk])
        order_clause = f"ORDER BY {cols}"

    sql = f'SELECT * FROM "public"."specialty" {order_clause} LIMIT :limit'
    try:
        rows = exec_all(db, sql, limit=limit)
        return {"ok": True, "count": len(rows), "rows": [dict(r._mapping) for r in rows]}
    except Exception as e:
        return {"ok": False, "error": str(e), "sql": sql}

# ---------------------------------------------------------------------------
# Validations
# ---------------------------------------------------------------------------

@specialty_router.get("/_db-validate-tables")
def db_validate_tables(schema: str = Query("public"), db: Session = Depends(get_db)):
    """Check presence of expected tables/columns and return row counts."""
    expected = {
        "category": ["id", "category_name"],
        "specialty": ["id", "specialty_name", "language"],
        "specialty_category": ["category_id", "specialty_id"],
        "artist": ["id", "artist_name", "language"],
        "track": ["id", "track_name", "artist_id", "language"],
        "specialty_ranking": ["id", "specialty_category_id", "track_id", "ranking", "language"],
        "genre": ["id", "genre_name"],
        "artist_genre": ["artist_id", "genre_id"],
    }

    report = []
    for table, cols in expected.items():
        t_exists = exec_one(db, """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = :s AND table_name = :t
            )
        """, s=schema, t=table)[0]

        table_info = {"table": table, "exists": bool(t_exists), "missing_columns": [], "count": None}
        if t_exists:
            present_cols = {r[0] for r in exec_all(db, """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = :s AND table_name = :t
            """, s=schema, t=table)}
            missing = [c for c in cols if c not in present_cols]
            table_info["missing_columns"] = missing

            cnt = exec_one(db, f'SELECT COUNT(*) FROM "{schema}"."{table}"')[0]
            table_info["count"] = cnt

        report.append(table_info)

    ok = all(r["exists"] and not r["missing_columns"] for r in report)
    return {"ok": ok, "schema": schema, "tables": report}

@specialty_router.get("/_db-validate-fk")
def db_validate_fk(schema: str = Query("public"), db: Session = Depends(get_db)):
    """Orphan check for common FK relationships (counts > 0 = problems)."""
    checks = {
        "track.artist_id → artist.id":
            f'SELECT COUNT(*) FROM "{schema}"."track" t '
            f'LEFT JOIN "{schema}"."artist" a ON a.id = t.artist_id '
            f'WHERE t.artist_id IS NOT NULL AND a.id IS NULL',
        "artist_genre.artist_id → artist.id":
            f'SELECT COUNT(*) FROM "{schema}"."artist_genre" ag '
            f'LEFT JOIN "{schema}"."artist" a ON a.id = ag.artist_id '
            f'WHERE ag.artist_id IS NOT NULL AND a.id IS NULL',
        "artist_genre.genre_id → genre.id":
            f'SELECT COUNT(*) FROM "{schema}"."artist_genre" ag '
            f'LEFT JOIN "{schema}"."genre" g ON g.id = ag.genre_id '
            f'WHERE ag.genre_id IS NOT NULL AND g.id IS NULL',
        "specialty_category.category_id → category.id":
            f'SELECT COUNT(*) FROM "{schema}"."specialty_category" sc '
            f'LEFT JOIN "{schema}"."category" c ON c.id = sc.category_id '
            f'WHERE sc.category_id IS NOT NULL AND c.id IS NULL',
        "specialty_category.specialty_id → specialty.id":
            f'SELECT COUNT(*) FROM "{schema}"."specialty_category" sc '
            f'LEFT JOIN "{schema}"."specialty" s ON s.id = sc.specialty_id '
            f'WHERE sc.specialty_id IS NOT NULL AND s.id IS NULL',
        "specialty_ranking.specialty_category_id → specialty_category":
            f'SELECT COUNT(*) FROM "{schema}"."specialty_ranking" sr '
            f'LEFT JOIN "{schema}"."specialty_category" sc2 ON sc2.id = sr.specialty_category_id '
            f'WHERE sr.specialty_category_id IS NOT NULL AND sc2.id IS NULL',
        "specialty_ranking.track_id → track.id":
            f'SELECT COUNT(*) FROM "{schema}"."specialty_ranking" sr '
            f'LEFT JOIN "{schema}"."track" t ON t.id = sr.track_id '
            f'WHERE sr.track_id IS NOT NULL AND t.id IS NULL',
    }

    results = []
    for name, sql in checks.items():
        try:
            c = exec_one(db, sql)[0]
        except Exception as e:
            results.append({"check": name, "error": str(e)})
        else:
            results.append({"check": name, "orphans": int(c)})

    ok = all(r.get("orphans", 0) == 0 for r in results if "error" not in r)
    return {"ok": ok, "schema": schema, "results": results}

# ---------------------------------------------------------------------------
# Minimal real write: ensure Category + Specialty + link
# ---------------------------------------------------------------------------

@specialty_router.post("/specialty/ensure-combo")
def ensure_combo(
    category: str = Query(..., description="e.g. 'Before 1990s' or '1960s'"),
    specialty: str = Query(..., description="e.g. 'latin favorites'"),
    language: str = Query("en", description="two-letter or name; stored as provided"),
    db: Session = Depends(get_db),
):
    """Ensure Category, Specialty(language), and their link exist."""
    category = category.strip()
    specialty = specialty.strip()
    lang = language.strip().lower()

    created = {"category": False, "specialty": False, "link": False}

    # Ensure Category
    row = exec_one(db, """
        INSERT INTO public.category (category_name)
        SELECT :category
        WHERE NOT EXISTS (
            SELECT 1 FROM public.category WHERE category_name = :category
        )
        RETURNING id
    """, category=category)
    if row:
        cat_id = row[0]
        created["category"] = True
    else:
        cat_id = exec_one(db, """
            SELECT id FROM public.category WHERE category_name = :category
        """, category=category)[0]

    # Ensure Specialty (name + language)
    row = exec_one(db, """
        INSERT INTO public.specialty (specialty_name, language)
        SELECT :specialty, :lang
        WHERE NOT EXISTS (
            SELECT 1 FROM public.specialty
            WHERE specialty_name = :specialty AND language = :lang
        )
        RETURNING id
    """, specialty=specialty, lang=lang)
    if row:
        spec_id = row[0]
        created["specialty"] = True
    else:
        spec_id = exec_one(db, """
            SELECT id FROM public.specialty
            WHERE specialty_name = :specialty AND language = :lang
        """, specialty=specialty, lang=lang)[0]

    # Ensure link table
    row = exec_one(db, """
        INSERT INTO public.specialty_category (category_id, specialty_id)
        SELECT :cat_id, :spec_id
        WHERE NOT EXISTS (
            SELECT 1 FROM public.specialty_category
            WHERE category_id = :cat_id AND specialty_id = :spec_id
        )
        RETURNING category_id, specialty_id
    """, cat_id=cat_id, spec_id=spec_id)
    if row:
        created["link"] = True

    db.commit()
    return {
        "ok": True,
        "category": {"name": category, "id": cat_id, "created": created["category"]},
        "specialty": {"name": specialty, "language": lang, "id": spec_id, "created": created["specialty"]},
        "linked": created["link"]
    }

# ---------------------------------------------------------------------------
# Safe write probe (persistent, not TEMP — PgBouncer-friendly)
# ---------------------------------------------------------------------------

@specialty_router.post("/_db-write-probe")
def _db_write_probe(db: Session = Depends(get_db)):
    """Create a throwaway row in a probe table, verify, then delete."""
    run_id = str(uuid.uuid4())
    try:
        db.exec(text("""
            CREATE TABLE IF NOT EXISTS public.__probe (
                id BIGSERIAL PRIMARY KEY,
                run_id UUID NOT NULL,
                note TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        db.exec(text("""
            INSERT INTO public.__probe (run_id, note)
            VALUES (:run_id, 'hello from write probe')
        """), params={"run_id": run_id})
        seen = exec_one(db, """
            SELECT COUNT(*) FROM public.__probe WHERE run_id = :run_id
        """, run_id=run_id)[0]
        db.exec(text("DELETE FROM public.__probe WHERE run_id = :run_id"),
                params={"run_id": run_id})
        db.commit()
        return {"ok": True, "inserted_and_seen": seen, "run_id": run_id}
    except Exception as e:
        db.rollback()
        return {"ok": False, "error": str(e)}

@specialty_router.get("/specialty/list-combos")
def list_combos(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)):
    rows = exec_all(db, """
        SELECT sc.id AS specialty_category_id,
               c.category_name,
               s.specialty_name,
               s.language
        FROM public.specialty_category sc
        JOIN public.category  c ON c.id = sc.category_id
        JOIN public.specialty s ON s.id = sc.specialty_id
        ORDER BY c.category_name, s.specialty_name, s.language
        LIMIT :limit
    """, limit=limit)
    return {"ok": True, "count": len(rows), "rows": [dict(r._mapping) for r in rows]}


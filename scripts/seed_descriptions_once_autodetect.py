#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import create_engine, text

def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)

def main():
    ap = argparse.ArgumentParser(description="One-time seed of decade/genre/decade_genre descriptions.")
    ap.add_argument("--path", default="data/json_files/metadata/music_descriptions_seed_v2.json",
                    help="Path to JSON seed file")
    ap.add_argument("--dsn", default=os.getenv("DATABASE_URL"),
                    help="SQLAlchemy DSN, e.g. postgresql+psycopg2://user:pass@host:5432/dbname")
    ap.add_argument("--schema", default="public", help="Target schema (default: public)")
    ap.add_argument("--dry-run", action="store_true", help="Parse only; do not write")
    ap.add_argument("--echo", action="store_true", help="SQLAlchemy echo SQL")
    args = ap.parse_args()

    if not args.dsn:
        die("Provide --dsn or set $DATABASE_URL")

    seed_path = Path(args.path)
    if not seed_path.exists():
        die(f"Seed file not found: {seed_path}")

    try:
        doc: Dict[str, Any] = json.loads(seed_path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"Failed to parse JSON: {e}")

    decades: List[Dict[str, Any]] = doc.get("decades") or []
    genres:  List[Dict[str, Any]] = doc.get("genres") or []
    combos:  List[Dict[str, Any]] = doc.get("decade_genre") or []

    print(f"Loaded: decades={len(decades)}, genres={len(genres)}, combos={len(combos)}")
    if args.dry_run:
        print("--dry-run set; exiting before DB writes.")
        return

    engine = create_engine(args.dsn, future=True, echo=args.echo)

    def q(tbl: str) -> str:
        # schema-qualify and keep lowercase identifiers (no quotes needed)
        return f"{args.schema}.{tbl}" if args.schema else tbl

    # Ensure conflict targets exist (safe if already present)
    ensure_indexes = [
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_decade_slug ON {q('decade')} (slug);",
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_genre_slug  ON {q('genre')}  (slug);",
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_decade_genre_pair ON {q('decade_genre')} (decade_id, genre_id);",
    ]

    # Upserts
    upsert_decade = text(f"""
        INSERT INTO {q('decade')} (slug, description)
        VALUES (:slug, :description)
        ON CONFLICT (slug) DO UPDATE
        SET description = EXCLUDED.description
    """)
    upsert_genre = text(f"""
        INSERT INTO {q('genre')} (slug, description)
        VALUES (:slug, :description)
        ON CONFLICT (slug) DO UPDATE
        SET description = EXCLUDED.description
    """)

    # Map (decade_slug, genre_slug) -> (decade_id, genre_id) via CTE; upsert description
    upsert_combo = text(f"""
        WITH d AS (SELECT id FROM {q('decade')} WHERE slug = :dslug),
             g AS (SELECT id FROM {q('genre')}  WHERE slug = :gslug)
        INSERT INTO {q('decade_genre')} (decade_id, genre_id, description)
        SELECT d.id, g.id, :description
        FROM d CROSS JOIN g
        ON CONFLICT (decade_id, genre_id) DO UPDATE
        SET description = EXCLUDED.description
    """)

    # Sanity probes (fail early if tables missing)
    sanity = [
        f"SELECT 1 FROM {q('decade')} LIMIT 1;",
        f"SELECT 1 FROM {q('genre')} LIMIT 1;",
        f"SELECT 1 FROM {q('decade_genre')} LIMIT 1;",
    ]

    with engine.begin() as conn:
        # Set search_path to your chosen schema
        conn.exec_driver_sql(f"SET search_path TO {args.schema}, pg_catalog;")

        # verify tables exist
        for s in sanity:
            conn.exec_driver_sql(s)

        # ensure unique indexes
        for sql in ensure_indexes:
            conn.exec_driver_sql(sql)

        # upsert decades
        dec_upd = 0
        for d in decades:
            slug = (d.get("slug") or "").strip()
            if not slug:
                continue
            conn.execute(upsert_decade, {"slug": slug, "description": d.get("description")})
            dec_upd += 1

        # upsert genres
        gen_upd = 0
        for g in genres:
            slug = (g.get("slug") or "").strip()
            if not slug:
                continue
            conn.execute(upsert_genre, {"slug": slug, "description": g.get("description")})
            gen_upd += 1

        # upsert combos
        combo_total = 0
        missing_pairs = []
        for c in combos:
            dslug = (c.get("decade") or "").strip()
            gslug = (c.get("genre") or "").strip()
            if not dslug or not gslug:
                continue
            res = conn.execute(upsert_combo, {"dslug": dslug, "gslug": gslug, "description": c.get("description")})
            if res.rowcount == 0:
                missing_pairs.append({"decade": dslug, "genre": gslug})
            combo_total += 1

    print("✅ Upsert complete.")
    print(f"- decades upserted: {dec_upd}")
    print(f"- genres upserted:  {gen_upd}")
    print(f"- combos attempted: {combo_total}")
    if missing_pairs:
        print(f"- WARNING: {len(missing_pairs)} combos skipped (unknown slugs):")
        for p in missing_pairs:
            print(f"    - {p['decade']} × {p['genre']}")
    else:
        print("- all combos applied")

if __name__ == "__main__":
    main()

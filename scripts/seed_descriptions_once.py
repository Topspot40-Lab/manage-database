#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import create_engine, text

def main():
    ap = argparse.ArgumentParser(description="One-time seed of decade/genre/decade_genre descriptions.")
    ap.add_argument("--path", default="data/json_files/metadata/music_descriptions_seed_v2.json",
                    help="Path to JSON seed file")
    ap.add_argument("--dsn", default=os.getenv("DATABASE_URL"),
                    help="SQLAlchemy DSN, e.g. postgresql+psycopg2://user:pass@host:5432/dbname "
                         "(defaults to $DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true", help="Parse only; do not write")
    args = ap.parse_args()

    if not args.dsn:
        print("ERROR: Provide --dsn or set $DATABASE_URL", file=sys.stderr)
        sys.exit(1)

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: Seed file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        doc: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}", file=sys.stderr)
        sys.exit(1)

    decades: List[Dict[str, Any]] = doc.get("decades") or []
    genres:  List[Dict[str, Any]] = doc.get("genres") or []
    combos:  List[Dict[str, Any]] = doc.get("decade_genre") or []

    print(f"Loaded: {len(decades)} decades, {len(genres)} genres, {len(combos)} decade-genre combos.")
    if args.dry_run:
        print("--dry-run set; exiting before DB writes.")
        return

    engine = create_engine(args.dsn, future=True)

    # SQL (column/table names assumed):
    #   decade(slug TEXT UNIQUE, description TEXT)
    #   genre(slug TEXT UNIQUE, description TEXT)
    #   decade_genre(decade_id INT, genre_id INT, description TEXT, UNIQUE(decade_id, genre_id))
    ensure_indexes = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_decade_slug ON decade (slug);",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_genre_slug  ON genre  (slug);",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_decade_genre_pair ON decade_genre (decade_id, genre_id);",
    ]

    upsert_decade = text("""
        INSERT INTO decade (slug, description)
        VALUES (:slug, :description)
        ON CONFLICT (slug) DO UPDATE
        SET description = EXCLUDED.description
    """)
    upsert_genre = text("""
        INSERT INTO genre (slug, description)
        VALUES (:slug, :description)
        ON CONFLICT (slug) DO UPDATE
        SET description = EXCLUDED.description
    """)

    upsert_combo = text("""
        WITH d AS (SELECT id FROM decade WHERE slug = :dslug),
             g AS (SELECT id FROM genre  WHERE slug = :gslug)
        INSERT INTO decade_genre (decade_id, genre_id, description)
        SELECT d.id, g.id, :description
        FROM d CROSS JOIN g
        ON CONFLICT (decade_id, genre_id) DO UPDATE
        SET description = EXCLUDED.description
    """)

    with engine.begin() as conn:
        # Make sure indexes (conflict targets) exist
        for sql in ensure_indexes:
            conn.execute(text(sql))

        dec_upd = gen_upd = 0
        for d in decades:
            slug = d.get("slug"); descr = d.get("description")
            if not slug: continue
            conn.execute(upsert_decade, {"slug": slug, "description": descr})
            dec_upd += 1

        for g in genres:
            slug = g.get("slug"); descr = g.get("description")
            if not slug: continue
            conn.execute(upsert_genre, {"slug": slug, "description": descr})
            gen_upd += 1

        combo_total = 0
        missing_pairs = []
        for c in combos:
            dslug = c.get("decade"); gslug = c.get("genre"); descr = c.get("description")
            if not dslug or not gslug: continue
            res = conn.execute(upsert_combo, {"dslug": dslug, "gslug": gslug, "description": descr})
            # If either slug didn't exist, the CTE SELECT returns 0 rows; detect that
            if res.rowcount == 0:
                missing_pairs.append({"decade": dslug, "genre": gslug})
            combo_total += 1

    print("✅ Upsert complete.")
    print(f"- decades upserted: {dec_upd}")
    print(f"- genres upserted:  {gen_upd}")
    print(f"- combos attempted: {combo_total}")
    if missing_pairs:
        print(f"- WARNING: {len(missing_pairs)} combos skipped due to missing slugs:")
        for p in missing_pairs:
            print(f"    - {p['decade']} × {p['genre']}")
    else:
        print("- all combos applied")

if __name__ == "__main__":
    main()

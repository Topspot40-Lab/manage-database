-- ============================================================================
-- TopSpot — Schema Update Reference
-- File: 2025-11-08_collection_categories.sql
-- Purpose: Introduce collection categories + seed categories/collections
-- Notes:
--   • Idempotent where possible (IF NOT EXISTS)
--   • Keep this file under version control for future reference/replication
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1) TABLE: collection_category
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS collection_category (
  id         SERIAL PRIMARY KEY,
  name       VARCHAR(100) NOT NULL,
  slug       VARCHAR(100) NOT NULL UNIQUE,
  intro      TEXT,
  sort_order INTEGER DEFAULT 0
);

-- ────────────────────────────────────────────────────────────────────────────
-- 2) COLUMN: collection.category_id  (FK → collection_category.id)
-- ────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'collection' AND column_name = 'category_id'
  ) THEN
    ALTER TABLE collection
      ADD COLUMN category_id INTEGER REFERENCES collection_category(id) ON DELETE SET NULL;
  END IF;
END$$;

-- (Optional) Ensure collection.intro exists (rename/skip if your table already has it)
-- DO $$
-- BEGIN
--   IF NOT EXISTS (
--     SELECT 1 FROM information_schema.columns
--     WHERE table_name = 'collection' AND column_name = 'intro'
--   ) THEN
--     ALTER TABLE collection ADD COLUMN intro TEXT;
--   END IF;
-- END$$;

-- (Optional) Ensure collection.sort_order exists if you want per-collection display ordering
-- DO $$
-- BEGIN
--   IF NOT EXISTS (
--     SELECT 1 FROM information_schema.columns
--     WHERE table_name = 'collection' AND column_name = 'sort_order'
--   ) THEN
--     ALTER TABLE collection ADD COLUMN sort_order INTEGER DEFAULT 0;
--   END IF;
-- END$$;

-- ────────────────────────────────────────────────────────────────────────────
-- 3) SEED: Top-level categories (idempotent)
-- ────────────────────────────────────────────────────────────────────────────
INSERT INTO collection_category (name, slug, sort_order) VALUES
  ('Stage & Screen',  'stage_and_screen',  1),
  ('Classical Music', 'classical_music',   2),
  ('Music Trends',    'music_trends',      3),
  ('Specialty Mixes', 'specialty_mixes',   4),
  ('Music Legends',   'music_legends',     6)
ON CONFLICT (slug) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 4) LINK: Existing collections → categories
-- (Run anytime; safe if already linked)
-- ────────────────────────────────────────────────────────────────────────────

-- Stage & Screen
UPDATE collection
SET category_id = (SELECT id FROM collection_category WHERE slug = 'stage_and_screen')
WHERE slug IN (
  'disney_classics_pre_1988',
  'disney_revival_after_1988',
  'stage_screen_broadway_classics',
  'stage_screen_movie_themes',
  'video_game_themes'
);

-- Classical Music
UPDATE collection
SET category_id = (SELECT id FROM collection_category WHERE slug = 'classical_music')
WHERE slug IN (
  'classical_music_baroque_period_1600_1750',
  'classical_music_classical_period_1750_1820',
  'classical_music_romantic_period_1820_1910'
);

-- Music Trends
UPDATE collection
SET category_id = (SELECT id FROM collection_category WHERE slug = 'music_trends')
WHERE slug IN (
  'power_ballads',
  'disco_favorites',
  'dance_floor_anthems',
  'motown_magic',
  'one_hit_wonders',
  'protest_social_justice'
);

-- Specialty Mixes
UPDATE collection
SET category_id = (SELECT id FROM collection_category WHERE slug = 'specialty_mixes')
WHERE slug IN (
  'country_duets',
  'holiday_favorites',
  'latin_crossovers',
  'novelty_songs',
  'pop_duets'
);

-- ────────────────────────────────────────────────────────────────────────────
-- 5) SEED: “Music Legends” collections (one per genre)
-- Uses `intro`; if you don’t have collection.sort_order, this still works.
-- ────────────────────────────────────────────────────────────────────────────
WITH cat AS (
  SELECT id FROM collection_category WHERE slug = 'music_legends'
)
INSERT INTO collection (name, slug, intro, category_id, sort_order)
VALUES
  ('Legends – Country',        'legends_country',        'Top 40 Country legends across all decades.',         (SELECT id FROM cat), 1),
  ('Legends – Pop',            'legends_pop',            'Top 40 Pop legends across all decades.',             (SELECT id FROM cat), 2),
  ('Legends – Rock',           'legends_rock',           'Top 40 Rock legends across all decades.',            (SELECT id FROM cat), 3),
  ('Legends – TV Themes',      'legends_tv_themes',      'Top 40 TV theme legends across all decades.',        (SELECT id FROM cat), 4),
  ('Legends – RnB Soul',       'legends_rnb_soul',       'Top 40 RnB & Soul legends across all decades.',      (SELECT id FROM cat), 5),
  ('Legends – Latin Global',   'legends_latin_global',   'Top 40 Latin & Global legends across all decades.',  (SELECT id FROM cat), 6),
  ('Legends – Blues Jazz',     'legends_blues_jazz',     'Top 40 Blues & Jazz legends across all decades.',    (SELECT id FROM cat), 7),
  ('Legends – Folk Acoustic',  'legends_folk_acoustic',  'Top 40 Folk & Acoustic legends across all decades.', (SELECT id FROM cat), 8)
ON CONFLICT (slug) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────────
-- 6) QUICK CHECKS
-- ────────────────────────────────────────────────────────────────────────────
-- Verify columns exist
-- SELECT column_name FROM information_schema.columns WHERE table_name='collection' ORDER BY ordinal_position;
-- SELECT column_name FROM information_schema.columns WHERE table_name='collection_category' ORDER BY ordinal_position;

-- Verify grouping
-- SELECT cat.name AS category, c.name AS collection, c.slug, c.sort_order
-- FROM collection c
-- LEFT JOIN collection_category cat ON c.category_id = cat.id
-- ORDER BY cat.sort_order, c.sort_order, c.name;

-- Network catalogue (M2 WP2): stops, lines, ordered line stops, line routes and schedules.
--
-- The tables were created in M1 (`…03_catalogue.sql`); this migration adds what the M2 use
-- cases need: trigram search, keyset-pagination indexes and the invariants the domain value
-- objects guarantee (so that no code path can store something the API would refuse).

-- Trigram operator classes for substring search (`ILIKE '%…%'`) on names.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- --- Stops ------------------------------------------------------------------------------------

-- `GET /stops?q=`:
--   SELECT … FROM stops WHERE name ILIKE $1 ESCAPE '\' AND … ORDER BY created_at DESC, id DESC
-- → Bitmap Index Scan on stops_name_trgm_idx (for patterns of 3+ characters; shorter ones
--   cannot be served by trigrams and scan, which is fine for a bounded catalogue).
CREATE INDEX stops_name_trgm_idx ON stops USING gin (name gin_trgm_ops);

-- Keyset pagination of `GET /stops` (ADR 0010):
--   … WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT $3
-- → Index Scan using stops_created_idx.
CREATE INDEX stops_created_idx ON stops (created_at DESC, id DESC);

-- Features are short tags (the domain allows at most 20 of `[a-z0-9_]{1,40}`).
ALTER TABLE stops
    ADD CONSTRAINT stops_features_count CHECK (cardinality(features) <= 20);

-- --- Lines ------------------------------------------------------------------------------------

-- `GET /lines?q=` matches the code and the name at once:
--   … WHERE (code || ' ' || name) ILIKE $1 ESCAPE '\' …
-- → Bitmap Index Scan on lines_search_trgm_idx (the expression must match exactly).
CREATE INDEX lines_search_trgm_idx ON lines USING gin ((code || ' ' || name) gin_trgm_ops);

-- Keyset pagination of `GET /lines`.
CREATE INDEX lines_created_idx ON lines (created_at DESC, id DESC);

-- Codes are stored upper-case (`LineCode`), so uniqueness is case-insensitive in effect.
ALTER TABLE lines
    ADD CONSTRAINT lines_code_format CHECK (code ~ '^[A-Z0-9-]{1,20}$');
-- Colours are stored upper-case (`HexColor`); `lines_color_hex` (M1) accepts both cases.
ALTER TABLE lines
    ADD CONSTRAINT lines_color_upper CHECK (color ~ '^#[0-9A-F]{6}$');
-- A route is a real itinerary: at least two points (the domain allows at most 10 000).
ALTER TABLE lines
    ADD CONSTRAINT lines_route_points CHECK (ST_NPoints(route::geometry) BETWEEN 2 AND 10000);

-- --- Line stops -------------------------------------------------------------------------------

-- Positions are 0-based and contiguous (maintained by the repository under a lock of the line
-- row); a line has at most 200 stops.
ALTER TABLE line_stops
    ADD CONSTRAINT line_stops_position_max CHECK (position < 200);
-- Segment times are bounded to a day (the domain refuses more).
ALTER TABLE line_stops
    ADD CONSTRAINT line_stops_time_max CHECK (time_from_previous_s <= 86400);
-- The first stop has no previous stop, hence no segment metrics.
ALTER TABLE line_stops
    ADD CONSTRAINT line_stops_first_has_no_segment CHECK (
        position > 0 OR (distance_from_previous_m IS NULL AND time_from_previous_s IS NULL)
    );

-- --- Schedules --------------------------------------------------------------------------------

-- `GET /lines/{id}/schedules`:
--   SELECT … FROM schedules WHERE line_id = $1 ORDER BY day_of_week, start_time, id
-- → Index Scan using schedules_line_day_idx (no sort; `id` orders inactive schedules that
--   start at the same time). Also serves the `ON DELETE CASCADE` from `lines`: the GiST index
--   of `schedules_no_overlap` only covers active rows.
CREATE INDEX schedules_line_day_idx ON schedules (line_id, day_of_week, start_time, id);

-- Extensions and shared helpers.
--
-- Requires PostgreSQL 18+ (uuidv7()) with PostGIS.

CREATE EXTENSION IF NOT EXISTS postgis;
-- Lets GiST exclusion constraints mix equality on scalar columns with range overlap.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Maintains updated_at. The application may set it explicitly (injected clock); when an UPDATE
-- leaves it unchanged, the transaction timestamp is used.
CREATE FUNCTION set_updated_at() RETURNS trigger
    LANGUAGE plpgsql AS
$$
BEGIN
    IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
        NEW.updated_at := now();
    END IF;
    RETURN NEW;
END
$$;

-- Time-of-day range, used to forbid overlapping schedules.
CREATE TYPE timerange AS RANGE (subtype = time);

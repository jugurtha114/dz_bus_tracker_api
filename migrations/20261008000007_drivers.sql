-- Driver programme (M2 WP3): applications, the driver state machine and its history.
--
-- The `drivers` table was created in M1 (`…03_catalogue.sql`); this migration adds the status
-- history, the indexes the M2 use cases need and the invariants the domain guarantees.
--
-- State machine (`dz_domain::driver`): pending → approved | rejected; approved → suspended;
-- suspended → approved (reinstate); rejected → pending (reapply); a document change on an
-- approved profile sends it back to pending. Every status change is recorded below, in the
-- transaction of the change.

-- --- Status history ---------------------------------------------------------------------------

CREATE TABLE driver_status_log (
    id          uuid        PRIMARY KEY,
    -- Driver profiles are never deleted (suspension replaces deletion, legacy L-02).
    driver_id   uuid        NOT NULL REFERENCES drivers (id),
    -- NULL for the application itself (no previous status).
    from_status text,
    to_status   text        NOT NULL,
    reason      text        NOT NULL DEFAULT '',
    -- The user who caused the change (the driver for self-service, the reviewer otherwise);
    -- NULL = the system, or an account deleted since.
    changed_by  uuid        REFERENCES users (id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL,
    CONSTRAINT driver_status_log_from_check CHECK (
        from_status IN ('pending', 'approved', 'rejected', 'suspended')
    ),
    CONSTRAINT driver_status_log_to_check CHECK (
        to_status IN ('pending', 'approved', 'rejected', 'suspended')
    ),
    -- Only real changes are logged (a document change that keeps the status is not one).
    CONSTRAINT driver_status_log_changes_status CHECK (from_status IS DISTINCT FROM to_status),
    CONSTRAINT driver_status_log_reason_length CHECK (char_length(reason) <= 1000),
    -- Rejections and suspensions are always explained to the driver.
    CONSTRAINT driver_status_log_reason_required CHECK (
        to_status NOT IN ('rejected', 'suspended') OR char_length(btrim(reason)) > 0
    )
);

-- `GET /drivers/{id}/status-history` (keyset pagination, newest first):
--   SELECT … FROM driver_status_log WHERE driver_id = $1 AND (created_at, id) < ($2, $3)
--   ORDER BY created_at DESC, id DESC LIMIT $4
-- → Index Scan using driver_status_log_driver_idx (no sort).
CREATE INDEX driver_status_log_driver_idx
    ON driver_status_log (driver_id, created_at DESC, id DESC);
-- `ON DELETE SET NULL` from `users` finds the entries of the deleted account by author.
CREATE INDEX driver_status_log_changed_by_idx ON driver_status_log (changed_by)
    WHERE changed_by IS NOT NULL;

-- Append-only, like `audit_log`. The only update allowed is the one performed by
-- `ON DELETE SET NULL` when the author's account is deleted: `changed_by` becomes NULL and
-- nothing else changes.
CREATE FUNCTION driver_status_log_reject_mutation() RETURNS trigger
    LANGUAGE plpgsql AS
$$
BEGIN
    IF TG_OP = 'UPDATE'
        AND OLD.changed_by IS NOT NULL AND NEW.changed_by IS NULL
        AND (NEW.id, NEW.driver_id, NEW.from_status, NEW.to_status, NEW.reason, NEW.created_at)
            IS NOT DISTINCT FROM
            (OLD.id, OLD.driver_id, OLD.from_status, OLD.to_status, OLD.reason, OLD.created_at)
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'driver_status_log is append-only' USING ERRCODE = 'insufficient_privilege';
END
$$;

CREATE TRIGGER driver_status_log_no_update_or_delete
    BEFORE UPDATE OR DELETE ON driver_status_log
    FOR EACH ROW EXECUTE FUNCTION driver_status_log_reject_mutation();

CREATE TRIGGER driver_status_log_no_truncate
    BEFORE TRUNCATE ON driver_status_log
    FOR EACH STATEMENT EXECUTE FUNCTION driver_status_log_reject_mutation();

-- --- Drivers ----------------------------------------------------------------------------------

-- Keyset pagination of `GET /drivers` without a status filter (ADR 0010):
--   … WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT $3
-- → Index Scan using drivers_created_idx. With `?status=`, `drivers_status_created_idx` (M1)
--   serves the same order.
CREATE INDEX drivers_created_idx ON drivers (created_at DESC, id DESC);

-- Licence numbers are stored upper-case (`LicenseNumber`), so uniqueness is case-insensitive
-- in effect; `drivers_license_length` (M1) only bounded the length.
ALTER TABLE drivers
    ADD CONSTRAINT drivers_license_format CHECK (driver_license_number ~ '^[A-Z0-9-]{1,20}$');

-- Only approved drivers can be available for service: every transition out of `approved`
-- clears the flag, and `PUT /drivers/me/availability` refuses other statuses.
ALTER TABLE drivers
    ALTER COLUMN is_available SET DEFAULT false,
    ADD CONSTRAINT drivers_available_only_when_approved CHECK (
        status = 'approved' OR NOT is_available
    );

-- Bus operations take a suspended driver's buses off duty (L-25):
--   UPDATE buses SET status = 'inactive' … WHERE driver_id = $1 AND status <> 'inactive'
-- → Index Scan using buses_driver_idx (M1).

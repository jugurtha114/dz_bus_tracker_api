-- Durable job queue (replaces Celery + Redis broker) and cron de-duplication.
--
-- Workers claim jobs with FOR UPDATE SKIP LOCKED and hold a lease (locked_until); a job whose
-- lease expired is considered abandoned and can be claimed again.

CREATE TABLE jobs (
    id           uuid        PRIMARY KEY,
    kind         text        NOT NULL,
    payload      jsonb       NOT NULL,
    status       text        NOT NULL DEFAULT 'queued',
    attempts     smallint    NOT NULL DEFAULT 0,
    max_attempts smallint    NOT NULL DEFAULT 5,
    run_at       timestamptz NOT NULL,
    dedup_key    text,
    locked_by    text,
    locked_until timestamptz,
    last_error   text,
    created_at   timestamptz NOT NULL,
    updated_at   timestamptz NOT NULL,
    finished_at  timestamptz,
    CONSTRAINT jobs_kind_length CHECK (char_length(kind) BETWEEN 1 AND 100),
    CONSTRAINT jobs_status_check CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    CONSTRAINT jobs_attempts_range CHECK (attempts >= 0 AND max_attempts BETWEEN 1 AND 100),
    CONSTRAINT jobs_dedup_key_length CHECK (char_length(dedup_key) <= 300),
    CONSTRAINT jobs_lease_consistent CHECK ((status = 'running') = (locked_until IS NOT NULL))
);

-- Next ready job.
CREATE INDEX jobs_ready_idx ON jobs (run_at) WHERE status = 'queued';
-- Abandoned leases.
CREATE INDEX jobs_lease_idx ON jobs (locked_until) WHERE status = 'running';
-- At most one pending job per de-duplication key.
CREATE UNIQUE INDEX jobs_dedup_pending_idx ON jobs (dedup_key)
    WHERE dedup_key IS NOT NULL AND status IN ('queued', 'running');
-- Retention purge.
CREATE INDEX jobs_finished_idx ON jobs (finished_at) WHERE status IN ('succeeded', 'failed');

-- Wake idle workers immediately instead of waiting for the next poll.
CREATE FUNCTION jobs_notify() RETURNS trigger
    LANGUAGE plpgsql AS
$$
BEGIN
    PERFORM pg_notify('dz_jobs', NEW.kind);
    RETURN NULL;
END
$$;

CREATE TRIGGER jobs_notify_insert
    AFTER INSERT ON jobs
    FOR EACH ROW EXECUTE FUNCTION jobs_notify();

-- One row per (cron job, scheduled slot): the replica whose INSERT succeeds runs that slot.
CREATE TABLE cron_runs (
    name       text        NOT NULL,
    slot       timestamptz NOT NULL,
    claimed_by text        NOT NULL,
    claimed_at timestamptz NOT NULL,
    PRIMARY KEY (name, slot)
);

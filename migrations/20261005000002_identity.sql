-- Users, profiles, sessions, password resets, API keys and the audit log.

CREATE TABLE users (
    id                    uuid        PRIMARY KEY DEFAULT uuidv7(),
    email                 text        NOT NULL,
    -- NULL = no usable password. Argon2id PHC strings, or Django PBKDF2 hashes imported from the
    -- legacy system (upgraded on the next successful login).
    password_hash         text,
    role                  text        NOT NULL DEFAULT 'passenger',
    first_name            text        NOT NULL DEFAULT '',
    last_name             text        NOT NULL DEFAULT '',
    phone_number          text,
    is_active             boolean     NOT NULL DEFAULT true,
    email_verified_at     timestamptz,
    failed_login_attempts integer     NOT NULL DEFAULT 0,
    locked_until          timestamptz,
    last_login_at         timestamptz,
    password_changed_at   timestamptz,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_key UNIQUE (email),
    -- One account per phone number (SMS notifications and future OTP sign-in).
    CONSTRAINT users_phone_number_key UNIQUE (phone_number),
    CONSTRAINT users_email_normalized CHECK (
        email = lower(btrim(email)) AND char_length(email) BETWEEN 3 AND 254
        AND position('@' IN email) > 1
    ),
    CONSTRAINT users_role_check CHECK (role IN ('admin', 'driver', 'passenger')),
    CONSTRAINT users_names_length CHECK (
        char_length(first_name) <= 150 AND char_length(last_name) <= 150
    ),
    CONSTRAINT users_phone_e164 CHECK (phone_number ~ '^\+213[567][0-9]{8}$'),
    CONSTRAINT users_failed_attempts_nonnegative CHECK (failed_login_attempts >= 0)
);

-- Admin listing: keyset pagination, optionally filtered by role.
CREATE INDEX users_created_idx ON users (created_at DESC, id DESC);
CREATE INDEX users_role_created_idx ON users (role, created_at DESC, id DESC);
-- Admin search by e-mail prefix (LIKE 'abc%') regardless of the database collation.
CREATE INDEX users_email_prefix_idx ON users (email text_pattern_ops);

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE profiles (
    user_id                     uuid        PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    avatar_key                  text,
    bio                         text        NOT NULL DEFAULT '',
    language                    text        NOT NULL DEFAULT 'fr',
    push_notifications_enabled  boolean     NOT NULL DEFAULT true,
    email_notifications_enabled boolean     NOT NULL DEFAULT true,
    sms_notifications_enabled   boolean     NOT NULL DEFAULT false,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT profiles_language_check CHECK (language IN ('fr', 'ar', 'en')),
    CONSTRAINT profiles_bio_length CHECK (char_length(bio) <= 1000),
    CONSTRAINT profiles_avatar_key_length CHECK (char_length(avatar_key) <= 512)
);

CREATE TRIGGER profiles_set_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- A session is a refresh-token family: every rotation stays in the same session, so reuse of a
-- spent token can revoke the whole family.
CREATE TABLE auth_sessions (
    id             uuid        PRIMARY KEY,
    user_id        uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at     timestamptz NOT NULL,
    last_used_at   timestamptz NOT NULL,
    -- Absolute end of the session regardless of activity.
    expires_at     timestamptz NOT NULL,
    revoked_at     timestamptz,
    revoked_reason text,
    user_agent     text,
    ip             inet,
    CONSTRAINT auth_sessions_reason_check CHECK (revoked_reason IN (
        'logout', 'password_changed', 'password_reset', 'refresh_token_reuse', 'admin_action',
        'user_request'
    )),
    CONSTRAINT auth_sessions_revocation_consistent CHECK (
        (revoked_at IS NULL) = (revoked_reason IS NULL)
    ),
    CONSTRAINT auth_sessions_user_agent_length CHECK (char_length(user_agent) <= 255),
    CONSTRAINT auth_sessions_lifetime CHECK (expires_at > created_at)
);

CREATE INDEX auth_sessions_active_user_idx ON auth_sessions (user_id) WHERE revoked_at IS NULL;
CREATE INDEX auth_sessions_expires_idx ON auth_sessions (expires_at);

-- Only SHA-256 hashes of refresh tokens are stored.
CREATE TABLE refresh_tokens (
    token_hash bytea       PRIMARY KEY,
    session_id uuid        NOT NULL REFERENCES auth_sessions (id) ON DELETE CASCADE,
    issued_at  timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    CONSTRAINT refresh_tokens_hash_length CHECK (octet_length(token_hash) = 32)
);

CREATE INDEX refresh_tokens_session_idx ON refresh_tokens (session_id);
CREATE INDEX refresh_tokens_expires_idx ON refresh_tokens (expires_at);

CREATE TABLE password_reset_tokens (
    token_hash bytea       PRIMARY KEY,
    user_id    uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    used_at    timestamptz,
    CONSTRAINT password_reset_tokens_hash_length CHECK (octet_length(token_hash) = 32)
);

CREATE INDEX password_reset_tokens_unused_idx
    ON password_reset_tokens (user_id) WHERE used_at IS NULL;
CREATE INDEX password_reset_tokens_expires_idx ON password_reset_tokens (expires_at);

-- Machine-to-machine credentials ("service" role). The public prefix identifies the key; only a
-- SHA-256 hash of the full secret is stored.
CREATE TABLE api_keys (
    id           uuid        PRIMARY KEY,
    name         text        NOT NULL,
    prefix       text        NOT NULL,
    secret_hash  bytea       NOT NULL,
    scopes       text[]      NOT NULL,
    created_by   uuid        REFERENCES users (id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL,
    expires_at   timestamptz,
    last_used_at timestamptz,
    revoked_at   timestamptz,
    CONSTRAINT api_keys_prefix_key UNIQUE (prefix),
    CONSTRAINT api_keys_prefix_format CHECK (prefix ~ '^dzk_[0-9a-f]{16}$'),
    CONSTRAINT api_keys_name_length CHECK (char_length(name) BETWEEN 1 AND 100),
    CONSTRAINT api_keys_secret_hash_length CHECK (octet_length(secret_hash) = 32),
    CONSTRAINT api_keys_scopes_nonempty CHECK (cardinality(scopes) > 0)
);

CREATE INDEX api_keys_created_idx ON api_keys (created_at DESC, id DESC);

-- Append-only record of administrative actions.
CREATE TABLE audit_log (
    id            uuid        PRIMARY KEY,
    occurred_at   timestamptz NOT NULL,
    actor_type    text        NOT NULL,
    actor_id      uuid,
    action        text        NOT NULL,
    resource_type text        NOT NULL,
    resource_id   text,
    details       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ip            inet,
    request_id    text,
    CONSTRAINT audit_log_actor_type_check CHECK (actor_type IN ('user', 'service', 'system')),
    CONSTRAINT audit_log_actor_consistent CHECK ((actor_type = 'system') = (actor_id IS NULL)),
    CONSTRAINT audit_log_action_length CHECK (char_length(action) BETWEEN 1 AND 100),
    CONSTRAINT audit_log_resource_type_length CHECK (char_length(resource_type) BETWEEN 1 AND 100),
    CONSTRAINT audit_log_resource_id_length CHECK (char_length(resource_id) <= 100),
    CONSTRAINT audit_log_request_id_length CHECK (char_length(request_id) <= 100),
    CONSTRAINT audit_log_details_object CHECK (jsonb_typeof(details) = 'object')
);

CREATE INDEX audit_log_occurred_idx ON audit_log (occurred_at DESC, id DESC);
CREATE INDEX audit_log_resource_idx ON audit_log (resource_type, resource_id, occurred_at DESC);
CREATE INDEX audit_log_actor_idx ON audit_log (actor_id, occurred_at DESC)
    WHERE actor_id IS NOT NULL;

CREATE FUNCTION audit_log_reject_mutation() RETURNS trigger
    LANGUAGE plpgsql AS
$$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'insufficient_privilege';
END
$$;

CREATE TRIGGER audit_log_no_update_or_delete
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();

CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_reject_mutation();

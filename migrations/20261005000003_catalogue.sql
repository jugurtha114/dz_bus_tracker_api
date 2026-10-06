-- Core network and fleet schema: drivers, buses, stops, lines, line_stops, schedules.
-- Business logic for these tables arrives in milestone M2; constraints are enforced here so
-- that no code path can bypass them (legacy defects L-22, L-23, L-49).

CREATE TABLE drivers (
    id                       uuid        PRIMARY KEY DEFAULT uuidv7(),
    user_id                  uuid        NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    phone_number             text        NOT NULL,
    id_card_number           text        NOT NULL,
    -- Object-storage keys of private documents (never public URLs).
    id_card_photo_key        text        NOT NULL,
    driver_license_number    text        NOT NULL,
    driver_license_photo_key text        NOT NULL,
    status                   text        NOT NULL DEFAULT 'pending',
    status_reason            text        NOT NULL DEFAULT '',
    status_changed_at        timestamptz NOT NULL DEFAULT now(),
    years_of_experience      smallint    NOT NULL DEFAULT 0,
    is_available             boolean     NOT NULL DEFAULT true,
    -- Average rating = rating_sum / rating_count, maintained atomically.
    rating_sum               integer     NOT NULL DEFAULT 0,
    rating_count             integer     NOT NULL DEFAULT 0,
    created_at               timestamptz NOT NULL DEFAULT now(),
    updated_at               timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT drivers_user_key UNIQUE (user_id),
    CONSTRAINT drivers_id_card_number_key UNIQUE (id_card_number),
    CONSTRAINT drivers_driver_license_number_key UNIQUE (driver_license_number),
    CONSTRAINT drivers_phone_e164 CHECK (phone_number ~ '^\+213[567][0-9]{8}$'),
    CONSTRAINT drivers_id_card_format CHECK (id_card_number ~ '^[0-9]{18}$'),
    CONSTRAINT drivers_license_length CHECK (char_length(driver_license_number) BETWEEN 1 AND 20),
    CONSTRAINT drivers_photo_keys_length CHECK (
        char_length(id_card_photo_key) BETWEEN 1 AND 512
        AND char_length(driver_license_photo_key) BETWEEN 1 AND 512
    ),
    CONSTRAINT drivers_status_check CHECK (
        status IN ('pending', 'approved', 'rejected', 'suspended')
    ),
    CONSTRAINT drivers_status_reason_length CHECK (char_length(status_reason) <= 1000),
    CONSTRAINT drivers_experience_range CHECK (years_of_experience BETWEEN 0 AND 60),
    CONSTRAINT drivers_rating_consistent CHECK (
        rating_count >= 0 AND rating_sum BETWEEN rating_count AND rating_count * 5
    )
);

CREATE INDEX drivers_status_created_idx ON drivers (status, created_at DESC, id DESC);

CREATE TRIGGER drivers_set_updated_at
    BEFORE UPDATE ON drivers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE buses (
    id                 uuid        PRIMARY KEY DEFAULT uuidv7(),
    license_plate      text        NOT NULL,
    driver_id          uuid        NOT NULL REFERENCES drivers (id) ON DELETE RESTRICT,
    model              text        NOT NULL,
    manufacturer       text        NOT NULL,
    year               smallint    NOT NULL,
    capacity           smallint    NOT NULL,
    -- Fallback speed for ETAs when neither live nor historical data is usable.
    average_speed_kmh  real        NOT NULL DEFAULT 30,
    bus_type           text        NOT NULL DEFAULT 'city_bus',
    is_air_conditioned boolean     NOT NULL DEFAULT false,
    photo_key          text,
    features           text[]      NOT NULL DEFAULT '{}',
    description        text        NOT NULL DEFAULT '',
    -- Operational state, controlled by administrators.
    status             text        NOT NULL DEFAULT 'active',
    approval_status    text        NOT NULL DEFAULT 'pending',
    approval_reason    text        NOT NULL DEFAULT '',
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT buses_license_plate_key UNIQUE (license_plate),
    CONSTRAINT buses_license_plate_format CHECK (license_plate ~ '^[0-9]{1,5}-[0-9]{3}-[0-9]{2}$'),
    CONSTRAINT buses_model_length CHECK (char_length(model) BETWEEN 1 AND 100),
    CONSTRAINT buses_manufacturer_length CHECK (char_length(manufacturer) BETWEEN 1 AND 100),
    CONSTRAINT buses_year_range CHECK (year BETWEEN 1950 AND 2100),
    CONSTRAINT buses_capacity_range CHECK (capacity BETWEEN 1 AND 300),
    CONSTRAINT buses_average_speed_range CHECK (average_speed_kmh > 0 AND average_speed_kmh <= 120),
    CONSTRAINT buses_type_check CHECK (
        bus_type IN ('microbus', 'city_bus', 'articulated', 'minibus')
    ),
    CONSTRAINT buses_photo_key_length CHECK (char_length(photo_key) <= 512),
    CONSTRAINT buses_description_length CHECK (char_length(description) <= 2000),
    CONSTRAINT buses_status_check CHECK (status IN ('active', 'inactive', 'maintenance')),
    CONSTRAINT buses_approval_status_check CHECK (
        approval_status IN ('pending', 'approved', 'rejected')
    ),
    CONSTRAINT buses_approval_reason_length CHECK (char_length(approval_reason) <= 1000)
);

CREATE INDEX buses_driver_idx ON buses (driver_id);
CREATE INDEX buses_created_idx ON buses (created_at DESC, id DESC);

CREATE TRIGGER buses_set_updated_at
    BEFORE UPDATE ON buses
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE stops (
    id          uuid                   PRIMARY KEY DEFAULT uuidv7(),
    name        text                   NOT NULL,
    location    geography(Point, 4326) NOT NULL,
    address     text                   NOT NULL DEFAULT '',
    wilaya      text                   NOT NULL DEFAULT '',
    commune     text                   NOT NULL DEFAULT '',
    is_active   boolean                NOT NULL DEFAULT true,
    description text                   NOT NULL DEFAULT '',
    features    text[]                 NOT NULL DEFAULT '{}',
    photo_key   text,
    created_at  timestamptz            NOT NULL DEFAULT now(),
    updated_at  timestamptz            NOT NULL DEFAULT now(),
    CONSTRAINT stops_name_length CHECK (char_length(name) BETWEEN 1 AND 100),
    CONSTRAINT stops_address_length CHECK (char_length(address) <= 255),
    CONSTRAINT stops_area_length CHECK (char_length(wilaya) <= 100 AND char_length(commune) <= 100),
    CONSTRAINT stops_description_length CHECK (char_length(description) <= 2000),
    CONSTRAINT stops_photo_key_length CHECK (char_length(photo_key) <= 512)
);

-- Proximity searches (ST_DWithin) and KNN ordering (<->).
CREATE INDEX stops_location_gix ON stops USING gist (location);

CREATE TRIGGER stops_set_updated_at
    BEFORE UPDATE ON stops
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE lines (
    id                uuid                        PRIMARY KEY DEFAULT uuidv7(),
    code              text                        NOT NULL,
    name              text                        NOT NULL,
    description       text                        NOT NULL DEFAULT '',
    is_active         boolean                     NOT NULL DEFAULT true,
    color             text                        NOT NULL DEFAULT '#000000',
    frequency_minutes smallint,
    fare_dza          integer,
    -- Geometry of the itinerary (replaces the legacy route segments).
    route             geography(LineString, 4326),
    created_at        timestamptz                 NOT NULL DEFAULT now(),
    updated_at        timestamptz                 NOT NULL DEFAULT now(),
    CONSTRAINT lines_code_key UNIQUE (code),
    CONSTRAINT lines_code_length CHECK (char_length(code) BETWEEN 1 AND 20),
    CONSTRAINT lines_name_length CHECK (char_length(name) BETWEEN 1 AND 100),
    CONSTRAINT lines_description_length CHECK (char_length(description) <= 2000),
    CONSTRAINT lines_color_hex CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT lines_frequency_range CHECK (frequency_minutes BETWEEN 1 AND 1440),
    CONSTRAINT lines_fare_nonnegative CHECK (fare_dza >= 0)
);

-- Route deviation checks and map queries.
CREATE INDEX lines_route_gix ON lines USING gist (route);

CREATE TRIGGER lines_set_updated_at
    BEFORE UPDATE ON lines
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE line_stops (
    line_id                  uuid     NOT NULL REFERENCES lines (id) ON DELETE CASCADE,
    stop_id                  uuid     NOT NULL REFERENCES stops (id) ON DELETE RESTRICT,
    position                 smallint NOT NULL,
    distance_from_previous_m real,
    time_from_previous_s     integer,
    PRIMARY KEY (line_id, stop_id),
    -- Deferrable so that stops can be re-ordered inside one transaction (legacy L-22).
    CONSTRAINT line_stops_position_key UNIQUE (line_id, position) DEFERRABLE INITIALLY IMMEDIATE,
    CONSTRAINT line_stops_position_nonnegative CHECK (position >= 0),
    CONSTRAINT line_stops_distance_nonnegative CHECK (distance_from_previous_m >= 0),
    CONSTRAINT line_stops_time_nonnegative CHECK (time_from_previous_s >= 0)
);

-- Lines through a stop (journey planning, stop details).
CREATE INDEX line_stops_stop_idx ON line_stops (stop_id);

CREATE TABLE schedules (
    id                uuid        PRIMARY KEY DEFAULT uuidv7(),
    line_id           uuid        NOT NULL REFERENCES lines (id) ON DELETE CASCADE,
    -- ISO 8601: 1 = Monday … 7 = Sunday (= EXTRACT(isodow FROM …)).
    day_of_week       smallint    NOT NULL,
    start_time        time        NOT NULL,
    end_time          time        NOT NULL,
    frequency_minutes smallint    NOT NULL,
    is_active         boolean     NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT schedules_day_range CHECK (day_of_week BETWEEN 1 AND 7),
    CONSTRAINT schedules_time_order CHECK (end_time > start_time),
    CONSTRAINT schedules_frequency_range CHECK (frequency_minutes BETWEEN 1 AND 1440),
    -- Active schedules of a line may not overlap on the same day (legacy L-23).
    CONSTRAINT schedules_no_overlap EXCLUDE USING gist (
        line_id WITH =,
        day_of_week WITH =,
        timerange(start_time, end_time) WITH &&
    ) WHERE (is_active)
);

CREATE TRIGGER schedules_set_updated_at
    BEFORE UPDATE ON schedules
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

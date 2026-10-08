//! Network catalogue: stops, lines, ordered line stops, line routes and schedules.
//!
//! Locking: every write to the stop list of a line first locks the line row (`UPDATE lines`),
//! so writes to one line are serialised, then takes `FOR SHARE` locks on the stops it links
//! (so that a concurrent move of a stop waits and recomputes the distances it affects). A stop
//! move locks the lines serving the stop before the stop itself: both orders agree, so they
//! cannot deadlock. Once it holds the stop row, the move reads the lines serving the stop
//! again: one that gained the stop meanwhile (its writer committed while the move waited, or
//! before the move locked the stop) is not locked, and taking its lock now would invert the
//! order, so the move starts over and locks it first. It then recomputes the distances of
//! every line serving the stop, all locked. Positions are rewritten with
//! `line_stops_position_key` deferred to the commit, so intermediate duplicates inside the
//! transaction are allowed (legacy L-22).

use std::collections::HashSet;

use async_trait::async_trait;
use chrono::{DateTime, NaiveTime, Timelike, Utc};
use dz_app::network::ports::{
    LineFilter, LinePatch, LineRepository, NearbyStop, NewLine, NewSchedule, NewStop,
    ScheduleRepository, SchedulePatch, StopFilter, StopPatch, StopRepository,
};
use dz_app::pagination::{Cursor, Page, PageRequest};
use dz_app::ports::{ClaimedUpload, WriteEffects};
use dz_app::{AppError, AppResult};
use dz_domain::geo::{GeoPoint, LineGeometry};
use dz_domain::ids::{LineId, ScheduleId, StopId};
use dz_domain::network::{
    Fare, FeatureTags, Frequency, HexColor, Line, LineCode, LineName, LineStop, Schedule, Stop,
    StopName, StopSequence, StopSequenceEntry, TimeOfDay, TimeWindow, Weekday, insert_position,
};
use dz_domain::{ConflictKind, Violation};
use sqlx::{PgExecutor, Postgres, Transaction};
use uuid::Uuid;

use super::{PgStore, db_error, effects, like_contains, uploads, violated_constraint};

// --- Rows ----------------------------------------------------------------------------------------

fn corrupt(what: &str) -> AppError {
    AppError::Internal(anyhow::anyhow!("invalid {what} in database"))
}

struct StopRow {
    id: Uuid,
    name: String,
    lat: f64,
    lng: f64,
    address: String,
    wilaya: String,
    commune: String,
    description: String,
    features: Vec<String>,
    is_active: bool,
    photo_key: Option<String>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl StopRow {
    fn into_stop(self) -> Stop {
        Stop {
            id: StopId::from_uuid(self.id),
            name: StopName::from_trusted(self.name),
            location: GeoPoint::from_trusted(self.lat, self.lng),
            address: self.address,
            wilaya: self.wilaya,
            commune: self.commune,
            description: self.description,
            features: FeatureTags::from_trusted(self.features),
            is_active: self.is_active,
            photo_key: self.photo_key,
            created_at: self.created_at,
            updated_at: self.updated_at,
        }
    }
}

struct NearbyRow {
    id: Uuid,
    name: String,
    lat: f64,
    lng: f64,
    address: String,
    wilaya: String,
    commune: String,
    description: String,
    features: Vec<String>,
    is_active: bool,
    photo_key: Option<String>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
    distance_m: f64,
}

struct LineRow {
    id: Uuid,
    code: String,
    name: String,
    description: String,
    color: String,
    frequency_minutes: Option<i16>,
    fare_dza: Option<i32>,
    is_active: bool,
    has_route: bool,
    stops_count: i64,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl LineRow {
    fn into_line(self) -> AppResult<Line> {
        let frequency_minutes = self
            .frequency_minutes
            .map(|f| Frequency::parse(i64::from(f)).map_err(|_| corrupt("line frequency")))
            .transpose()?;
        let fare_dza = self
            .fare_dza
            .map(|f| Fare::parse(i64::from(f)).map_err(|_| corrupt("line fare")))
            .transpose()?;
        Ok(Line {
            id: LineId::from_uuid(self.id),
            code: LineCode::from_trusted(self.code),
            name: LineName::from_trusted(self.name),
            description: self.description,
            color: HexColor::from_trusted(self.color),
            frequency_minutes,
            fare_dza,
            is_active: self.is_active,
            has_route: self.has_route,
            stops_count: u32::try_from(self.stops_count).map_err(|_| corrupt("stop count"))?,
            created_at: self.created_at,
            updated_at: self.updated_at,
        })
    }
}

struct LineStopRow {
    position: i16,
    distance_from_previous_m: Option<f32>,
    time_from_previous_s: Option<i32>,
    id: Uuid,
    name: String,
    lat: f64,
    lng: f64,
    address: String,
    wilaya: String,
    commune: String,
    description: String,
    features: Vec<String>,
    is_active: bool,
    photo_key: Option<String>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl LineStopRow {
    fn into_line_stop(self) -> AppResult<LineStop> {
        let stop = StopRow {
            id: self.id,
            name: self.name,
            lat: self.lat,
            lng: self.lng,
            address: self.address,
            wilaya: self.wilaya,
            commune: self.commune,
            description: self.description,
            features: self.features,
            is_active: self.is_active,
            photo_key: self.photo_key,
            created_at: self.created_at,
            updated_at: self.updated_at,
        };
        Ok(LineStop {
            position: u16::try_from(self.position).map_err(|_| corrupt("stop position"))?,
            stop: stop.into_stop(),
            distance_from_previous_m: self.distance_from_previous_m.map(f64::from),
            time_from_previous_s: self
                .time_from_previous_s
                .map(|t| u32::try_from(t).map_err(|_| corrupt("segment time")))
                .transpose()?,
        })
    }
}

struct ScheduleRow {
    id: Uuid,
    line_id: Uuid,
    day_of_week: i16,
    start_time: NaiveTime,
    end_time: NaiveTime,
    frequency_minutes: i16,
    is_active: bool,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

/// Minute precision: seconds of imported legacy times are dropped.
fn time_of_day(t: NaiveTime) -> AppResult<TimeOfDay> {
    let minutes = u16::try_from(t.hour() * 60 + t.minute()).map_err(|_| corrupt("time"))?;
    TimeOfDay::from_minutes(minutes).ok_or_else(|| corrupt("time"))
}

fn naive_time(t: TimeOfDay) -> NaiveTime {
    NaiveTime::from_hms_opt(u32::from(t.hour()), u32::from(t.minute()), 0).unwrap_or_default()
}

impl ScheduleRow {
    fn into_schedule(self) -> AppResult<Schedule> {
        let window = TimeWindow::new(time_of_day(self.start_time)?, time_of_day(self.end_time)?)
            .map_err(|_| corrupt("schedule window"))?;
        Ok(Schedule {
            id: ScheduleId::from_uuid(self.id),
            line_id: LineId::from_uuid(self.line_id),
            day: Weekday::parse(i64::from(self.day_of_week)).map_err(|_| corrupt("weekday"))?,
            window,
            frequency: Frequency::parse(i64::from(self.frequency_minutes))
                .map_err(|_| corrupt("schedule frequency"))?,
            is_active: self.is_active,
            created_at: self.created_at,
            updated_at: self.updated_at,
        })
    }
}

fn smallint(value: u16) -> AppResult<i16> {
    i16::try_from(value).map_err(AppError::internal)
}

/// Attempts of a stop move that lines keep joining concurrently (see the module documentation).
const MOVE_ATTEMPTS: usize = 5;

fn int(value: u32) -> AppResult<i32> {
    i32::try_from(value).map_err(AppError::internal)
}

// --- Shared statements ---------------------------------------------------------------------------

/// Recomputes `distance_from_previous_m` of every stop of `lines` (geodesic distance between
/// consecutive stops), writing only the rows whose value changes.
async fn recompute_distances(
    tx: &mut Transaction<'_, Postgres>,
    lines: &[Uuid],
) -> AppResult<()> {
    sqlx::query!(
        r#"
        UPDATE line_stops ls
        SET distance_from_previous_m = d.distance
        FROM (
            SELECT l.line_id, l.stop_id,
                   ST_Distance(s.location, lag(s.location) OVER (
                       PARTITION BY l.line_id ORDER BY l.position
                   ))::real AS distance
            FROM line_stops l
            JOIN stops s ON s.id = l.stop_id
            WHERE l.line_id = ANY($1)
        ) d
        WHERE ls.line_id = d.line_id AND ls.stop_id = d.stop_id
          AND ls.distance_from_previous_m IS DISTINCT FROM d.distance
        "#,
        lines,
    )
    .execute(&mut **tx)
    .await
    .map_err(db_error)?;
    Ok(())
}

/// Starts a transaction that rewrites the stop list of `line`: positions are checked at
/// commit, and the line row is locked (and stamped) for the rest of the transaction.
async fn begin_stop_list_change(
    store: &PgStore,
    line: LineId,
    at: DateTime<Utc>,
) -> AppResult<Transaction<'static, Postgres>> {
    let mut tx = store.pool().begin().await.map_err(db_error)?;
    sqlx::query!("SET CONSTRAINTS line_stops_position_key DEFERRED")
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
    let locked = sqlx::query!("UPDATE lines SET updated_at = $2 WHERE id = $1", line.as_uuid(), at)
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
    if locked.rows_affected() == 0 {
        return Err(AppError::NotFound("line"));
    }
    Ok(tx)
}

async fn load_line_stops<'e>(
    executor: impl PgExecutor<'e>,
    line: LineId,
) -> AppResult<Vec<LineStop>> {
    sqlx::query_as!(
        LineStopRow,
        r#"
        SELECT ls.position, ls.distance_from_previous_m, ls.time_from_previous_s,
               s.id, s.name, ST_Y(s.location::geometry) AS "lat!",
               ST_X(s.location::geometry) AS "lng!", s.address, s.wilaya, s.commune,
               s.description, s.features, s.is_active, s.photo_key, s.created_at, s.updated_at
        FROM line_stops ls
        JOIN stops s ON s.id = ls.stop_id
        WHERE ls.line_id = $1
        ORDER BY ls.position
        "#,
        line.as_uuid(),
    )
    .fetch_all(executor)
    .await
    .map_err(db_error)?
    .into_iter()
    .map(LineStopRow::into_line_stop)
    .collect()
}

/// Commits a stop-list change with its effects and returns the new list.
async fn finish_stop_list_change(
    mut tx: Transaction<'_, Postgres>,
    line: LineId,
    effects: &WriteEffects,
) -> AppResult<Vec<LineStop>> {
    recompute_distances(&mut tx, &[line.as_uuid()]).await?;
    let stops = load_line_stops(&mut *tx, line).await?;
    effects::persist(&mut tx, effects).await?;
    tx.commit().await.map_err(|e| match violated_constraint(&e) {
        // Unreachable while every writer keeps positions contiguous under the line lock.
        Some("line_stops_position_key") => AppError::Conflict(ConflictKind::StaleState),
        _ => db_error(e),
    })?;
    Ok(stops)
}

fn line_stop_conflict(error: sqlx::Error) -> AppError {
    match violated_constraint(&error) {
        Some("line_stops_pkey") => AppError::Conflict(ConflictKind::StopAlreadyOnLine),
        Some("line_stops_stop_id_fkey") => {
            AppError::invalid("stop_id", Violation::UnknownReference)
        }
        _ => db_error(error),
    }
}

// --- Stops ---------------------------------------------------------------------------------------

#[async_trait]
impl StopRepository for PgStore {
    async fn insert(&self, stop: NewStop, effects: WriteEffects) -> AppResult<Stop> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            StopRow,
            r#"
            INSERT INTO stops (id, name, location, address, wilaya, commune, description,
                               features, is_active, created_at, updated_at)
            VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography, $5, $6, $7, $8,
                    $9, $10, $11, $11)
            RETURNING id, name, ST_Y(location::geometry) AS "lat!",
                      ST_X(location::geometry) AS "lng!", address, wilaya, commune, description,
                      features, is_active, photo_key, created_at, updated_at
            "#,
            stop.id.as_uuid(),
            stop.name.as_str(),
            stop.location.lng(),
            stop.location.lat(),
            stop.address,
            stop.wilaya,
            stop.commune,
            stop.description,
            stop.features.as_slice(),
            stop.is_active,
            stop.created_at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(db_error)?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(row.into_stop())
    }

    async fn find(&self, id: StopId) -> AppResult<Option<Stop>> {
        let row = sqlx::query_as!(
            StopRow,
            r#"
            SELECT id, name, ST_Y(location::geometry) AS "lat!",
                   ST_X(location::geometry) AS "lng!", address, wilaya, commune, description,
                   features, is_active, photo_key, created_at, updated_at
            FROM stops WHERE id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?;
        Ok(row.map(StopRow::into_stop))
    }

    async fn existing(&self, ids: &[StopId]) -> AppResult<HashSet<StopId>> {
        let ids: Vec<Uuid> = ids.iter().map(StopId::as_uuid).collect();
        let found = sqlx::query_scalar!("SELECT id FROM stops WHERE id = ANY($1)", &ids)
            .fetch_all(self.pool())
            .await
            .map_err(db_error)?;
        Ok(found.into_iter().map(StopId::from_uuid).collect())
    }

    async fn list(&self, filter: &StopFilter, page: PageRequest) -> AppResult<Page<Stop>> {
        let rows = sqlx::query_as!(
            StopRow,
            r#"
            SELECT s.id, s.name, ST_Y(s.location::geometry) AS "lat!",
                   ST_X(s.location::geometry) AS "lng!", s.address, s.wilaya, s.commune,
                   s.description, s.features, s.is_active, s.photo_key, s.created_at,
                   s.updated_at
            FROM stops s
            WHERE ($1::text IS NULL OR s.name ILIKE $1 ESCAPE '\')
              AND ($2::text IS NULL OR lower(s.wilaya) = lower($2))
              AND ($3::text IS NULL OR lower(s.commune) = lower($3))
              AND ($4::uuid IS NULL OR EXISTS (
                      SELECT 1 FROM line_stops ls JOIN lines l ON l.id = ls.line_id
                      WHERE ls.line_id = $4 AND ls.stop_id = s.id AND ($9::bool OR l.is_active)
                  ))
              AND ($5::bool IS NULL OR s.is_active = $5)
              AND ($6::timestamptz IS NULL OR (s.created_at, s.id) < ($6, $7))
            ORDER BY s.created_at DESC, s.id DESC
            LIMIT $8
            "#,
            filter.q.as_deref().map(like_contains),
            filter.wilaya,
            filter.commune,
            filter.line_id.map(|l| l.as_uuid()),
            filter.is_active,
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
            filter.include_inactive_lines,
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let stops = rows.into_iter().map(StopRow::into_stop).collect();
        Ok(Page::from_rows(stops, page, |s: &Stop| Cursor {
            created_at: s.created_at,
            id: s.id.as_uuid(),
        }))
    }

    async fn nearby(
        &self,
        center: GeoPoint,
        radius_m: u32,
        limit: u32,
    ) -> AppResult<Vec<NearbyStop>> {
        // KNN ordering (`<->`, served by `stops_location_gix`) bounded by `ST_DWithin`. Both
        // and the reported distance use the sphere, so the distances are sorted.
        let rows = sqlx::query_as!(
            NearbyRow,
            r#"
            WITH center AS (
                SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography AS point
            )
            SELECT s.id, s.name, ST_Y(s.location::geometry) AS "lat!",
                   ST_X(s.location::geometry) AS "lng!", s.address, s.wilaya, s.commune,
                   s.description, s.features, s.is_active, s.photo_key, s.created_at,
                   s.updated_at, ST_Distance(s.location, c.point, false) AS "distance_m!"
            FROM stops s, center c
            WHERE s.is_active AND ST_DWithin(s.location, c.point, $3, false)
            ORDER BY s.location <-> c.point, s.id
            LIMIT $4
            "#,
            center.lng(),
            center.lat(),
            f64::from(radius_m),
            i64::from(limit),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        Ok(rows
            .into_iter()
            .map(|r| NearbyStop {
                distance_m: r.distance_m,
                stop: StopRow {
                    id: r.id,
                    name: r.name,
                    lat: r.lat,
                    lng: r.lng,
                    address: r.address,
                    wilaya: r.wilaya,
                    commune: r.commune,
                    description: r.description,
                    features: r.features,
                    is_active: r.is_active,
                    photo_key: r.photo_key,
                    created_at: r.created_at,
                    updated_at: r.updated_at,
                }
                .into_stop(),
            })
            .collect())
    }

    async fn update(
        &self,
        id: StopId,
        patch: StopPatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Stop> {
        let moving = patch.location.is_some();
        for _ in 0..MOVE_ATTEMPTS {
            let mut tx = self.pool().begin().await.map_err(db_error)?;
            // A move changes the distances of the lines serving the stop: lock them first
            // (the order used by stop-list writers, see the module documentation).
            let lines = if moving {
                sqlx::query_scalar!(
                    r#"
                    SELECT id FROM lines
                    WHERE id IN (SELECT line_id FROM line_stops WHERE stop_id = $1)
                    ORDER BY id
                    FOR UPDATE
                    "#,
                    id.as_uuid(),
                )
                .fetch_all(&mut *tx)
                .await
                .map_err(db_error)?
            } else {
                Vec::new()
            };
            let row = sqlx::query_as!(
                StopRow,
                r#"
                UPDATE stops SET
                    name = COALESCE($2, name),
                    location = COALESCE(
                        ST_SetSRID(ST_MakePoint($3::float8, $4::float8), 4326)::geography,
                        location
                    ),
                    address = COALESCE($5, address),
                    wilaya = COALESCE($6, wilaya),
                    commune = COALESCE($7, commune),
                    description = COALESCE($8, description),
                    features = COALESCE($9, features),
                    is_active = COALESCE($10, is_active),
                    updated_at = $11
                WHERE id = $1
                RETURNING id, name, ST_Y(location::geometry) AS "lat!",
                          ST_X(location::geometry) AS "lng!", address, wilaya, commune,
                          description, features, is_active, photo_key, created_at, updated_at
                "#,
                id.as_uuid(),
                patch.name.as_ref().map(StopName::as_str),
                patch.location.map(GeoPoint::lng),
                patch.location.map(GeoPoint::lat),
                patch.address.as_deref(),
                patch.wilaya.as_deref(),
                patch.commune.as_deref(),
                patch.description.as_deref(),
                patch.features.as_ref().map(FeatureTags::as_slice),
                patch.is_active,
                at,
            )
            .fetch_optional(&mut *tx)
            .await
            .map_err(db_error)?
            .ok_or(AppError::NotFound("stop"))?;
            if moving {
                // Lines that gained the stop while this transaction waited for its row lock
                // (their writers held `FOR SHARE` on it) are not locked: locking them now would
                // invert the lock order, so start again with them in the first query.
                let serving = sqlx::query_scalar!(
                    "SELECT DISTINCT line_id FROM line_stops WHERE stop_id = $1",
                    id.as_uuid(),
                )
                .fetch_all(&mut *tx)
                .await
                .map_err(db_error)?;
                if serving.iter().any(|line| !lines.contains(line)) {
                    tx.rollback().await.map_err(db_error)?;
                    continue;
                }
                recompute_distances(&mut tx, &lines).await?;
            }
            effects::persist(&mut tx, &effects).await?;
            tx.commit().await.map_err(db_error)?;
            return Ok(row.into_stop());
        }
        // Each attempt lost the race to a new line serving the stop.
        Err(AppError::Conflict(ConflictKind::StaleState))
    }

    async fn delete(
        &self,
        id: StopId,
        expected_photo: Option<&str>,
        effects: WriteEffects,
    ) -> AppResult<()> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Compare-and-delete on the photo: `effects` delete the object we saw.
        let deleted = sqlx::query!(
            "DELETE FROM stops WHERE id = $1 AND photo_key IS NOT DISTINCT FROM $2::text",
            id.as_uuid(),
            expected_photo,
        )
        .execute(&mut *tx)
        .await
        .map_err(|e| match violated_constraint(&e) {
            Some("line_stops_stop_id_fkey") => AppError::Conflict(ConflictKind::StopInUse),
            _ => db_error(e),
        })?;
        if deleted.rows_affected() == 0 {
            let exists = sqlx::query_scalar!(
                r#"SELECT EXISTS (SELECT 1 FROM stops WHERE id = $1) AS "exists!""#,
                id.as_uuid(),
            )
            .fetch_one(&mut *tx)
            .await
            .map_err(db_error)?;
            return Err(if exists {
                AppError::Conflict(ConflictKind::StaleState)
            } else {
                AppError::NotFound("stop")
            });
        }
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(())
    }

    async fn set_photo(
        &self,
        id: StopId,
        photo: Option<&ClaimedUpload>,
        expected: Option<&str>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Stop> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Compare-and-set on the previous key, as for avatars.
        let row = sqlx::query_as!(
            StopRow,
            r#"
            UPDATE stops SET photo_key = $2, updated_at = $3
            WHERE id = $1 AND photo_key IS NOT DISTINCT FROM $4::text
            RETURNING id, name, ST_Y(location::geometry) AS "lat!",
                      ST_X(location::geometry) AS "lng!", address, wilaya, commune, description,
                      features, is_active, photo_key, created_at, updated_at
            "#,
            id.as_uuid(),
            photo.map(|claimed| claimed.object_key.as_str()),
            at,
            expected,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?;
        let Some(row) = row else {
            let exists = sqlx::query_scalar!(
                r#"SELECT EXISTS (SELECT 1 FROM stops WHERE id = $1) AS "exists!""#,
                id.as_uuid(),
            )
            .fetch_one(&mut *tx)
            .await
            .map_err(db_error)?;
            return Err(if exists {
                AppError::Conflict(ConflictKind::StaleState)
            } else {
                AppError::NotFound("stop")
            });
        };
        if let Some(claimed) = photo {
            uploads::mark_attached(&mut tx, claimed, at).await?;
        }
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(row.into_stop())
    }

    async fn lines(&self, id: StopId, include_inactive: bool) -> AppResult<Vec<Line>> {
        // `line_stops_stop_idx` finds the lines of the stop.
        sqlx::query_as!(
            LineRow,
            r#"
            SELECT l.id, l.code, l.name, l.description, l.color, l.frequency_minutes, l.fare_dza,
                   l.is_active, l.route IS NOT NULL AS "has_route!",
                   (SELECT count(*) FROM line_stops c WHERE c.line_id = l.id) AS "stops_count!",
                   l.created_at, l.updated_at
            FROM lines l
            WHERE EXISTS (SELECT 1 FROM line_stops ls WHERE ls.line_id = l.id AND ls.stop_id = $1)
              AND ($2 OR l.is_active)
            ORDER BY l.code
            "#,
            id.as_uuid(),
            include_inactive,
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?
        .into_iter()
        .map(LineRow::into_line)
        .collect()
    }
}

// --- Lines ---------------------------------------------------------------------------------------

#[async_trait]
impl LineRepository for PgStore {
    async fn insert(&self, line: NewLine, effects: WriteEffects) -> AppResult<Line> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            LineRow,
            r#"
            INSERT INTO lines (id, code, name, description, color, frequency_minutes, fare_dza,
                               is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
            RETURNING id, code, name, description, color, frequency_minutes, fare_dza, is_active,
                      route IS NOT NULL AS "has_route!", 0::int8 AS "stops_count!", created_at,
                      updated_at
            "#,
            line.id.as_uuid(),
            line.code.as_str(),
            line.name.as_str(),
            line.description,
            line.color.as_str(),
            line.frequency_minutes.map(|f| smallint(f.minutes())).transpose()?,
            line.fare_dza.map(|f| int(f.dzd())).transpose()?,
            line.is_active,
            line.created_at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(|e| match violated_constraint(&e) {
            Some("lines_code_key") => AppError::Conflict(ConflictKind::LineCodeTaken),
            _ => db_error(e),
        })?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        row.into_line()
    }

    async fn find(&self, id: LineId) -> AppResult<Option<Line>> {
        sqlx::query_as!(
            LineRow,
            r#"
            SELECT l.id, l.code, l.name, l.description, l.color, l.frequency_minutes, l.fare_dza,
                   l.is_active, l.route IS NOT NULL AS "has_route!",
                   (SELECT count(*) FROM line_stops c WHERE c.line_id = l.id) AS "stops_count!",
                   l.created_at, l.updated_at
            FROM lines l WHERE l.id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(LineRow::into_line)
        .transpose()
    }

    async fn list(&self, filter: &LineFilter, page: PageRequest) -> AppResult<Page<Line>> {
        // The search expression is exactly the one of `lines_search_trgm_idx`.
        let rows = sqlx::query_as!(
            LineRow,
            r#"
            SELECT l.id, l.code, l.name, l.description, l.color, l.frequency_minutes, l.fare_dza,
                   l.is_active, l.route IS NOT NULL AS "has_route!",
                   (SELECT count(*) FROM line_stops c WHERE c.line_id = l.id) AS "stops_count!",
                   l.created_at, l.updated_at
            FROM lines l
            WHERE ($1::text IS NULL OR (l.code || ' ' || l.name) ILIKE $1 ESCAPE '\')
              AND ($2::uuid IS NULL OR EXISTS (
                      SELECT 1 FROM line_stops ls WHERE ls.line_id = l.id AND ls.stop_id = $2
                  ))
              AND ($3::bool IS NULL OR l.is_active = $3)
              AND ($4::timestamptz IS NULL OR (l.created_at, l.id) < ($4, $5))
            ORDER BY l.created_at DESC, l.id DESC
            LIMIT $6
            "#,
            filter.q.as_deref().map(like_contains),
            filter.stop_id.map(|s| s.as_uuid()),
            filter.is_active,
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let lines = rows.into_iter().map(LineRow::into_line).collect::<AppResult<Vec<_>>>()?;
        Ok(Page::from_rows(lines, page, |l: &Line| Cursor {
            created_at: l.created_at,
            id: l.id.as_uuid(),
        }))
    }

    async fn update(
        &self,
        id: LineId,
        patch: LinePatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Line> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            LineRow,
            r#"
            UPDATE lines l SET
                name = COALESCE($2, name),
                description = COALESCE($3, description),
                color = COALESCE($4, color),
                frequency_minutes = CASE WHEN $5 THEN $6 ELSE frequency_minutes END,
                fare_dza = CASE WHEN $7 THEN $8 ELSE fare_dza END,
                is_active = COALESCE($9, is_active),
                updated_at = $10
            WHERE id = $1
            RETURNING l.id, l.code, l.name, l.description, l.color, l.frequency_minutes,
                      l.fare_dza, l.is_active, l.route IS NOT NULL AS "has_route!",
                      (SELECT count(*) FROM line_stops c WHERE c.line_id = l.id)
                          AS "stops_count!",
                      l.created_at, l.updated_at
            "#,
            id.as_uuid(),
            patch.name.as_ref().map(LineName::as_str),
            patch.description,
            patch.color.as_ref().map(HexColor::as_str),
            patch.frequency_minutes.is_some(),
            patch.frequency_minutes.flatten().map(|f| smallint(f.minutes())).transpose()?,
            patch.fare_dza.is_some(),
            patch.fare_dza.flatten().map(|f| int(f.dzd())).transpose()?,
            patch.is_active,
            at,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        .ok_or(AppError::NotFound("line"))?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        row.into_line()
    }

    async fn delete(&self, id: LineId, effects: WriteEffects) -> AppResult<()> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Cascades `line_stops` and `schedules`. Bus assignments (M2 WP4,
        // `bus_line_assignments.line_id … ON DELETE RESTRICT`) refuse the deletion.
        let deleted = sqlx::query!("DELETE FROM lines WHERE id = $1", id.as_uuid())
            .execute(&mut *tx)
            .await
            .map_err(|e| match violated_constraint(&e) {
                Some("bus_line_assignments_line_id_fkey") => {
                    AppError::Conflict(ConflictKind::LineInUse)
                }
                _ => db_error(e),
            })?;
        if deleted.rows_affected() == 0 {
            return Err(AppError::NotFound("line"));
        }
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(())
    }

    async fn stops(&self, id: LineId) -> AppResult<Vec<LineStop>> {
        load_line_stops(self.pool(), id).await
    }

    async fn replace_stops(
        &self,
        id: LineId,
        stops: &StopSequence,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>> {
        let ids: Vec<Uuid> = stops.entries().iter().map(|e| e.stop_id.as_uuid()).collect();
        let times = stops
            .entries()
            .iter()
            .map(|e| e.time_from_previous_s.map(int).transpose())
            .collect::<AppResult<Vec<Option<i32>>>>()?;
        let mut tx = begin_stop_list_change(self, id, at).await?;
        // Keeps the stops from being deleted or moved until the distances are stored.
        let locked = sqlx::query_scalar!(
            "SELECT id FROM stops WHERE id = ANY($1) ORDER BY id FOR SHARE",
            &ids,
        )
        .fetch_all(&mut *tx)
        .await
        .map_err(db_error)?;
        if locked.len() != ids.len() {
            return Err(AppError::invalid("stops", Violation::UnknownReference));
        }
        sqlx::query!("DELETE FROM line_stops WHERE line_id = $1", id.as_uuid())
            .execute(&mut *tx)
            .await
            .map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO line_stops (line_id, stop_id, position, time_from_previous_s)
            SELECT $1, t.stop_id, (t.n - 1)::smallint, t.time_s
            FROM unnest($2::uuid[], $3::int4[]) WITH ORDINALITY AS t(stop_id, time_s, n)
            "#,
            id.as_uuid(),
            &ids,
            &times as &[Option<i32>],
        )
        .execute(&mut *tx)
        .await
        .map_err(|e| match violated_constraint(&e) {
            Some("line_stops_stop_id_fkey") => {
                AppError::invalid("stops", Violation::UnknownReference)
            }
            _ => db_error(e),
        })?;
        finish_stop_list_change(tx, id, &effects).await
    }

    async fn add_stop(
        &self,
        id: LineId,
        entry: StopSequenceEntry,
        position: Option<i64>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>> {
        let mut tx = begin_stop_list_change(self, id, at).await?;
        let stop = sqlx::query_scalar!(
            "SELECT id FROM stops WHERE id = $1 FOR SHARE",
            entry.stop_id.as_uuid(),
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?;
        if stop.is_none() {
            return Err(AppError::invalid("stop_id", Violation::UnknownReference));
        }
        let current = sqlx::query!(
            r#"
            SELECT count(*) AS "count!",
                   COALESCE(bool_or(stop_id = $2), false) AS "present!"
            FROM line_stops WHERE line_id = $1
            "#,
            id.as_uuid(),
            entry.stop_id.as_uuid(),
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(db_error)?;
        if current.present {
            return Err(AppError::Conflict(ConflictKind::StopAlreadyOnLine));
        }
        let len = usize::try_from(current.count).map_err(AppError::internal)?;
        let position = insert_position(len, position)
            .map_err(|violation| AppError::invalid("position", violation))?;
        if position == 0 && entry.time_from_previous_s.is_some() {
            return Err(AppError::invalid("time_from_previous_s", Violation::NotAllowed));
        }
        // Later stops move one place down; the stop that followed the insertion point now
        // follows the new stop, so its segment time is unknown.
        sqlx::query!(
            r#"
            UPDATE line_stops
            SET position = position + 1,
                time_from_previous_s = CASE WHEN position = $2 THEN NULL
                                            ELSE time_from_previous_s END
            WHERE line_id = $1 AND position >= $2
            "#,
            id.as_uuid(),
            smallint(position)?,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        sqlx::query!(
            r#"
            INSERT INTO line_stops (line_id, stop_id, position, time_from_previous_s)
            VALUES ($1, $2, $3, $4)
            "#,
            id.as_uuid(),
            entry.stop_id.as_uuid(),
            smallint(position)?,
            entry.time_from_previous_s.map(int).transpose()?,
        )
        .execute(&mut *tx)
        .await
        .map_err(line_stop_conflict)?;
        finish_stop_list_change(tx, id, &effects).await
    }

    async fn remove_stop(
        &self,
        id: LineId,
        stop_id: StopId,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Vec<LineStop>> {
        let mut tx = begin_stop_list_change(self, id, at).await?;
        let removed = sqlx::query!(
            r#"
            DELETE FROM line_stops WHERE line_id = $1 AND stop_id = $2
            RETURNING position, time_from_previous_s
            "#,
            id.as_uuid(),
            stop_id.as_uuid(),
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        .ok_or(AppError::NotFound("line_stop"))?;
        // Later stops move one place up. The next stop's segment now starts at the removed
        // stop's predecessor: its time is the sum of both segments when both are known (capped
        // to a day), and it has no segment at all when it becomes the first stop.
        sqlx::query!(
            r#"
            UPDATE line_stops
            SET position = position - 1,
                time_from_previous_s = CASE
                    WHEN position = 1 THEN NULL
                    WHEN position = $2 + 1 THEN LEAST(time_from_previous_s + $3, 86400)
                    ELSE time_from_previous_s END,
                distance_from_previous_m = CASE WHEN position = 1 THEN NULL
                                                ELSE distance_from_previous_m END
            WHERE line_id = $1 AND position > $2
            "#,
            id.as_uuid(),
            removed.position,
            removed.time_from_previous_s,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        finish_stop_list_change(tx, id, &effects).await
    }

    async fn route(&self, id: LineId) -> AppResult<Option<LineGeometry>> {
        let points = sqlx::query!(
            r#"
            SELECT ST_Y(dp.geom) AS "lat!", ST_X(dp.geom) AS "lng!"
            FROM lines l, ST_DumpPoints(l.route::geometry) AS dp
            WHERE l.id = $1 AND l.route IS NOT NULL
            ORDER BY dp.path[1]
            "#,
            id.as_uuid(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        if points.is_empty() {
            return Ok(None);
        }
        let points = points.into_iter().map(|p| GeoPoint::from_trusted(p.lat, p.lng)).collect();
        Ok(Some(LineGeometry::from_trusted(points)))
    }

    async fn set_route(
        &self,
        id: LineId,
        route: Option<&LineGeometry>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Line> {
        let (lngs, lats): (Vec<f64>, Vec<f64>) = route
            .map(|r| r.points().iter().map(|p| (p.lng(), p.lat())).unzip())
            .unwrap_or_default();
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            LineRow,
            r#"
            UPDATE lines l SET
                route = CASE WHEN $2 THEN ST_SetSRID(ST_MakeLine(ARRAY(
                            SELECT ST_MakePoint(p.lng, p.lat)
                            FROM unnest($3::float8[], $4::float8[])
                                 WITH ORDINALITY AS p(lng, lat, n)
                            ORDER BY p.n
                        )), 4326)::geography
                        ELSE NULL END,
                updated_at = $5
            WHERE id = $1
            RETURNING l.id, l.code, l.name, l.description, l.color, l.frequency_minutes,
                      l.fare_dza, l.is_active, l.route IS NOT NULL AS "has_route!",
                      (SELECT count(*) FROM line_stops c WHERE c.line_id = l.id)
                          AS "stops_count!",
                      l.created_at, l.updated_at
            "#,
            id.as_uuid(),
            route.is_some(),
            &lngs,
            &lats,
            at,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        .ok_or(AppError::NotFound("line"))?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        row.into_line()
    }
}

// --- Schedules -----------------------------------------------------------------------------------

/// Maps the constraints of `schedules` to the errors the API reports.
fn schedule_error(error: sqlx::Error) -> AppError {
    match violated_constraint(&error) {
        Some("schedules_no_overlap") => AppError::Conflict(ConflictKind::ScheduleOverlap),
        Some("schedules_line_id_fkey") => AppError::NotFound("line"),
        Some("schedules_time_order") => AppError::invalid(
            "end_time",
            Violation::MustBeAfter { field: "start_time".into() },
        ),
        Some("schedules_day_range") => {
            AppError::invalid("day_of_week", Violation::OutOfRange { min: 1, max: 7 })
        }
        Some("schedules_frequency_range") => AppError::invalid(
            "frequency_minutes",
            Violation::OutOfRange { min: 1, max: i64::from(Frequency::MAX_MINUTES) },
        ),
        _ => db_error(error),
    }
}

#[async_trait]
impl ScheduleRepository for PgStore {
    async fn insert(&self, schedule: NewSchedule, effects: WriteEffects) -> AppResult<Schedule> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            ScheduleRow,
            r#"
            INSERT INTO schedules (id, line_id, day_of_week, start_time, end_time,
                                   frequency_minutes, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
            RETURNING id, line_id, day_of_week, start_time, end_time, frequency_minutes,
                      is_active, created_at, updated_at
            "#,
            schedule.id.as_uuid(),
            schedule.line_id.as_uuid(),
            i16::from(schedule.day.iso()),
            naive_time(schedule.window.start()),
            naive_time(schedule.window.end()),
            smallint(schedule.frequency.minutes())?,
            schedule.is_active,
            schedule.created_at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(schedule_error)?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        row.into_schedule()
    }

    async fn find(&self, id: ScheduleId) -> AppResult<Option<Schedule>> {
        sqlx::query_as!(
            ScheduleRow,
            r#"
            SELECT id, line_id, day_of_week, start_time, end_time, frequency_minutes, is_active,
                   created_at, updated_at
            FROM schedules WHERE id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(ScheduleRow::into_schedule)
        .transpose()
    }

    async fn list_for_line(
        &self,
        line_id: LineId,
        include_inactive: bool,
    ) -> AppResult<Vec<Schedule>> {
        // Served by `schedules_line_day_idx` without a sort.
        sqlx::query_as!(
            ScheduleRow,
            r#"
            SELECT id, line_id, day_of_week, start_time, end_time, frequency_minutes, is_active,
                   created_at, updated_at
            FROM schedules
            WHERE line_id = $1 AND ($2 OR is_active)
            ORDER BY day_of_week, start_time, id
            "#,
            line_id.as_uuid(),
            include_inactive,
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?
        .into_iter()
        .map(ScheduleRow::into_schedule)
        .collect()
    }

    async fn update(
        &self,
        id: ScheduleId,
        patch: SchedulePatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Schedule> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            ScheduleRow,
            r#"
            UPDATE schedules SET
                day_of_week = COALESCE($2, day_of_week),
                start_time = COALESCE($3, start_time),
                end_time = COALESCE($4, end_time),
                frequency_minutes = COALESCE($5, frequency_minutes),
                is_active = COALESCE($6, is_active),
                updated_at = $7
            WHERE id = $1
            RETURNING id, line_id, day_of_week, start_time, end_time, frequency_minutes,
                      is_active, created_at, updated_at
            "#,
            id.as_uuid(),
            patch.day.map(|d| i16::from(d.iso())),
            patch.start.map(naive_time),
            patch.end.map(naive_time),
            patch.frequency.map(|f| smallint(f.minutes())).transpose()?,
            patch.is_active,
            at,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(schedule_error)?
        .ok_or(AppError::NotFound("schedule"))?;
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        row.into_schedule()
    }

    async fn delete(&self, id: ScheduleId, effects: WriteEffects) -> AppResult<()> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let deleted = sqlx::query!("DELETE FROM schedules WHERE id = $1", id.as_uuid())
            .execute(&mut *tx)
            .await
            .map_err(db_error)?;
        if deleted.rows_affected() == 0 {
            return Err(AppError::NotFound("schedule"));
        }
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(())
    }
}

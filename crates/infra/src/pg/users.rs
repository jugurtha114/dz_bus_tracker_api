//! Users and profiles.

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use dz_app::pagination::{Cursor, Page, PageRequest};
use dz_app::ports::{
    AdminUserPatch, AdminUserUpdate, ClaimedUpload, Credentials, LockoutPolicy, NewUser,
    ProfilePatch, UserFilter, UserPatch, UserRepository, WriteEffects,
};
use dz_app::{AppError, AppResult};
use dz_domain::ids::{SessionId, UserId};
use dz_domain::user::{Bio, Email, PersonName, PhoneNumber, Profile, Role, User};
use dz_domain::{ConflictKind, Lang};
use uuid::Uuid;

use super::{PgStore, db_error, effects, like_prefix, uploads, violated_constraint};

/// Columns of `users` as selected by every query below.
#[derive(Debug)]
struct UserRow {
    id: Uuid,
    email: String,
    role: String,
    first_name: String,
    last_name: String,
    phone_number: Option<String>,
    is_active: bool,
    email_verified_at: Option<DateTime<Utc>>,
    last_login_at: Option<DateTime<Utc>>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl UserRow {
    fn into_user(self) -> AppResult<User> {
        let role = Role::parse(&self.role)
            .filter(|r| r.is_user_role())
            .ok_or_else(|| AppError::Internal(anyhow::anyhow!("invalid role in database")))?;
        Ok(User {
            id: UserId::from_uuid(self.id),
            email: Email::from_trusted(self.email),
            role,
            first_name: PersonName::from_trusted(self.first_name),
            last_name: PersonName::from_trusted(self.last_name),
            phone_number: self.phone_number.map(PhoneNumber::from_trusted),
            is_active: self.is_active,
            email_verified_at: self.email_verified_at,
            last_login_at: self.last_login_at,
            created_at: self.created_at,
            updated_at: self.updated_at,
        })
    }
}

#[derive(Debug)]
struct ProfileRow {
    user_id: Uuid,
    avatar_key: Option<String>,
    bio: String,
    language: String,
    push_notifications_enabled: bool,
    email_notifications_enabled: bool,
    sms_notifications_enabled: bool,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl ProfileRow {
    fn into_profile(self) -> Profile {
        Profile {
            user_id: UserId::from_uuid(self.user_id),
            avatar_key: self.avatar_key,
            bio: Bio::from_trusted(self.bio),
            language: Lang::from_code(&self.language).unwrap_or_default(),
            push_notifications_enabled: self.push_notifications_enabled,
            email_notifications_enabled: self.email_notifications_enabled,
            sms_notifications_enabled: self.sms_notifications_enabled,
            created_at: self.created_at,
            updated_at: self.updated_at,
        }
    }
}

#[derive(Debug)]
struct CredentialsRow {
    id: Uuid,
    email: String,
    role: String,
    first_name: String,
    last_name: String,
    phone_number: Option<String>,
    is_active: bool,
    email_verified_at: Option<DateTime<Utc>>,
    last_login_at: Option<DateTime<Utc>>,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
    password_hash: Option<String>,
    failed_login_attempts: i32,
    locked_until: Option<DateTime<Utc>>,
    language: Option<String>,
}

impl CredentialsRow {
    fn into_credentials(self) -> AppResult<Credentials> {
        let language = self.language.as_deref().and_then(Lang::from_code).unwrap_or_default();
        let user = UserRow {
            id: self.id,
            email: self.email,
            role: self.role,
            first_name: self.first_name,
            last_name: self.last_name,
            phone_number: self.phone_number,
            is_active: self.is_active,
            email_verified_at: self.email_verified_at,
            last_login_at: self.last_login_at,
            created_at: self.created_at,
            updated_at: self.updated_at,
        }
        .into_user()?;
        Ok(Credentials {
            user,
            password_hash: self.password_hash,
            failed_login_attempts: u32::try_from(self.failed_login_attempts).unwrap_or(0),
            locked_until: self.locked_until,
            language,
        })
    }
}

#[async_trait]
impl UserRepository for PgStore {
    async fn insert(&self, new: NewUser) -> AppResult<(User, Profile)> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let row = sqlx::query_as!(
            UserRow,
            r#"
            INSERT INTO users (id, email, password_hash, role, first_name, last_name, phone_number,
                               password_changed_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8, $8)
            RETURNING id, email, role, first_name, last_name, phone_number, is_active,
                      email_verified_at, last_login_at, created_at, updated_at
            "#,
            new.id.as_uuid(),
            new.email.as_str(),
            new.password_hash,
            new.role.as_str(),
            new.first_name.as_str(),
            new.last_name.as_str(),
            new.phone_number.as_ref().map(PhoneNumber::as_str),
            new.created_at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(unique_conflict)?;
        let profile = sqlx::query_as!(
            ProfileRow,
            r#"
            INSERT INTO profiles (user_id, language, created_at, updated_at)
            VALUES ($1, $2, $3, $3)
            RETURNING user_id, avatar_key, bio, language, push_notifications_enabled,
                      email_notifications_enabled, sms_notifications_enabled, created_at, updated_at
            "#,
            new.id.as_uuid(),
            new.language.as_str(),
            new.created_at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(db_error)?;
        tx.commit().await.map_err(db_error)?;
        Ok((row.into_user()?, profile.into_profile()))
    }

    async fn find(&self, id: UserId) -> AppResult<Option<User>> {
        sqlx::query_as!(
            UserRow,
            r#"
            SELECT id, email, role, first_name, last_name, phone_number, is_active,
                   email_verified_at, last_login_at, created_at, updated_at
            FROM users WHERE id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(UserRow::into_user)
        .transpose()
    }

    async fn credentials_by_email(&self, email: &Email) -> AppResult<Option<Credentials>> {
        sqlx::query_as!(
            CredentialsRow,
            r#"
            SELECT u.id, u.email, u.role, u.first_name, u.last_name, u.phone_number, u.is_active,
                   u.email_verified_at, u.last_login_at, u.created_at, u.updated_at,
                   u.password_hash, u.failed_login_attempts, u.locked_until,
                   p.language AS "language?"
            FROM users u LEFT JOIN profiles p ON p.user_id = u.id
            WHERE u.email = $1
            "#,
            email.as_str(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(CredentialsRow::into_credentials)
        .transpose()
    }

    async fn credentials_by_id(&self, id: UserId) -> AppResult<Option<Credentials>> {
        sqlx::query_as!(
            CredentialsRow,
            r#"
            SELECT u.id, u.email, u.role, u.first_name, u.last_name, u.phone_number, u.is_active,
                   u.email_verified_at, u.last_login_at, u.created_at, u.updated_at,
                   u.password_hash, u.failed_login_attempts, u.locked_until,
                   p.language AS "language?"
            FROM users u LEFT JOIN profiles p ON p.user_id = u.id
            WHERE u.id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(CredentialsRow::into_credentials)
        .transpose()
    }

    async fn record_login_success(
        &self,
        id: UserId,
        at: DateTime<Utc>,
        upgraded_hash: Option<String>,
    ) -> AppResult<()> {
        sqlx::query!(
            r#"
            UPDATE users
            SET failed_login_attempts = 0,
                locked_until = NULL,
                last_login_at = $2,
                password_hash = COALESCE($3, password_hash)
            WHERE id = $1
            "#,
            id.as_uuid(),
            at,
            upgraded_hash,
        )
        .execute(self.pool())
        .await
        .map_err(db_error)?;
        Ok(())
    }

    async fn record_login_failure(
        &self,
        id: UserId,
        at: DateTime<Utc>,
        policy: LockoutPolicy,
    ) -> AppResult<()> {
        // Counter and lock are computed in one statement so concurrent failures cannot race.
        sqlx::query!(
            r#"
            UPDATE users
            SET failed_login_attempts = failed_login_attempts + 1,
                locked_until = CASE
                    WHEN failed_login_attempts + 1 >= $2 THEN
                        $3::timestamptz
                            + make_interval(secs => $4::float8 * power(2, LEAST(failed_login_attempts + 1 - $2, 5)))
                    ELSE locked_until
                END
            WHERE id = $1
            "#,
            id.as_uuid(),
            i32::try_from(policy.threshold).unwrap_or(i32::MAX),
            at,
            policy.base.as_secs_f64(),
        )
        .execute(self.pool())
        .await
        .map_err(db_error)?;
        Ok(())
    }

    async fn change_password(
        &self,
        id: UserId,
        password_hash: String,
        at: DateTime<Utc>,
        keep: Option<SessionId>,
    ) -> AppResult<Vec<SessionId>> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let updated = sqlx::query!(
            r#"
            UPDATE users
            SET password_hash = $2, password_changed_at = $3, updated_at = $3,
                failed_login_attempts = 0, locked_until = NULL
            WHERE id = $1
            "#,
            id.as_uuid(),
            password_hash,
            at,
        )
        .execute(&mut *tx)
        .await
        .map_err(db_error)?;
        if updated.rows_affected() == 0 {
            return Err(AppError::NotFound("user"));
        }
        let revoked = super::sessions::revoke_all_in(
            &mut tx,
            id,
            "password_changed",
            at,
            keep,
        )
        .await?;
        tx.commit().await.map_err(db_error)?;
        Ok(revoked)
    }

    async fn update(&self, id: UserId, patch: UserPatch, at: DateTime<Utc>) -> AppResult<User> {
        let set_phone = patch.phone_number.is_some();
        let phone = patch.phone_number.flatten();
        sqlx::query_as!(
            UserRow,
            r#"
            UPDATE users
            SET first_name = COALESCE($2, first_name),
                last_name = COALESCE($3, last_name),
                phone_number = CASE WHEN $4 THEN $5 ELSE phone_number END,
                updated_at = $6
            WHERE id = $1
            RETURNING id, email, role, first_name, last_name, phone_number, is_active,
                      email_verified_at, last_login_at, created_at, updated_at
            "#,
            id.as_uuid(),
            patch.first_name.as_ref().map(PersonName::as_str),
            patch.last_name.as_ref().map(PersonName::as_str),
            set_phone,
            phone.as_ref().map(PhoneNumber::as_str),
            at,
        )
        .fetch_optional(self.pool())
        .await
        .map_err(unique_conflict)?
        .ok_or(AppError::NotFound("user"))?
        .into_user()
    }

    async fn profile(&self, id: UserId) -> AppResult<Option<Profile>> {
        Ok(sqlx::query_as!(
            ProfileRow,
            r#"
            SELECT user_id, avatar_key, bio, language, push_notifications_enabled,
                   email_notifications_enabled, sms_notifications_enabled, created_at, updated_at
            FROM profiles WHERE user_id = $1
            "#,
            id.as_uuid(),
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .map(ProfileRow::into_profile))
    }

    async fn update_profile(
        &self,
        id: UserId,
        patch: ProfilePatch,
        at: DateTime<Utc>,
    ) -> AppResult<Profile> {
        Ok(sqlx::query_as!(
            ProfileRow,
            r#"
            UPDATE profiles
            SET bio = COALESCE($2, bio),
                language = COALESCE($3, language),
                push_notifications_enabled = COALESCE($4, push_notifications_enabled),
                email_notifications_enabled = COALESCE($5, email_notifications_enabled),
                sms_notifications_enabled = COALESCE($6, sms_notifications_enabled),
                updated_at = $7
            WHERE user_id = $1
            RETURNING user_id, avatar_key, bio, language, push_notifications_enabled,
                      email_notifications_enabled, sms_notifications_enabled, created_at, updated_at
            "#,
            id.as_uuid(),
            patch.bio.as_ref().map(Bio::as_str),
            patch.language.map(Lang::as_str),
            patch.push_notifications_enabled,
            patch.email_notifications_enabled,
            patch.sms_notifications_enabled,
            at,
        )
        .fetch_optional(self.pool())
        .await
        .map_err(db_error)?
        .ok_or(AppError::NotFound("profile"))?
        .into_profile())
    }

    async fn list(&self, filter: &UserFilter, page: PageRequest) -> AppResult<Page<User>> {
        let rows = sqlx::query_as!(
            UserRow,
            r#"
            SELECT id, email, role, first_name, last_name, phone_number, is_active,
                   email_verified_at, last_login_at, created_at, updated_at
            FROM users
            WHERE ($1::text IS NULL OR role = $1)
              AND ($2::bool IS NULL OR is_active = $2)
              AND ($3::text IS NULL OR email LIKE $3 ESCAPE '\')
              AND ($4::timestamptz IS NULL OR (created_at, id) < ($4, $5))
            ORDER BY created_at DESC, id DESC
            LIMIT $6
            "#,
            filter.role.map(Role::as_str),
            filter.is_active,
            filter.email_prefix.as_deref().map(like_prefix),
            page.after.map(|c| c.created_at),
            page.after.map(|c| c.id),
            page.fetch_limit(),
        )
        .fetch_all(self.pool())
        .await
        .map_err(db_error)?;
        let users = rows.into_iter().map(UserRow::into_user).collect::<AppResult<Vec<_>>>()?;
        Ok(Page::from_rows(users, page, |u| Cursor { created_at: u.created_at, id: u.id.as_uuid() }))
    }

    async fn admin_update(
        &self,
        id: UserId,
        patch: AdminUserPatch,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<AdminUserUpdate> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        let before = sqlx::query!(
            "SELECT is_active, role FROM users WHERE id = $1 FOR UPDATE",
            id.as_uuid(),
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?
        .ok_or(AppError::NotFound("user"))?;
        let row = sqlx::query_as!(
            UserRow,
            r#"
            UPDATE users
            SET is_active = COALESCE($2, is_active),
                role = COALESCE($3, role),
                updated_at = $4
            WHERE id = $1
            RETURNING id, email, role, first_name, last_name, phone_number, is_active,
                      email_verified_at, last_login_at, created_at, updated_at
            "#,
            id.as_uuid(),
            patch.is_active,
            patch.role.map(Role::as_str),
            at,
        )
        .fetch_one(&mut *tx)
        .await
        .map_err(db_error)?;
        let deactivated = before.is_active && !row.is_active;
        let role_changed = before.role != row.role;
        let revoked_sessions = if deactivated || role_changed {
            super::sessions::revoke_all_in(&mut tx, id, "admin_action", at, None).await?
        } else {
            Vec::new()
        };
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(AdminUserUpdate { user: row.into_user()?, revoked_sessions })
    }

    async fn set_avatar(
        &self,
        id: UserId,
        avatar: Option<&ClaimedUpload>,
        expected: Option<&str>,
        at: DateTime<Utc>,
        effects: WriteEffects,
    ) -> AppResult<Profile> {
        let mut tx = self.pool().begin().await.map_err(db_error)?;
        // Compare-and-set on the previous key: the row lock serialises concurrent changes and
        // the loser sees zero rows (its outbox job would delete the winner's object otherwise).
        let row = sqlx::query_as!(
            ProfileRow,
            r#"
            UPDATE profiles SET avatar_key = $2, updated_at = $3
            WHERE user_id = $1 AND avatar_key IS NOT DISTINCT FROM $4::text
            RETURNING user_id, avatar_key, bio, language, push_notifications_enabled,
                      email_notifications_enabled, sms_notifications_enabled, created_at, updated_at
            "#,
            id.as_uuid(),
            avatar.map(|claimed| claimed.object_key.as_str()),
            at,
            expected,
        )
        .fetch_optional(&mut *tx)
        .await
        .map_err(db_error)?;
        let Some(row) = row else {
            let exists = sqlx::query_scalar!(
                r#"SELECT EXISTS (SELECT 1 FROM profiles WHERE user_id = $1) AS "exists!""#,
                id.as_uuid(),
            )
            .fetch_one(&mut *tx)
            .await
            .map_err(db_error)?;
            return Err(if exists {
                AppError::Conflict(ConflictKind::StaleState)
            } else {
                AppError::NotFound("profile")
            });
        };
        if let Some(claimed) = avatar {
            uploads::mark_attached(&mut tx, claimed, at).await?;
        }
        effects::persist(&mut tx, &effects).await?;
        tx.commit().await.map_err(db_error)?;
        Ok(row.into_profile())
    }
}

/// Maps unique-constraint violations on `users` to conflicts the client can act on.
fn unique_conflict(error: sqlx::Error) -> AppError {
    match violated_constraint(&error) {
        Some("users_email_key") => AppError::Conflict(ConflictKind::EmailTaken),
        Some("users_phone_number_key") => AppError::Conflict(ConflictKind::PhoneTaken),
        _ => db_error(error),
    }
}

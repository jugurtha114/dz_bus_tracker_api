//! Background jobs: the closed set of job kinds and the use-cases that execute them.
//!
//! Job kinds are an enum, so a kind can never be registered twice or misspelled (legacy Celery
//! registered four task names twice, L-35b). The queue mechanics live in `dz-infra`.

use std::net::IpAddr;
use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use dz_domain::Lang;
use dz_domain::user::Email;
use serde::{Deserialize, Serialize};

use crate::auth::secrets;
use crate::error::AppResult;
use crate::mail;
use crate::ports::{
    Clock, JobOptions, JobQueue, Mailer, PasswordResetRepository, SessionRepository,
    UserRepository,
};

/// Every job the worker knows how to run.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload", rename_all = "snake_case")]
pub enum Job {
    /// Someone asked to reset the password of `email`. The worker issues the token and sends
    /// the e-mail, so the HTTP response time never depends on whether the account exists.
    PasswordResetRequested { email: String, lang: Lang, requested_ip: Option<IpAddr> },
    /// Deletes expired sessions, refresh tokens and reset tokens.
    PurgeExpiredAuth,
    /// Deletes finished jobs and old cron claims.
    PurgeFinishedJobs,
}

impl Job {
    /// Stable identifier stored in the queue (also used as a metrics label).
    #[must_use]
    pub const fn kind(&self) -> &'static str {
        match self {
            Self::PasswordResetRequested { .. } => "password_reset_requested",
            Self::PurgeExpiredAuth => "purge_expired_auth",
            Self::PurgeFinishedJobs => "purge_finished_jobs",
        }
    }
}

/// A recurring job.
#[derive(Debug, Clone, Copy)]
pub struct CronEntry {
    /// Unique name; equals the job kind.
    pub name: &'static str,
    /// Cron expression in UTC with a leading seconds field.
    pub schedule: &'static str,
    pub job: fn() -> Job,
}

/// Recurring jobs.
pub const CRON_SCHEDULE: &[CronEntry] = &[
    CronEntry { name: "purge_expired_auth", schedule: "0 17 * * * *", job: || Job::PurgeExpiredAuth },
    CronEntry {
        name: "purge_finished_jobs",
        schedule: "0 41 3 * * *",
        job: || Job::PurgeFinishedJobs,
    },
];

/// Settings the job handlers need.
#[derive(Debug, Clone)]
pub struct JobSettings {
    pub password_reset_ttl: Duration,
    /// Front-end page; the token is appended as `#token=...`.
    pub password_reset_url: String,
    /// Expired auth rows are kept this long before deletion (forensics).
    pub auth_retention: Duration,
    /// Finished jobs are kept this long for inspection.
    pub job_retention: Duration,
}

/// Executes jobs. Every handler is idempotent: running a job twice has no extra effect beyond
/// what a single run would have had (a second reset e-mail invalidates the first link).
pub struct JobRunner {
    pub users: Arc<dyn UserRepository>,
    pub sessions: Arc<dyn SessionRepository>,
    pub resets: Arc<dyn PasswordResetRepository>,
    pub mailer: Arc<dyn Mailer>,
    pub queue: Arc<dyn JobQueue>,
    pub clock: Arc<dyn Clock>,
    pub settings: JobSettings,
}

impl JobRunner {
    pub async fn run(&self, job: &Job) -> AppResult<()> {
        match job {
            Job::PasswordResetRequested { email, lang, .. } => {
                self.send_password_reset(email, *lang).await
            }
            Job::PurgeExpiredAuth => self.purge_expired_auth().await,
            Job::PurgeFinishedJobs => {
                let before = self.clock.now() - chrono_duration(self.settings.job_retention);
                let purged = self.queue.purge_finished(before).await?;
                tracing::info!(purged, "purged finished jobs");
                Ok(())
            }
        }
    }

    async fn send_password_reset(&self, email: &str, lang: Lang) -> AppResult<()> {
        let Ok(email) = Email::parse(email) else {
            return Ok(());
        };
        let Some(credentials) = self.users.credentials_by_email(&email).await? else {
            tracing::info!("password reset requested for an unknown address");
            return Ok(());
        };
        if !credentials.user.is_active {
            tracing::info!(user_id = %credentials.user.id, "password reset ignored for inactive account");
            return Ok(());
        }
        let now = self.clock.now();
        let token = secrets::generate("dzp");
        let expires_at = now + chrono_duration(self.settings.password_reset_ttl);
        self.resets.issue(credentials.user.id, token.hash, now, expires_at).await?;
        let link = format!("{}#token={}", self.settings.password_reset_url, token.plaintext);
        // The user's saved language wins over the language of the anonymous request.
        let lang = if credentials.language == lang { lang } else { credentials.language };
        let message = mail::password_reset(
            credentials.user.email.as_str(),
            lang,
            &link,
            self.settings.password_reset_ttl,
        );
        self.mailer.send(&message).await?;
        tracing::info!(user_id = %credentials.user.id, "password reset e-mail sent");
        Ok(())
    }

    async fn purge_expired_auth(&self) -> AppResult<()> {
        let before = self.clock.now() - chrono_duration(self.settings.auth_retention);
        let sessions = self.sessions.purge_expired(before).await?;
        let resets = self.resets.purge_expired(before).await?;
        tracing::info!(sessions, resets, "purged expired authentication records");
        Ok(())
    }
}

/// Enqueues a job with default options.
pub async fn enqueue(queue: &dyn JobQueue, job: Job) -> AppResult<()> {
    queue.enqueue(&job, JobOptions::default()).await.map(|_| ())
}

/// Converts a std duration to a chrono duration, saturating on overflow.
#[must_use]
pub fn chrono_duration(d: Duration) -> chrono::Duration {
    chrono::Duration::from_std(d).unwrap_or(chrono::Duration::MAX)
}

/// The instant `d` after `t`, saturating.
#[must_use]
pub fn after(t: DateTime<Utc>, d: Duration) -> DateTime<Utc> {
    t.checked_add_signed(chrono_duration(d)).unwrap_or(DateTime::<Utc>::MAX_UTC)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn job_serialization_is_tagged_and_stable() {
        let job = Job::PasswordResetRequested {
            email: "a@b.dz".into(),
            lang: Lang::Ar,
            requested_ip: None,
        };
        let json = serde_json::to_value(&job).unwrap();
        assert_eq!(json["kind"], "password_reset_requested");
        assert_eq!(json["payload"]["lang"], "ar");
        assert_eq!(serde_json::from_value::<Job>(json).unwrap(), job);
        assert_eq!(job.kind(), "password_reset_requested");
    }

    #[test]
    fn cron_jobs_have_matching_kinds() {
        for entry in CRON_SCHEDULE {
            assert_eq!((entry.job)().kind(), entry.name);
        }
    }
}

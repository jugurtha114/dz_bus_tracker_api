//! Transactional outbox: the [`WriteEffects`] of a repository write (audit entries and jobs)
//! are inserted in the write's own transaction, so they exist if and only if the change
//! committed, and jobs run only after the commit (legacy L-08).

use dz_app::AppResult;
use dz_app::ports::WriteEffects;
use sqlx::{Postgres, Transaction};

use super::audit;

/// Inserts the audit entries and jobs of `effects` inside `tx`. Jobs follow the queue's
/// `dedup_key` rule (a pending job with the same key makes the insert a no-op).
pub async fn persist(tx: &mut Transaction<'_, Postgres>, effects: &WriteEffects) -> AppResult<()> {
    for entry in &effects.audit {
        audit::insert(tx, entry).await?;
    }
    for outbox in &effects.jobs {
        crate::jobs::insert_job(&mut **tx, &outbox.job, &outbox.options).await?;
    }
    Ok(())
}

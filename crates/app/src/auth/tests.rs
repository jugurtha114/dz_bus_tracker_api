//! Use-case tests against the in-memory ports.

#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::sync::atomic::Ordering;
use std::time::Duration;

use dz_domain::authz::{Actor, Permission};
use dz_domain::password::PasswordPolicy;
use dz_domain::user::Role;
use dz_domain::{DenyReason, Lang};
use secrecy::SecretString;

use super::*;
use crate::account::{AccountService, UpdateMeInput};
use crate::admin::{AdminUserService, ApiKeyService, CreateApiKeyInput};
use crate::jobs::{JobRunner, JobSettings};
use crate::testing::Fakes;

const PASSWORD: &str = "correct horse battery";

struct Harness {
    fakes: Fakes,
    auth: AuthService,
}

fn settings() -> AuthSettings {
    AuthSettings {
        access_ttl: Duration::from_secs(900),
        refresh_ttl: Duration::from_secs(14 * 86_400),
        session_max_lifetime: Duration::from_secs(60 * 86_400),
        password_policy: PasswordPolicy::default(),
        lockout: LockoutPolicy { threshold: 5, base: Duration::from_secs(60) },
        reset_quota: Quota { limit: 3, period: Duration::from_secs(900), burst: 3 },
        revocation_fail_open: false,
    }
}

fn harness() -> Harness {
    let fakes = Fakes::default();
    let deps = AuthDeps {
        users: fakes.store.clone(),
        sessions: fakes.store.clone(),
        resets: fakes.store.clone(),
        hasher: fakes.hasher.clone(),
        tokens: fakes.tokens.clone(),
        revocations: fakes.revocations.clone(),
        jobs: fakes.queue.clone(),
        limiter: fakes.limiter.clone(),
        clock: fakes.clock.clone(),
    };
    Harness { auth: AuthService::new(deps, settings()), fakes }
}

fn secret(s: &str) -> SecretString {
    SecretString::from(s.to_owned())
}

fn register_input(email: &str) -> RegisterInput {
    RegisterInput {
        email: email.to_owned(),
        password: secret(PASSWORD),
        first_name: Some("Amina".into()),
        last_name: Some("Belkacem".into()),
        phone_number: Some("0555 12 34 56".into()),
        language: Some(Lang::Ar),
    }
}

async fn register(h: &Harness, email: &str) -> SignedIn {
    h.auth.register(register_input(email), &RequestMeta::default()).await.unwrap()
}

fn violation_codes(err: AppError) -> Vec<(String, &'static str)> {
    match err {
        AppError::Validation(v) => {
            v.iter().map(|f| (f.field.to_string(), f.violation.code())).collect()
        }
        other => panic!("expected validation error, got {other:?}"),
    }
}

#[tokio::test]
async fn registration_creates_a_passenger_with_a_working_session() {
    let h = harness();
    let signed = register(&h, " Amina@Example.DZ ").await;
    assert_eq!(signed.user.role, Role::Passenger);
    assert_eq!(signed.user.email.as_str(), "amina@example.dz");
    assert_eq!(signed.user.phone_number.as_ref().unwrap().as_str(), "+213555123456");
    assert_eq!(signed.profile.unwrap().language, Lang::Ar);
    let claims = h.auth.authenticate(&signed.tokens.access_token).await.unwrap();
    assert_eq!(claims.sub, signed.user.id);
    assert_eq!(claims.role, Role::Passenger);
    assert_eq!(claims.lang, Lang::Ar);
}

#[tokio::test]
async fn registration_reports_every_invalid_field_and_duplicates() {
    let h = harness();
    let mut input = register_input("not-an-email");
    input.phone_number = Some("123".into());
    input.password = secret("short");
    let codes = violation_codes(h.auth.register(input, &RequestMeta::default()).await.unwrap_err());
    assert!(codes.contains(&("email".into(), "invalid_email")));
    assert!(codes.contains(&("phone_number".into(), "invalid_phone")));

    let mut weak = register_input("x@example.dz");
    weak.password = secret("amina-belkacem-2026");
    let codes = violation_codes(h.auth.register(weak, &RequestMeta::default()).await.unwrap_err());
    assert_eq!(codes, vec![("password".to_owned(), "password_too_similar")]);

    register(&h, "dup@example.dz").await;
    let err = h.auth.register(register_input("DUP@example.dz"), &RequestMeta::default()).await;
    assert!(matches!(err, Err(AppError::Conflict(dz_domain::ConflictKind::EmailTaken))));
}

#[tokio::test]
async fn login_failures_are_generic_and_lock_the_account() {
    let h = harness();
    let user = register(&h, "lock@example.dz").await.user;
    let meta = RequestMeta::default();
    let invalid = |r: AppResult<SignedIn>| {
        matches!(r, Err(AppError::Unauthenticated(AuthFailure::InvalidCredentials)))
    };

    assert!(invalid(h.auth.login("nobody@example.dz", &secret(PASSWORD), &meta).await));
    assert!(invalid(h.auth.login("garbage", &secret(PASSWORD), &meta).await));
    for _ in 0..5 {
        assert!(invalid(h.auth.login("lock@example.dz", &secret("wrong password!"), &meta).await));
    }
    // Locked: even the right password is refused, with the same error.
    assert!(invalid(h.auth.login("lock@example.dz", &secret(PASSWORD), &meta).await));
    h.fakes.clock.advance(Duration::from_secs(61));
    let signed = h.auth.login("LOCK@example.dz", &secret(PASSWORD), &meta).await.unwrap();
    assert_eq!(signed.user.id, user.id);
    assert!(signed.user.last_login_at.is_some());
}

#[tokio::test]
async fn deactivated_accounts_cannot_log_in() {
    let h = harness();
    let user = register(&h, "off@example.dz").await.user;
    let admin = Actor::User {
        id: dz_domain::ids::UserId::generate(),
        role: Role::Admin,
        session_id: dz_domain::ids::SessionId::generate(),
    };
    let admins = AdminUserService::new(
        h.fakes.store.clone(),
        h.fakes.revocations.clone(),
        h.fakes.clock.clone(),
        Duration::from_secs(960),
    );
    admins.update(&admin, user.id, Some(false), None, &RequestMeta::default()).await.unwrap();
    let r = h.auth.login("off@example.dz", &secret(PASSWORD), &RequestMeta::default()).await;
    assert!(matches!(r, Err(AppError::Unauthenticated(AuthFailure::InvalidCredentials))));
}

#[tokio::test]
async fn legacy_hashes_are_upgraded_on_login() {
    let h = harness();
    let user = register(&h, "legacy@example.dz").await.user;
    h.fakes.store.set_password_hash(user.id, &format!("legacy${PASSWORD}"));
    h.auth.login("legacy@example.dz", &secret(PASSWORD), &RequestMeta::default()).await.unwrap();
    assert_eq!(h.fakes.store.password_hash(user.id).unwrap(), format!("plain${PASSWORD}"));
}

#[tokio::test]
async fn refresh_rotates_and_detects_reuse() {
    let h = harness();
    let first = register(&h, "rot@example.dz").await.tokens;
    let second = h.auth.refresh(&first.refresh_token).await.unwrap();
    assert_ne!(second.refresh_token, first.refresh_token);
    assert_eq!(second.session_id, first.session_id);

    // Replaying the spent token revokes the whole session.
    let reuse = h.auth.refresh(&first.refresh_token).await;
    assert!(matches!(reuse, Err(AppError::Unauthenticated(AuthFailure::RefreshTokenReused))));
    let after_reuse = h.auth.refresh(&second.refresh_token).await;
    assert!(matches!(after_reuse, Err(AppError::Unauthenticated(AuthFailure::RefreshTokenInvalid))));
    let access = h.auth.authenticate(&second.access_token).await;
    assert!(matches!(access, Err(AppError::Unauthenticated(AuthFailure::SessionRevoked))));

    let garbage = h.auth.refresh("dzr_nope").await;
    assert!(matches!(garbage, Err(AppError::Unauthenticated(AuthFailure::RefreshTokenInvalid))));
}

#[tokio::test]
async fn refresh_tokens_expire() {
    let h = harness();
    let tokens = register(&h, "exp@example.dz").await.tokens;
    h.fakes.clock.advance(Duration::from_secs(15 * 86_400));
    let r = h.auth.refresh(&tokens.refresh_token).await;
    assert!(matches!(r, Err(AppError::Unauthenticated(AuthFailure::RefreshTokenInvalid))));
}

#[tokio::test]
async fn logout_cuts_off_access_tokens_immediately() {
    let h = harness();
    let tokens = register(&h, "out@example.dz").await.tokens;
    let other = h.auth.login("out@example.dz", &secret(PASSWORD), &RequestMeta::default()).await.unwrap();
    let claims = h.auth.authenticate(&tokens.access_token).await.unwrap();
    h.auth.logout(&claims, false).await.unwrap();
    assert!(h.auth.authenticate(&tokens.access_token).await.is_err());
    assert!(h.auth.refresh(&tokens.refresh_token).await.is_err());
    // The other device is untouched until "log out everywhere".
    let other_claims = h.auth.authenticate(&other.tokens.access_token).await.unwrap();
    h.auth.logout(&other_claims, true).await.unwrap();
    assert!(h.auth.authenticate(&other.tokens.access_token).await.is_err());
}

#[tokio::test]
async fn revocation_store_outage_fails_closed_by_default() {
    let h = harness();
    let tokens = register(&h, "down@example.dz").await.tokens;
    h.fakes.revocations.failing.store(true, Ordering::SeqCst);
    let r = h.auth.authenticate(&tokens.access_token).await;
    assert!(matches!(r, Err(AppError::Unavailable(_))));

    let mut open = settings();
    open.revocation_fail_open = true;
    let auth = AuthService::new(h.auth.deps.clone(), open);
    assert!(auth.authenticate(&tokens.access_token).await.is_ok());
}

#[tokio::test]
async fn expired_access_tokens_are_rejected() {
    let h = harness();
    let tokens = register(&h, "late@example.dz").await.tokens;
    h.fakes.clock.advance(Duration::from_secs(901));
    let r = h.auth.authenticate(&tokens.access_token).await;
    assert!(matches!(r, Err(AppError::Unauthenticated(AuthFailure::TokenExpired))));
}

#[tokio::test]
async fn changing_the_password_keeps_only_the_current_session() {
    let h = harness();
    let current = register(&h, "chg@example.dz").await.tokens;
    let other = h.auth.login("chg@example.dz", &secret(PASSWORD), &RequestMeta::default()).await.unwrap();
    let claims = h.auth.authenticate(&current.access_token).await.unwrap();

    let wrong = h.auth.change_password(&claims, &secret("not it at all"), &secret("brand new passphrase")).await;
    assert_eq!(violation_codes(wrong.unwrap_err()), vec![("current_password".into(), "incorrect")]);
    let same = h.auth.change_password(&claims, &secret(PASSWORD), &secret(PASSWORD)).await;
    assert_eq!(violation_codes(same.unwrap_err()), vec![("new_password".into(), "password_reused")]);

    h.auth.change_password(&claims, &secret(PASSWORD), &secret("brand new passphrase")).await.unwrap();
    assert!(h.auth.authenticate(&current.access_token).await.is_ok());
    assert!(h.auth.authenticate(&other.tokens.access_token).await.is_err());
    let relog = h.auth.login("chg@example.dz", &secret("brand new passphrase"), &RequestMeta::default()).await;
    assert!(relog.is_ok());
}

fn runner(h: &Harness) -> JobRunner {
    JobRunner {
        users: h.fakes.store.clone(),
        sessions: h.fakes.store.clone(),
        resets: h.fakes.store.clone(),
        uploads: h.fakes.store.clone(),
        storage: Some(h.fakes.storage.clone()),
        mailer: h.fakes.mailer.clone(),
        queue: h.fakes.queue.clone(),
        clock: h.fakes.clock.clone(),
        settings: JobSettings {
            password_reset_ttl: Duration::from_secs(3600),
            password_reset_url: "https://app.example/reset".into(),
            auth_retention: Duration::from_secs(86_400),
            job_retention: Duration::from_secs(7 * 86_400),
            upload_purge_grace: Duration::from_secs(3600),
        },
    }
}

fn token_from_mail(h: &Harness) -> String {
    let sent = h.fakes.mailer.sent.lock().unwrap();
    let body = &sent.last().unwrap().text_body;
    let start = body.find("#token=").unwrap() + "#token=".len();
    body[start..].split_whitespace().next().unwrap().to_owned()
}

#[tokio::test]
async fn password_reset_round_trip() {
    let h = harness();
    let tokens = register(&h, "reset@example.dz").await.tokens;
    let meta = RequestMeta::default();
    h.auth.request_password_reset("Reset@example.dz", Lang::En, &meta).await.unwrap();
    // A second request while the first is pending is deduplicated.
    h.auth.request_password_reset("reset@example.dz", Lang::En, &meta).await.unwrap();
    let jobs = h.fakes.queue.drain();
    assert_eq!(jobs.len(), 1);

    let runner = runner(&h);
    runner.run(&jobs[0]).await.unwrap();
    let mail = h.fakes.mailer.sent.lock().unwrap().last().cloned().unwrap();
    assert_eq!(mail.to, "reset@example.dz");
    assert_eq!(mail.lang, Lang::Ar, "the account language wins");
    let token = token_from_mail(&h);

    let weak = h.auth.confirm_password_reset(&token, &secret("123")).await;
    assert!(matches!(weak, Err(AppError::Validation(_))));
    h.auth.confirm_password_reset(&token, &secret("a fresh passphrase")).await.unwrap();
    assert!(h.auth.authenticate(&tokens.access_token).await.is_err(), "sessions revoked");
    let again = h.auth.confirm_password_reset(&token, &secret("another passphrase")).await;
    assert!(matches!(again, Err(AppError::Unauthenticated(AuthFailure::ResetTokenInvalid))));
    assert!(h.auth.login("reset@example.dz", &secret("a fresh passphrase"), &meta).await.is_ok());
}

#[tokio::test]
async fn password_reset_is_silent_for_unknown_accounts_and_expires() {
    let h = harness();
    register(&h, "known@example.dz").await;
    let meta = RequestMeta::default();
    h.auth.request_password_reset("ghost@example.dz", Lang::Fr, &meta).await.unwrap();
    let runner = runner(&h);
    for job in h.fakes.queue.drain() {
        runner.run(&job).await.unwrap();
    }
    assert!(h.fakes.mailer.sent.lock().unwrap().is_empty());

    h.auth.request_password_reset("known@example.dz", Lang::Fr, &meta).await.unwrap();
    for job in h.fakes.queue.drain() {
        runner.run(&job).await.unwrap();
    }
    let token = token_from_mail(&h);
    h.fakes.clock.advance(Duration::from_secs(3601));
    let r = h.auth.confirm_password_reset(&token, &secret("a fresh passphrase")).await;
    assert!(matches!(r, Err(AppError::Unauthenticated(AuthFailure::ResetTokenInvalid))));
}

#[tokio::test]
async fn reset_requests_are_rate_limited_per_address() {
    let h = harness();
    let meta = RequestMeta::default();
    for _ in 0..5 {
        h.auth.request_password_reset("spam@example.dz", Lang::Fr, &meta).await.unwrap();
        h.fakes.queue.drain();
    }
    // Quota of 3: the last two were silently dropped (counted by the fake limiter).
    let key = format!("password_reset:{}", secrets::opaque_key("spam@example.dz"));
    let limited = h.fakes.limiter.check(&key, settings().reset_quota).await;
    assert!(!limited.unwrap().allowed);
}

#[tokio::test]
async fn sessions_can_be_listed_and_revoked_by_their_owner() {
    let h = harness();
    let a = register(&h, "sess@example.dz").await.tokens;
    let b = h.auth.login("sess@example.dz", &secret(PASSWORD), &RequestMeta::default()).await.unwrap().tokens;
    let claims = h.auth.authenticate(&a.access_token).await.unwrap();
    let sessions = h.auth.list_sessions(&claims).await.unwrap();
    assert_eq!(sessions.len(), 2);
    assert_eq!(sessions.iter().filter(|s| s.current).count(), 1);

    let actor = actor_from_claims(&claims);
    h.auth.revoke_session(&actor, b.session_id).await.unwrap();
    assert!(h.auth.authenticate(&b.access_token).await.is_err());
    let missing = h.auth.revoke_session(&actor, b.session_id).await;
    assert!(matches!(missing, Err(AppError::NotFound("session"))));
}

#[tokio::test]
async fn account_updates_validate_and_clear_fields() {
    let h = harness();
    let signed = register(&h, "me@example.dz").await;
    let claims = h.auth.authenticate(&signed.tokens.access_token).await.unwrap();
    let actor = actor_from_claims(&claims);
    let accounts =
        AccountService::new(h.fakes.store.clone(), h.fakes.uploads(), h.fakes.clock.clone());

    let bad = accounts
        .update_me(&actor, UpdateMeInput { phone_number: Some(Some("12".into())), ..Default::default() })
        .await;
    assert_eq!(violation_codes(bad.unwrap_err()), vec![("phone_number".into(), "invalid_phone")]);
    let user = accounts
        .update_me(&actor, UpdateMeInput { phone_number: Some(None), first_name: Some(" Lina ".into()), ..Default::default() })
        .await
        .unwrap();
    assert_eq!(user.phone_number, None);
    assert_eq!(user.first_name.as_str(), "Lina");
    assert!(accounts.me(&Actor::Anonymous).await.is_err());
}

#[tokio::test]
async fn admin_user_management_is_audited_and_guarded() {
    let h = harness();
    let target = register(&h, "target@example.dz").await;
    let admins = AdminUserService::new(
        h.fakes.store.clone(),
        h.fakes.revocations.clone(),
        h.fakes.clock.clone(),
        Duration::from_secs(960),
    );
    let admin_id = dz_domain::ids::UserId::generate();
    let admin =
        Actor::User { id: admin_id, role: Role::Admin, session_id: dz_domain::ids::SessionId::generate() };
    let passenger = Actor::User {
        id: target.user.id,
        role: Role::Passenger,
        session_id: target.tokens.session_id,
    };
    let meta = RequestMeta::default();

    let denied = admins.update(&passenger, target.user.id, Some(false), None, &meta).await;
    assert!(matches!(denied, Err(AppError::Forbidden(DenyReason::MissingPermission))));
    let own = admins.update(&admin, admin_id, Some(false), None, &meta).await;
    assert!(matches!(own, Err(AppError::Forbidden(DenyReason::InvalidState))));
    let bad_role = admins.update(&admin, target.user.id, None, Some("service"), &meta).await;
    assert!(matches!(bad_role, Err(AppError::Validation(_))));

    let user = admins.update(&admin, target.user.id, None, Some("driver"), &meta).await.unwrap();
    assert_eq!(user.role, Role::Driver);
    assert_eq!(h.fakes.store.audit_len(), 1);
    // The role is embedded in access tokens, so the user is signed out.
    assert!(h.auth.authenticate(&target.tokens.access_token).await.is_err());
}

#[tokio::test]
async fn api_keys_authenticate_with_their_scopes_until_revoked() {
    let h = harness();
    let keys = ApiKeyService::new(h.fakes.store.clone(), h.fakes.clock.clone());
    let admin = Actor::User {
        id: dz_domain::ids::UserId::generate(),
        role: Role::Admin,
        session_id: dz_domain::ids::SessionId::generate(),
    };
    let meta = RequestMeta::default();

    let invalid = keys
        .create(&admin, CreateApiKeyInput { name: " ".into(), scopes: vec!["user:manage".into(), "nope".into()], expires_at: None }, &meta)
        .await;
    let codes = violation_codes(invalid.unwrap_err());
    assert!(codes.contains(&("name".into(), "required")));
    assert!(codes.contains(&("scopes[0]".into(), "invalid_choice")));
    assert!(codes.contains(&("scopes[1]".into(), "invalid_choice")));

    let created = keys
        .create(&admin, CreateApiKeyInput { name: "Open data".into(), scopes: vec!["tracking:read".into(), "analytics:read".into()], expires_at: None }, &meta)
        .await
        .unwrap();
    assert!(created.secret.starts_with(&created.record.prefix));
    let actor = keys.authenticate(&created.secret).await.unwrap();
    assert!(actor.has(Permission::AnalyticsRead));
    assert!(!actor.has(Permission::UserManage));

    let tampered = format!("{}x", created.secret);
    assert!(keys.authenticate(&tampered).await.is_err());
    assert!(keys.authenticate("dzk_short_x").await.is_err());

    keys.revoke(&admin, created.record.id, &meta).await.unwrap();
    assert!(keys.authenticate(&created.secret).await.is_err());
    assert_eq!(h.fakes.store.audit_len(), 2);
    let passenger = Actor::User {
        id: dz_domain::ids::UserId::generate(),
        role: Role::Passenger,
        session_id: dz_domain::ids::SessionId::generate(),
    };
    assert!(keys.list(&passenger, crate::pagination::PageRequest::default()).await.is_err());
}

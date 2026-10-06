//! A fully wired application over real PostgreSQL and Valkey.

use std::net::SocketAddr;
use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;

use axum::Router;
use axum::Extension;
use axum::extract::ConnectInfo;
use axum::http::{Method, StatusCode};
use dz_app::ports::EmailMessage;
use dz_app::testing::FakeMailer;
use dz_config::{Environment, Settings};
use dz_domain::user::Role;
use dz_http::state::{AppServices, AppState};
use dz_infra::jobs::{self, WorkerConfig};
use dz_infra::valkey::Valkey;
use dz_infra::wiring::Infrastructure;
use serde_json::{Value, json};
use sqlx::PgPool;
use uuid::Uuid;

use crate::client::TestRequest;
use crate::database::TestDatabase;

/// Password of every account created by the helpers.
pub const PASSWORD: &str = "correct horse battery staple";

/// Peer address of in-process requests (TEST-NET-2; not a trusted proxy by default).
const DEFAULT_PEER: SocketAddr =
    SocketAddr::new(std::net::IpAddr::V4(std::net::Ipv4Addr::new(198, 51, 100, 7)), 50_000);

/// A signed-in account.
#[derive(Debug, Clone)]
pub struct Account {
    pub id: Uuid,
    pub email: String,
    pub role: Role,
    pub access_token: String,
    pub refresh_token: String,
    pub session_id: Uuid,
}

type Configure = Box<dyn FnOnce(&mut Settings) + Send>;

/// Builds a [`TestApp`] with adjusted settings or peer address.
#[must_use]
pub struct TestAppBuilder {
    peer: SocketAddr,
    configure: Vec<Configure>,
}

impl TestAppBuilder {
    /// The TCP peer of every request (what the server sees before proxy headers).
    pub fn peer(mut self, peer: SocketAddr) -> Self {
        self.peer = peer;
        self
    }

    /// Adjusts settings before the application is built (validated afterwards).
    pub fn configure(mut self, f: impl FnOnce(&mut Settings) + Send + 'static) -> Self {
        self.configure.push(Box::new(f));
        self
    }

    pub async fn build(self) -> TestApp {
        let db = TestDatabase::create().await;
        let mut settings = test_settings(&db);
        for f in self.configure {
            f(&mut settings);
        }
        settings.validate().expect("test settings are valid");

        let pool = dz_infra::pg::connect(&settings.database, "dz-test").await.unwrap();
        let valkey = Valkey::connect(&settings.valkey).await.unwrap();
        let mailer = Arc::new(FakeMailer::default());
        let infra = Infrastructure::assemble(settings, pool, valkey, mailer.clone()).unwrap();
        let services = infra.services();
        let state = AppState::new(AppServices {
            settings: infra.settings.clone(),
            auth: services.auth,
            accounts: services.accounts,
            admin_users: services.admin_users,
            api_keys: services.api_keys,
            audit: services.audit,
            limiter: services.limiter,
            idempotency: services.idempotency,
            readiness: services.readiness,
            jwks: services.jwks,
        });
        // What `into_make_service_with_connect_info` provides in the server.
        let router = dz_http::router(state).layer(Extension(ConnectInfo(self.peer)));
        TestApp { router, infra, mailer, accounts: AtomicU32::new(0), db }
    }
}

fn test_settings(db: &TestDatabase) -> Settings {
    let mut s = Settings { env: Environment::Test, ..Settings::default() };
    s.database.url = db.url.clone().into();
    s.database.min_connections = 0;
    s.database.max_connections = 8;
    s.valkey.url = db.valkey_url.clone().into();
    s.valkey.pool_size = 2;
    s.valkey.key_prefix = format!("t:{}:", db.name);
    s.auth.allow_ephemeral_keys = true;
    // Cheap hashing keeps the suite fast; production parameters are covered by unit tests.
    s.auth.argon2_memory_kib = 64;
    s.auth.argon2_iterations = 1;
    // Generous limits: tests that exercise rate limiting configure their own.
    s.rate_limit.anon_per_minute = 10_000;
    s.rate_limit.user_per_minute = 10_000;
    s.rate_limit.burst = 10_000;
    s.rate_limit.auth_per_minute = 10_000;
    s.rate_limit.service_per_minute = 10_000;
    s.http.public_base_url = "http://api.test".parse().unwrap();
    s
}

/// The application under test. Dropping it drops its database.
pub struct TestApp {
    router: Router,
    pub infra: Infrastructure,
    pub mailer: Arc<FakeMailer>,
    accounts: AtomicU32,
    // Last: dropped after the pools above.
    db: TestDatabase,
}

impl TestApp {
    /// An application with default test settings.
    pub async fn spawn() -> Self {
        Self::builder().build().await
    }

    pub fn builder() -> TestAppBuilder {
        TestAppBuilder { peer: DEFAULT_PEER, configure: Vec::new() }
    }

    #[must_use]
    pub fn pool(&self) -> &PgPool {
        &self.infra.pool
    }

    #[must_use]
    pub fn database_name(&self) -> &str {
        &self.db.name
    }

    pub fn request(&self, method: Method, uri: &str) -> TestRequest {
        TestRequest::new(self.router.clone(), method, uri)
    }

    pub fn get(&self, uri: &str) -> TestRequest {
        self.request(Method::GET, uri)
    }

    pub fn post(&self, uri: &str) -> TestRequest {
        self.request(Method::POST, uri)
    }

    pub fn patch(&self, uri: &str) -> TestRequest {
        self.request(Method::PATCH, uri)
    }

    pub fn delete(&self, uri: &str) -> TestRequest {
        self.request(Method::DELETE, uri)
    }

    /// Runs every background job that is due, as the worker would.
    pub async fn run_jobs(&self) -> usize {
        let config = WorkerConfig {
            worker_id: "dz-test-worker".to_owned(),
            concurrency: 4,
            poll_interval: Duration::from_millis(100),
            lease: Duration::from_secs(60),
            job_timeout: Duration::from_secs(30),
        };
        jobs::drain(self.pool(), &self.infra.job_runner(), &config).await.unwrap()
    }

    /// E-mails delivered so far.
    #[must_use]
    pub fn sent_mail(&self) -> Vec<EmailMessage> {
        self.mailer.sent.lock().unwrap().clone()
    }

    /// A fresh, unique e-mail address.
    pub fn unique_email(&self, label: &str) -> String {
        let n = self.accounts.fetch_add(1, Ordering::Relaxed);
        format!("{label}{n}@example.test")
    }

    /// Registers a passenger through the API.
    pub async fn register(&self, email: &str) -> Account {
        let response = self
            .post("/api/v1/auth/register")
            .json(&json!({
                "email": email,
                "password": PASSWORD,
                "first_name": "Test",
                "last_name": "User",
            }))
            .send()
            .await
            .expect(StatusCode::CREATED);
        account_from(&response.json(), Role::Passenger)
    }

    /// Signs in through the API.
    pub async fn login(&self, email: &str) -> Account {
        let response = self
            .post("/api/v1/auth/login")
            .json(&json!({ "email": email, "password": PASSWORD }))
            .send()
            .await
            .expect(StatusCode::OK);
        let body = response.json();
        let role = serde_json::from_value(body["user"]["role"].clone()).unwrap();
        account_from(&body, role)
    }

    /// A signed-in account with `role` (registered, then promoted directly in the database).
    pub async fn account(&self, role: Role) -> Account {
        let email = self.unique_email(role.as_str());
        let account = self.register(&email).await;
        if role == Role::Passenger {
            return account;
        }
        sqlx::query("UPDATE users SET role = $1 WHERE id = $2")
            .bind(role.as_str())
            .bind(account.id)
            .execute(self.pool())
            .await
            .unwrap();
        self.login(&email).await
    }

    /// Creates an API key with `scopes` (as `admin`) and returns its secret.
    pub async fn api_key(&self, admin: &Account, scopes: &[&str]) -> String {
        let response = self
            .post("/api/v1/admin/api-keys")
            .bearer(&admin.access_token)
            .json(&json!({ "name": "test key", "scopes": scopes }))
            .send()
            .await
            .expect(StatusCode::CREATED);
        response.json()["secret"].as_str().expect("API key secret").to_owned()
    }
}

fn account_from(body: &Value, role: Role) -> Account {
    let uuid = |v: &Value| v.as_str().and_then(|s| s.parse().ok()).expect("uuid");
    let text = |v: &Value| v.as_str().expect("string").to_owned();
    Account {
        id: uuid(&body["user"]["id"]),
        email: text(&body["user"]["email"]),
        role,
        access_token: text(&body["tokens"]["access_token"]),
        refresh_token: text(&body["tokens"]["refresh_token"]),
        session_id: uuid(&body["tokens"]["session_id"]),
    }
}

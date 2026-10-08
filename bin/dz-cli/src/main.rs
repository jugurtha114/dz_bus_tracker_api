//! `dz-cli`: operator tasks.
//!
//! * `migrate` / `migration-status` — apply or inspect database migrations.
//! * `create-admin` — create an administrator (password read from stdin, never from argv).
//! * `gen-signing-key` — write a new Ed25519 token-signing key (`<kid>.pem`, mode 0600).
//! * `storage create-bucket` — create the configured object-storage bucket (idempotent).

use std::io::{BufRead, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use clap::{Parser, Subcommand};
use dz_app::admin::{BootstrapAdminInput, bootstrap_admin};
use dz_config::Settings;
use dz_domain::password::PasswordPolicy;
use dz_infra::storage::S3Storage;
use dz_infra::wiring::password_hasher;
use dz_infra::{jwt, pg};
use secrecy::SecretString;

#[derive(Parser)]
#[command(name = "dz-cli", version, about = "DZ Bus Tracker operator CLI")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Apply pending database migrations.
    Migrate,
    /// Show whether the database schema matches this binary.
    MigrationStatus,
    /// Create an administrator account. The password is read from the first line of stdin.
    CreateAdmin {
        #[arg(long)]
        email: String,
        #[arg(long, default_value = "")]
        first_name: String,
        #[arg(long, default_value = "")]
        last_name: String,
    },
    /// Generate an Ed25519 signing key as `<out-dir>/<kid>.pem`.
    GenSigningKey {
        /// Key id, e.g. `2026-10`.
        #[arg(long)]
        kid: String,
        #[arg(long, default_value = "./secrets/jwt")]
        out_dir: PathBuf,
    },
    /// Object storage administration (`DZ_STORAGE__*`).
    Storage {
        #[command(subcommand)]
        command: StorageCommand,
    },
}

#[derive(Subcommand)]
enum StorageCommand {
    /// Create the configured bucket; succeeds when it already exists (one-shot provisioning).
    CreateBucket,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match run(cli.command) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("dz-cli: {error:#}");
            ExitCode::FAILURE
        }
    }
}

fn run(command: Command) -> anyhow::Result<()> {
    if let Command::GenSigningKey { kid, out_dir } = &command {
        return gen_signing_key(kid, out_dir);
    }
    let settings = Settings::load()?;
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build()?;
    if let Command::Storage { command: StorageCommand::CreateBucket } = &command {
        // Needs no database: runs before PostgreSQL is reachable in a fresh deployment.
        return runtime.block_on(create_bucket(&settings));
    }
    runtime.block_on(async move {
        let pool = pg::connect(&settings.database, "dz-cli").await?;
        let result = match command {
            Command::Migrate => {
                pg::migrate(&pool).await?;
                println_out("migrations applied")
            }
            Command::MigrationStatus => {
                let status = pg::migration_status(&pool).await?;
                println_out(&format!(
                    "expected {}, applied {}, pending {:?}, checksum mismatch {:?}",
                    status.expected, status.applied, status.pending, status.checksum_mismatch
                ))?;
                anyhow::ensure!(status.is_up_to_date(), "schema is not up to date");
                Ok(())
            }
            Command::CreateAdmin { email, first_name, last_name } => {
                let password = read_password()?;
                let store = dz_infra::PgStore::new(pool.clone());
                let hasher = password_hasher(&settings)?;
                let policy = PasswordPolicy {
                    min_length: settings.auth.password_min_length,
                    max_length: 128,
                };
                let user = bootstrap_admin(
                    &store,
                    &hasher,
                    &dz_app::ports::SystemClock,
                    policy,
                    BootstrapAdminInput { email, password, first_name, last_name },
                )
                .await
                .map_err(describe)?;
                println_out(&format!("administrator {} created ({})", user.email, user.id))
            }
            Command::GenSigningKey { .. } | Command::Storage { .. } => Ok(()),
        };
        pool.close().await;
        result
    })
}

async fn create_bucket(settings: &Settings) -> anyhow::Result<()> {
    anyhow::ensure!(
        settings.storage.enabled(),
        "object storage is not configured (DZ_STORAGE__ENDPOINT)"
    );
    let storage = S3Storage::new(&settings.storage, Arc::new(dz_app::ports::SystemClock))?;
    let bucket = &settings.storage.bucket;
    if storage.create_bucket().await? {
        println_out(&format!("bucket {bucket} created"))
    } else {
        println_out(&format!("bucket {bucket} already exists"))
    }
}

/// Human-readable rendering of use-case errors.
fn describe(error: dz_app::AppError) -> anyhow::Error {
    match error {
        dz_app::AppError::Validation(violations) => {
            let list: Vec<String> = violations
                .iter()
                .map(|v| format!("{}: {}", v.field, v.violation.code()))
                .collect();
            anyhow::anyhow!("invalid input ({})", list.join(", "))
        }
        other => anyhow::anyhow!(other),
    }
}

fn read_password() -> anyhow::Result<SecretString> {
    let mut line = String::new();
    std::io::stdin().lock().read_line(&mut line)?;
    let password = line.trim_end_matches(['\r', '\n']).to_owned();
    anyhow::ensure!(!password.is_empty(), "no password on stdin");
    Ok(SecretString::from(password))
}

fn gen_signing_key(kid: &str, out_dir: &std::path::Path) -> anyhow::Result<()> {
    anyhow::ensure!(
        !kid.is_empty()
            && kid.len() <= 64
            && kid.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-')),
        "key id must be 1-64 characters of [A-Za-z0-9._-]"
    );
    std::fs::create_dir_all(out_dir)?;
    let path = out_dir.join(format!("{kid}.pem"));
    let pem = jwt::generate_key_pem()?;
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&path)
        .map_err(|e| anyhow::anyhow!("cannot create {} (refusing to overwrite): {e}", path.display()))?;
    file.write_all(pem.as_bytes())?;
    println_out(&format!(
        "wrote {}\nset DZ_AUTH__SIGNING_KEYS_DIR={} and DZ_AUTH__ACTIVE_KEY_ID={kid}",
        path.display(),
        out_dir.display()
    ))
}

#[allow(clippy::print_stdout)]
fn println_out(message: &str) -> anyhow::Result<()> {
    println!("{message}");
    Ok(())
}

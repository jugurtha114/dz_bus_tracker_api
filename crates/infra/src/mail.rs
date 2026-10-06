//! E-mail delivery: SMTP (lettre, rustls) or a log-only transport for development.

use std::time::Duration;

use async_trait::async_trait;
use dz_app::ports::{EmailMessage, Mailer};
use dz_app::{AppError, AppResult};
use dz_config::{EmailSettings, EmailTransport};
use lettre::message::{Mailbox, MultiPart};
use lettre::{AsyncSmtpTransport, AsyncTransport, Message, Tokio1Executor};
use secrecy::ExposeSecret;

/// Builds the mailer selected by the configuration.
pub fn build_mailer(settings: &EmailSettings) -> anyhow::Result<std::sync::Arc<dyn Mailer>> {
    let from: Mailbox = settings
        .from
        .parse()
        .map_err(|e| anyhow::anyhow!("invalid email.from `{}`: {e}", settings.from))?;
    Ok(match settings.transport {
        EmailTransport::Log => std::sync::Arc::new(LogMailer { from }),
        EmailTransport::Smtp => {
            let url = settings
                .smtp_url
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("email.smtp_url is required"))?;
            let transport = AsyncSmtpTransport::<Tokio1Executor>::from_url(url.expose_secret())?
                .timeout(Some(Duration::from_secs(settings.timeout_secs)))
                .build();
            std::sync::Arc::new(SmtpMailer { transport, from })
        }
    })
}

fn build_message(from: &Mailbox, message: &EmailMessage) -> AppResult<Message> {
    let to: Mailbox = message.to.parse().map_err(AppError::internal)?;
    Message::builder()
        .from(from.clone())
        .to(to)
        .subject(&message.subject)
        .multipart(MultiPart::alternative_plain_html(
            message.text_body.clone(),
            message.html_body.clone(),
        ))
        .map_err(AppError::internal)
}

/// Sends through an SMTP relay.
pub struct SmtpMailer {
    transport: AsyncSmtpTransport<Tokio1Executor>,
    from: Mailbox,
}

#[async_trait]
impl Mailer for SmtpMailer {
    async fn send(&self, message: &EmailMessage) -> AppResult<()> {
        let email = build_message(&self.from, message)?;
        self.transport.send(email).await.map_err(|e| {
            tracing::warn!(error = %e, "SMTP delivery failed");
            AppError::Unavailable("smtp")
        })?;
        metrics::counter!("dz_emails_sent_total").increment(1);
        Ok(())
    }
}

/// Logs messages instead of sending them (forbidden in production by configuration).
pub struct LogMailer {
    from: Mailbox,
}

#[async_trait]
impl Mailer for LogMailer {
    async fn send(&self, message: &EmailMessage) -> AppResult<()> {
        // Validate exactly like the SMTP path so that bad addresses fail in development too.
        build_message(&self.from, message)?;
        tracing::info!(
            to = %message.to,
            subject = %message.subject,
            body = %message.text_body,
            "e-mail (log transport, not sent)"
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dz_domain::Lang;

    #[tokio::test]
    async fn log_mailer_accepts_valid_messages_and_rejects_bad_addresses() {
        let settings = EmailSettings::default();
        let mailer = build_mailer(&settings).unwrap();
        let mut msg = EmailMessage {
            to: "a@example.dz".into(),
            subject: "s".into(),
            text_body: "t".into(),
            html_body: "<p>t</p>".into(),
            lang: Lang::Fr,
        };
        mailer.send(&msg).await.unwrap();
        msg.to = "not an address".into();
        assert!(mailer.send(&msg).await.is_err());
    }
}

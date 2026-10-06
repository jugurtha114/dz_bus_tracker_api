//! Process signal handling for graceful shutdown.

use tokio_util::sync::CancellationToken;

/// Cancels `token` on SIGTERM (container stop) or SIGINT (Ctrl-C).
pub fn cancel_on_signal(token: CancellationToken) {
    tokio::spawn(async move {
        wait_for_signal().await;
        tracing::info!("shutdown signal received");
        token.cancel();
    });
}

#[cfg(unix)]
async fn wait_for_signal() {
    use tokio::signal::unix::{SignalKind, signal};
    match (signal(SignalKind::terminate()), signal(SignalKind::interrupt())) {
        (Ok(mut term), Ok(mut int)) => {
            tokio::select! {
                _ = term.recv() => {}
                _ = int.recv() => {}
            }
        }
        _ => {
            tracing::error!("cannot install signal handlers; falling back to Ctrl-C only");
            let _ = tokio::signal::ctrl_c().await;
        }
    }
}

#[cfg(not(unix))]
async fn wait_for_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

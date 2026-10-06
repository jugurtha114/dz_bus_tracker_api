//! Client IP resolution behind reverse proxies.
//!
//! `X-Forwarded-For` / `X-Real-IP` are trusted only when the TCP peer is a configured proxy.
//! The chain is walked from the right (closest proxy first) and the first address that is not
//! itself a trusted proxy is the client. Anything else uses the peer address, so a client cannot
//! spoof its address (legacy defect L-12).

use std::net::{IpAddr, SocketAddr};

use axum::extract::{ConnectInfo, Request};
use axum::http::HeaderMap;
use axum::middleware::Next;
use axum::response::Response;
use ipnet::IpNet;

/// The resolved client address.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ClientIp(pub IpAddr);

/// Resolves the client address from the peer and the forwarding headers.
#[must_use]
pub fn resolve(peer: IpAddr, headers: &HeaderMap, trusted: &[IpNet]) -> IpAddr {
    let is_trusted = |ip: &IpAddr| trusted.iter().any(|net| net.contains(ip));
    if !is_trusted(&peer) {
        return peer;
    }
    let forwarded: Vec<IpAddr> = headers
        .get_all("x-forwarded-for")
        .iter()
        .filter_map(|v| v.to_str().ok())
        .flat_map(|v| v.split(','))
        .filter_map(|part| part.trim().parse::<IpAddr>().ok())
        .collect();
    if let Some(client) = forwarded.iter().rev().find(|ip| !is_trusted(ip)) {
        return *client;
    }
    headers
        .get("x-real-ip")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.trim().parse::<IpAddr>().ok())
        .or_else(|| forwarded.first().copied())
        .unwrap_or(peer)
}

pub async fn client_ip(
    axum::extract::State(trusted): axum::extract::State<std::sync::Arc<Vec<IpNet>>>,
    mut request: Request,
    next: Next,
) -> Response {
    let peer = request.extensions().get::<ConnectInfo<SocketAddr>>().map(|c| c.0.ip());
    if let Some(peer) = peer {
        let ip = resolve(peer, request.headers(), &trusted);
        request.extensions_mut().insert(ClientIp(ip));
    }
    next.run(request).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    fn trusted() -> Vec<IpNet> {
        vec!["10.0.0.0/8".parse().unwrap()]
    }

    fn headers(xff: &str) -> HeaderMap {
        let mut h = HeaderMap::new();
        h.insert("x-forwarded-for", HeaderValue::from_str(xff).unwrap());
        h
    }

    #[test]
    fn untrusted_peers_cannot_spoof() {
        let peer: IpAddr = "203.0.113.9".parse().unwrap();
        assert_eq!(resolve(peer, &headers("1.2.3.4"), &trusted()), peer);
    }

    #[test]
    fn trusted_proxy_chain_is_walked_from_the_right() {
        let peer: IpAddr = "10.0.0.2".parse().unwrap();
        let ip = resolve(peer, &headers("6.6.6.6, 198.51.100.7, 10.0.0.5"), &trusted());
        assert_eq!(ip, "198.51.100.7".parse::<IpAddr>().unwrap(), "left-most entries are client-controlled");
    }

    #[test]
    fn falls_back_to_real_ip_then_peer() {
        let peer: IpAddr = "10.0.0.2".parse().unwrap();
        let mut h = HeaderMap::new();
        h.insert("x-real-ip", HeaderValue::from_static("192.0.2.1"));
        assert_eq!(resolve(peer, &h, &trusted()), "192.0.2.1".parse::<IpAddr>().unwrap());
        assert_eq!(resolve(peer, &HeaderMap::new(), &trusted()), peer);
    }
}

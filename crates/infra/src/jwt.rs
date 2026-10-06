//! EdDSA (Ed25519) access tokens with key rotation.
//!
//! Keys live in a directory as PKCS#8 PEM files named `<kid>.pem`. Every key verifies tokens;
//! only the active one signs. Rotation: add a new key file, switch `DZ_AUTH__ACTIVE_KEY_ID`,
//! keep the old file until the last token it signed has expired (access-token lifetime), then
//! delete it. The public keys are published as a JWKS so that third parties can verify tokens
//! without calling the API.

use std::collections::HashMap;
use std::path::Path;

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use chrono::{DateTime, Utc};
use dz_app::AppError;
use dz_app::ports::{AccessClaims, AccessTokenCodec};
use dz_app::AuthFailure;
use dz_domain::Lang;
use dz_domain::ids::{SessionId, UserId};
use dz_domain::user::Role;
use ed25519_dalek::SigningKey;
use ed25519_dalek::pkcs8::spki::der::pem::LineEnding;
use ed25519_dalek::pkcs8::{DecodePrivateKey, EncodePrivateKey};
use jsonwebtoken::{Algorithm, DecodingKey, EncodingKey, Header, Validation};
use rand::Rng;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use uuid::Uuid;

/// Accepted clock difference when checking `exp` and `iat`.
const LEEWAY_SECS: i64 = 30;

#[derive(Debug, Serialize, Deserialize)]
struct JwtClaims {
    iss: String,
    aud: String,
    sub: UserId,
    sid: SessionId,
    role: Role,
    lang: Lang,
    iat: i64,
    exp: i64,
    jti: Uuid,
}

struct LoadedKey {
    encoding: EncodingKey,
    decoding: DecodingKey,
    jwk: Value,
}

/// Signs and verifies access tokens.
pub struct JwtCodec {
    issuer: String,
    audience: String,
    active_kid: String,
    active: EncodingKey,
    verifiers: HashMap<String, DecodingKey>,
    jwks: Value,
}

impl std::fmt::Debug for JwtCodec {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("JwtCodec")
            .field("issuer", &self.issuer)
            .field("active_kid", &self.active_kid)
            .field("kids", &self.verifiers.keys().collect::<Vec<_>>())
            .finish_non_exhaustive()
    }
}

fn load_key(kid: &str, pem: &str) -> anyhow::Result<LoadedKey> {
    let signing = SigningKey::from_pkcs8_pem(pem)
        .map_err(|e| anyhow::anyhow!("key `{kid}` is not an Ed25519 PKCS#8 PEM: {e}"))?;
    let x = URL_SAFE_NO_PAD.encode(signing.verifying_key().to_bytes());
    Ok(LoadedKey {
        encoding: EncodingKey::from_ed_pem(pem.as_bytes())?,
        decoding: DecodingKey::from_ed_components(&x)?,
        jwk: json!({ "kty": "OKP", "crv": "Ed25519", "x": x, "kid": kid, "alg": "EdDSA", "use": "sig" }),
    })
}

/// Generates a new Ed25519 private key as PKCS#8 PEM.
pub fn generate_key_pem() -> anyhow::Result<String> {
    let mut seed = [0u8; 32];
    rand::rng().fill_bytes(&mut seed);
    let key = SigningKey::from_bytes(&seed);
    let pem = key.to_pkcs8_pem(LineEnding::LF).map_err(|e| anyhow::anyhow!("{e}"))?;
    Ok(pem.to_string())
}

/// Valid key ids: 1–64 chars of `[A-Za-z0-9._-]`.
fn valid_kid(kid: &str) -> bool {
    !kid.is_empty()
        && kid.len() <= 64
        && kid.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-'))
}

impl JwtCodec {
    /// Loads every `*.pem` in `dir`; `active_kid` must be one of them.
    pub fn from_dir(
        dir: &Path,
        active_kid: &str,
        issuer: &str,
        audience: &str,
    ) -> anyhow::Result<Self> {
        let mut keys = Vec::new();
        for entry in std::fs::read_dir(dir)
            .map_err(|e| anyhow::anyhow!("cannot read signing key directory {}: {e}", dir.display()))?
        {
            let path = entry?.path();
            if path.extension().and_then(|e| e.to_str()) != Some("pem") {
                continue;
            }
            let Some(kid) = path.file_stem().and_then(|s| s.to_str()).map(str::to_owned) else {
                continue;
            };
            anyhow::ensure!(valid_kid(&kid), "invalid key id `{kid}` (file {})", path.display());
            let pem = std::fs::read_to_string(&path)?;
            keys.push((kid, pem));
        }
        Self::from_pems(keys, active_kid, issuer, audience)
    }

    /// Builds a codec from `(kid, pem)` pairs.
    pub fn from_pems(
        pems: Vec<(String, String)>,
        active_kid: &str,
        issuer: &str,
        audience: &str,
    ) -> anyhow::Result<Self> {
        let mut verifiers = HashMap::new();
        let mut jwks = Vec::new();
        let mut active = None;
        for (kid, pem) in pems {
            let key = load_key(&kid, &pem)?;
            if kid == active_kid {
                active = Some(key.encoding);
            }
            jwks.push(key.jwk);
            verifiers.insert(kid, key.decoding);
        }
        let active = active.ok_or_else(|| {
            anyhow::anyhow!("active signing key `{active_kid}` not found among the loaded keys")
        })?;
        Ok(Self {
            issuer: issuer.to_owned(),
            audience: audience.to_owned(),
            active_kid: active_kid.to_owned(),
            active,
            verifiers,
            jwks: json!({ "keys": jwks }),
        })
    }

    /// A throw-away key for development and tests. Tokens die with the process.
    pub fn ephemeral(issuer: &str, audience: &str) -> anyhow::Result<Self> {
        let kid = format!("ephemeral-{}", &Uuid::new_v4().simple().to_string()[..8]);
        Self::from_pems(vec![(kid.clone(), generate_key_pem()?)], &kid, issuer, audience)
    }

    /// The public keys as a JSON Web Key Set.
    #[must_use]
    pub fn jwks(&self) -> &Value {
        &self.jwks
    }

    #[must_use]
    pub fn active_kid(&self) -> &str {
        &self.active_kid
    }
}

impl AccessTokenCodec for JwtCodec {
    fn issue(&self, claims: &AccessClaims) -> Result<String, AppError> {
        let mut header = Header::new(Algorithm::EdDSA);
        header.kid = Some(self.active_kid.clone());
        header.typ = Some("JWT".to_owned());
        let claims = JwtClaims {
            iss: self.issuer.clone(),
            aud: self.audience.clone(),
            sub: claims.sub,
            sid: claims.sid,
            role: claims.role,
            lang: claims.lang,
            iat: claims.iat,
            exp: claims.exp,
            jti: claims.jti,
        };
        jsonwebtoken::encode(&header, &claims, &self.active).map_err(AppError::internal)
    }

    fn verify(&self, token: &str, now: DateTime<Utc>) -> Result<AccessClaims, AuthFailure> {
        if token.len() > 4096 {
            return Err(AuthFailure::TokenInvalid);
        }
        let header = jsonwebtoken::decode_header(token).map_err(|_| AuthFailure::TokenInvalid)?;
        if header.alg != Algorithm::EdDSA {
            return Err(AuthFailure::TokenInvalid);
        }
        let key = header
            .kid
            .as_deref()
            .and_then(|kid| self.verifiers.get(kid))
            .ok_or(AuthFailure::TokenInvalid)?;
        let mut validation = Validation::new(Algorithm::EdDSA);
        validation.set_issuer(&[&self.issuer]);
        validation.set_audience(&[&self.audience]);
        validation.set_required_spec_claims(&["exp", "iat", "iss", "aud", "sub"]);
        // Expiry is checked below against the injected clock.
        validation.validate_exp = false;
        let data = jsonwebtoken::decode::<JwtClaims>(token, key, &validation)
            .map_err(|_| AuthFailure::TokenInvalid)?;
        let claims = data.claims;
        let now = now.timestamp();
        if claims.iat > now + LEEWAY_SECS || claims.exp <= claims.iat {
            return Err(AuthFailure::TokenInvalid);
        }
        if claims.exp + LEEWAY_SECS <= now {
            return Err(AuthFailure::TokenExpired);
        }
        if !claims.role.is_user_role() {
            return Err(AuthFailure::TokenInvalid);
        }
        Ok(AccessClaims {
            sub: claims.sub,
            sid: claims.sid,
            role: claims.role,
            lang: claims.lang,
            iat: claims.iat,
            exp: claims.exp,
            jti: claims.jti,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn claims(now: DateTime<Utc>) -> AccessClaims {
        AccessClaims {
            sub: UserId::generate(),
            sid: SessionId::generate(),
            role: Role::Passenger,
            lang: Lang::Ar,
            iat: now.timestamp(),
            exp: now.timestamp() + 900,
            jti: Uuid::now_v7(),
        }
    }

    #[test]
    fn issues_and_verifies() {
        let codec = JwtCodec::ephemeral("dz", "api").unwrap();
        let now = Utc::now();
        let c = claims(now);
        let token = codec.issue(&c).unwrap();
        assert_eq!(codec.verify(&token, now).unwrap(), c);
        let jwks = codec.jwks();
        assert_eq!(jwks["keys"][0]["kty"], "OKP");
        assert_eq!(jwks["keys"][0]["kid"], codec.active_kid());
    }

    #[test]
    fn rejects_expired_foreign_and_tampered_tokens() {
        let codec = JwtCodec::ephemeral("dz", "api").unwrap();
        let now = Utc::now();
        let token = codec.issue(&claims(now)).unwrap();
        let later = now + chrono::Duration::seconds(900 + LEEWAY_SECS + 1);
        assert_eq!(codec.verify(&token, later), Err(AuthFailure::TokenExpired));

        let other = JwtCodec::ephemeral("dz", "api").unwrap();
        assert_eq!(other.verify(&token, now), Err(AuthFailure::TokenInvalid), "unknown kid");

        let wrong_audience = JwtCodec::from_pems(
            vec![("k".into(), generate_key_pem().unwrap())],
            "k",
            "dz",
            "other",
        )
        .unwrap();
        let foreign = wrong_audience.issue(&claims(now)).unwrap();
        assert_eq!(codec.verify(&foreign, now), Err(AuthFailure::TokenInvalid));

        let mut parts: Vec<String> = token.split('.').map(str::to_owned).collect();
        parts[1] = URL_SAFE_NO_PAD.encode(br#"{"sub":"x"}"#);
        assert_eq!(codec.verify(&parts.join("."), now), Err(AuthFailure::TokenInvalid));
        assert_eq!(codec.verify("not.a.jwt", now), Err(AuthFailure::TokenInvalid));
    }

    #[test]
    fn rotation_keeps_old_keys_verifying() {
        let old = generate_key_pem().unwrap();
        let new = generate_key_pem().unwrap();
        let before = JwtCodec::from_pems(vec![("2026-09".into(), old.clone())], "2026-09", "dz", "api")
            .unwrap();
        let now = Utc::now();
        let token = before.issue(&claims(now)).unwrap();
        let after = JwtCodec::from_pems(
            vec![("2026-09".into(), old), ("2026-10".into(), new)],
            "2026-10",
            "dz",
            "api",
        )
        .unwrap();
        assert!(after.verify(&token, now).is_ok());
        assert_eq!(after.jwks()["keys"].as_array().unwrap().len(), 2);
        assert!(JwtCodec::from_pems(vec![], "missing", "dz", "api").is_err());
    }

    #[test]
    fn key_ids_are_restricted() {
        assert!(valid_kid("2026-10.a_b"));
        assert!(!valid_kid("../etc"));
        assert!(!valid_kid(""));
    }
}

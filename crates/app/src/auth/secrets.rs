//! Opaque secrets (refresh tokens, reset tokens, API keys): generated from the OS CSPRNG,
//! shown to the client once, stored only as SHA-256 hashes.

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use rand::Rng;
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

use crate::ports::TokenHash;

/// Bytes of entropy in every secret (256 bits).
const SECRET_BYTES: usize = 32;

/// A freshly generated secret: the plaintext goes to the client, the hash to the database.
pub struct GeneratedSecret {
    pub plaintext: String,
    pub hash: TokenHash,
}

impl std::fmt::Debug for GeneratedSecret {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("GeneratedSecret").finish_non_exhaustive()
    }
}

/// Generates `<prefix>_<43 base64url chars>`. The prefix makes leaked secrets recognisable by
/// secret scanners (`dzr` refresh token, `dzp` password reset, `dzk` API key).
#[must_use]
pub fn generate(prefix: &str) -> GeneratedSecret {
    let plaintext = format!("{prefix}_{}", random_b64(SECRET_BYTES));
    let hash = hash(&plaintext);
    GeneratedSecret { plaintext, hash }
}

/// `n` random bytes encoded as unpadded base64url.
#[must_use]
pub fn random_b64(n: usize) -> String {
    let mut bytes = vec![0u8; n];
    rand::rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

/// SHA-256 of a secret. A fast hash is appropriate: secrets carry 256 bits of entropy, so
/// brute force is infeasible without a slow KDF.
#[must_use]
pub fn hash(secret: &str) -> TokenHash {
    TokenHash(Sha256::digest(secret.as_bytes()).into())
}

/// Constant-time equality of two hashes.
#[must_use]
pub fn hashes_equal(a: &TokenHash, b: &TokenHash) -> bool {
    a.0.ct_eq(&b.0).into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secrets_are_prefixed_unique_and_hash_consistently() {
        let a = generate("dzr");
        let b = generate("dzr");
        assert!(a.plaintext.starts_with("dzr_"));
        assert_eq!(a.plaintext.len(), 4 + 43);
        assert_ne!(a.plaintext, b.plaintext);
        assert!(hashes_equal(&hash(&a.plaintext), &a.hash));
        assert!(!hashes_equal(&a.hash, &b.hash));
    }
}

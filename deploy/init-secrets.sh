#!/bin/sh
# Generates the secrets used by compose.yaml into deploy/secrets/ (never overwrites).
#
#   deploy/secrets/                0700  only the operator can enter it on the host
#     postgres_password            0644  readable inside the containers (non-root users);
#     database_url                       the 0700 parent keeps them private on the host
#     valkey.acl, valkey_url
#     smtp_url                           placeholder: edit before starting
#     s3_access_key, s3_secret_key       object storage credentials (bundled RustFS, or replace
#                                        them with the keys of your S3 provider)
#     jwt/<kid>.pem                      Ed25519 signing key (PKCS#8 PEM)
#
# Requires: openssl (1.1.1+), sha256sum or shasum.
set -eu

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
dir="$here/secrets"
umask 077
mkdir -p "$dir/jwt"
chmod 0700 "$dir"
chmod 0755 "$dir/jwt"

random() { openssl rand -hex 32; }
sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$1" | sha256sum | cut -d' ' -f1
    else
        printf '%s' "$1" | shasum -a 256 | cut -d' ' -f1
    fi
}
# write <name> <content>: creates the file once, readable by the containers.
write() {
    if [ -e "$dir/$1" ]; then
        echo "kept      $1"
        return 0
    fi
    printf '%s\n' "$2" > "$dir/$1"
    chmod 0644 "$dir/$1"
    echo "created   $1"
}

if [ ! -e "$dir/postgres_password" ]; then
    pg_password=$(random)
    write postgres_password "$pg_password"
    write database_url "postgres://dzbus:${pg_password}@postgres:5432/dzbus"
else
    echo "kept      postgres_password, database_url"
fi

if [ ! -e "$dir/valkey.acl" ]; then
    valkey_password=$(random)
    # `default` is disabled; the application user may only touch its own key prefix and
    # cannot run administrative or dangerous commands; `healthcheck` may only PING.
    write valkey.acl "user default off
user healthcheck on nopass -@all +ping
user dzbus on #$(sha256 "$valkey_password") ~dz:* &dz:* +@all -@admin -@dangerous"
    write valkey_url "redis://dzbus:${valkey_password}@valkey:6379/0"
else
    echo "kept      valkey.acl, valkey_url"
fi

write smtp_url "smtps://USER:PASSWORD@smtp.example.com:465"

# Root credentials of the bundled RustFS, also used by the API and the worker.
write s3_access_key "dz-$(openssl rand -hex 8)"
write s3_secret_key "$(random)"

kid="${1:-$(date -u +%Y-%m)}"
if ls "$dir"/jwt/*.pem >/dev/null 2>&1; then
    echo "kept      jwt/ ($(cd "$dir/jwt" && ls -- *.pem | tr '\n' ' '))"
else
    openssl genpkey -algorithm ed25519 -out "$dir/jwt/$kid.pem"
    chmod 0644 "$dir/jwt/$kid.pem"
    echo "created   jwt/$kid.pem"
    echo
    echo "Set DZ_AUTH__ACTIVE_KEY_ID=$kid in deploy/dz.env"
fi

echo
echo "Edit $dir/smtp_url before starting the stack."

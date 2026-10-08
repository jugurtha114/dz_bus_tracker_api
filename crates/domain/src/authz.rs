//! Central authorization policy.
//!
//! * [`Permission`] is the closed list of coarse capabilities.
//! * [`role_permissions`] is the **only** place where roles are mapped to permissions.
//! * [`Policy::authorize`] adds resource rules (ownership, state) on top of permissions.
//!
//! Everything is deny-by-default: an actor can do something only if a rule below explicitly
//! allows it. Adding a role or a permission means editing this module only; handlers declare
//! the permission they need and use-cases call [`Policy::authorize`].

use std::fmt;

use serde::{Deserialize, Serialize};

use crate::error::DenyReason;
use crate::ids::{ApiKeyId, SessionId, UserId};
use crate::upload::UploadPurpose;
use crate::user::Role;

macro_rules! permissions {
    ($($(#[$meta:meta])* $variant:ident = $code:literal),+ $(,)?) => {
        /// A typed capability. The string code is stable and used for API-key scopes.
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
        #[repr(u8)]
        pub enum Permission {
            $($(#[$meta])* $variant),+
        }

        impl Permission {
            pub const ALL: &'static [Self] = &[$(Self::$variant),+];

            #[must_use]
            pub const fn code(self) -> &'static str {
                match self {
                    $(Self::$variant => $code),+
                }
            }

            #[must_use]
            pub fn from_code(code: &str) -> Option<Self> {
                match code {
                    $($code => Some(Self::$variant),)+
                    _ => None,
                }
            }
        }
    };
}

permissions! {
    // --- Accounts & identity -------------------------------------------------------------
    /// Read/update one's own account, profile, sessions, password and device tokens.
    AccountSelfManage = "account:self",
    /// Read any user account.
    UserRead = "user:read",
    /// Activate/deactivate users and change their role.
    UserManage = "user:manage",
    /// Create, list and revoke machine-to-machine API keys.
    ApiKeyManage = "api_key:manage",
    /// Read the append-only audit log.
    AuditLogRead = "audit_log:read",

    // --- Catalogue (lines, stops, schedules, disruptions) --------------------------------
    /// Read the public catalogue.
    CatalogRead = "catalog:read",
    LineWrite = "line:write",
    StopWrite = "stop:write",
    ScheduleWrite = "schedule:write",
    DisruptionWrite = "disruption:write",

    // --- Drivers & buses ------------------------------------------------------------------
    /// Apply to become a driver (or re-apply after a rejection).
    DriverApply = "driver:apply",
    /// Read any driver profile (drivers can always read their own).
    DriverRead = "driver:read",
    /// Approve, reject or suspend drivers.
    DriverReview = "driver:review",
    /// Register and edit one's own buses (as a driver).
    BusRegister = "bus:register",
    /// Read bus details.
    BusRead = "bus:read",
    /// Approve, activate/deactivate and edit any bus.
    BusManage = "bus:manage",

    // --- Real-time tracking ---------------------------------------------------------------
    /// Read live positions, ETAs and active buses.
    TrackingRead = "tracking:read",
    /// Publish location updates for an assigned bus.
    TrackingPublish = "tracking:publish",
    /// Start and end one's own trips.
    TripManage = "trip:manage",
    /// Read all trips and their history.
    TripReadAll = "trip:read_all",
    /// Report an anomaly.
    AnomalyReport = "anomaly:report",
    /// Resolve anomalies.
    AnomalyResolve = "anomaly:resolve",

    // --- Passenger features ---------------------------------------------------------------
    /// Join or leave a bus waiting list.
    WaitingListJoin = "waiting_list:join",
    /// Submit crowd-sourced waiting counts.
    WaitingReportSubmit = "waiting_report:submit",
    /// Verify crowd-sourced waiting counts (drivers at the stop).
    WaitingReportVerify = "waiting_report:verify",
    /// Rate a driver (subject to eligibility rules).
    DriverRate = "driver:rate",
    /// Record on-board passenger counts.
    PassengerCountRecord = "passenger_count:record",

    // --- Notifications ----------------------------------------------------------------------
    /// Send notifications to other users (broadcasts, targeted messages).
    NotificationSend = "notification:send",

    // --- Gamification & analytics -----------------------------------------------------------
    /// Read leaderboards and one's own rewards.
    RewardsRead = "rewards:read",
    /// Purchase premium features with virtual currency.
    PremiumPurchase = "premium:purchase",
    /// Credit/debit any user's virtual currency.
    CurrencyAdjust = "currency:adjust",
    /// Read operational analytics dashboards.
    AnalyticsRead = "analytics:read",
    /// Use the offline cache/sync endpoints.
    OfflineSync = "offline:sync",
}

impl Permission {
    const fn bit(self) -> u64 {
        1u64 << (self as u8)
    }

    /// Whether the permission may be granted to a machine-to-machine API key.
    ///
    /// Identity administration and anything that only makes sense for a human acting on their
    /// own behalf (self-service, ratings, purchases, waiting lists) is excluded.
    #[must_use]
    pub const fn grantable_to_service(self) -> bool {
        matches!(
            self,
            Self::CatalogRead
                | Self::LineWrite
                | Self::StopWrite
                | Self::ScheduleWrite
                | Self::DisruptionWrite
                | Self::BusRead
                | Self::TrackingRead
                | Self::TripReadAll
                | Self::NotificationSend
                | Self::AnalyticsRead
                | Self::AuditLogRead
        )
    }
}

impl fmt::Display for Permission {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.code())
    }
}

impl Serialize for Permission {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(self.code())
    }
}

impl<'de> Deserialize<'de> for Permission {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let code = String::deserialize(deserializer)?;
        Self::from_code(&code)
            .ok_or_else(|| serde::de::Error::custom(format!("unknown permission `{code}`")))
    }
}

/// A compact set of permissions.
#[derive(Clone, Copy, PartialEq, Eq, Hash, Default)]
pub struct PermissionSet(u64);

impl PermissionSet {
    pub const EMPTY: Self = Self(0);

    #[must_use]
    pub const fn of(perms: &[Permission]) -> Self {
        let mut bits = 0;
        let mut i = 0;
        while i < perms.len() {
            bits |= perms[i].bit();
            i += 1;
        }
        Self(bits)
    }

    #[must_use]
    pub const fn contains(self, p: Permission) -> bool {
        self.0 & p.bit() != 0
    }

    #[must_use]
    pub const fn union(self, other: Self) -> Self {
        Self(self.0 | other.0)
    }

    #[must_use]
    pub const fn intersection(self, other: Self) -> Self {
        Self(self.0 & other.0)
    }

    #[must_use]
    pub const fn is_empty(self) -> bool {
        self.0 == 0
    }

    pub fn iter(self) -> impl Iterator<Item = Permission> {
        Permission::ALL.iter().copied().filter(move |p| self.contains(*p))
    }
}

impl fmt::Debug for PermissionSet {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_set().entries(self.iter().map(Permission::code)).finish()
    }
}

impl FromIterator<Permission> for PermissionSet {
    fn from_iter<I: IntoIterator<Item = Permission>>(iter: I) -> Self {
        Self(iter.into_iter().fold(0, |acc, p| acc | p.bit()))
    }
}

/// Permissions of unauthenticated callers.
pub const ANONYMOUS_PERMISSIONS: PermissionSet =
    PermissionSet::of(&[Permission::CatalogRead, Permission::TrackingRead, Permission::BusRead]);

const AUTHENTICATED_BASE: PermissionSet = PermissionSet::of(&[
    Permission::AccountSelfManage,
    Permission::CatalogRead,
    Permission::TrackingRead,
    Permission::BusRead,
    Permission::AnomalyReport,
    Permission::RewardsRead,
    Permission::PremiumPurchase,
    Permission::OfflineSync,
]);

const PASSENGER_EXTRA: PermissionSet = PermissionSet::of(&[
    Permission::DriverApply,
    Permission::WaitingListJoin,
    Permission::WaitingReportSubmit,
    Permission::DriverRate,
]);

const DRIVER_EXTRA: PermissionSet = PermissionSet::of(&[
    // Re-applying after a rejection goes through the same capability.
    Permission::DriverApply,
    Permission::BusRegister,
    Permission::TrackingPublish,
    Permission::TripManage,
    Permission::WaitingReportVerify,
    Permission::PassengerCountRecord,
]);

const ADMIN_EXTRA: PermissionSet = PermissionSet::of(&[
    Permission::UserRead,
    Permission::UserManage,
    Permission::ApiKeyManage,
    Permission::AuditLogRead,
    Permission::LineWrite,
    Permission::StopWrite,
    Permission::ScheduleWrite,
    Permission::DisruptionWrite,
    Permission::DriverRead,
    Permission::DriverReview,
    Permission::BusManage,
    Permission::TripReadAll,
    Permission::AnomalyResolve,
    Permission::NotificationSend,
    Permission::CurrencyAdjust,
    Permission::AnalyticsRead,
]);

/// The single role → permission mapping.
///
/// `Service` returns the empty set: API keys carry explicit scopes instead.
#[must_use]
pub const fn role_permissions(role: Role) -> PermissionSet {
    match role {
        Role::Admin => AUTHENTICATED_BASE.union(ADMIN_EXTRA),
        Role::Driver => AUTHENTICATED_BASE.union(DRIVER_EXTRA),
        Role::Passenger => AUTHENTICATED_BASE.union(PASSENGER_EXTRA),
        Role::Service => PermissionSet::EMPTY,
    }
}

/// Who is performing an action.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Actor {
    Anonymous,
    User { id: UserId, role: Role, session_id: SessionId },
    Service { key_id: ApiKeyId, scopes: PermissionSet },
}

impl Actor {
    #[must_use]
    pub fn permissions(&self) -> PermissionSet {
        match self {
            Self::Anonymous => ANONYMOUS_PERMISSIONS,
            Self::User { role, .. } => role_permissions(*role),
            // Defence in depth: scopes are filtered at creation *and* here.
            Self::Service { scopes, .. } => scopes
                .iter()
                .filter(|p| p.grantable_to_service())
                .collect::<PermissionSet>()
                .union(ANONYMOUS_PERMISSIONS),
        }
    }

    #[must_use]
    pub fn has(&self, permission: Permission) -> bool {
        self.permissions().contains(permission)
    }

    #[must_use]
    pub const fn user_id(&self) -> Option<UserId> {
        match self {
            Self::User { id, .. } => Some(*id),
            _ => None,
        }
    }

    #[must_use]
    pub const fn role(&self) -> Option<Role> {
        match self {
            Self::User { role, .. } => Some(*role),
            Self::Service { .. } => Some(Role::Service),
            Self::Anonymous => None,
        }
    }

    /// Requires the coarse permission, distinguishing "log in first" from "not allowed".
    pub fn require(&self, permission: Permission) -> Result<(), DenyReason> {
        if self.has(permission) {
            Ok(())
        } else if matches!(self, Self::Anonymous) {
            Err(DenyReason::AuthenticationRequired)
        } else {
            Err(DenyReason::MissingPermission)
        }
    }
}

/// An action on a resource, carrying the facts the resource rules need.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    /// Read or update the actor's own account/profile/sessions.
    ManageOwnAccount,
    /// Read another user's account.
    ReadUser { target: UserId },
    /// Change another user's activation status or role.
    ManageUser { target: UserId },
    /// Create/list/revoke API keys.
    ManageApiKeys,
    /// Read the audit log.
    ReadAuditLog,
    /// Request a presigned upload for `purpose`. Uploads are owned by a human account, so API
    /// keys are refused whatever their scopes.
    RequestUpload { purpose: UploadPurpose },
}

/// Resource-level authorization rules.
pub struct Policy;

impl Policy {
    /// Decides whether `actor` may perform `action`. Deny by default.
    pub fn authorize(actor: &Actor, action: &Action) -> Result<(), DenyReason> {
        match action {
            Action::ManageOwnAccount => {
                actor.require(Permission::AccountSelfManage)?;
                // Self-service needs a human account to act on.
                actor.user_id().map(|_| ()).ok_or(DenyReason::MissingPermission)
            }
            Action::ReadUser { target } => {
                if actor.user_id() == Some(*target) && actor.has(Permission::AccountSelfManage) {
                    return Ok(());
                }
                actor.require(Permission::UserRead)
            }
            Action::ManageUser { target } => {
                actor.require(Permission::UserManage)?;
                // An admin cannot deactivate or demote themselves (prevents lock-out of the
                // last administrator by accident).
                if actor.user_id() == Some(*target) {
                    return Err(DenyReason::InvalidState);
                }
                Ok(())
            }
            Action::ManageApiKeys => actor.require(Permission::ApiKeyManage),
            Action::ReadAuditLog => actor.require(Permission::AuditLogRead),
            Action::RequestUpload { purpose } => {
                let allowed = match purpose {
                    UploadPurpose::Avatar => actor.require(Permission::AccountSelfManage),
                    UploadPurpose::DriverIdCard | UploadPurpose::DriverLicense => {
                        actor.require(Permission::DriverApply)
                    }
                    UploadPurpose::BusPhoto => actor
                        .require(Permission::BusRegister)
                        .or_else(|_| actor.require(Permission::BusManage)),
                    UploadPurpose::StopPhoto => actor.require(Permission::StopWrite),
                };
                allowed?;
                actor.user_id().map(|_| ()).ok_or(DenyReason::MissingPermission)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn user(role: Role) -> Actor {
        Actor::User { id: UserId::generate(), role, session_id: SessionId::generate() }
    }

    fn service(scopes: &[Permission]) -> Actor {
        Actor::Service { key_id: ApiKeyId::generate(), scopes: PermissionSet::of(scopes) }
    }

    #[test]
    fn permission_codes_round_trip_and_fit_in_the_bitset() {
        assert!(Permission::ALL.len() <= 64);
        for p in Permission::ALL {
            assert_eq!(Permission::from_code(p.code()), Some(*p));
        }
    }

    /// Role × permission matrix. `true` = granted.
    #[test]
    fn role_permission_matrix() {
        use Permission as P;
        #[rustfmt::skip]
        let table: &[(P, bool, bool, bool, bool)] = &[
            //                         anon   pass   driver admin
            (P::AccountSelfManage,     false, true,  true,  true),
            (P::UserRead,              false, false, false, true),
            (P::UserManage,            false, false, false, true),
            (P::ApiKeyManage,          false, false, false, true),
            (P::AuditLogRead,          false, false, false, true),
            (P::CatalogRead,           true,  true,  true,  true),
            (P::LineWrite,             false, false, false, true),
            (P::StopWrite,             false, false, false, true),
            (P::ScheduleWrite,         false, false, false, true),
            (P::DisruptionWrite,       false, false, false, true),
            (P::DriverApply,           false, true,  true,  false),
            (P::DriverRead,            false, false, false, true),
            (P::DriverReview,          false, false, false, true),
            (P::BusRegister,           false, false, true,  false),
            (P::BusRead,               true,  true,  true,  true),
            (P::BusManage,             false, false, false, true),
            (P::TrackingRead,          true,  true,  true,  true),
            (P::TrackingPublish,       false, false, true,  false),
            (P::TripManage,            false, false, true,  false),
            (P::TripReadAll,           false, false, false, true),
            (P::AnomalyReport,         false, true,  true,  true),
            (P::AnomalyResolve,        false, false, false, true),
            (P::WaitingListJoin,       false, true,  false, false),
            (P::WaitingReportSubmit,   false, true,  false, false),
            (P::WaitingReportVerify,   false, false, true,  false),
            (P::DriverRate,            false, true,  false, false),
            (P::PassengerCountRecord,  false, false, true,  false),
            (P::NotificationSend,      false, false, false, true),
            (P::RewardsRead,           false, true,  true,  true),
            (P::PremiumPurchase,       false, true,  true,  true),
            (P::CurrencyAdjust,        false, false, false, true),
            (P::AnalyticsRead,         false, false, false, true),
            (P::OfflineSync,           false, true,  true,  true),
        ];
        assert_eq!(table.len(), Permission::ALL.len(), "every permission must be in the matrix");
        for (perm, anon, passenger, driver, admin) in table {
            assert_eq!(Actor::Anonymous.has(*perm), *anon, "anonymous × {perm}");
            assert_eq!(user(Role::Passenger).has(*perm), *passenger, "passenger × {perm}");
            assert_eq!(user(Role::Driver).has(*perm), *driver, "driver × {perm}");
            assert_eq!(user(Role::Admin).has(*perm), *admin, "admin × {perm}");
        }
        assert!(role_permissions(Role::Service).is_empty());
    }

    #[test]
    fn services_only_get_grantable_scopes() {
        let actor = service(&[Permission::UserManage, Permission::NotificationSend]);
        assert!(actor.has(Permission::NotificationSend));
        assert!(!actor.has(Permission::UserManage), "identity admin is never grantable");
        assert!(actor.has(Permission::CatalogRead), "services can read public data");
        assert_eq!(actor.require(Permission::UserManage), Err(DenyReason::MissingPermission));
    }

    #[test]
    fn anonymous_is_told_to_authenticate() {
        assert_eq!(
            Actor::Anonymous.require(Permission::AccountSelfManage),
            Err(DenyReason::AuthenticationRequired)
        );
    }

    /// Action × actor decision table.
    #[test]
    fn policy_decisions() {
        let admin = user(Role::Admin);
        let admin_id = admin.user_id().unwrap();
        let passenger = user(Role::Passenger);
        let passenger_id = passenger.user_id().unwrap();
        let driver = user(Role::Driver);
        let other = UserId::generate();
        let svc = service(&[Permission::AuditLogRead]);

        let deny_perm = Err(DenyReason::MissingPermission);
        let deny_auth = Err(DenyReason::AuthenticationRequired);
        let cases: Vec<(&str, &Actor, Action, Result<(), DenyReason>)> = vec![
            ("passenger manages self", &passenger, Action::ManageOwnAccount, Ok(())),
            ("driver manages self", &driver, Action::ManageOwnAccount, Ok(())),
            ("anon manages self", &Actor::Anonymous, Action::ManageOwnAccount, deny_auth),
            ("service has no self", &svc, Action::ManageOwnAccount, deny_perm),
            ("passenger reads self", &passenger, Action::ReadUser { target: passenger_id }, Ok(())),
            ("passenger reads other", &passenger, Action::ReadUser { target: other }, deny_perm),
            ("admin reads other", &admin, Action::ReadUser { target: other }, Ok(())),
            ("anon reads user", &Actor::Anonymous, Action::ReadUser { target: other }, deny_auth),
            ("admin manages other", &admin, Action::ManageUser { target: other }, Ok(())),
            (
                "admin cannot manage self",
                &admin,
                Action::ManageUser { target: admin_id },
                Err(DenyReason::InvalidState),
            ),
            ("driver manages user", &driver, Action::ManageUser { target: other }, deny_perm),
            ("admin manages keys", &admin, Action::ManageApiKeys, Ok(())),
            ("passenger manages keys", &passenger, Action::ManageApiKeys, deny_perm),
            ("service manages keys", &svc, Action::ManageApiKeys, deny_perm),
            ("admin reads audit", &admin, Action::ReadAuditLog, Ok(())),
            ("scoped service reads audit", &svc, Action::ReadAuditLog, Ok(())),
            ("driver reads audit", &driver, Action::ReadAuditLog, deny_perm),
        ];
        for (name, actor, action, expected) in cases {
            assert_eq!(Policy::authorize(actor, &action), expected, "{name}");
        }
    }

    /// Who may request an upload for which purpose (actor × purpose).
    #[test]
    fn upload_requests() {
        use UploadPurpose as U;
        let admin = user(Role::Admin);
        let passenger = user(Role::Passenger);
        let driver = user(Role::Driver);
        let writer = service(&[Permission::StopWrite, Permission::BusRead]);
        let ok = Ok(());
        let deny_perm = Err(DenyReason::MissingPermission);
        let deny_auth = Err(DenyReason::AuthenticationRequired);
        #[rustfmt::skip]
        let cases: Vec<(&str, &Actor, U, Result<(), DenyReason>)> = vec![
            ("passenger avatar",           &passenger,        U::Avatar,        ok),
            ("driver avatar",              &driver,           U::Avatar,        ok),
            ("admin avatar",               &admin,            U::Avatar,        ok),
            ("anon avatar",                &Actor::Anonymous, U::Avatar,        deny_auth),
            ("service avatar",             &writer,           U::Avatar,        deny_perm),
            ("passenger id card",          &passenger,        U::DriverIdCard,  ok),
            ("driver licence",             &driver,           U::DriverLicense, ok),
            ("admin id card",              &admin,            U::DriverIdCard,  deny_perm),
            ("passenger bus photo",        &passenger,        U::BusPhoto,      deny_perm),
            ("driver bus photo",           &driver,           U::BusPhoto,      ok),
            ("admin bus photo",            &admin,            U::BusPhoto,      ok),
            ("admin stop photo",           &admin,            U::StopPhoto,     ok),
            ("driver stop photo",          &driver,           U::StopPhoto,     deny_perm),
            ("stop:write key stop photo",  &writer,           U::StopPhoto,     deny_perm),
            ("anon stop photo",            &Actor::Anonymous, U::StopPhoto,     deny_auth),
        ];
        for (name, actor, purpose, expected) in cases {
            let action = Action::RequestUpload { purpose };
            assert_eq!(Policy::authorize(actor, &action), expected, "{name}");
        }
    }
}

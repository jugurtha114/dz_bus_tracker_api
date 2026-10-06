//! Localized texts for problem details (fr default, ar, en).
//!
//! Keys are the stable machine codes used in responses (`code` fields), so clients can also
//! localize on their side.

use dz_domain::{Lang, Violation};

/// Title and detail of a problem type.
pub struct ProblemText {
    pub title: &'static str,
    pub detail: &'static str,
}

const fn t(title: &'static str, detail: &'static str) -> ProblemText {
    ProblemText { title, detail }
}

/// Localized title/detail for a problem `code`.
#[must_use]
pub fn problem(code: &str, lang: Lang) -> ProblemText {
    use Lang::{Ar, En, Fr};
    match (code, lang) {
        ("validation_error", Fr) => t("Données invalides", "Certains champs de la requête sont invalides."),
        ("validation_error", Ar) => t("بيانات غير صالحة", "بعض حقول الطلب غير صالحة."),
        ("validation_error", En) => t("Invalid data", "Some fields of the request are invalid."),

        ("malformed_request", Fr) => t("Requête mal formée", "Le corps de la requête n'est pas un JSON valide pour ce point d'accès."),
        ("malformed_request", Ar) => t("طلب غير سليم", "محتوى الطلب ليس JSON صالحًا لهذه النقطة."),
        ("malformed_request", En) => t("Malformed request", "The request body is not valid JSON for this endpoint."),

        ("unsupported_media_type", Fr) => t("Type de contenu non pris en charge", "Utilisez « Content-Type: application/json »."),
        ("unsupported_media_type", Ar) => t("نوع محتوى غير مدعوم", "استخدم « Content-Type: application/json »."),
        ("unsupported_media_type", En) => t("Unsupported media type", "Use \"Content-Type: application/json\"."),

        ("payload_too_large", Fr) => t("Requête trop volumineuse", "Le corps de la requête dépasse la taille autorisée."),
        ("payload_too_large", Ar) => t("الطلب كبير جدًا", "حجم محتوى الطلب يتجاوز الحد المسموح."),
        ("payload_too_large", En) => t("Payload too large", "The request body exceeds the allowed size."),

        ("invalid_credentials", Fr) => t("Identifiants invalides", "Adresse e-mail ou mot de passe incorrect."),
        ("invalid_credentials", Ar) => t("بيانات اعتماد غير صالحة", "البريد الإلكتروني أو كلمة المرور غير صحيحة."),
        ("invalid_credentials", En) => t("Invalid credentials", "Incorrect e-mail address or password."),

        ("authentication_required", Fr) => t("Authentification requise", "Connectez-vous pour accéder à cette ressource."),
        ("authentication_required", Ar) => t("المصادقة مطلوبة", "سجّل الدخول للوصول إلى هذا المورد."),
        ("authentication_required", En) => t("Authentication required", "Sign in to access this resource."),

        ("token_invalid", Fr) => t("Jeton invalide", "Le jeton d'accès est invalide."),
        ("token_invalid", Ar) => t("رمز غير صالح", "رمز الوصول غير صالح."),
        ("token_invalid", En) => t("Invalid token", "The access token is invalid."),

        ("token_expired", Fr) => t("Jeton expiré", "Le jeton d'accès a expiré ; renouvelez-le."),
        ("token_expired", Ar) => t("انتهت صلاحية الرمز", "انتهت صلاحية رمز الوصول؛ يرجى تجديده."),
        ("token_expired", En) => t("Token expired", "The access token has expired; refresh it."),

        ("session_revoked", Fr) => t("Session terminée", "Cette session a été fermée ; reconnectez-vous."),
        ("session_revoked", Ar) => t("انتهت الجلسة", "تم إغلاق هذه الجلسة؛ يرجى تسجيل الدخول مجددًا."),
        ("session_revoked", En) => t("Session ended", "This session has been closed; sign in again."),

        ("refresh_token_invalid", Fr) => t("Jeton de rafraîchissement invalide", "Reconnectez-vous."),
        ("refresh_token_invalid", Ar) => t("رمز التجديد غير صالح", "يرجى تسجيل الدخول مجددًا."),
        ("refresh_token_invalid", En) => t("Invalid refresh token", "Sign in again."),

        ("refresh_token_reused", Fr) => t("Session compromise", "Un ancien jeton a été réutilisé ; la session a été fermée par sécurité."),
        ("refresh_token_reused", Ar) => t("جلسة مخترقة", "أُعيد استخدام رمز قديم؛ أُغلقت الجلسة احتياطًا."),
        ("refresh_token_reused", En) => t("Session compromised", "An old token was reused; the session was closed as a precaution."),

        ("api_key_invalid", Fr) => t("Clé d'API invalide", "La clé d'API est inconnue, expirée ou révoquée."),
        ("api_key_invalid", Ar) => t("مفتاح API غير صالح", "مفتاح API غير معروف أو منتهي أو ملغى."),
        ("api_key_invalid", En) => t("Invalid API key", "The API key is unknown, expired or revoked."),

        ("reset_token_invalid", Fr) => t("Lien invalide", "Ce lien de réinitialisation est invalide ou a expiré."),
        ("reset_token_invalid", Ar) => t("رابط غير صالح", "رابط إعادة التعيين غير صالح أو منتهي الصلاحية."),
        ("reset_token_invalid", En) => t("Invalid link", "This reset link is invalid or has expired."),

        ("forbidden", Fr) => t("Accès refusé", "Vous n'avez pas l'autorisation d'effectuer cette action."),
        ("forbidden", Ar) => t("الوصول مرفوض", "ليس لديك صلاحية تنفيذ هذا الإجراء."),
        ("forbidden", En) => t("Forbidden", "You are not allowed to perform this action."),

        ("not_found", Fr) => t("Introuvable", "La ressource demandée n'existe pas."),
        ("not_found", Ar) => t("غير موجود", "المورد المطلوب غير موجود."),
        ("not_found", En) => t("Not found", "The requested resource does not exist."),

        ("method_not_allowed", Fr) => t("Méthode non autorisée", "Cette méthode HTTP n'est pas prise en charge ici."),
        ("method_not_allowed", Ar) => t("طريقة غير مسموحة", "طريقة HTTP هذه غير مدعومة هنا."),
        ("method_not_allowed", En) => t("Method not allowed", "This HTTP method is not supported here."),

        ("email_taken", Fr) => t("Adresse déjà utilisée", "Un compte existe déjà avec cette adresse e-mail."),
        ("email_taken", Ar) => t("البريد مستخدم", "يوجد حساب بهذا البريد الإلكتروني بالفعل."),
        ("email_taken", En) => t("E-mail already used", "An account already exists with this e-mail address."),

        ("phone_taken", Fr) => t("Numéro déjà utilisé", "Ce numéro de téléphone est déjà associé à un compte."),
        ("phone_taken", Ar) => t("الرقم مستخدم", "رقم الهاتف هذا مرتبط بحساب آخر."),
        ("phone_taken", En) => t("Phone already used", "This phone number is already linked to an account."),

        ("already_exists", Fr) => t("Conflit", "La ressource existe déjà."),
        ("already_exists", Ar) => t("تعارض", "المورد موجود بالفعل."),
        ("already_exists", En) => t("Conflict", "The resource already exists."),

        ("stale_state", Fr) => t("Conflit", "La ressource a été modifiée entre-temps ; rechargez-la."),
        ("stale_state", Ar) => t("تعارض", "تم تعديل المورد في الأثناء؛ أعد تحميله."),
        ("stale_state", En) => t("Conflict", "The resource changed in the meantime; reload it."),

        ("invalid_state", Fr) => t("Action impossible", "L'état actuel de la ressource ne permet pas cette action."),
        ("invalid_state", Ar) => t("إجراء غير ممكن", "الحالة الحالية للمورد لا تسمح بهذا الإجراء."),
        ("invalid_state", En) => t("Action not possible", "The current state of the resource does not allow this action."),

        ("idempotency_in_progress", Fr) => t("Requête en cours", "Une requête avec la même clé d'idempotence est en cours de traitement."),
        ("idempotency_in_progress", Ar) => t("طلب قيد المعالجة", "طلب بنفس مفتاح التكرار قيد المعالجة."),
        ("idempotency_in_progress", En) => t("Request in progress", "A request with the same idempotency key is being processed."),

        ("idempotency_key_reused", Fr) => t("Clé d'idempotence réutilisée", "Cette clé a déjà servi pour une requête différente."),
        ("idempotency_key_reused", Ar) => t("مفتاح تكرار مستعمل", "استُخدم هذا المفتاح لطلب مختلف."),
        ("idempotency_key_reused", En) => t("Idempotency key reused", "This key was already used for a different request."),

        ("rate_limited", Fr) => t("Trop de requêtes", "Réessayez dans quelques instants."),
        ("rate_limited", Ar) => t("طلبات كثيرة جدًا", "أعد المحاولة بعد قليل."),
        ("rate_limited", En) => t("Too many requests", "Try again in a moment."),

        ("service_unavailable", Fr) => t("Service indisponible", "Un service nécessaire est momentanément indisponible."),
        ("service_unavailable", Ar) => t("الخدمة غير متاحة", "إحدى الخدمات اللازمة غير متاحة مؤقتًا."),
        ("service_unavailable", En) => t("Service unavailable", "A required service is temporarily unavailable."),

        ("request_timeout", Fr) => t("Délai dépassé", "Le traitement a pris trop de temps."),
        ("request_timeout", Ar) => t("انتهت المهلة", "استغرقت المعالجة وقتًا طويلًا."),
        ("request_timeout", En) => t("Timeout", "Processing took too long."),

        (_, Fr) => t("Erreur interne", "Une erreur inattendue s'est produite."),
        (_, Ar) => t("خطأ داخلي", "حدث خطأ غير متوقع."),
        (_, En) => t("Internal error", "An unexpected error occurred."),
    }
}

/// Localized message for a field violation.
#[must_use]
pub fn violation(v: &Violation, lang: Lang) -> String {
    use Lang::{Ar, En, Fr};
    match (v, lang) {
        (Violation::Required, Fr) => "Ce champ est obligatoire.".into(),
        (Violation::Required, Ar) => "هذا الحقل إلزامي.".into(),
        (Violation::Required, En) => "This field is required.".into(),
        (Violation::InvalidFormat, Fr) => "Format invalide.".into(),
        (Violation::InvalidFormat, Ar) => "تنسيق غير صالح.".into(),
        (Violation::InvalidFormat, En) => "Invalid format.".into(),
        (Violation::InvalidEmail, Fr) => "Adresse e-mail invalide.".into(),
        (Violation::InvalidEmail, Ar) => "بريد إلكتروني غير صالح.".into(),
        (Violation::InvalidEmail, En) => "Invalid e-mail address.".into(),
        (Violation::InvalidPhone, Fr) => "Numéro de mobile algérien invalide (05, 06 ou 07).".into(),
        (Violation::InvalidPhone, Ar) => "رقم هاتف جزائري غير صالح (05 أو 06 أو 07).".into(),
        (Violation::InvalidPhone, En) => "Invalid Algerian mobile number (05, 06 or 07).".into(),
        (Violation::TooShort { min }, Fr) => format!("Au moins {min} caractère(s)."),
        (Violation::TooShort { min }, Ar) => format!("على الأقل {min} حرف."),
        (Violation::TooShort { min }, En) => format!("At least {min} character(s)."),
        (Violation::TooLong { max }, Fr) => format!("Au plus {max} caractère(s)."),
        (Violation::TooLong { max }, Ar) => format!("على الأكثر {max} حرف."),
        (Violation::TooLong { max }, En) => format!("At most {max} character(s)."),
        (Violation::OutOfRange { min, max }, Fr) => format!("Doit être compris entre {min} et {max}."),
        (Violation::OutOfRange { min, max }, Ar) => format!("يجب أن يكون بين {min} و {max}."),
        (Violation::OutOfRange { min, max }, En) => format!("Must be between {min} and {max}."),
        (Violation::InvalidChoice { allowed }, Fr) => format!("Valeur non autorisée ({}).", allowed.join(", ")),
        (Violation::InvalidChoice { allowed }, Ar) => format!("قيمة غير مسموحة ({}).", allowed.join("، ")),
        (Violation::InvalidChoice { allowed }, En) => format!("Value not allowed ({}).", allowed.join(", ")),
        (Violation::PasswordTooShort { min }, Fr) => format!("Le mot de passe doit contenir au moins {min} caractères."),
        (Violation::PasswordTooShort { min }, Ar) => format!("يجب أن تحتوي كلمة المرور على {min} أحرف على الأقل."),
        (Violation::PasswordTooShort { min }, En) => format!("The password must be at least {min} characters long."),
        (Violation::PasswordTooLong { max }, Fr) => format!("Le mot de passe ne peut dépasser {max} caractères."),
        (Violation::PasswordTooLong { max }, Ar) => format!("لا يمكن أن تتجاوز كلمة المرور {max} حرفًا."),
        (Violation::PasswordTooLong { max }, En) => format!("The password cannot exceed {max} characters."),
        (Violation::PasswordTooCommon, Fr) => "Ce mot de passe est trop courant.".into(),
        (Violation::PasswordTooCommon, Ar) => "كلمة المرور هذه شائعة جدًا.".into(),
        (Violation::PasswordTooCommon, En) => "This password is too common.".into(),
        (Violation::PasswordEntirelyNumeric, Fr) => "Le mot de passe ne peut pas être uniquement numérique.".into(),
        (Violation::PasswordEntirelyNumeric, Ar) => "لا يمكن أن تكون كلمة المرور أرقامًا فقط.".into(),
        (Violation::PasswordEntirelyNumeric, En) => "The password cannot be entirely numeric.".into(),
        (Violation::PasswordTooSimilar, Fr) => "Le mot de passe ressemble trop à vos informations personnelles.".into(),
        (Violation::PasswordTooSimilar, Ar) => "كلمة المرور مشابهة جدًا لمعلوماتك الشخصية.".into(),
        (Violation::PasswordTooSimilar, En) => "The password is too similar to your personal information.".into(),
        (Violation::PasswordReused, Fr) => "Le nouveau mot de passe doit être différent de l'actuel.".into(),
        (Violation::PasswordReused, Ar) => "يجب أن تختلف كلمة المرور الجديدة عن الحالية.".into(),
        (Violation::PasswordReused, En) => "The new password must differ from the current one.".into(),
        (Violation::Incorrect, Fr) => "Valeur incorrecte.".into(),
        (Violation::Incorrect, Ar) => "قيمة غير صحيحة.".into(),
        (Violation::Incorrect, En) => "Incorrect value.".into(),
        (Violation::UnknownField, Fr) => "Champ inconnu.".into(),
        (Violation::UnknownField, Ar) => "حقل غير معروف.".into(),
        (Violation::UnknownField, En) => "Unknown field.".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_code_is_translated_in_every_language() {
        let codes = [
            "validation_error",
            "malformed_request",
            "unsupported_media_type",
            "payload_too_large",
            "invalid_credentials",
            "authentication_required",
            "token_invalid",
            "token_expired",
            "session_revoked",
            "refresh_token_invalid",
            "refresh_token_reused",
            "api_key_invalid",
            "reset_token_invalid",
            "forbidden",
            "not_found",
            "method_not_allowed",
            "email_taken",
            "phone_taken",
            "already_exists",
            "stale_state",
            "invalid_state",
            "idempotency_in_progress",
            "idempotency_key_reused",
            "rate_limited",
            "service_unavailable",
            "request_timeout",
        ];
        let fallback = problem("internal_error", Lang::En).title;
        for code in codes {
            for lang in Lang::ALL {
                let text = problem(code, lang);
                assert!(!text.title.is_empty() && !text.detail.is_empty());
                if lang == Lang::En {
                    assert_ne!(text.title, fallback, "{code} falls back to the generic text");
                }
            }
        }
    }
}

//! Transactional e-mail templates in French (default), Arabic and English.

use std::time::Duration;

use dz_domain::Lang;
use dz_domain::driver::DriverStatus;
use dz_domain::ids::DriverId;

use crate::ports::EmailMessage;

/// The password-reset e-mail.
#[must_use]
pub fn password_reset(to: &str, lang: Lang, link: &str, valid_for: Duration) -> EmailMessage {
    let minutes = valid_for.as_secs() / 60;
    let (subject, greeting, body, action, ignore) = match lang {
        Lang::Fr => (
            "Réinitialisation de votre mot de passe DZ Bus Tracker".to_owned(),
            "Bonjour,",
            format!(
                "Nous avons reçu une demande de réinitialisation du mot de passe de votre compte. \
                 Ce lien est valable {minutes} minutes et ne peut être utilisé qu'une seule fois."
            ),
            "Choisir un nouveau mot de passe",
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : \
             votre mot de passe actuel reste valable.",
        ),
        Lang::Ar => (
            "إعادة تعيين كلمة مرور DZ Bus Tracker".to_owned(),
            "مرحبًا،",
            format!(
                "تلقينا طلبًا لإعادة تعيين كلمة مرور حسابك. هذا الرابط صالح لمدة {minutes} دقيقة \
                 ولا يمكن استخدامه إلا مرة واحدة."
            ),
            "اختيار كلمة مرور جديدة",
            "إذا لم تطلب ذلك، يمكنك تجاهل هذه الرسالة: تبقى كلمة مرورك الحالية صالحة.",
        ),
        Lang::En => (
            "Reset your DZ Bus Tracker password".to_owned(),
            "Hello,",
            format!(
                "We received a request to reset the password of your account. This link is valid \
                 for {minutes} minutes and can be used only once."
            ),
            "Choose a new password",
            "If you did not ask for this, ignore this e-mail: your current password stays valid.",
        ),
    };
    let dir = if lang == Lang::Ar { "rtl" } else { "ltr" };
    let text_body = format!("{greeting}\n\n{body}\n\n{action}: {link}\n\n{ignore}\n");
    let html_body = format!(
        "<!doctype html><html lang=\"{lang}\" dir=\"{dir}\"><body>\
         <p>{greeting}</p><p>{body}</p>\
         <p><a href=\"{href}\">{action}</a></p>\
         <p>{ignore}</p></body></html>",
        lang = lang.as_str(),
        greeting = escape_html(greeting),
        body = escape_html(&body),
        href = escape_html(link),
        action = escape_html(action),
        ignore = escape_html(ignore),
    );
    EmailMessage { to: to.to_owned(), subject, text_body, html_body, lang }
}

/// Tells a driver about the new status of their profile, with the reason of a rejection or a
/// suspension.
#[must_use]
pub fn driver_status_changed(
    to: &str,
    lang: Lang,
    first_name: &str,
    status: DriverStatus,
    reason: &str,
) -> EmailMessage {
    use DriverStatus as S;
    let (subject, greeting, reason_label) = match lang {
        Lang::Fr => (
            "DZ Bus Tracker : votre profil de conducteur",
            greeting("Bonjour", first_name, ","),
            "Motif",
        ),
        Lang::Ar => ("DZ Bus Tracker: ملفك كسائق", greeting("مرحبًا", first_name, "،"), "السبب"),
        Lang::En => (
            "DZ Bus Tracker: your driver profile",
            greeting("Hello", first_name, ","),
            "Reason",
        ),
    };
    let body = match (lang, status) {
        (Lang::Fr, S::Pending) => {
            "Votre demande de conducteur a bien été reçue : elle sera examinée prochainement."
        }
        (Lang::Fr, S::Approved) => {
            "Votre profil de conducteur est approuvé : vous pouvez désormais conduire avec \
             DZ Bus Tracker."
        }
        (Lang::Fr, S::Rejected) => {
            "Votre demande de conducteur n'a pas été acceptée. Vous pouvez corriger vos \
             documents et la soumettre à nouveau."
        }
        (Lang::Fr, S::Suspended) => {
            "Votre profil de conducteur est suspendu : vous ne pouvez plus conduire pour le moment."
        }
        (Lang::Ar, S::Pending) => "تم استلام طلبك لتصبح سائقًا وستتم مراجعته قريبًا.",
        (Lang::Ar, S::Approved) => {
            "تمت الموافقة على ملفك كسائق: يمكنك الآن القيادة مع DZ Bus Tracker."
        }
        (Lang::Ar, S::Rejected) => {
            "لم يتم قبول طلبك لتصبح سائقًا. يمكنك تصحيح وثائقك وإعادة تقديم الطلب."
        }
        (Lang::Ar, S::Suspended) => "تم تعليق ملفك كسائق: لا يمكنك القيادة حاليًا.",
        (Lang::En, S::Pending) => {
            "Your driver application was received: it will be reviewed soon."
        }
        (Lang::En, S::Approved) => {
            "Your driver profile is approved: you can now drive with DZ Bus Tracker."
        }
        (Lang::En, S::Rejected) => {
            "Your driver application was not accepted. You can correct your documents and \
             apply again."
        }
        (Lang::En, S::Suspended) => {
            "Your driver profile is suspended: you cannot drive for the time being."
        }
    };
    let mut paragraphs = vec![greeting, body.to_owned()];
    if !reason.trim().is_empty() {
        paragraphs.push(format!("{reason_label}: {}", reason.trim()));
    }
    message(to, lang, subject, &paragraphs)
}

/// Asks a reviewer to examine a driver profile waiting for review.
#[must_use]
pub fn driver_review_requested(
    to: &str,
    lang: Lang,
    applicant: &str,
    driver_id: DriverId,
) -> EmailMessage {
    let (subject, paragraphs) = match lang {
        Lang::Fr => (
            "DZ Bus Tracker : profil de conducteur à examiner",
            [
                "Bonjour,".to_owned(),
                format!(
                    "Le profil de conducteur de {applicant} attend votre examen \
                     (identifiant {driver_id})."
                ),
            ],
        ),
        Lang::Ar => (
            "DZ Bus Tracker: ملف سائق بحاجة إلى مراجعة",
            [
                "مرحبًا،".to_owned(),
                format!("ملف السائق {applicant} بانتظار مراجعتك (المعرّف {driver_id})."),
            ],
        ),
        Lang::En => (
            "DZ Bus Tracker: driver profile to review",
            [
                "Hello,".to_owned(),
                format!(
                    "The driver profile of {applicant} is waiting for your review \
                     (id {driver_id})."
                ),
            ],
        ),
    };
    message(to, lang, subject, &paragraphs)
}

/// `<salutation> <name><punctuation>`, without the name when it is empty.
fn greeting(salutation: &str, name: &str, punctuation: &str) -> String {
    match name.trim() {
        "" => format!("{salutation}{punctuation}"),
        name => format!("{salutation} {name}{punctuation}"),
    }
}

/// A plain message made of paragraphs, as text and as escaped HTML.
fn message(to: &str, lang: Lang, subject: &str, paragraphs: &[String]) -> EmailMessage {
    let dir = if lang == Lang::Ar { "rtl" } else { "ltr" };
    let text_body = format!("{}\n", paragraphs.join("\n\n"));
    let html: String = paragraphs.iter().map(|p| format!("<p>{}</p>", escape_html(p))).collect();
    let html_body = format!(
        "<!doctype html><html lang=\"{lang}\" dir=\"{dir}\"><body>{html}</body></html>",
        lang = lang.as_str(),
    );
    EmailMessage { to: to.to_owned(), subject: subject.to_owned(), text_body, html_body, lang }
}

/// Minimal HTML escaping for text and attribute values.
#[must_use]
pub fn escape_html(raw: &str) -> String {
    let mut out = String::with_capacity(raw.len());
    for c in raw.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            other => out.push(other),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn renders_every_language_with_the_link() {
        for lang in Lang::ALL {
            let msg = password_reset(
                "a@b.dz",
                lang,
                "https://app.example/reset#token=abc",
                Duration::from_secs(3600),
            );
            assert!(msg.text_body.contains("https://app.example/reset#token=abc"));
            assert!(msg.html_body.contains("href=\"https://app.example/reset#token=abc\""));
            assert!(msg.text_body.contains("60"));
            assert_eq!(msg.lang, lang);
        }
        let ar = password_reset("a@b.dz", Lang::Ar, "x", Duration::from_secs(60));
        assert!(ar.html_body.contains("dir=\"rtl\""));
    }

    #[test]
    fn driver_status_mails_exist_in_every_language_with_the_reason() {
        use DriverStatus as S;
        for lang in Lang::ALL {
            let mut bodies = Vec::new();
            for status in DriverStatus::ALL {
                let msg = driver_status_changed("d@b.dz", lang, "Amine", status, "");
                assert_eq!((msg.to.as_str(), msg.lang), ("d@b.dz", lang));
                assert!(msg.text_body.contains("Amine"), "{lang:?} {status:?}");
                assert!(!msg.subject.is_empty());
                bodies.push(msg.text_body);
            }
            let distinct: std::collections::BTreeSet<_> = bodies.iter().collect();
            assert_eq!(distinct.len(), DriverStatus::ALL.len(), "one text per status ({lang:?})");
            let reason = " Blurry <scan> ";
            let rejected = driver_status_changed("d@b.dz", lang, "", S::Rejected, reason);
            assert!(rejected.text_body.contains("Blurry <scan>"));
            assert!(rejected.html_body.contains("Blurry &lt;scan&gt;"), "the reason is escaped");
        }
        let ar = driver_status_changed("d@b.dz", Lang::Ar, "أمين", DriverStatus::Approved, "");
        assert!(ar.html_body.contains("dir=\"rtl\""));
        let anonymous = driver_status_changed("d@b.dz", Lang::En, " ", DriverStatus::Pending, "");
        assert!(anonymous.text_body.starts_with("Hello,"));
    }

    #[test]
    fn review_requests_name_the_applicant_and_the_profile() {
        let id = DriverId::generate();
        for lang in Lang::ALL {
            let msg = driver_review_requested("admin@b.dz", lang, "Amine <B>", id);
            assert!(msg.text_body.contains("Amine <B>") && msg.text_body.contains(&id.to_string()));
            assert!(msg.html_body.contains("Amine &lt;B&gt;"));
            assert_eq!(msg.lang, lang);
        }
    }

    #[test]
    fn escapes_markup() {
        assert_eq!(escape_html("<a href=\"x\">&'"), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
    }
}

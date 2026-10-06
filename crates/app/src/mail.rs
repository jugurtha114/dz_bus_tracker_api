//! Transactional e-mail templates in French (default), Arabic and English.

use std::time::Duration;

use dz_domain::Lang;

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
    fn escapes_markup() {
        assert_eq!(escape_html("<a href=\"x\">&'"), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
    }
}

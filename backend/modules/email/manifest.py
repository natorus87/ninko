from core.module_registry import ModuleManifest

async def check_email_health() -> dict:
    """ Health Check für das Dashboard. """
    return {"status": "ok", "detail": "Email-Modul initialisiert (Health über IMAP/SMTP Ping folgt)"}

module_manifest = ModuleManifest(
    name="email",
    display_name="Email (SMTP/IMAP)",
    description="E-Mail Client für Ninko. Senden via SMTP und Lesen/Verwalten via IMAP. Unterstützt Basic Auth und MSAL (Microsoft 365 OAuth2).",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=True,
    env_prefix="EMAIL_",
    
    # Der Secret-Schlüssel für Passwörter oder Client-Secrets
    required_secrets=["EMAIL_SECRET"],
    optional_secrets=[],
    
    routing_keywords=[
        "email", "mail", "posteingang", "postfach", "smtp", "imap",
        "ordner", "senden", "versenden", "mail", "inbox", "mails"
    ],
    
    api_prefix="/api/email",
    
    dashboard_tab={
        "id": "email",
        "label": "Email",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>'
    },
    
    health_check=check_email_health,
)

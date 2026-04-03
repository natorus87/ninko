"""
Email Module — LangGraph @tool functions for SMTP/IMAP.
"""

import asyncio
import email
import mimetypes
import os
from email.message import EmailMessage
from email.header import decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
import imaplib
import smtplib
import json
import logging
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
import msal

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault
from .schemas import (
    SendEmailRequest, FilterEmailRequest, MoveEmailRequest, DeleteEmailRequest
)

logger = logging.getLogger("ninko.modules.email.tools")

async def _get_auth_context(connection_id: str = "") -> dict:
    """Load setup parameters and generate an OAuth2 token or return the Basic Auth password."""
    conn = await ConnectionManager.get_connection("email", connection_id)
    if not conn:
        conn = await ConnectionManager.get_default_connection("email")
    if not conn:
        raise ValueError(
            _t(
                de="Keine E-Mail Verbindung konfiguriert.",
                en="No email connection configured.",
            )
        )

    cfg = conn.config
    auth_type = cfg.get("auth_type", "basic")

    vault = get_vault()
    secret_path = conn.vault_keys.get("EMAIL_SECRET")
    secret = await vault.get_secret(secret_path) if secret_path else ""

    context = {
        "imap_server": cfg.get("imap_server", "imap.gmail.com"),
        "imap_port": int(cfg.get("imap_port", 993)),
        "smtp_server": cfg.get("smtp_server", "smtp.gmail.com"),
        "smtp_port": int(cfg.get("smtp_port", 587)),
        "email_address": cfg.get("email_address", ""),
        "auth_type": auth_type,
        "password": secret,
        "oauth_token": None
    }

    if auth_type == "oauth2":
        client_id = cfg.get("client_id", "")
        tenant_id = cfg.get("tenant_id", "common")

        if not client_id or not secret:
            raise ValueError(
                _t(
                    de="Für OAuth2 müssen Client ID und EMAIL_SECRET (Client Secret) gesetzt sein.",
                    en="For OAuth2, Client ID and EMAIL_SECRET (Client Secret) must be set.",
                )
            )

        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id, authority=authority, client_credential=secret
        )

        scopes = ["https://outlook.office365.com/.default"]

        result = app.acquire_token_silent(scopes, account=None)
        if not result:
            result = app.acquire_token_for_client(scopes=scopes)

        if "access_token" in result:
            context["oauth_token"] = result["access_token"]
        else:
            raise Exception(
                _t(
                    de=f"OAuth2 Fehler: Konnte MSAL Token nicht abrufen. Details: {result.get('error_description')}",
                    en=f"OAuth2 error: Could not acquire MSAL token. Details: {result.get('error_description')}",
                )
            )

    return context


def _create_imap_connection(ctx: dict) -> imaplib.IMAP4_SSL:
    """Helper: create an IMAP SSL connection in a synchronized thread."""
    mail = imaplib.IMAP4_SSL(ctx["imap_server"], ctx["imap_port"])

    if ctx["auth_type"] == "oauth2":
        auth_string = f"user={ctx['email_address']}\\x01auth=Bearer {ctx['oauth_token']}\\x01\\x01"
        mail.authenticate("XOAUTH2", lambda x: auth_string.encode("utf-8"))
    else:
        mail.login(ctx["email_address"], ctx["password"])

    return mail

async def check_connection(connection_id: str) -> dict:
    """Test IMAP and SMTP connections asynchronously."""
    try:
        ctx = await _get_auth_context(connection_id)

        def _test_imap():
            mail = _create_imap_connection(ctx)
            mail.logout()
        await asyncio.to_thread(_test_imap)

        def _test_smtp():
            if ctx["smtp_port"] == 465:
                server = smtplib.SMTP_SSL(ctx["smtp_server"], ctx["smtp_port"])
            else:
                server = smtplib.SMTP(ctx["smtp_server"], ctx["smtp_port"])
                server.starttls()

            with server:
                if ctx["auth_type"] == "oauth2":
                    auth_string = f"user={ctx['email_address']}\\x01auth=Bearer {ctx['oauth_token']}\\x01\\x01"
                    server.docmd("AUTH", "XOAUTH2 " + auth_string.encode("ascii").hex())
                else:
                    server.login(ctx["email_address"], ctx["password"])
        await asyncio.to_thread(_test_smtp)

        return {"status": "ok", "message": "IMAP & SMTP connected successfully."}
    except Exception as e:
        logger.error("Email connection check failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}

# ================================
# LangChain Tools
# ================================

def _attach_file(msg_multipart: MIMEMultipart, file_path: str) -> bool:
    """Attach a file to a MIMEMultipart message. Returns True on success."""
    if not os.path.isfile(file_path):
        logger.warning("send_email: attachment not found: %s", file_path)
        return False

    ctype, encoding = mimetypes.guess_type(file_path)
    if ctype is None or encoding is not None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)

    with open(file_path, "rb") as f:
        file_data = f.read()

    if maintype == "text":
        part = MIMEText(file_data.decode("utf-8", errors="replace"), _subtype=subtype)
    else:
        part = MIMEBase(maintype, subtype)
        part.set_payload(file_data)
        encoders.encode_base64(part)

    filename = os.path.basename(file_path)
    part.add_header("Content-Disposition", "attachment", filename=filename)
    msg_multipart.attach(part)
    return True


@tool(args_schema=SendEmailRequest)
async def send_email(to: str, subject: str, body: str, cc: Optional[str] = None, bcc: Optional[str] = None, is_html: bool = True, attachments: Optional[List[str]] = None, connection_id: str = "") -> str:
    """
    Send an email via SMTP, optionally with file attachments.
    This is the ONLY way to actually send an email.
    IMPORTANT: This tool MUST be called — an email cannot be sent by displaying text.
    Without this tool call, NO email will be sent.

    Args:
        to: Recipient address (e.g. 'max@example.com')
        subject: Email subject
        body: Email content (HTML or plaintext, depending on is_html)
        is_html: True for HTML format (default), False for plaintext
        attachments: Optional list of absolute file paths to attach (e.g. ['/app/data/uploads/report.pdf'])
        connection_id: Optional connection ID (default: default connection)
    """
    ctx = await _get_auth_context(connection_id)

    attachment_list = attachments or []
    has_attachments = len(attachment_list) > 0
    logger.info(
        "send_email: to=%s | subject=%s | body_len=%d | attachments=%d | from=%s | smtp=%s:%s",
        to, subject, len(body), len(attachment_list),
        ctx["email_address"], ctx["smtp_server"], ctx["smtp_port"],
    )

    attached_count = 0
    if has_attachments:
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = ctx["email_address"]
        msg['To'] = to
        if cc: msg['Cc'] = cc
        if bcc: msg['Bcc'] = bcc

        text_subtype = "html" if is_html else "plain"
        msg.attach(MIMEText(body, _subtype=text_subtype, _charset="utf-8"))

        for file_path in attachment_list:
            if _attach_file(msg, file_path):
                attached_count += 1
        logger.info("send_email: %d/%d attachments attached successfully", attached_count, len(attachment_list))
    else:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = ctx["email_address"]
        msg['To'] = to
        if cc: msg['Cc'] = cc
        if bcc: msg['Bcc'] = bcc
        if is_html:
            msg.set_content(body, subtype='html')
        else:
            msg.set_content(body)

    def _send():
        if ctx["smtp_port"] == 465:
            server = smtplib.SMTP_SSL(ctx["smtp_server"], ctx["smtp_port"])
        else:
            server = smtplib.SMTP(ctx["smtp_server"], ctx["smtp_port"])
            server.starttls()

        with server:
            if ctx["auth_type"] == "oauth2":
                auth_string = f"user={ctx['email_address']}\\x01auth=Bearer {ctx['oauth_token']}\\x01\\x01"
                server.docmd("AUTH", "XOAUTH2 " + auth_string.encode("ascii").hex())
            else:
                server.login(ctx["email_address"], ctx["password"])
            refused = server.send_message(msg)
            if refused:
                logger.warning("send_email: refused recipients: %s", refused)
            else:
                logger.info("send_email: SMTP accepted — all recipients delivered.")

    await asyncio.to_thread(_send)

    if has_attachments:
        return _t(
            de=f"E-Mail mit {attached_count} Anhang/Anhängen wurde erfolgreich gesendet.",
            en=f"Email with {attached_count} attachment(s) sent successfully.",
        )
    return _t(
        de="E-Mail wurde erfolgreich gesendet.",
        en="Email sent successfully.",
    )

@tool(args_schema=FilterEmailRequest)
async def read_emails(folder: str = "INBOX", limit: int = 10, query: str = "ALL", connection_id: str = "") -> str:
    """Read the inbox (IMAP) based on a search query."""
    ctx = await _get_auth_context(connection_id)

    def _fetch():
        mail = _create_imap_connection(ctx)
        mail.select(folder)

        status, messages = mail.search(None, query)
        if status != "OK":
            mail.logout()
            return "Could not search the folder."

        mail_ids = messages[0].split()[-limit:]
        mail_ids.reverse()

        result_list = []
        for i in mail_ids:
            res, msg_data = mail.fetch(i, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    subject = "No subject"
                    if msg.get('Subject'):
                        decoded_bytes, charset = decode_header(msg.get('Subject'))[0]
                        if charset:
                            subject = decoded_bytes.decode(charset)
                        else:
                            subject = decoded_bytes if isinstance(decoded_bytes, str) else decoded_bytes.decode("utf-8", "ignore")

                    body_text = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    body_text = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "ignore")
                                    break
                                except: pass
                    else:
                        try:
                            body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "ignore")
                        except: pass

                    result_list.append({
                        "uid": i.decode("utf-8"),
                        "from": msg.get("From"),
                        "date": msg.get("Date"),
                        "subject": subject,
                        "snippet": body_text[:200].replace("\\n", " ").strip() + "..."
                    })
        mail.logout()
        return json.dumps(result_list, indent=2, ensure_ascii=False)

    res = await asyncio.to_thread(_fetch)
    return res

@tool(args_schema=MoveEmailRequest)
async def move_email(uid: str, source_folder: str, dest_folder: str, connection_id: str = "") -> str:
    """Move an email between IMAP folders."""
    ctx = await _get_auth_context(connection_id)
    def _move():
        mail = _create_imap_connection(ctx)
        mail.select(source_folder)
        res, data = mail.uid('COPY', uid, dest_folder)
        if res == "OK":
            mail.uid('STORE', uid, '+FLAGS', '(\\Deleted)')
            mail.expunge()
        mail.logout()
        return _t(
            de="E-Mail erfolgreich verschoben.",
            en="Email moved successfully.",
        )
    return await asyncio.to_thread(_move)

@tool(args_schema=DeleteEmailRequest)
async def delete_email(uid: str, folder: str, hard_delete: bool = False, connection_id: str = "") -> str:
    """Delete an email based on its UID."""
    ctx = await _get_auth_context(connection_id)

    trash_folder = "Trash"

    if not hard_delete:
        return await move_email.ainvoke({"uid": uid, "source_folder": folder, "dest_folder": trash_folder, "connection_id": connection_id})
    else:
        def _delete():
            mail = _create_imap_connection(ctx)
            mail.select(folder)
            mail.uid('STORE', uid, '+FLAGS', '(\\Deleted)')
            mail.expunge()
            mail.logout()
            return _t(
                de="E-Mail dauerhaft gelöscht.",
                en="Email permanently deleted.",
            )
        return await asyncio.to_thread(_delete)

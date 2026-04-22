"""Feature 40: Async email notification service."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


async def send_email(to: str, subject: str, html_body: str):
    """Send an email via SMTP. Runs synchronously but is called from async context."""
    if not _smtp_configured():
        logger.warning("SMTP not configured — skipping email to %s", to)
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(msg["From"], [to], msg.as_string())

        logger.info("Email sent to %s: %s", to, subject)
    except Exception:
        logger.exception("Failed to send email to %s", to)


async def send_contact_notification(
    tenant_name: str,
    support_email: str,
    visitor_name: str,
    visitor_email: str,
    message: str,
    conversation_id: str | None = None,
    api_base_url: str = "",
):
    """Send email notification when a contact request is created."""
    transcript_link = ""
    if conversation_id and api_base_url:
        transcript_link = f'<p><a href="{api_base_url}/admin#conversation-{conversation_id}">View conversation transcript</a></p>'

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #2563eb;">New Contact Request — {tenant_name}</h2>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px; font-weight: bold; color: #555;">Name</td><td style="padding: 8px;">{visitor_name}</td></tr>
            <tr><td style="padding: 8px; font-weight: bold; color: #555;">Email</td><td style="padding: 8px;"><a href="mailto:{visitor_email}">{visitor_email}</a></td></tr>
        </table>
        <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
            <p style="margin: 0; color: #333;">{message}</p>
        </div>
        {transcript_link}
        <p style="color: #999; font-size: 12px;">Sent by TBM Chatbot Platform</p>
    </div>
    """
    await send_email(
        to=support_email,
        subject=f"[{tenant_name}] Contact request from {visitor_name}",
        html_body=html,
    )


async def send_negative_feedback_alert(
    tenant_name: str,
    support_email: str,
    user_question: str,
    bot_response: str,
    conversation_id: str,
):
    """Send email alert when negative feedback is received (if tenant opted in)."""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #dc2626;">Negative Feedback Alert — {tenant_name}</h2>
        <h3 style="color: #555;">User Question</h3>
        <div style="background: #fef2f2; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
            <p style="margin: 0;">{user_question}</p>
        </div>
        <h3 style="color: #555;">Bot Response (thumbs down)</h3>
        <div style="background: #f8f9fa; padding: 12px; border-radius: 8px;">
            <p style="margin: 0;">{bot_response}</p>
        </div>
        <p style="color: #999; font-size: 12px; margin-top: 24px;">Conversation: {conversation_id}</p>
    </div>
    """
    await send_email(
        to=support_email,
        subject=f"[{tenant_name}] Negative feedback received",
        html_body=html,
    )

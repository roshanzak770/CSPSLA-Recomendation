"""
Email notification service using Gmail SMTP (configured in .env).
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_threshold_alert(
    to_email: str,
    provider_name: str,
    metric: str,
    operator: str,
    threshold_value: float,
    actual_value: float,
) -> bool:
    """Send an email when a user-defined SLA threshold is breached."""
    metric_labels = {
        "uptime_sla_pct":       "Uptime SLA (%)",
        "rto_hours":            "Recovery Time Objective (hrs)",
        "rpo_hours":            "Recovery Point Objective (hrs)",
        "penalty_credit_pct":   "Penalty Credit (%)",
    }
    label = metric_labels.get(metric, metric)
    direction = "dropped below" if operator == "below" else "risen above"

    subject = f"[SLAwise] Alert: {provider_name} {label} {direction} {threshold_value}"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <div style="background: #1e293b; padding: 24px; border-radius: 12px;">
        <h2 style="color: #f1f5f9; margin: 0 0 16px;">⚠️ SLA Threshold Alert</h2>
        <div style="background: #0f172a; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
          <table style="width: 100%; color: #cbd5e1; font-size: 14px; border-collapse: collapse;">
            <tr><td style="padding: 6px 0; color: #94a3b8;">Provider</td>
                <td style="padding: 6px 0; font-weight: bold; color: #f1f5f9;">{provider_name}</td></tr>
            <tr><td style="padding: 6px 0; color: #94a3b8;">Metric</td>
                <td style="padding: 6px 0; color: #f1f5f9;">{label}</td></tr>
            <tr><td style="padding: 6px 0; color: #94a3b8;">Your Threshold</td>
                <td style="padding: 6px 0; color: #fbbf24;">{operator} {threshold_value}</td></tr>
            <tr><td style="padding: 6px 0; color: #94a3b8;">Actual Value</td>
                <td style="padding: 6px 0; color: #f87171; font-weight: bold;">{actual_value}</td></tr>
          </table>
        </div>
        <p style="color: #94a3b8; font-size: 13px; margin: 0;">
          <strong style="color: #f1f5f9;">{provider_name}</strong>'s {label} has {direction} your
          threshold of <strong style="color: #fbbf24;">{threshold_value}</strong>.
          Current value is <strong style="color: #f87171;">{actual_value}</strong>.
        </p>
        <p style="color: #64748b; font-size: 11px; margin-top: 16px;">
          Sent by SLAwise · Manage your alerts in the Alerts tab.
        </p>
      </div>
    </div>
    """

    if not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP not configured — skipping email to %s", to_email)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.smtp_user
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_user, to_email, msg.as_string())

        logger.info("Threshold alert email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send threshold alert email: %s", e)
        return False

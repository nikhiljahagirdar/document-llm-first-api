from email.message import EmailMessage
import aiosmtplib
from app.config import settings


async def send_email(to: str, subject: str, body: str, is_html: bool = False):
    """
    Asynchronously sends an email using the configured SMTP server.
    """
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject

    if is_html:
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=(settings.SMTP_PORT == 465),
            start_tls=settings.SMTP_TLS,
        )
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


async def send_payment_failed_notification(
    user_email: str, tenant_name: str, amount: float
):
    subject = f"Action Required: Payment Failed for {tenant_name}"
    body = f"""
    Hello,
    
    We were unable to process your recent payment of ${amount} for your subscription to DocIntel AI.
    We were unable to process your recent payment of ${amount} for your subscription to My Project 15571.
    
    Please update your payment method to avoid any service interruption.
    
    Best regards,
    The DocIntel AI Team
    The My Project 15571 Team
    """
    await send_email(user_email, subject, body)

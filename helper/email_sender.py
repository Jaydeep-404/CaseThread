import os
from email.message import EmailMessage
import aiosmtplib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def send_email_async(subject: str, recipient: str, body: str):
    message = EmailMessage()
    message["From"] = os.getenv("EMAIL_FROM")
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname="smtp.gmail.com",
        port=587,
        start_tls=True,
        username=os.getenv("EMAIL_FROM"),
        password=os.getenv("EMAIL_PASSWORD"),
    )

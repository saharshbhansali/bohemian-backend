import random
import string
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import csv
import os
from dotenv import load_dotenv

load_dotenv()


def generate_otp(length=21):
    characters = string.ascii_letters + string.digits
    otp = "".join(random.choice(characters) for i in range(length))
    return otp


def hash_email_otp(email, otp):
    return hashlib.sha256((email + otp).encode()).hexdigest()


def send_email(recipient, subject, body):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT"))

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, recipient, text)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def handle_otp_storage_and_notification(
    email_otp_mapping, send_emails=False, write_to_csv=False
):
    if write_to_csv:
        if not os.path.exists("identities.csv"):
            with open("identities.csv", mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["email", "otp"])

        with open("identities.csv", mode="a", newline="") as file:
            writer = csv.writer(file)
            for username, otp in email_otp_mapping.items():
                writer.writerow([username, otp])
                if send_emails:
                    send_email(username, "Your OTP", f"Your OTP is: {otp}")
    else:
        for username, otp in email_otp_mapping.items():
            if send_emails:
                send_email(username, "Your OTP", f"Your OTP is: {otp}")

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

def send_password_reset_email(to_email: str, token: str):
    subject = "🔐 Redefinição de Senha - Sistema QUANT"
    link = f"http://localhost:8000/resetar?token={token}"  # Altere para o frontend real se tiver
    body = f"""
    <html>
        <body>
            <p>Olá,</p>
            <p>Você solicitou a redefinição da sua senha.</p>
            <p>Clique no link abaixo para criar uma nova senha. O link expira em 30 minutos:</p>
            <p><a href="{link}">Redefinir Senha</a></p>
            <br>
            <p>Se você não fez essa solicitação, ignore este e-mail.</p>
            <hr>
            <p><b>Equipe Sistema Lindo</b></p>
        </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("Erro ao enviar e-mail:", e)
        return False

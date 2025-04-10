from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from datetime import datetime
from fastapi import HTTPException
from ...core.config import settings

# Email settings from config
SMTP_SERVER = settings.SMTP_SERVER
SMTP_PORT = settings.SMTP_PORT
SMTP_USERNAME = settings.SMTP_USERNAME
SMTP_PASSWORD = settings.SMTP_PASSWORD

def send_verification_email(email: str, code: str):
    """Send verification code via email"""
    print(f"Sending verification email to: {email}")
    
    try:
        # Create a more professional HTML email
        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 5px;">
                    <h2 style="color: #333;">AIClinic Login Verification</h2>
                    <p>Hello,</p>
                    <p>You are receiving this email because you requested to log in to your AIClinic account. 
                    Please use the following verification code to complete your login:</p>
                    <div style="background-color: #eee; padding: 10px; text-align: center; font-size: 24px; letter-spacing: 2px; margin: 20px 0;">
                        <strong>{code}</strong>
                    </div>
                    <p>This code will expire in {settings.MFA_EXPIRE_MINUTES} minutes.</p>
                    <p>If you did not request this code, please ignore this email.</p>
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">This is an automated message, please do not reply.</p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg["Subject"] = "AIClinic Login Verification Code"
        msg["From"] = f"AIClinic Security <{SMTP_USERNAME}>"
        msg["To"] = email
        msg["Message-ID"] = f"<{datetime.now().strftime('%Y%m%d%H%M%S')}.{code}@aiclinic.com>"
        
        # Add both plain text and HTML versions
        text = f"Your AIClinic verification code is: {code}\nThis code will expire in {settings.MFA_EXPIRE_MINUTES} minutes."
        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            print("Connecting to SMTP server...")
            server.starttls()
            print("Starting TLS...")
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            print("Logged in successfully")
            response = server.send_message(msg)
            if not response:
                print("Email accepted by SMTP server")
            else:
                print(f"Some recipients were rejected: {response}")
            
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP Authentication failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to authenticate with email server")
    except smtplib.SMTPException as e:
        print(f"Failed to send email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send verification email")
    except Exception as e:
        print(f"Unexpected error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
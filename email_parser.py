import imaplib
import email
import smtplib
from email.mime.text import MIMEText
from email.header import decode_header
from email.utils import parseaddr
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
from bs4 import BeautifulSoup
import re
import getpass
import sys
import os
import time
import logging
import argparse
from dotenv import load_dotenv
import socket


load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    filename="email_parser.log",
    format="%(asctime)s - %(levelname)s - %(message)s"
)


EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
XAI_API_KEY = os.getenv("XAI_API_KEY")


XAI_API_URL = "https://api.x.ai/v1/chat/completions"


IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def setup_credentials():
    """Prompt for credentials if not set in environment variables."""
    global EMAIL_ADDRESS, EMAIL_PASSWORD, XAI_API_KEY
    if not EMAIL_ADDRESS:
        EMAIL_ADDRESS = input("Enter your email address: ")
    if not EMAIL_PASSWORD:
        EMAIL_PASSWORD = getpass.getpass("Enter your email password (use App Password for Gmail): ")
    if not XAI_API_KEY:
        XAI_API_KEY = getpass.getpass("Enter your xAI API key: ")

def connect_to_email(folder="inbox"):
    """Connect to the email server via IMAP."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select(folder)
        logging.info(f"Connected to email folder: {folder}")
        return mail
    except Exception as e:
        logging.error(f"Error connecting to email: {e}")
        print(f"Error connecting to email: {e}")
        sys.exit(1)

def clean_html(raw_html):
    """Clean HTML content to plain text."""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text()
    # Remove extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def parse_email_content(msg):
    """Parse email content, handling plain text and HTML."""
    subject = decode_header(msg["Subject"])[0][0]
    if isinstance(subject, bytes):
        subject = subject.decode()
    sender = msg.get("From")

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
            elif content_type == "text/html":
                body = clean_html(part.get_payload(decode=True).decode(errors="ignore"))
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            body = msg.get_payload(decode=True).decode(errors="ignore")
        elif content_type == "text/html":
            body = clean_html(msg.get_payload(decode=True).decode(errors="ignore"))

    return subject, sender, body

def analyze_email_with_xai(subject, body):
    """Use xAI API to determine urgency and summarize email."""
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Analyze the following email content and perform two tasks:\n"
        f"1. Determine the urgency level (Low, Medium, High) based on keywords, tone, and context. "
        f"Explain your reasoning briefly.\n"
        f"2. Summarize the email in 1-2 sentences in a ticket-like format, capturing the main point.\n\n"
        f"Subject: {subject}\n"
        f"Body: {body}\n\n"
        f"Return the response in JSON format with fields: 'urgency', 'reasoning', and 'summary'."
    )

    payload = {
        "model": "grok-3-latest",  # Match curl command
        "messages": [
            {"role": "system", "content": "You are an email analysis assistant."},  # Add system message
            {"role": "user", "content": prompt}
        ],
        "stream": False,  # Match curl command
        "temperature": 0,  # Match curl command
        "max_tokens": 500  # Keep for safety
    }

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    try:
        print(f"Client IP: {socket.gethostbyname(socket.gethostname())}")
        response = session.post(XAI_API_URL, headers=headers, json=payload)
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        print(f"Response Body: {response.text}")
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        try:
            parsed_response = json.loads(content)
            logging.info(f"Successfully analyzed email with subject: {subject}")
            return parsed_response
        except json.JSONDecodeError:
            logging.error("Failed to parse API response as JSON")
            return {
                "urgency": "Unknown",
                "reasoning": "Failed to parse API response",
                "summary": "Unable to summarize due to invalid response format"
            }
    except Exception as e:
        logging.error(f"Error with xAI API: {e}")
        print(f"Error with xAI API: {e}")
        return {
            "urgency": "Unknown",
            "reasoning": f"API error: {str(e)}",
            "summary": "Unable to summarize due to API failure"
        }

def generate_response_with_xai(subject, body):
    """Use xAI API to generate an automated response."""
    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = (
        f"Generate a polite, context-aware email response for the following email. "
        f"The response should address the main points, match the tone, and be concise. "
        f"Do not include sensitive information or commit to actions without confirmation.\n\n"
        f"Subject: {subject}\n"
        f"Body: {body}\n\n"
        f"Return the response as plain text."
    )

    payload = {
        "model": "grok-3-latest",  # Match curl command
        "messages": [
            {"role": "system", "content": "You are an email response assistant."},  # Add system message
            {"role": "user", "content": prompt}
        ],
        "stream": False,  # Match curl command
        "temperature": 0,  # Match curl command
        "max_tokens": 300  # Keep for safety
    }

    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    try:
        print(f"Client IP: {socket.gethostbyname(socket.gethostname())}")


        response = session.post(XAI_API_URL, headers=headers, json=payload)
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        print(f"Response Body: {response.text}")
        response.raise_for_status()
        result = response.json()
        response_text = result["choices"][0]["message"]["content"].strip()
        logging.info(f"Generated response for email with subject: {subject}")
        return response_text
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        print(f"Error generating response: {e}")
        return "Thank you for your email. I will get back to you soon."

def send_email(to_address, subject, body):
    """Send an email response using SMTP."""
    msg = MIMEText(body)
    msg["Subject"] = f"Re: {subject}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_address

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        logging.info(f"Response sent to {to_address}")
        print(f"Response sent to {to_address}")
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        print(f"Error sending email: {e}")

def main(args):
    """Main function to process emails and handle responses."""
    setup_credentials()
    mail = connect_to_email(args.folder)
    status, messages = mail.search(None, "UNSEEN")
    if status != "OK" or not messages[0]:
        logging.info("No unread emails found.")
        print("No unread emails found.")
        mail.logout()
        return

    email_ids = messages[0].split()
    tickets = []

    for email_id in email_ids:
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        subject, sender, body = parse_email_content(msg)
        analysis = analyze_email_with_xai(subject, body)
        response = generate_response_with_xai(subject, body)

        ticket = {
            "email_id": email_id.decode(),
            "subject": subject,
            "sender": sender,
            "urgency": analysis.get("urgency", "Unknown"),
            "reasoning": analysis.get("reasoning", "No reasoning provided"),
            "summary": analysis.get("summary", "No summary available"),
            "response": response
        }
        tickets.append(ticket)
        time.sleep(1)

    urgency_order = {"High": 1, "Medium": 2, "Low": 3, "Unknown": 4}
    tickets.sort(key=lambda x: urgency_order.get(x["urgency"], 4))

    for i, ticket in enumerate(tickets, 1):
        print(f"\n=== Ticket {i} ===")
        print(f"Subject: {ticket['subject']}")
        print(f"From: {ticket['sender']}")
        print(f"Urgency: {ticket['urgency']}")
        print(f"Reasoning: {ticket['reasoning']}")
        print(f"Summary: {ticket['summary']}")
        print(f"Proposed Response:\n{ticket['response']}\n")

        while True:
            edit = input("Edit response? (y/n): ").lower()
            if edit in ["y", "n"]:
                break
            print("Please enter 'y' or 'n'.")
        if edit == "y":
            ticket["response"] = input("Enter new response:\n")
            logging.info(f"User edited response for ticket {i}")

        while True:
            choice = input("Send response? (y/n): ").lower()
            if choice in ["y", "n"]:
                break
            print("Please enter 'y' or 'n'.")

        if choice == "y":
            _, to_address = parseaddr(ticket["sender"])
            if not to_address:
                to_address = ticket["sender"]
            send_email(to_address, ticket["subject"], ticket["response"])
            mail.store(ticket["email_id"], "+FLAGS", "\\Seen")
            logging.info(f"Marked email {ticket['email_id']} as read")

    mail.logout()
    logging.info("Disconnected from email server")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Email Parser and Responder")
    parser.add_argument("--folder", default="inbox", help="Email folder to monitor")
    args = parser.parse_args()
    main(args)
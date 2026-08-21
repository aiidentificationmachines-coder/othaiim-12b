#!/usr/bin/env python3
"""
Solas Email Sender — Local DGX Edition
Sends emails via Gmail API or SMTP from the DGX Spark.
No cloud credits needed — uses local SMTP or Gmail API.

Modes:
1. SMTP (if Gmail app password configured)
2. API (if Gmail OAuth token available)
3. Queue (offline mode, queues emails for later sending)
"""

import json, os, sys, smtplib, ssl, time, urllib.request
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

EMAIL_DIR = os.path.expanduser("~/othaiim-12b/emails")
os.makedirs(EMAIL_DIR, exist_ok=True)
os.makedirs(os.path.join(EMAIL_DIR, "queue"), exist_ok=True)

# Try to load Gmail config
GMAIL_USER = os.environ.get("GMAIL_USER", "aiidentificationmachines@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_OAUTH_TOKEN = os.environ.get("GMAIL_OAUTH_TOKEN", "")

env_path = os.path.expanduser("~/othaiim-12b/.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.startswith("GMAIL_APP_PASSWORD="):
                GMAIL_APP_PASSWORD = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("GMAIL_OAUTH_TOKEN="):
                GMAIL_OAUTH_TOKEN = line.split("=", 1)[1].strip().strip('"')

def send_smtp(to_email, subject, body, from_email=None):
    """Send email via Gmail SMTP using app password."""
    sender = from_email or GMAIL_USER
    if not GMAIL_APP_PASSWORD:
        return {"error": "No Gmail app password configured. Set GMAIL_APP_PASSWORD in .env"}
    
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender, GMAIL_APP_PASSWORD)
            server.sendmail(sender, to_email.split(','), msg.as_string())
        return {"success": True, "to": to_email, "subject": subject}
    except Exception as e:
        return {"error": str(e)}

def send_api(to_email, subject, body, from_email=None):
    """Send email via Gmail API using OAuth token."""
    sender = from_email or GMAIL_USER
    if not GMAIL_OAUTH_TOKEN:
        return {"error": "No Gmail OAuth token configured"}
    
    import base64
    raw = f"From: {sender}\r\nTo: {to_email}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n{body}"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode()
    
    payload = json.dumps({"raw": encoded}).encode()
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {GMAIL_OAUTH_TOKEN}")
    req.add_header("Content-Type", "application/json")
    
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        return {"success": True, "message_id": result.get("id")}
    except Exception as e:
        return {"error": str(e)}

def queue_email(to_email, subject, body):
    """Queue email for later sending."""
    queue_item = {
        "id": f"email_{int(time.time())}",
        "to": to_email,
        "subject": subject,
        "body": body,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    path = os.path.join(EMAIL_DIR, "queue", f"{queue_item['id']}.json")
    with open(path, "w") as f:
        json.dump(queue_item, f, indent=2)
    return {"queued": True, "id": queue_item["id"]}

def send_email(to_email, subject, body, from_email=None):
    """Send email using best available method."""
    # Try SMTP first
    if GMAIL_APP_PASSWORD:
        result = send_smtp(to_email, subject, body, from_email)
        if "success" in result:
            return result
        print(f"  SMTP failed: {result.get('error')}, trying API...")
    
    # Try API
    if GMAIL_OAUTH_TOKEN:
        result = send_api(to_email, subject, body, from_email)
        if "success" in result:
            return result
        print(f"  API failed: {result.get('error')}, queuing...")
    
    # Queue for later
    print(f"  No email credentials — queuing email")
    return queue_email(to_email, subject, body)

def process_email_queue():
    """Send all queued emails."""
    queue_dir = os.path.join(EMAIL_DIR, "queue")
    if not os.path.exists(queue_dir):
        return
    
    pending = [f for f in os.listdir(queue_dir) if f.endswith(".json")]
    if not pending:
        print("  Email queue is empty")
        return
    
    print(f"  Processing {len(pending)} queued emails...")
    for fname in pending:
        path = os.path.join(queue_dir, fname)
        with open(path) as f:
            item = json.load(f)
        
        if item["status"] != "pending":
            continue
        
        result = send_email(item["to"], item["subject"], item["body"])
        if "success" in result or "queued" in result:
            item["status"] = "sent" if "success" in result else "still_queued"
            with open(path, "w") as f:
                json.dump(item, f, indent=2)
            print(f"    Sent: {item['subject']}")
        else:
            print(f"    Failed: {item['subject']} — {result.get('error')}")

# === CLI ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "send":
            if len(sys.argv) >= 4:
                to = sys.argv[2]
                subject = sys.argv[3]
                body = sys.argv[4] if len(sys.argv) > 4 else ""
                result = send_email(to, subject, body)
                print(f"  Result: {result}")
            else:
                print("Usage: send <to> <subject> [body]")
        elif cmd == "queue":
            process_email_queue()
        elif cmd == "status":
            print(f"  SMTP: {'configured' if GMAIL_APP_PASSWORD else 'MISSING'}")
            print(f"  API: {'configured' if GMAIL_OAUTH_TOKEN else 'MISSING'}")
            queue_dir = os.path.join(EMAIL_DIR, "queue")
            queued = len([f for f in os.listdir(queue_dir) if f.endswith(".json")]) if os.path.exists(queue_dir) else 0
            print(f"  Queued: {queued}")
        else:
            print(f"Usage: {sys.argv[0]} [send|queue|status]")
    else:
        print("Solas Email Sender — Local DGX Edition")
        print(f"  SMTP: {'configured' if GMAIL_APP_PASSWORD else 'MISSING'}")
        print(f"  API: {'configured' if GMAIL_OAUTH_TOKEN else 'MISSING'}")

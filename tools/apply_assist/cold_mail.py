#!/usr/bin/env python
"""
Cold email to a company's published recruiting address, sent from Sai's Gmail with his resume attached.

  python tools/apply_assist/cold_mail.py --to careers@hevodata.com --company "Hevo Data" --role "Associate SDE"   # preview
  python tools/apply_assist/cold_mail.py ... --send                                                          # send

Rules: only addresses a company published (see src/lib/recruitingContacts.js); one email per address per 30 days
(log: runs/cold_mail.jsonl); text uses only true resume facts. Needs GMAIL_APP_PASSWORD in .env.
"""
import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LOG = HERE / "runs" / "cold_mail.jsonl"
RESUME = HERE / "resume.pdf"
SENDER = "sairaghava1318@gmail.com"
PORTFOLIO = "https://productivity-automations.vercel.app"
LINKEDIN = "https://www.linkedin.com/in/nandam-venkata-sai-raghava-946b3735b/"
GITHUB = "https://github.com/VeratrilS"
GAP = timedelta(days=30)


def compose(company, role=None, name=None):
    what = f"the {role} role" if role else "software engineering roles"
    subject = f"{role or 'Software Engineer'} at {company}: Nandam Venkata Sai Raghava, NIT Rourkela 2027"
    body = "\n".join([
        f"Hi {name}," if name else "Hi,",
        "",
        f"I'm a final-year B.Tech CSE student at NIT Rourkela (CGPA 8.99, graduating 2027) and I'm very interested in "
        f"{what} at {company}.",
        "",
        "A few things I have built:",
        "- SR-CarRentals, a car rental and shared-ride backend: 8 microservices over 14 Kafka topics, 3-layer "
        "concurrency control against double-booking (Redis locks, row locks, exclusion constraints) and Saga rollbacks.",
        "- A redis-cli-compatible cache server in C++17 (RESP, 29 commands, LRU/LFU eviction, thread pool).",
        "- Software Engineering Intern at Maruti Suzuki (MERN portal, 120+ REST APIs); Coding Expert at DataAnnotation "
        "(C++ fixes in llama.cpp).",
        "- Codeforces Specialist, LeetCode contest rating 1750.",
        "",
        "I'm available for a 6-month internship from January 2027 or full-time from May 2027. My resume is attached; "
        "I'd be grateful for a chance to interview, or a pointer to the right person.",
        "",
        "Thanks,",
        "Nandam Venkata Sai Raghava",
        f"+91 9110307856 · Portfolio: {PORTFOLIO}",
        f"LinkedIn: {LINKEDIN} · GitHub: {GITHUB}",
    ])
    return subject, body


def sent_recently(address, now=None, log=LOG):
    now = now or datetime.now(timezone.utc)
    if not log.exists():
        return False
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        ts = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
        if e.get("to", "").lower() == address.lower() and e.get("sent") and now - ts < GAP:
            return True
    return False


def build_message(to, company, role=None, resume=RESUME, name=None):
    subject, body = compose(company, role, name)
    msg = EmailMessage()
    msg["From"] = f"Nandam Venkata Sai Raghava <{SENDER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if Path(resume).exists():
        msg.add_attachment(Path(resume).read_bytes(), maintype="application", subtype="pdf",
                           filename="NandamVenkataSaiRaghava_Resume.pdf")
    return msg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cold email a published recruiting address from Sai's Gmail.")
    ap.add_argument("--to", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--role")
    ap.add_argument("--name", help="recipient's first name for the greeting")
    ap.add_argument("--send", action="store_true", help="really send (default: preview only)")
    args = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    if sent_recently(args.to) and args.to.lower() != SENDER:
        sys.exit(f"Already emailed {args.to} in the last 30 days: not sending again.")
    msg = build_message(args.to, args.company, args.role, name=args.name)
    print(f"To: {msg['To']}\nSubject: {msg['Subject']}\n\n{msg.get_body(('plain',)).get_content()}")
    print(f"[attachment: {'resume.pdf' if RESUME.exists() else 'NONE'}]")
    if not args.send:
        print("\n(preview only: add --send to send)")
        return
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not password:
        sys.exit("GMAIL_APP_PASSWORD is not set in .env")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(SENDER, password)
        s.send_message(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "to": args.to, "company": args.company,
                             "role": args.role, "sent": True}) + "\n")
    print(f"\nSent to {args.to}.")


if __name__ == "__main__":
    main()

import os
import random
import smtplib
import socket
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import openai
from dotenv import load_dotenv

# Force IPv4 to fix WinError 10060 over Cloudflare WARP
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo

# Load environment variables
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = "sairaghava1318@gmail.com"

CATEGORIES = {
    "Women Safety": ["Molestation", "Harassment", "Domestic Violence", "Others"],
    "Traffic": ["Road Accident", "Abnormal Traffic", "Road Rage", "Others"],
    "Others": ["Others"]
}

def check_for_stop():
    """Checks the inbox for a STOP reply. Creates stopped.flag if found."""
    if os.path.exists("stopped.flag"):
        return True
        
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(SENDER_EMAIL, SENDER_PASSWORD)
        mail.select("inbox")
        
        # Search for unseen emails from the receiver
        status, messages = mail.search(None, f'(UNSEEN FROM "{RECEIVER_EMAIL}")')
        if status == "OK":
            for num in messages[0].split():
                typ, data = mail.fetch(num, "(RFC822)")
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        # Get body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body += part.get_payload(decode=True).decode(errors="ignore")
                        else:
                            body = msg.get_payload(decode=True).decode(errors="ignore")
                            
                        if "stop" in body.lower():
                            with open("stopped.flag", "w") as f:
                                f.write("STOP request received.")
                            print("STOP request detected. Automation paused forever.")
                            return True
        mail.logout()
    except Exception as e:
        print(f"Error checking IMAP: {e}")
    return False

def generate_incident_details(category, incident_type):
    prompt = f"""
    You are generating a highly realistic, fictional incident report for a sampling dataset.
    The category is '{category}' and the specific incident type is '{incident_type}'.
    
    Provide a JSON response with two keys:
    "title": A brief, professional title for the incident.
    "description": A detailed, unique description of the incident (around 3-4 sentences). Make it completely different from generic examples. Do NOT include any intro or outro text, just the JSON.
    """
    
    try:
        # Use OpenAI
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash",
            max_tokens=500,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
                {"role": "user", "content": prompt}
            ]
        )
        import json
        text = response.choices[0].message.content.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        data = json.loads(text)
        return data.get("title", f"Incident: {incident_type}"), data.get("description", "Description could not be generated.")
    except Exception as e:
        print(f"OpenAI API failed ({e}). Falling back to local templates.")
        # Fallback to local templates if OpenAI API fails
        templates = {
            "Molestation": [
                f"A report was filed regarding an incident near the central metro station where a suspect allegedly groped a passenger during rush hour.",
                f"An individual reported inappropriate physical contact by a stranger while walking through the community park in the evening.",
            ],
            "Harassment": [
                f"A formal complaint was lodged concerning repeated verbal harassment and stalking behavior by an unidentified individual outside a local cafe.",
                f"A victim experienced persistent catcalling and aggressive following for several blocks in the downtown district.",
            ],
            "Domestic Violence": [
                f"Police responded to a domestic disturbance call. Neighbors reported hearing loud shouting and breaking glass from the adjacent apartment.",
                f"A domestic violence incident was recorded involving a physical altercation between household members, requiring immediate medical assessment.",
            ],
            "Road Accident": [
                f"A severe two-car collision occurred on the main highway, resulting in significant vehicle damage and traffic rerouting for two hours.",
                f"A pedestrian was minorly injured after being clipped by a speeding vehicle that failed to stop at the crosswalk.",
            ],
            "Abnormal Traffic": [
                f"Unusual traffic congestion was observed spanning over 5 miles, caused by a sudden sinkhole opening on the right lane of the interstate.",
                f"Due to an unannounced protest march, the central business district experienced complete gridlock for over three hours.",
            ],
            "Road Rage": [
                f"An aggressive road rage incident escalated when a driver exited their vehicle at a red light and began striking the hood of the car behind them.",
                f"Authorities were called after a prolonged high-speed chase between two civilian vehicles weaving dangerously through suburban streets.",
            ],
            "Others": [
                f"A general public nuisance complaint was filed regarding a large group playing extremely loud music and blocking the sidewalk.",
                f"A report of minor vandalism was logged after several park benches were found covered in fresh graffiti.",
            ]
        }
        type_templates = templates.get(incident_type, templates["Others"])
        import random as rnd
        description = rnd.choice(type_templates)
        title = f"{incident_type} Incident Report"
        return title, description

def send_email(category, incident_type, title, description):
    subject = f"Daily Incident Report: {title}"
    body = f"""
New Incident Report (Sampling Data)

Category: {category}
Incident Type: {incident_type}

Title: {title}

Description:
{description}

---
To stop receiving these automated daily emails, simply reply to this email with the word "STOP".
"""
    
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, text)
        server.quit()
        print(f"Email sent successfully to {RECEIVER_EMAIL}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def main():
    if not all([OPENROUTER_API_KEY, SENDER_EMAIL, SENDER_PASSWORD]):
        print("Missing required environment variables in .env file.")
        return False, "Missing required environment variables in .env file."
        
    if check_for_stop():
        print("Script stopped due to user STOP request.")
        return False, "Script stopped due to user STOP request."
        
    category = random.choice(list(CATEGORIES.keys()))
    incident_type = random.choice(CATEGORIES[category])
    
    print(f"Selected - Category: {category}, Type: {incident_type}")
    print("Generating context...")
    title, description = generate_incident_details(category, incident_type)
    
    print(f"Generated Title: {title}")
    print("Sending email...")
    send_email(category, incident_type, title, description)
    return True, {"category": category, "type": incident_type, "title": title}

if __name__ == "__main__":
    main()

"""
SYSTEM DESIGN CONCEPT: Controller Layer (Model-View-Controller pattern)
This file handles HTTP routing only. It delegates the heavy lifting to the Domain/Service layers.
"""
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from api.core.db import init_db, SessionLocal
from api.domain.factory import NotifierFactory

app = Flask(__name__)
# Enable CORS so our React frontend (running on different port) can talk to this API
CORS(app)

# Initialize the Database
init_db()

from api.domain.repositories import NotificationRepository
from datetime import datetime, timezone

@app.route('/api/trigger', methods=['POST'])
def trigger_notification():
    """
    Expects JSON: {"type": "incident" | "leetcode"}
    """
    data = request.json or {}
    notif_type = data.get("type", "incident")

    db = SessionLocal()
    try:
        notifier = NotifierFactory.get_notifier(notif_type, db)
        result = notifier.run()
        
        if result["status"] == "success":
            return jsonify({"status": "success", "data": result})
        else:
            return jsonify({"status": "error", "message": "Failed to send email."}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/logs', methods=['GET'])
def get_logs():
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        logs = repo.get_all_leetcode_logs()
        return jsonify({"status": "success", "data": [{"id": l.id, "title": l.title, "is_completed": l.is_completed, "timestamp": l.timestamp.isoformat()} for l in logs]})
    finally:
        db.close()

@app.route('/api/logs/<int:log_id>', methods=['PUT'])
def update_log(log_id):
    db = SessionLocal()
    try:
        data = request.json
        repo = NotificationRepository(db)
        repo.mark_task_completed(log_id, data.get("is_completed", True))
        return jsonify({"status": "success"})
    finally:
        db.close()

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        if request.method == 'POST':
            interval = request.json.get("leetcode_interval_minutes", "60")
            repo.set_setting("leetcode_interval_minutes", str(interval))
            return jsonify({"status": "success"})
        else:
            interval = repo.get_setting("leetcode_interval_minutes", "60")
            return jsonify({"status": "success", "leetcode_interval_minutes": interval})
    finally:
        db.close()

@app.route('/api/cron', methods=['POST'])
def cron_trigger():
    db = SessionLocal()
    try:
        repo = NotificationRepository(db)
        interval_minutes = int(repo.get_setting("leetcode_interval_minutes", "60"))
        
        # Bug 5 fix: Only check successful sends, so a failed email doesn't reset the timer
        last_successful = repo.get_latest_successful_leetcode_log()
        if last_successful:
            elapsed = (datetime.now(timezone.utc) - last_successful.timestamp.replace(tzinfo=timezone.utc)).total_seconds() / 60.0
            if elapsed < interval_minutes:
                return jsonify({"status": "skipped", "message": f"Only {elapsed:.1f} mins elapsed."})
        
        notifier = NotifierFactory.get_notifier("leetcode", db)
        result = notifier.run()
        return jsonify({"status": "success", "data": result})
    finally:
        db.close()

from api.domain.pdf_analyzer import PDFAnalyzer

@app.route('/api/pdf/explain', methods=['POST'])
def explain_pdf():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Empty filename"}), 400
        
    # We will use 10 pages per chunk as requested
    analyzer = PDFAnalyzer(chunk_size=10)
    
    # We stream the results back using Server-Sent Events (SSE)
    return Response(analyzer.analyze_pdf_stream(file), mimetype='text/event-stream')

@app.route('/api/pdf/quiz', methods=['POST'])
def generate_quiz():
    data = request.json or {}
    text = data.get("text")
    if not text:
        return jsonify({"status": "error", "message": "No text provided"}), 400
        
    analyzer = PDFAnalyzer()
    result = analyzer.generate_quiz(text)
    
    if result["status"] == "success":
        return jsonify(result)
    else:
        return jsonify(result), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)

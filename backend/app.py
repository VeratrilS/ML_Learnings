"""
SYSTEM DESIGN CONCEPT: Controller Layer (Model-View-Controller pattern)
This file handles HTTP routing only. It delegates the heavy lifting to the Domain/Service layers.
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
from backend.core.db import init_db, SessionLocal
from backend.domain.factory import NotifierFactory

app = Flask(__name__)
# Enable CORS so our React frontend (running on different port) can talk to this API
CORS(app)

# Initialize the Database
init_db()

@app.route('/api/trigger', methods=['POST'])
def trigger_notification():
    """
    Expects JSON: {"type": "incident" | "leetcode"}
    """
    data = request.json or {}
    notif_type = data.get("type", "incident")

    # Dependency Injection: Get a fresh DB session for this request
    db = SessionLocal()
    try:
        # FACTORY PATTERN: Get the correct notifier instance
        notifier = NotifierFactory.get_notifier(notif_type, db)
        
        # POLYMORPHISM: We just call run(), we don't care if it's LeetCode or Incident!
        result = notifier.run()
        
        if result["status"] == "success":
            return jsonify({"status": "success", "data": result})
        else:
            return jsonify({"status": "error", "message": "Failed to send email."}), 400
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)

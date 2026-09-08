from flask import Flask, render_template, jsonify
from generate_and_send import main as generate_and_send_main

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/trigger', methods=['POST'])
def trigger_generation():
    success, data = generate_and_send_main()
    if success:
        return jsonify({"status": "success", "data": data})
    else:
        return jsonify({"status": "error", "message": data}), 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)

from flask import Flask, jsonify
from threading import Thread
import time
import os

app = Flask(__name__)
start_time = time.time()

@app.route('/')
def index():
    return "Bot is Alive and Running!"

@app.route('/health')
def health():
    uptime = int(time.time() - start_time)
    return jsonify({
        "status": "healthy",
        "uptime_seconds": uptime,
        "deployment": os.getenv("REPLIT_DEPLOYMENT") == "1",
        "timestamp": int(time.time())
    })

@app.route('/ping')
def ping():
    return "pong"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False)

def keep_alive():
    print("🌐 Starting keep-alive server on port 8080...")
    t = Thread(target=run)
    t.daemon = True
    t.start()
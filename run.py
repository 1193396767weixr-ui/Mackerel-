import sys
import os
import subprocess
import threading
import webbrowser
import time
from flask import Flask, send_from_directory

backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')

sys.path.insert(0, backend_dir)

from app import app as flask_app, init_db

init_db()

@flask_app.route('/')
def serve_index():
    return send_from_directory(frontend_dir, 'index.html')

@flask_app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(frontend_dir, path)

def open_browser():
    time.sleep(1)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    print("正在启动英语每日记录...")
    print("请在浏览器中访问 http://localhost:5000")
    print("按 Ctrl+C 退出程序")
    threading.Thread(target=open_browser, daemon=True).start()
    flask_app.run(host='0.0.0.0', port=5000, debug=False)

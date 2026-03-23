import http.server
import socketserver
import webbrowser
import os
import sys
import threading
import time
import ssl

PORT = 8765

class PWAServer(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
    
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    
    def guess_type(self, path):
        base, ext = os.path.splitext(path)
        if ext == '.js':
            return 'application/javascript'
        if ext == '.json':
            return 'application/json'
        if ext == '.svg':
            return 'image/svg+xml'
        if ext == '.webmanifest':
            return 'application/manifest+json'
        return super().guess_type(path)
    
    def log_message(self, format, *args):
        pass

def open_browser():
    time.sleep(1)
    webbrowser.open(f'http://localhost:{PORT}')

def main():
    print("=" * 50)
    print("       英语每日记录 - PWA版")
    print("=" * 50)
    print()
    print(f"服务已启动，请在浏览器中访问:")
    print(f"    http://localhost:{PORT}")
    print()
    print("iOS添加到主屏幕方法:")
    print("    1. 在Safari中打开上述网址")
    print("    2. 点击底部分享按钮")
    print("    3. 选择'添加到主屏幕'")
    print("    4. 点击'添加'")
    print()
    print("按 Ctrl+C 退出程序")
    print()
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    with socketserver.TCPServer(("", PORT), PWAServer) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n程序已退出")

if __name__ == "__main__":
    main()

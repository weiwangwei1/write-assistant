# -*- coding: utf-8 -*-
"""自定义静态服务器：为 dashboard 面板提供正确的 Content-Type。
- .jsonl/.txt/.md/.html 等均显式声明 charset=utf-8，避免浏览器乱码或触发下载。
用法：python serve.py [port]
"""
import functools
import http.server
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
ROOT = os.path.dirname(os.path.abspath(__file__))

# 静态文件扩展名 -> MIME 类型（显式带 charset，避免中文乱码/触发下载）
EXT_MAP = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jsonl": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".pdf": "application/pdf",
}

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        return EXT_MAP.get(ext, "application/octet-stream")

    def end_headers(self):
        # 关键：对文本类文件强制带 charset，避免 Windows 浏览器乱码
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    os.chdir(ROOT)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"TRAE 面板服务器已启动：http://localhost:{PORT}/dashboard.html?project=please")
    print(f"文档根目录：{ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
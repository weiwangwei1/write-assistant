# -*- coding: utf-8 -*-
"""本地接收服务器：浏览器页面 POST 数据 → 落盘到 raw/captures/"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = r'd:\personFile\write-assist\write-assistant\docs\topic-notes\research-20261013\raw\captures'
os.makedirs(OUT, exist_ok=True)

class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        path = self.path.strip('/').replace('..', '_').replace('/', '_') or 'unnamed.json'
        if not path.endswith('.json'):
            path += '.json'
        with open(os.path.join(OUT, path), 'wb') as f:
            f.write(body)
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK ' + str(len(body)).encode())
        print('saved', path, len(body), flush=True)

    def log_message(self, *a):
        pass

HTTPServer(('127.0.0.1', 8717), H).serve_forever()
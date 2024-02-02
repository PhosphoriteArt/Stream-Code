#!/usr/bin/env python3.9
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from util import create_logger, create_filter

import os
import multiprocessing
import threading
import signal

LOG = create_logger("transcription-server")
FILTER = create_filter()
HTML_PATH = Path(os.path.dirname(__file__)).joinpath("view_transcript.html")

HOST_NAME = "localhost"
SERVER_PORT = 8080
with open(HTML_PATH, "rb") as f:
    VIEW_HTML = f.read()

temp_text = ""
text_log = ""
text_mtx = threading.Lock()


class TranscriptHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Keep the server quiet
        pass
    
    def do_GET(self):
        global temp_text
        global text_mtx
        global text_log
        if "text" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            with text_mtx:
                self.wfile.write(bytes(text_log + temp_text, "utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(VIEW_HTML)

web_server_mtx = threading.Lock()
web_server = None
def start_server():
    global web_server
    with web_server_mtx:
        web_server = HTTPServer((HOST_NAME, SERVER_PORT), TranscriptHandler)
        LOG.info("Server started http://%s:%s" % (HOST_NAME, SERVER_PORT))

    try:
        web_server.serve_forever()
    except KeyboardInterrupt:
        pass

    web_server.server_close()
    LOG.info("transcript server stopped")


def start_listener(mp_q: multiprocessing.Queue):
    global temp_text
    global text_mtx
    global text_log
    while True:
        obj = mp_q.get()
        if "stop" in obj and obj["stop"]:
            LOG.info("transcript-reading loop finished")
            return
        with text_mtx:
            if "log" in obj:
                text_log += obj["log"] + "\n"
                temp_text = ""
            elif "stream" in obj:
                temp_text = obj["stream"]


def start(mp_q: multiprocessing.Queue):
    server_thread = threading.Thread(target=start_server)
    listener_thread = threading.Thread(target=start_listener, args=(mp_q,))
    server_thread.start()
    listener_thread.start()

    def on_term(*_):
        LOG.info("quitting")
        mp_q.put({"stop": True})
        with web_server_mtx:
            web_server.shutdown()
        


    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    server_thread.join()
    listener_thread.join()
    LOG.info("done")

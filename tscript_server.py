#!/usr/bin/env python3.9
from http.server import BaseHTTPRequestHandler, HTTPServer
import multiprocessing
import logging
import sys
import threading
from better_profanity import profanity

LOG = logging.getLogger("transcription-server")
LOG.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
LOG.addHandler(handler)

filter = profanity.load_censor_words(
    whitelist_words=[
        "fuck",
        "shit",
        "damn",
        "goddamn",
        "ass",
        "shitty",
        "fucking",
        "fucked",
        "hell",
        "crap",
        "asshole",
        "dick",
        "drunk",
        "dumb",
        "dumbass",
        "fat",
        "gay",
        "gays",
        "god",
        "homo",
        "lesbian",
        "lesbians",
        "lmao",
        "lust",
        "loin",
        "loins",
        "masochist",
        "menstruate",
        "naked",
        "nude",
        "nudes",
        "omg",
        "pee",
        "piss",
        "pot",
        "puss",
        "screw",
        "sex",
        "sexual",
        "smut",
        "stoned",
        "suck",
        "sucks",
        "tampon",
        "sucked",
        "thug",
        "thrust",
        "trashy",
        "ugly",
        "vomit",
        "weed",
        "weirdo",
        "weird",
        "womb",
        "yaoi",
        "yuri",
        "yury",
    ]
)


hostName = "localhost"
serverPort = 8080

curText = ""
textLog = ""
textLock = threading.Lock()


class MyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        global curText
        global textLock
        global textLog
        if "text" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            with textLock:
                self.wfile.write(bytes(textLog + curText, "utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                bytes(
                    """
<html>
  <head><title>Transcription</title></head>
  <body>
    <p id="text"></p>
    <script>
      const text = document.getElementById("text");

      async function updateText() {
        try {
          const res = await (await fetch("/text")).text();
          if (res) {
            text.innerText = res;
          }
          document.body.scrollTop = document.body.scrollHeight;
        } catch (e) {
          console.warn(e);
        }
        window.setTimeout(updateText, 750);
      }

      updateText();
    </script>
  </body>
</html>
""",
                    "utf-8",
                )
            )


def start_server():
    webServer = HTTPServer((hostName, serverPort), MyServer)
    LOG.info("Server started http://%s:%s" % (hostName, serverPort))

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    LOG.info("Server stopped.")


def start_listener(mp_q: multiprocessing.Queue):
    global curText
    global textLock
    global textLog
    while True:
        obj = mp_q.get()
        with textLock:
            if "log" in obj:
                textLog += obj["log"] + "\n"
                curText = ""
            elif "stream" in obj:
                curText = obj["stream"]


def start(mp_q: multiprocessing.Queue):
    server_thread = threading.Thread(target=start_server)
    listener_thread = threading.Thread(target=start_listener, args=(mp_q,))
    server_thread.start()
    listener_thread.start()

    server_thread.join()
    listener_thread.join()

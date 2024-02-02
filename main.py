#!/usr/bin/env python3.9
from nowplaying import start as start_nowplaying
from transcription import start as start_transcription
from tscript_server import start as start_server

from multiprocessing import Process, Queue
from os import kill
from signal import SIGINT

if __name__ == "__main__":
    transcription_queue = Queue()
    nowplaying = Process(target=start_nowplaying)
    transcription = Process(target=start_transcription, args=(transcription_queue,))
    server = Process(target=start_server, args=(transcription_queue,))
    nowplaying.start()
    transcription.start()
    server.start()

    try:
        while True:
            input()
    except KeyboardInterrupt:
        kill(nowplaying.pid, SIGINT)
        kill(server.pid, SIGINT)
        kill(transcription.pid, SIGINT)
        nowplaying.join()
        server.join()
        transcription.join()

#!/usr/bin/env python3.9
import signal

from nowplaying import start as start_nowplaying
from transcription import start as start_transcription
from tscript_server import start as start_server

from multiprocessing import Process, Queue, Semaphore
    

if __name__ == "__main__":
    transcription_queue = Queue()
    nowplaying = Process(target=start_nowplaying)
    transcription = Process(target=start_transcription, args=(transcription_queue,))
    server = Process(target=start_server, args=(transcription_queue,))
    nowplaying.start()
    transcription.start()
    server.start()

    lck = Semaphore(0)
    def on_term(*_):
        print("Cleaning up...")
        nowplaying.terminate()
        server.terminate()
        transcription.terminate()
        nowplaying.join()
        server.join()
        transcription.join()

        transcription_queue.close()
        lck.release()
    
    signal.signal(signal.SIGINT, on_term)
    lck.acquire()
    print("Quitting")
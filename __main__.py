#!/usr/bin/env python3.9
import signal

from nowplaying import start as start_nowplaying
from transcription_engine import start as start_transcription
from transcription_server import start as start_server

from multiprocessing import Process, Queue, Semaphore
    

if __name__ == "__main__":
    # Queue message format: Dictionary ->
    #   log:     committed text that won't change anymore
    #   stream:  streaming text that hasn't finished changing yet
    #   stop:    if true, we're shutting down
    transcription_queue = Queue()
    nowplaying = Process(target=start_nowplaying)
    transcription = Process(target=start_transcription, args=(transcription_queue,))
    server = Process(target=start_server, args=(transcription_queue,))

    nowplaying.start()
    transcription.start()
    server.start()

    exit_lock = Semaphore(0)
    quitting = False
    def on_term(*_):
        global quitting
        if quitting:
            return
        quitting = True
        print("Cleaning up...")
        nowplaying.terminate()
        server.terminate()
        transcription.terminate()
        nowplaying.join()
        server.join()
        transcription.join()

        transcription_queue.close()
        exit_lock.release()
    
    signal.signal(signal.SIGINT, on_term)
    exit_lock.acquire()
    print("Quitting")
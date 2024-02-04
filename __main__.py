#!/usr/bin/env python3.9
import signal

from nowplaying import start as start_nowplaying
from transcription_engine import start as start_transcription
from transcription_server import start as start_server

from multiprocessing import Process, Queue, Semaphore

class NonlocalBreak(Exception):
    pass

if __name__ == "__main__":
    # Queue message format: Dictionary ->
    #   log:     committed text that won't change anymore
    #   stream:  streaming text that hasn't finished changing yet
    #   stop:    if true, we're shutting down
    #   clear:   clear transcription log
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

        # Escapes the loop below even if we ^C instead of writing 'q'
        raise NonlocalBreak()
    
    signal.signal(signal.SIGINT, on_term)
    try:
        while True:
            inp = input("Type q and press enter to quit, or clear and enter to clear the log:").strip().lower()
            if inp == "q":
                on_term()
                # on_term will break the loop
            elif inp == "clear":
                transcription_queue.put({'clear': True})
    except NonlocalBreak:
        pass
    exit_lock.acquire()
    print("Quitting")
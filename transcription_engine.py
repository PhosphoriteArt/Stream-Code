#!/usr/bin/env python3.9
from pathlib import Path
from contextlib import contextmanager
from util import create_logger

import multiprocessing
import sounddevice
import numpy
import time
import queue
import sys
import os
import soundfile
import signal

LOG = create_logger("transcription-engine")

ME = Path(os.path.dirname(__file__))
WAV_FILE = ME.joinpath(".transcript_temp.wav").resolve()

EMPTY_CUT_TO_S = 5
SEGMENT_TRAILS_CUT_PAST_S = 0
WINDOW_S = 2

NO_SPEECH_MAX = 0.2

exit = False
def on_term(*_):
    global exit
    LOG.info("exiting")
    exit = True

@contextmanager
def silenced_stderr():
    orig_stderr = sys.stderr
    try:
        with open(os.devnull, "w") as null:
            sys.stderr = null
            yield
    finally:
        sys.stderr = orig_stderr


def start(log_queue: multiprocessing.Queue):
    global exit

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # Silence whisper errors
    with silenced_stderr():
        import whisper

    model = whisper.load_model("base.en", in_memory=True)
    audio_queue = queue.Queue()

    audio_data = None

    def audio_callback(indata: numpy.ndarray, frames: int, time, status):
        if status:
            LOG.error(status, file=sys.stderr)
        audio_queue.put(indata.copy())

    try:
        with sounddevice.InputStream(callback=audio_callback, latency=1.0, channels=1) as istream:
            LOG.info(f"Readying window ({WINDOW_S} seconds)...")

            def time_to_samples(t):
                return int(t * istream.samplerate)

            def cur_len_s():
                nonlocal audio_data
                if audio_data is None:
                    return 0
                return len(audio_data) / istream.samplerate

            def receive():
                nonlocal audio_data
                didGetAll = False
                while not didGetAll:
                    try:
                        indata = audio_queue.get_nowait()
                    except queue.Empty:
                        indata = audio_queue.get()
                        didGetAll = True
                    audio_data = indata if audio_data is None else numpy.concatenate((audio_data, indata))

            def export_wav(to=str(WAV_FILE)):
                with soundfile.SoundFile(
                    file=to, mode="w", samplerate=int(istream.samplerate), channels=int(istream.channels)
                ) as sf:
                    sf.write(audio_data)

            while not exit:
                receive()

                if cur_len_s() >= WINDOW_S:
                    export_wav()

                    fl = whisper.load_audio(str(WAV_FILE))
                    start = time.time()
                    with silenced_stderr():
                        tscript = model.transcribe(
                            fl,
                            no_speech_threshold=NO_SPEECH_MAX,
                            condition_on_previous_text=False
                        )
                    dur = round(time.time() - start, 2)
                    orig_len = len(audio_data) / istream.samplerate

                    if len(tscript["segments"]) > 1:
                        LOG.debug("Cutting segments!")
                        segment_cutoff = time_to_samples(tscript["segments"][-2]["end"])
                        audio_data = audio_data[segment_cutoff:]
                        prev_text = "".join(
                            segment["text"]
                            for segment in tscript["segments"][:-1]
                            if segment["no_speech_prob"] < NO_SPEECH_MAX
                        )
                        log_queue.put({"log": prev_text})
                    elif all(segment["no_speech_prob"] > 0.3 for segment in tscript["segments"]):
                        LOG.debug("Cutting empty data")
                        audio_data = audio_data[min(max(0, len(audio_data) - time_to_samples(EMPTY_CUT_TO_S)), len(audio_data)) :]
                    elif len(tscript["segments"]) == 1 and cur_len_s() - tscript["segments"][0]["end"] > 7:
                        LOG.debug("Segment is done, cutting")
                        audio_data = audio_data[
                            max(
                                min(
                                    len(audio_data),
                                    time_to_samples(tscript["segments"][0]["end"] + SEGMENT_TRAILS_CUT_PAST_S),
                                ),
                                len(audio_data),
                            ) :
                        ]
                        if tscript["segments"][0]["no_speech_prob"] < NO_SPEECH_MAX:
                            log_queue.put({"log": tscript["segments"][0]["text"]})
                        tscript["segments"][0]["text"] = ""

                    if len(tscript["segments"]) >= 1:
                        cur_text = tscript["segments"][-1]["text"]
                        LOG.info(f"STT {dur}s / LEN {orig_len}s: {cur_text}")
                        if not all(segment["no_speech_prob"] > 0.3 for segment in tscript["segments"]):
                            log_queue.put({"stream": cur_text})
                    else:
                        LOG.info(f"STT {dur}s / LEN {orig_len}s: [empty]")

    except KeyboardInterrupt:
        LOG.warn("\nInterrupted by user")
    except Exception as e:
        LOG.error(type(e).__name__ + ": " + str(e))
    
    if WAV_FILE.exists():
        WAV_FILE.unlink()
    LOG.info("done")


if __name__ == "__main__":
    start()

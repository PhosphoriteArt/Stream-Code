#!/usr/bin/env python3.9
import multiprocessing
import sounddevice
import wavio
import numpy
import time
import queue
import sys
import os
import soundfile
import signal
import logging

LOG = logging.getLogger("streaming-trascription")
LOG.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
LOG.addHandler(handler)

EMPTY_CUT_TO_S = 5
SEGMENT_TRAILS_CUT_PAST_S = 0
WINDOW_S = 2

NO_SPEECH_MAX = 0.2

exit = False
def on_term(*_):
    global exit
    LOG.info("shutting down transcription engine")
    exit = True



def start(logQueue: multiprocessing.Queue):
    sys.stderr = open(os.devnull, "w")
    import whisper

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    model = whisper.load_model("base.en", in_memory=True)
    q = queue.Queue()

    data = None

    def cb(indata: numpy.ndarray, frames: int, time, status):
        if status:
            LOG.error(status, file=sys.stderr)
        q.put(indata.copy())

    try:
        with sounddevice.InputStream(callback=cb, latency=1.0, channels=1) as istream:
            LOG.info(f"Readying window ({WINDOW_S} seconds)...")

            def time_to_samples(t):
                return int(t * istream.samplerate)

            def cur_len_s():
                nonlocal data
                if data is None:
                    return 0
                return len(data) / istream.samplerate

            def receive():
                nonlocal data
                didGetAll = False
                while not didGetAll:
                    try:
                        indata = q.get_nowait()
                    except queue.Empty:
                        indata = q.get()
                        didGetAll = True
                    data = indata if data is None else numpy.concatenate((data, indata))

            def export_wav(to="test.wav"):
                with soundfile.SoundFile(
                    file=to, mode="w", samplerate=int(istream.samplerate), channels=int(istream.channels)
                ) as sf:
                    sf.write(data)

            while not exit:
                receive()

                if cur_len_s() >= WINDOW_S:
                    export_wav()

                    fl = whisper.load_audio("test.wav")
                    start = time.time()
                    tscript = model.transcribe(
                        fl,
                        no_speech_threshold=NO_SPEECH_MAX,
                        condition_on_previous_text=False
                        # word_timestamps=True,
                    )
                    dur = round(time.time() - start, 2)
                    orig_len = len(data) / istream.samplerate
                    # print(tscript)

                    if len(tscript["segments"]) > 1:
                        LOG.debug("Cutting segments!")
                        segment_cutoff = time_to_samples(tscript["segments"][-2]["end"])
                        data = data[segment_cutoff:]
                        prev_text = "".join(
                            segment["text"]
                            for segment in tscript["segments"][:-1]
                            if segment["no_speech_prob"] < NO_SPEECH_MAX
                        )
                        logQueue.put({"log": prev_text})
                    elif all(segment["no_speech_prob"] > 0.3 for segment in tscript["segments"]):
                        LOG.debug("Cutting empty data")
                        data = data[min(max(0, len(data) - time_to_samples(EMPTY_CUT_TO_S)), len(data)) :]
                    elif len(tscript["segments"]) == 1 and cur_len_s() - tscript["segments"][0]["end"] > 7:
                        LOG.debug("Segment is done, cutting")
                        data = data[
                            max(
                                min(
                                    len(data),
                                    time_to_samples(tscript["segments"][0]["end"] + SEGMENT_TRAILS_CUT_PAST_S),
                                ),
                                len(data),
                            ) :
                        ]
                        if tscript["segments"][0]["no_speech_prob"] < NO_SPEECH_MAX:
                            logQueue.put({"log": tscript["segments"][0]["text"]})
                        tscript["segments"][0]["text"] = ""

                    if len(tscript["segments"]) >= 1:
                        cur_text = tscript["segments"][-1]["text"]
                        LOG.info(f"STT {dur}s / LEN {orig_len}s: {cur_text}")
                        if not all(segment["no_speech_prob"] > 0.3 for segment in tscript["segments"]):
                            logQueue.put({"stream": cur_text})
                    else:
                        LOG.info(f"STT {dur}s / LEN {orig_len}s: [empty]")

    except KeyboardInterrupt:
        LOG.warn("\nInterrupted by user")
    except Exception as e:
        LOG.error(type(e).__name__ + ": " + str(e))
    
    LOG.info("transcription engine shutdown complete")


if __name__ == "__main__":
    start()

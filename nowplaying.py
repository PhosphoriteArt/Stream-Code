#!/usr/bin/env python3.9
# This module exports now-playing information that can be read by OBS

from subprocess import run, PIPE
from time import sleep
from pathlib import Path
from typing import Optional
from PIL import Image
from io import BytesIO
from abc import ABC, abstractmethod
from util import create_logger
import os
import base64
import platform
import daemon
import asyncio
import signal

LOG = create_logger("now-playing")

HOME = Path.home()
DEST = HOME.joinpath(".stream")
ME = Path(os.path.dirname(__file__))

TITLE_PATH = DEST.joinpath("title.txt")
ARTIST_PATH = DEST.joinpath("artist.txt")
ALBUM_PATH = DEST.joinpath("album.txt")
PROGRESS_PATH = ME.joinpath("res", "progress.png")

ARTWORK_PATH = DEST.joinpath("artwork.png")
ARTWORK_DEFAULT_PATH = ME.joinpath("res", "default_music.png")


exit = False
def on_term(*_):
    LOG.info("exiting")
    global exit
    exit = True


def artwork_is_default():
    if not ARTWORK_PATH.exists():
        return False

    return ARTWORK_PATH.samefile(ARTWORK_DEFAULT_PATH)


class MediaInfo(ABC):
    @staticmethod
    def create():
        if platform.system() == "Darwin":
            return MediaInfoImplMacOS()
        elif platform.system() == "Windows":
            return MediaInfoImplWindows()
        raise NotImplementedError("MediaInfo is not implemented on " + platform.system())

    @staticmethod
    def progress_as_image(progress: float, width=200, height=10) -> Image:
        progress = round(progress * width)
        progressImg = Image.new("RGBA", (width, height))
        for y in range(progressImg.height):
            for i in range(progress):
                progressImg.putpixel((i, y), (255, 255, 255, 255))
            for i in range(progress + 1, progressImg.width):
                progressImg.putpixel((i, y), (0, 0, 0, 0))

        return progressImg

    @property
    @abstractmethod
    def title(self) -> str:
        ...

    @property
    @abstractmethod
    def artist(self) -> str:
        ...

    @property
    @abstractmethod
    def album(self) -> str:
        ...

    @property
    @abstractmethod
    def artwork(self) -> Optional[Image.Image]:
        ...

    @property
    @abstractmethod
    def progress(self) -> Optional[float]:
        ...


class MediaInfoImplMacOS(MediaInfo):
    def __init__(self) -> None:
        super().__init__()
        self._nowplaying_cli = ME.joinpath("lib", "nowplaying-cli")
        self._base_args = [str(self._nowplaying_cli.resolve()), "get"]

    @property
    def title(self) -> str:
        title = run([*self._base_args, "title"], stdout=PIPE).stdout.decode().strip()
        return "" if title == "null" else title

    @property
    def artist(self) -> str:
        artist = run([*self._base_args, "artist"], stdout=PIPE).stdout.decode().strip()
        return "" if artist == "null" else artist

    @property
    def album(self) -> str:
        album = run([*self._base_args, "album"], stdout=PIPE).stdout.decode().strip()
        return "" if album == "null" else album

    @property
    def artwork(self) -> Optional[Image.Image]:
        artworkDataB64 = run([*self._base_args, "artworkData"], stdout=PIPE).stdout.decode().strip().encode("utf-8")
        if artworkDataB64 == b"null":
            return None

        artworkData = base64.decodebytes(artworkDataB64)
        return Image.open(BytesIO(artworkData))

    @property
    def progress(self) -> Optional[float]:
        duration = run([*self._base_args, "duration"], stdout=PIPE).stdout.decode().strip()
        elapsed = run([*self._base_args, "elapsedTime"], stdout=PIPE).stdout.decode().strip()

        if duration == "null" or elapsed == "null":
            return None

        duration = float(duration)
        elapsed = float(elapsed)
        if duration == 0:
            return 0.0

        return elapsed / duration


class MediaInfoImplWindows(MediaInfo):
    def __init__(self) -> None:
        super().__init__()
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager

        self._media_manager = MediaManager

    # source: https://stackoverflow.com/questions/65011660/how-can-i-get-the-title-of-the-currently-playing-media-in-windows-10-with-python
    async def _get_media_info_async(self):
        sessions = await self._media_manager.request_async()

        current_session = sessions.get_current_session()
        if current_session:  # there needs to be a media session running
            info = await current_session.try_get_media_properties_async()

            # song_attr[0] != '_' ignores system attributes
            info_dict = {song_attr: info.__getattribute__(song_attr) for song_attr in dir(info) if song_attr[0] != "_"}

            # converts winrt vector to list
            info_dict["genres"] = list(info_dict["genres"])

            return info_dict
        return None

    @staticmethod
    async def _read_stream_into_buffer(stream_ref, buffer):
        from winsdk.windows.storage.streams import InputStreamOptions

        readable_stream = await stream_ref.open_read_async()
        readable_stream.read_async(buffer, buffer.capacity, InputStreamOptions.READ_AHEAD)

    @staticmethod
    def _get_artwork_from_stream_ref(reference) -> bytes:
        from winsdk.windows.storage.streams import Buffer, DataReader

        thumb_read_buffer = Buffer(5 * 1024 * 1024)  # 5MB
        asyncio.run(MediaInfoImplWindows._read_stream_into_buffer(reference, thumb_read_buffer))
        buffer_reader = DataReader.from_buffer(thumb_read_buffer)
        byte_buffer = buffer_reader.read_bytes(thumb_read_buffer.length)
        return byte_buffer

    def _get_media_info(self):
        return asyncio.run(self._get_media_info_async())

    @property
    def title(self) -> str:
        info = self._get_media_info()
        if info is None or "title" not in info or info["title"] is None:
            return ""

        return info["title"]

    @property
    def artist(self) -> str:
        info = self._get_media_info()
        if info is None or "album_artist" not in info or info["album_artist"] is None:
            return ""

        return info["album_artist"]

    @property
    def album(self) -> str:
        info = self._get_media_info()
        if info is None or "album_title" not in info or info["album_title"] is None:
            return ""

        return info["album_title"]

    @property
    def artwork(self) -> Optional[Image.Image]:
        info = self._get_media_info()
        if info is None or "thumbnail" not in info or info["thumbnail"] is None:
            return None

        return Image.open(BytesIO(MediaInfoImplWindows._get_artwork_from_stream_ref(info["thumbnail"])))

    @property
    def progress(self) -> Optional[float]:
        # Not supported on Windows
        return None


def start():
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    DEST.mkdir(parents=True, exist_ok=True)

    info = MediaInfo.create()

    last_progress = None
    last_info = None
    while not exit:
        title, artist, album = curr_info = (info.title, info.artist, info.album)
        TITLE_PATH.write_text(title)
        ARTIST_PATH.write_text(artist)
        ALBUM_PATH.write_text(album)

        progress = info.progress
        progress = 0 if progress is None else progress
        if progress != last_progress:
            last_progress = progress
            MediaInfo.progress_as_image(progress).save(PROGRESS_PATH)

        artwork = info.artwork
        if curr_info != last_info:
            last_info = curr_info
            LOG.info(curr_info)
            if artwork is not None:
                if artwork_is_default():
                    ARTWORK_PATH.unlink()
                artwork.save(ARTWORK_PATH)
            elif not artwork_is_default():
                if ARTWORK_PATH.exists():
                    ARTWORK_PATH.unlink()
                os.link(ARTWORK_DEFAULT_PATH, ARTWORK_PATH)

        sleep(0.5)
    
    if TITLE_PATH.exists():
        TITLE_PATH.unlink()
    if ARTIST_PATH.exists():
        ARTIST_PATH.unlink()
    if ARTWORK_PATH.exists():
        ARTWORK_PATH.unlink()
    if ALBUM_PATH.exists():
        ALBUM_PATH.unlink()
    LOG.info("done")


if __name__ == "__main__":
    with open("/tmp/stream-nowplaying.err", "w+") as errlog:
        with open("/tmp/stream-nowplaying.out", "w+") as outlog:
            with daemon.DaemonContext(stdout=outlog, stderr=errlog):
                start()

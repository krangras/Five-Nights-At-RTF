import pygame
import cv2
import numpy as np
import subprocess
import tempfile
import os
import atexit
from imageio_ffmpeg import get_ffmpeg_exe


class ScreamerPlayer:
    def __init__(self, video_path, screen_size=(1280, 720)):
        self.video_path = video_path
        self.screen_size = screen_size
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0:
            self.fps = 30

        self._temp_wav = None
        self._sound = None
        atexit.register(self.close)

    def extract_audio(self):
        try:
            ffmpeg = get_ffmpeg_exe()
            self._temp_wav = tempfile.mktemp(suffix=".wav")
            subprocess.run(
                [ffmpeg, "-i", self.video_path, "-vn",
                 "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                 "-y", self._temp_wav],
                capture_output=True, timeout=30
            )
            if os.path.exists(self._temp_wav) and os.path.getsize(self._temp_wav) > 1000:
                self._sound = pygame.mixer.Sound(self._temp_wav)
        except Exception as e:
            print(f"Screamer audio error: {e}")

    def get_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = np.ascontiguousarray(frame.swapaxes(0, 1))
        surf = pygame.surfarray.make_surface(frame)
        surf = surf.convert()
        if surf.get_size() != self.screen_size:
            surf = pygame.transform.smoothscale(surf, self.screen_size)
        return surf

    def play_audio(self):
        if self._sound:
            self._sound.play()

    def close(self):
        atexit.unregister(self.close)
        if self.cap:
            self.cap.release()
            self.cap = None
        if self._temp_wav and os.path.exists(self._temp_wav):
            try:
                os.remove(self._temp_wav)
            except OSError:
                pass
            self._temp_wav = None

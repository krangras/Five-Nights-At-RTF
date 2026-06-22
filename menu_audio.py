import pygame

from audio_mix import apply_music_volume, effective_volume, ensure_audio_settings


MENU_MUSIC_PATH = "sounds/menu/Faulty_Ventilation.mp3"
MENU_BLIP_PATH = "sounds/ui/blip3.mp3"
MENU_MUSIC_DEFAULT_VOLUME = 0.42
MENU_HOVER_DEFAULT_VOLUME = 0.30


class MenuAudio:
    def __init__(self, settings_data=None):
        self.settings_data = ensure_audio_settings(settings_data)
        self._blip_sound = None
        self._music_loaded = False

    def ensure_music(self):
        if pygame.mixer.music.get_busy():
            apply_music_volume(self.settings_data, "menu_music", MENU_MUSIC_DEFAULT_VOLUME)
            return
        if not self._music_loaded:
            try:
                pygame.mixer.music.load(MENU_MUSIC_PATH)
                self._music_loaded = True
            except pygame.error:
                return
        try:
            pygame.mixer.music.play(-1)
            apply_music_volume(self.settings_data, "menu_music", MENU_MUSIC_DEFAULT_VOLUME)
        except pygame.error:
            pass

    def stop_music(self):
        pygame.mixer.music.stop()

    def play_hover(self):
        if self._blip_sound is None:
            try:
                self._blip_sound = pygame.mixer.Sound(MENU_BLIP_PATH)
            except pygame.error:
                return
        self._blip_sound.set_volume(
            effective_volume(self.settings_data, "menu_hover", MENU_HOVER_DEFAULT_VOLUME)
        )
        self._blip_sound.play()

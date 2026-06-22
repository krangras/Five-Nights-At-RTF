"""Server and laptop power, hacking, and reboot presentation logic."""

from fnar.services.laptop_power import LAPTOP_BOOT_TICKS, LAPTOP_SHUTDOWN_TICKS


HACK_TICKS_BY_NIGHT: dict[int, int] = {
    1: 3900,
    2: 5400,
    3: 6900,
    4: 8700,
    5: 10500,
}


class LaptopControllerMixin:
    """Coordinate laptop/server transitions while the model owns state."""

    def _update_server_anim(self) -> None:
        """Анимация включения/выключения сервера.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if self.model.server_state == "TURNING_ON":
            self._on_phase_frames -= 1
            if self._on_phase_frames <= 0:
                self._on_phase += 1
                if self._on_phase >= 8:
                    self.model.server_state = "ON"
                    self.model.server_blink = None
                    self.model.hack_active = True
                    self.model.server_overload = False
                    self.model.server_overload_warn = 0
                    self.model.schedule_next_overload()
                    if self.snd_work:
                        self.snd_work.play(-1)
                    return
                blink_seq = [
                    "red",
                    None,
                    "red",
                    None,
                    "green",
                    None,
                    "green",
                    None,
                ]
                self.model.server_blink = blink_seq[self._on_phase]
                self._on_phase_frames = 10

        elif self.model.server_state == "TURNING_OFF":
            if self._transition_frames <= 0:
                self._transition_frames = 60
                if self.snd_work:
                    self.snd_work.stop()
                if self.snd_off:
                    self.snd_off.play()
            self._transition_frames -= 1
            if self._transition_frames <= 0:
                self.model.server_state = "OFF"
                try_last_chance = getattr(self.model, "try_last_chance_server_shutdown", None)
                if try_last_chance is not None:
                    try_last_chance()

    def _shutdown_server_hotkey(self) -> None:
        """Выключить сервер клавишей S независимо от приложения и угрозы Алгема.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if self.model.game_over:
            return
        if self.model.server_state == "ON":
            self._toggle_server()
        elif self.model.server_state == "TURNING_ON":
            notify_shutdown = getattr(self.model, "notify_manual_server_shutdown_started", None)
            if notify_shutdown is not None:
                notify_shutdown()
            self.model.server_state = "TURNING_OFF"
            self._transition_frames = self._off_frames
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()

    def _toggle_server(self) -> None:
        """Включить или выключить сервер.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        self._check_node5_attack()
        if self.model.game_over:
            return
        if self.model.server_state == "ON":
            notify_shutdown = getattr(self.model, "notify_manual_server_shutdown_started", None)
            if notify_shutdown is not None:
                notify_shutdown()
            self.model.server_state = "TURNING_OFF"
            self._transition_frames = self._off_frames
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()
        elif self.model.server_state == "OFF":
            if self.model.laptop_power_state != "ON":
                return
            self.model.server_state = "TURNING_ON"
            self.model.server_blink = "red"
            self._on_phase = 0
            self._on_phase_frames = 10
            if self.snd_on:
                self.snd_on.play()

    def _update_laptop(self) -> None:
        """Состояния питания ноутбука без промежуточного zoom-режима.

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        self.model.laptop_zoom = 1.0 if self.model.laptop_open else 0.0

        if self.model.laptop_power_state == "BOOTING":
            if self.model.laptop_power_timer > 0:
                self.model.laptop_power_timer -= 1
            if self.model.laptop_power_timer > 90:
                self.model.laptop_boot_stage = "boot_black"
            elif self.model.laptop_power_timer > 0:
                self.model.laptop_boot_stage = "initializing"
                if self.model.laptop_power_timer <= 24 and not self._laptop_boot_sound_played:
                    if self.snd_laptop_on:
                        self.snd_laptop_on.play()
                    self._laptop_boot_sound_played = True
            else:
                self.model.laptop_power_state = "ON"
                self.model.laptop_boot_stage = "desktop"

        elif self.model.laptop_power_state == "SHUTTING_DOWN":
            if self.model.laptop_power_timer > 0:
                self.model.laptop_power_timer -= 1
            else:
                self.model.laptop_power_state = "OFF"
                self.model.laptop_boot_stage = "boot_black"

    def _update_hack(self) -> None:
        """Прогресс взлома через ноутбук (Claude Mythos).

        Args:
            Нет.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        # Взлом запускается из Claude Mythos и продвигается только пока сервер ON.
        # Во время ребута, перегрузки или выключенного сервера прогресс стоит.
        if self.model.laptop_app == "claude_mythos" and self.model.server_state == "ON" and not self.model.server_rebooting and not self.model.server_overload:
            self.model.hack_active = True
        if self.model.hack_active and not self.model.server_rebooting and not self.model.server_overload and self.model.server_state == "ON":
            hack_ticks = HACK_TICKS_BY_NIGHT.get(self.model.night, HACK_TICKS_BY_NIGHT[5])
            hack_rate = 1.0 / hack_ticks
            was_complete = self.model.hack_progress >= 1.0
            self.model.hack_progress = min(1.0, self.model.hack_progress + hack_rate)
            if not was_complete and self.model.hack_progress >= 1.0:
                start_post_hack = getattr(self.model, "_start_post_hack_phase", None)
                if start_post_hack is not None:
                    start_post_hack()

    def _update_reboot_sound(self) -> None:
        if self.model.server_rebooting and not self._wait_playing:
            self._wait_playing = True
            self._wait_timer = 0
            if self.snd_wait:
                self.snd_wait.play()
        if not self.model.server_rebooting and self._wait_playing:
            if self.snd_wait:
                self.snd_wait.stop()
            self._wait_playing = False

        if self._wait_playing:
            self._wait_timer += 1
            if self._wait_timer >= 180:
                self._wait_timer = 0
                if self.snd_wait:
                    self.snd_wait.play()

    def _start_laptop_boot(self) -> None:
        if self.model.laptop_power_state != "OFF":
            return
        self.model.laptop_power_state = "BOOTING"
        self.model.laptop_power_timer = LAPTOP_BOOT_TICKS
        self.model.laptop_boot_stage = "boot_black"
        self.model.laptop_start_menu = False
        self.model.laptop_app = None
        self._laptop_saved_app = None
        self._laptop_saved_menu = False
        self._projection_overlay_active = False
        self._projection_corner_idx = 0
        self._projection_dragging = False
        self._projection_overlay_active = False
        self._projection_corner_idx = 0
        self._projection_dragging = False
        self.model.ad_active = False
        self.model.ad_image_key = None
        self._laptop_boot_sound_played = False
        self._trigger_laptop_power_noise("on")

    def _start_laptop_shutdown(self) -> None:
        if self.model.laptop_power_state != "ON":
            return
        self._trigger_laptop_power_noise("off")
        self._sync_server_with_laptop_shutdown()
        self.model.laptop_power_state = "SHUTTING_DOWN"
        self.model.laptop_power_timer = LAPTOP_SHUTDOWN_TICKS
        self._laptop_boot_sound_played = False
        self.model.laptop_start_menu = False
        self.model.laptop_app = None
        self._laptop_saved_app = None
        self._laptop_saved_menu = False
        self.model.ad_active = False
        self.model.ad_image_key = None
        if self.snd_laptop_off:
            self.snd_laptop_off.play()

    def _trigger_laptop_power_noise(self, event: str) -> None:
        """Forward laptop on/off sounds to Algem with distance-based reaction.

        Args:
            event: Параметр типа ``str``, используемый методом ``_trigger_laptop_power_noise``.

        Returns:
            ``None``. Метод выполняет действие или обновляет состояние объекта."""
        if self.model.night <= 1:
            return
        self.model.notify_laptop_power_event(event)

    def _sync_server_with_laptop_shutdown(self) -> None:
        self.model.server_overload = False
        self.model.server_overload_warn = 0
        self.model.server_rebooting = False
        self.model.server_reboot_timer = 0
        self.model.hack_active = False
        if self.model.server_state in ("ON", "TURNING_ON", "TURNING_OFF"):
            self.model.server_state = "OFF"
            self._transition_frames = 0
            self.model.server_blink = None
            if self.snd_work:
                self.snd_work.stop()
            if self.snd_off:
                self.snd_off.play()

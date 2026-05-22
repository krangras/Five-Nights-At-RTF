import pygame
import random

def _normalize_brightness(images, target=15):
    for img in images:
        w, h = img.get_size()
        total = 0
        count = 0
        for y in range(0, h, 4):
            for x in range(0, w, 4):
                r, g, b, _ = img.get_at((x, y))
                total += int(0.299 * r + 0.587 * g + 0.114 * b)
                count += 1
        avg = total / count if count else target
        if avg > 0:
            factor = target / avg
            for y in range(h):
                for x in range(w):
                    r, g, b, a = img.get_at((x, y))
                    img.set_at((x, y), (
                        min(255, int(r * factor)),
                        min(255, int(g * factor)),
                        min(255, int(b * factor)),
                        a
                    ))

class GameView:
    def __init__(self, screen):
        self.screen = screen
        screen_w, screen_h = screen.get_size()

        raw_off = pygame.image.load("assets/office/server_is_off.png").convert()
        scale = screen_h / raw_off.get_height()
        target_size = (int(raw_off.get_width() * scale), screen_h)

        self.bg_off = pygame.transform.smoothscale(raw_off, target_size)

        self.bg_blinks = {}
        for name, key in [("server_turning_on_red.png", "red"), ("server_turning_on_green.png", "green")]:
            raw = pygame.image.load(f"assets/office/{name}").convert()
            self.bg_blinks[key] = pygame.transform.smoothscale(raw, target_size)

        self.bg_frames = []
        for name in ["office1.png", "office2.png"]:
            raw = pygame.image.load(f"assets/office/{name}").convert()
            self.bg_frames.append(pygame.transform.smoothscale(raw, target_size))
        _normalize_brightness([self.bg_off] + list(self.bg_blinks.values()) + self.bg_frames)

        self.max_offset = max(0, target_size[0] - screen_w)
        self.screen_w = screen_w
        self.font = pygame.font.SysFont("OCR-A", 30)
        self.switch_timer = random.randint(60, 180)
        self.current_idx = 0
        self.scale = scale
        self.server_hotspot = pygame.Rect(1151, 163, 131, 244)

        # Планшет — 10 отдельных картинок без фона
        self.cam_frames = []
        for i in range(1, 11):
            img = pygame.image.load(f"assets/office/tablet/tablet-{i}.png").convert_alpha()
            self.cam_frames.append(pygame.transform.smoothscale(img, (screen_w, screen_h)))

    def is_server_clicked(self, mouse_pos, offset):
        img_x = (mouse_pos[0] + offset) / self.scale
        img_y = mouse_pos[1] / self.scale
        return self.server_hotspot.collidepoint(img_x, img_y)

    def draw(self, model):
        offset = int((model.current_look + 1) / 2 * self.max_offset)

        if model.server_state == "OFF":
            self.screen.blit(self.bg_off, (-offset, 0))
        elif model.server_state == "TURNING_ON":
            img = self.bg_blinks.get(model.server_blink, self.bg_off)
            self.screen.blit(img, (-offset, 0))
        elif model.server_state == "TURNING_OFF":
            self.screen.blit(self.bg_off, (-offset, 0))
        elif model.server_state == "ON":
            self.switch_timer -= 1
            if self.switch_timer <= 0:
                self.current_idx = 1 - self.current_idx
                self.switch_timer = random.randint(60, 180)
            self.screen.blit(self.bg_frames[self.current_idx], (-offset, 0))

        if model.server_state != "OFF":
            if model.door_left_closed:
                pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, 300, 720))
            if model.door_right_closed:
                pygame.draw.rect(self.screen, (0, 0, 0), (980, 0, 300, 720))

        if model.tablet_open or model.tablet_animating:
            idx = model.tablet_anim_frame if model.tablet_animating else model.camera_idx
            self.screen.blit(self.cam_frames[idx], (0, 0))

        if model.server_state != "OFF":
            status = f"Power: {int(model.power)}% | Time: {model.hour} AM"
            self.screen.blit(self.font.render(status, True, (255, 255, 255)), (20, 20))

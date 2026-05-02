"""
FlowerFinder - Display Controller
-----------------------------------
This file handles ONLY game logic and screen transitions.
All visuals (images, fonts, colors) come from the /assets folder
which is owned by the ID/UX team.

Asset folder structure (ID team fills this in):
  assets/
    screens/
      insert_card.png       <- Screen 1 background
      searching.png         <- Screen 2 background
      wrong_scan.png        <- Screen 3a background
      success.png           <- Screen 3b background
      collection.png        <- Screen 4 background
    flowers/
      sunflower.png
      rose.png
      lavender.png
      daisy.png
      orchid.png
    ui/
      heart_full.png
      heart_empty.png
      star_full.png
      star_empty.png
      timer_ring.png
      score_badge.png
      plus_one_badge.png
    fonts/
      main.ttf              <- chosen by ID team
      bold.ttf
"""

import pygame
import sys
import time
import os
import math

# ── Screen config (hardware, not design) ────────────────────────────────────
SCREEN_W  = 480
SCREEN_H  = 320
FPS       = 60
ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

# ── Game constants (logic only) ──────────────────────────────────────────────
TIME_LIMIT      = 60    # seconds per round
POINTS_BASE     = 100   # points for finding flower
POINTS_PER_SEC  = 1     # bonus points per second remaining
POINTS_WRONG    = -10   # penalty per wrong scan
POINTS_HINT     = -20   # penalty for using hint
MAX_LIVES       = 3

# ── Flower data (name + hint only — visuals handled by assets) ───────────────
FLOWERS = [
    {"id": "sunflower", "name": "Sunflower", "hint": "Not a Rose",    "fact": "Always faces the sun!"},
    {"id": "rose",      "name": "Rose",      "hint": "Not Sunflower", "fact": "Symbol of love!"},
    {"id": "lavender",  "name": "Lavender",  "hint": "Not a Daisy",   "fact": "Makes you feel calm!"},
    {"id": "daisy",     "name": "Daisy",     "hint": "Not Lavender",  "fact": "Loves sunny fields!"},
    {"id": "orchid",    "name": "Orchid",    "hint": "Not a Tulip",   "fact": "Lives 100 years!"},
]


# ── Asset loader ─────────────────────────────────────────────────────────────
class Assets:
    """
    Loads all images and fonts from the assets folder.
    If an asset file is missing, falls back to a placeholder
    so the game still runs during development.
    """
    def __init__(self):
        self.images = {}
        self.fonts  = {}
        self._load_all()

    def _img(self, path, size=None):
        full = os.path.join(ASSET_DIR, path)
        if os.path.exists(full):
            img = pygame.image.load(full).convert_alpha()
            if size:
                img = pygame.transform.scale(img, size)
            return img
        # Fallback: magenta rectangle so missing assets are obvious
        s = pygame.Surface(size or (64, 64), pygame.SRCALPHA)
        s.fill((255, 0, 255, 120))
        font = pygame.font.SysFont("Arial", 10)
        t = font.render(os.path.basename(path), True, (255, 255, 255))
        s.blit(t, (2, 2))
        return s

    def _font(self, path, size):
        full = os.path.join(ASSET_DIR, path)
        if os.path.exists(full):
            return pygame.font.Font(full, size)
        return pygame.font.SysFont("Arial", size)

    def _load_all(self):
        sw, sh = SCREEN_W, SCREEN_H
        self.images["bg_insert"]     = self._img("screens/insert_card.png",  (sw, sh))
        self.images["bg_searching"]  = self._img("screens/searching.png",    (sw, sh))
        self.images["bg_wrong"]      = self._img("screens/wrong_scan.png",   (sw, sh))
        self.images["bg_success"]    = self._img("screens/success.png",      (sw, sh))
        self.images["bg_collection"] = self._img("screens/collection.png",   (sw, sh))
        for f in FLOWERS:
            self.images[f"flower_{f['id']}"] = self._img(f"flowers/{f['id']}.png", (80, 80))
        self.images["heart_full"]  = self._img("ui/heart_full.png",    (24, 24))
        self.images["heart_empty"] = self._img("ui/heart_empty.png",   (24, 24))
        self.images["star_full"]   = self._img("ui/star_full.png",     (20, 20))
        self.images["star_empty"]  = self._img("ui/star_empty.png",    (20, 20))
        self.images["timer_ring"]  = self._img("ui/timer_ring.png",    (60, 60))
        self.images["score_badge"] = self._img("ui/score_badge.png",   (80, 36))
        self.images["plus_one"]    = self._img("ui/plus_one_badge.png",(44, 28))
        self.fonts["large"]  = self._font("fonts/bold.ttf",  28)
        self.fonts["medium"] = self._font("fonts/main.ttf",  18)
        self.fonts["small"]  = self._font("fonts/main.ttf",  13)
        self.fonts["tiny"]   = self._font("fonts/main.ttf",  11)

    def img(self, key):
        return self.images.get(key)

    def font(self, key):
        return self.fonts.get(key, pygame.font.SysFont("Arial", 16))


# ── Text helper ───────────────────────────────────────────────────────────────
def blit_text(surf, assets, text, font_key, color, cx, cy, anchor="center"):
    font = assets.font(font_key)
    rendered = font.render(str(text), True, color)
    if anchor == "center":
        x = cx - rendered.get_width() // 2
        y = cy - rendered.get_height() // 2
    else:
        x, y = cx, cy - rendered.get_height() // 2
    surf.blit(rendered, (x, y))


# ── Game state ────────────────────────────────────────────────────────────────
class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.current_flower  = None
        self.lives           = MAX_LIVES
        self.score           = 0
        self.time_left       = TIME_LIMIT
        self.collected       = []
        self.last_wrong_scan = None
        self.time_bonus      = 0

    def start_round(self, flower):
        self.current_flower = flower
        self.lives          = MAX_LIVES
        self.time_left      = TIME_LIMIT

    def on_correct_scan(self):
        self.time_bonus = int(self.time_left * POINTS_PER_SEC)
        self.score     += POINTS_BASE + self.time_bonus
        if self.current_flower["id"] not in self.collected:
            self.collected.append(self.current_flower["id"])

    def on_wrong_scan(self, scanned_name):
        self.last_wrong_scan = scanned_name
        self.lives          -= 1
        self.score           = max(0, self.score + POINTS_WRONG)

    def stars_earned(self):
        if self.time_bonus > 40: return 3
        if self.time_bonus > 20: return 2
        return 1

    def is_game_over(self):
        return self.lives <= 0 or self.time_left <= 0


# ── Base screen ───────────────────────────────────────────────────────────────
class Screen:
    def __init__(self, app):
        self.app    = app
        self.assets = app.assets
        self.state  = app.state

    def update(self, dt): pass
    def draw(self, surf): pass
    def on_event(self, event): pass

    def go_to(self, screen):
        self.app.current = screen


# ── Screen 1: Insert Card ─────────────────────────────────────────────────────
class InsertCardScreen(Screen):
    def __init__(self, app):
        super().__init__(app)

    def draw(self, surf):
        surf.blit(self.assets.img("bg_insert"), (0, 0))
        leaderboard = "TOP: Mia 340  |  Leo 280  |  Sam 210"
        blit_text(surf, self.assets, leaderboard, "tiny", (110, 95, 140),
                  SCREEN_W // 2, 299)

    def on_rfid_card_read(self, flower):
        self.state.start_round(flower)
        self.go_to(SearchingScreen(self.app, flower))


# ── Screen 2: Searching ───────────────────────────────────────────────────────
class SearchingScreen(Screen):
    def __init__(self, app, flower):
        super().__init__(app)
        self.flower  = flower
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed         += dt
        self.state.time_left  = max(0, TIME_LIMIT - self.elapsed)
        if self.state.is_game_over():
            self.go_to(WrongScanScreen(self.app, reason="timeout"))

    def draw(self, surf):
        surf.blit(self.assets.img("bg_searching"), (0, 0))

        # Flower image (left panel — position set with ID team)
        flower_img = self.assets.img(f"flower_{self.flower['id']}")
        surf.blit(flower_img, (45, 100))

        # Text overlays — positions agreed with ID team in Figma
        blit_text(surf, self.assets, self.flower["name"],   "large", (200, 120, 220), 95, 70)
        blit_text(surf, self.assets, self.flower["hint"],   "small", (110, 95, 140),  95, 210)
        blit_text(surf, self.assets, self.flower["fact"],   "tiny",  (110, 95, 140),  95, 240)

        # Timer number over timer_ring asset
        tx, ty = 452, 38
        surf.blit(self.assets.img("timer_ring"), (tx - 30, ty - 30))
        t = int(self.state.time_left)
        col = (120,200,160) if t > 40 else ((240,190,80) if t > 15 else (230,100,90))
        blit_text(surf, self.assets, str(t), "small", col, tx, ty)

        # Hearts row
        for i in range(MAX_LIVES):
            key = "heart_full" if i < self.state.lives else "heart_empty"
            surf.blit(self.assets.img(key), (300 + i * 28, 290))

    def on_qr_scanned(self, scanned_name):
        if scanned_name.lower() == self.flower["name"].lower():
            self.state.on_correct_scan()
            self.go_to(SuccessScreen(self.app))
        else:
            self.state.on_wrong_scan(scanned_name)
            reason = "no_lives" if self.state.lives <= 0 else "wrong_flower"
            self.go_to(WrongScanScreen(self.app, reason=reason))


# ── Screen 3a: Wrong Scan ─────────────────────────────────────────────────────
class WrongScanScreen(Screen):
    def __init__(self, app, reason="wrong_flower"):
        super().__init__(app)
        self.reason  = reason
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += dt
        if self.elapsed >= 3.0:
            if self.reason == "wrong_flower":
                self.go_to(SearchingScreen(self.app, self.state.current_flower))
            else:
                self.state.reset()
                self.go_to(InsertCardScreen(self.app))

    def draw(self, surf):
        surf.blit(self.assets.img("bg_wrong"), (0, 0))
        if self.state.last_wrong_scan:
            blit_text(surf, self.assets, f'That was "{self.state.last_wrong_scan}"',
                      "medium", (240, 235, 250), SCREEN_W // 2, 200)
        for i in range(MAX_LIVES):
            key = "heart_full" if i < self.state.lives else "heart_empty"
            surf.blit(self.assets.img(key), (SCREEN_W//2 - 36 + i*28, 258))


# ── Screen 3b: Success ────────────────────────────────────────────────────────
class SuccessScreen(Screen):
    def __init__(self, app):
        super().__init__(app)

    def draw(self, surf):
        surf.blit(self.assets.img("bg_success"), (0, 0))
        surf.blit(self.assets.img("plus_one"), (SCREEN_W - 55, 12))
        flower = self.state.current_flower
        blit_text(surf, self.assets, f'"{flower["name"]}"', "large", (240,235,250), SCREEN_W//2, 168)
        blit_text(surf, self.assets, flower["fact"], "small", (110,95,140), SCREEN_W//2, 193)
        surf.blit(self.assets.img("score_badge"), (SCREEN_W//2 - 40, 215))
        blit_text(surf, self.assets, str(self.state.score), "large", (240,190,80), SCREEN_W//2, 250)
        blit_text(surf, self.assets, f"+{self.state.time_bonus} time bonus", "tiny", (110,95,140), SCREEN_W//2, 278)
        stars = self.state.stars_earned()
        for i in range(3):
            key = "star_full" if i < stars else "star_empty"
            surf.blit(self.assets.img(key), (SCREEN_W//2 - 32 + i*32, 292))

    def on_tap(self):
        self.go_to(CollectionScreen(self.app))


# ── Screen 4: Collection ──────────────────────────────────────────────────────
class CollectionScreen(Screen):
    def __init__(self, app):
        super().__init__(app)

    def draw(self, surf):
        surf.blit(self.assets.img("bg_collection"), (0, 0))
        surf.blit(self.assets.img("score_badge"), (SCREEN_W - 90, 52))
        blit_text(surf, self.assets, str(self.state.score), "small", (255,255,255), SCREEN_W-50, 71)
        found, total = len(self.state.collected), len(FLOWERS)
        blit_text(surf, self.assets, f"{found}/{total} found", "small", (160,145,190), 16, 60, anchor="left")

        cols = 5
        cell_w = (SCREEN_W - 20) // cols
        for i, flower in enumerate(FLOWERS):
            cx = 10 + (i % cols) * cell_w + cell_w // 2
            cy = 100 + (i // cols) * 90 + 30
            is_found = flower["id"] in self.state.collected
            img = self.assets.img(f"flower_{flower['id']}").copy()
            if not is_found:
                img.set_alpha(40)
            surf.blit(img, (cx - 40, cy - 40))
            label = flower["name"] if is_found else "???"
            color = (240,235,250) if is_found else (110,95,140)
            blit_text(surf, self.assets, label, "tiny", color, cx, cy + 44)

    def on_tap(self):
        self.go_to(InsertCardScreen(self.app))


# ── App controller ────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        pygame.init()
        self.screen_surf = pygame.display.set_mode((SCREEN_W*2, SCREEN_H*2), pygame.RESIZABLE)
        self.canvas  = pygame.Surface((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FlowerFinder")
        self.clock   = pygame.time.Clock()
        self.assets  = Assets()
        self.state   = GameState()
        self.current = InsertCardScreen(self)
        self._demo_events = [
            ("rfid",      FLOWERS[0]),
            ("qr_wrong",  "Rose"),
            ("qr_right",  FLOWERS[0]["name"]),
            ("tap",       None),
            ("tap",       None),
        ]
        self._demo_index = 0

    def run(self):
        prev = time.time()
        while True:
            now = time.time()
            dt  = min(now - prev, 0.05)
            prev = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_RIGHT):
                        self._fire_next_demo_event()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self._fire_next_demo_event()

            self.current.update(dt)
            self.current.draw(self.canvas)

            w, h  = self.screen_surf.get_size()
            scale = min(w / SCREEN_W, h / SCREEN_H)
            sw, sh = int(SCREEN_W * scale), int(SCREEN_H * scale)
            scaled = pygame.transform.scale(self.canvas, (sw, sh))
            self.screen_surf.fill((0, 0, 0))
            self.screen_surf.blit(scaled, ((w-sw)//2, (h-sh)//2))

            f = pygame.font.SysFont("Arial", 11)
            label = f.render(
                f"Screen: {type(self.current).__name__}  |  Space/Click = next event  |  ESC quit",
                True, (80,75,100))
            self.screen_surf.blit(label, (6, 3))

            pygame.display.flip()
            self.clock.tick(FPS)

    def _fire_next_demo_event(self):
        ev_type, ev_data = self._demo_events[self._demo_index % len(self._demo_events)]
        self._demo_index += 1
        screen = self.current
        if ev_type == "rfid"     and hasattr(screen, "on_rfid_card_read"): screen.on_rfid_card_read(ev_data)
        elif ev_type == "qr_wrong" and hasattr(screen, "on_qr_scanned"):   screen.on_qr_scanned(ev_data)
        elif ev_type == "qr_right" and hasattr(screen, "on_qr_scanned"):   screen.on_qr_scanned(ev_data)
        elif ev_type == "tap"     and hasattr(screen, "on_tap"):            screen.on_tap()


if __name__ == "__main__":
    App().run()

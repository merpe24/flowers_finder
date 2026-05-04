"""
FlowerFinder - Display Controller
All visuals come from assets/ folder (ID team).
Camera feed replaces radar on searching screen.
Lives removed — only time limit ends the game.
"""

import pygame
import sys
import time
import os
import math

# ── Hardware config ──────────────────────────────────────────────────────────
SCREEN_W  = 480
SCREEN_H  = 320
FPS       = 60
ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

# Try to import Pi camera — falls back to demo mode on non-Pi machines
try:
    from picamera2 import Picamera2
    import numpy as np
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

# ── Game constants ────────────────────────────────────────────────────────────
TIME_LIMIT     = 60    # seconds — only way to lose
POINTS_BASE    = 100
POINTS_PER_SEC = 1     # time bonus per second remaining
POINTS_WRONG   = -10   # penalty per wrong scan (no life lost)

# ── Flower data ───────────────────────────────────────────────────────────────
FLOWERS = [
    {"id": "sunflower", "name": "Sunflower", "hint": "Not a Rose",    "fact": "Always faces the sun!"},
    {"id": "rose",      "name": "Rose",      "hint": "Not Sunflower", "fact": "Symbol of love!"},
    {"id": "lavender",  "name": "Lavender",  "hint": "Not a Daisy",   "fact": "Makes you feel calm!"},
    {"id": "daisy",     "name": "Daisy",     "hint": "Not Lavender",  "fact": "Loves sunny fields!"},
    {"id": "orchid",    "name": "Orchid",    "hint": "Not a Tulip",   "fact": "Lives 100 years!"},
]


# ── Camera manager ────────────────────────────────────────────────────────────
class Camera:
    """
    Wraps Pi Camera 2.
    On non-Pi machines (dev/demo) returns a placeholder frame instead.
    """
    # Camera viewport on the searching screen — agreed with ID team
    VIEWPORT_X = 185
    VIEWPORT_Y = 10
    VIEWPORT_W = 285
    VIEWPORT_H = 265

    def __init__(self):
        self.cam   = None
        self.ready = False
        self._placeholder = None

        if CAMERA_AVAILABLE:
            try:
                self.cam = Picamera2()
                config = self.cam.create_preview_configuration(
                    {"size": (self.VIEWPORT_W, self.VIEWPORT_H)}
                )
                self.cam.configure(config)
                self.cam.start()
                self.ready = True
            except Exception as e:
                print(f"[Camera] Could not start: {e}")

    def get_frame(self):
        """Returns a pygame Surface of the current camera frame."""
        if self.ready and self.cam:
            try:
                frame = self.cam.capture_array()           # numpy array (H, W, 3)
                # picamera2 gives RGB — pygame wants RGB too, just needs transpose
                frame = np.rot90(frame, k=0)
                surface = pygame.surfarray.make_surface(
                    frame.transpose(1, 0, 2)
                )
                return pygame.transform.scale(
                    surface, (self.VIEWPORT_W, self.VIEWPORT_H)
                )
            except Exception:
                pass
        return self._get_placeholder()

    def _get_placeholder(self):
        """Shown on desktop / when camera unavailable."""
        if not self._placeholder:
            s = pygame.Surface((self.VIEWPORT_W, self.VIEWPORT_H))
            s.fill((20, 20, 35))
            font = pygame.font.SysFont("Arial", 14)
            lines = ["[ Camera feed ]", "Pi Camera not detected", "Running in demo mode"]
            for i, line in enumerate(lines):
                t = font.render(line, True, (80, 120, 100))
                s.blit(t, (self.VIEWPORT_W//2 - t.get_width()//2,
                           self.VIEWPORT_H//2 - 24 + i*22))
            # Draw a simple viewfinder corner marks
            c = (60, 160, 100)
            for x, y in [(8,8),(self.VIEWPORT_W-8,8),
                         (8,self.VIEWPORT_H-8),(self.VIEWPORT_W-8,self.VIEWPORT_H-8)]:
                pygame.draw.line(s, c, (x, y), (x+20*(1 if x<50 else -1), y), 2)
                pygame.draw.line(s, c, (x, y), (x, y+20*(1 if y<50 else -1)), 2)
            self._placeholder = s
        return self._placeholder

    def stop(self):
        if self.ready and self.cam:
            self.cam.stop()


# ── Asset loader ──────────────────────────────────────────────────────────────
class Assets:
    def __init__(self):
        self.images = {}
        self.fonts  = {}
        self._load_all()

    def _img(self, path, size=None):
        full = os.path.join(ASSET_DIR, path)
        if os.path.exists(full):
            img = pygame.image.load(full).convert_alpha()
            return pygame.transform.scale(img, size) if size else img
        s = pygame.Surface(size or (64, 64), pygame.SRCALPHA)
        s.fill((255, 0, 255, 100))
        t = pygame.font.SysFont("Arial", 10).render(os.path.basename(path), True, (255,255,255))
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
        self.images["star_full"]   = self._img("ui/star_full.png",  (20, 20))
        self.images["star_empty"]  = self._img("ui/star_empty.png", (20, 20))
        self.images["score_badge"] = self._img("ui/score_badge.png",(80, 36))
        self.images["plus_one"]    = self._img("ui/plus_one_badge.png", (44, 28))
        self.fonts["large"]  = self._font("fonts/bold.ttf",  28)
        self.fonts["medium"] = self._font("fonts/main.ttf",  18)
        self.fonts["small"]  = self._font("fonts/main.ttf",  13)
        self.fonts["tiny"]   = self._font("fonts/main.ttf",  11)

    def img(self, key):  return self.images.get(key)
    def font(self, key): return self.fonts.get(key, pygame.font.SysFont("Arial", 16))


# ── Text helper ───────────────────────────────────────────────────────────────
def blit_text(surf, assets, text, font_key, color, cx, cy, anchor="center"):
    font     = assets.font(font_key)
    rendered = font.render(str(text), True, color)
    x = cx - rendered.get_width()//2 if anchor == "center" else cx
    y = cy - rendered.get_height()//2
    surf.blit(rendered, (x, y))


# ── Game state ────────────────────────────────────────────────────────────────
class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.current_flower  = None
        self.score           = 0
        self.time_left       = TIME_LIMIT
        self.collected       = []
        self.last_wrong_scan = None
        self.time_bonus      = 0
        self.wrong_count     = 0   # wrong scans this round (info only, no penalty to lives)

    def start_round(self, flower):
        self.current_flower = flower
        self.time_left      = TIME_LIMIT
        self.wrong_count    = 0

    def on_correct_scan(self):
        self.time_bonus = int(self.time_left * POINTS_PER_SEC)
        self.score     += POINTS_BASE + self.time_bonus
        if self.current_flower["id"] not in self.collected:
            self.collected.append(self.current_flower["id"])

    def on_wrong_scan(self, scanned_name):
        """Wrong scan: score penalty only. No life lost. Keep playing."""
        self.last_wrong_scan = scanned_name
        self.wrong_count    += 1
        self.score           = max(0, self.score + POINTS_WRONG)

    def stars_earned(self):
        if self.time_bonus > 40: return 3
        if self.time_bonus > 20: return 2
        return 1


# ── Base screen ───────────────────────────────────────────────────────────────
class Screen:
    def __init__(self, app):
        self.app    = app
        self.assets = app.assets
        self.state  = app.state

    def update(self, dt): pass
    def draw(self, surf): pass
    def go_to(self, screen): self.app.current = screen


# ── Screen 1: Insert Card ─────────────────────────────────────────────────────
class InsertCardScreen(Screen):
    def draw(self, surf):
        surf.blit(self.assets.img("bg_insert"), (0, 0))
        blit_text(surf, self.assets, "TOP: Mia 340  |  Leo 280  |  Sam 210",
                  "tiny", (110, 95, 140), SCREEN_W//2, 299)

    def on_rfid_card_read(self, flower):
        self.state.start_round(flower)
        self.go_to(SearchingScreen(self.app, flower))


# ── Screen 2: Searching — LIVE CAMERA FEED ───────────────────────────────────
class SearchingScreen(Screen):
    """
    Left panel: flower info (from ID assets).
    Right panel: LIVE camera feed from Pi Camera 2.
                 On desktop shows a placeholder with corner marks.
    Timer counts down — when it hits 0 the round ends (game over).
    Wrong scans just show a brief flash message, no lives deducted.
    """
    def __init__(self, app, flower):
        super().__init__(app)
        self.flower       = flower
        self.elapsed      = 0.0
        self.wrong_flash  = 0.0   # countdown timer for "wrong flower" flash message
        self.wrong_name   = ""    # name of last wrong scan to display

    def update(self, dt):
        self.elapsed         += dt
        self.state.time_left  = max(0, TIME_LIMIT - self.elapsed)
        if self.wrong_flash > 0:
            self.wrong_flash -= dt

        # Time ran out → game over
        if self.state.time_left <= 0:
            self.go_to(TimeUpScreen(self.app))

    def draw(self, surf):
        # ID team background
        surf.blit(self.assets.img("bg_searching"), (0, 0))

        # ── Left panel: flower info ──
        surf.blit(self.assets.img(f"flower_{self.flower['id']}"), (45, 100))
        blit_text(surf, self.assets, self.flower["name"], "large", (200,120,220), 95, 70)
        blit_text(surf, self.assets, self.flower["hint"], "small", (110,95,140),  95, 210)
        blit_text(surf, self.assets, self.flower["fact"], "tiny",  (110,95,140),  95, 240)

        # ── Right panel: LIVE CAMERA FEED ──
        camera_frame = self.app.camera.get_frame()
        surf.blit(camera_frame, (Camera.VIEWPORT_X, Camera.VIEWPORT_Y))

        # Thin border around camera area (ID team can style this in bg asset instead)
        pygame.draw.rect(surf, (60, 160, 100),
                         (Camera.VIEWPORT_X, Camera.VIEWPORT_Y,
                          Camera.VIEWPORT_W, Camera.VIEWPORT_H), 1)

        # ── Timer (top right) ──
        tx, ty = 452, 38
        t = int(self.state.time_left)
        col = (120,200,160) if t > 40 else ((240,190,80) if t > 15 else (230,100,90))
        blit_text(surf, self.assets, str(t), "medium", col, tx, ty)

        # ── Wrong scan flash (brief red message, then keep scanning) ──
        if self.wrong_flash > 0:
            alpha = min(255, int(self.wrong_flash * 400))
            flash_surf = pygame.Surface((Camera.VIEWPORT_W, 36), pygame.SRCALPHA)
            flash_surf.fill((200, 60, 60, min(180, alpha)))
            surf.blit(flash_surf, (Camera.VIEWPORT_X, Camera.VIEWPORT_Y + Camera.VIEWPORT_H - 36))
            msg = f"Not {self.wrong_name}!  Keep looking..."
            blit_text(surf, self.assets, msg, "small", (255,220,220),
                      Camera.VIEWPORT_X + Camera.VIEWPORT_W//2,
                      Camera.VIEWPORT_Y + Camera.VIEWPORT_H - 18)

        # ── "Scan the QR code" label ──
        blit_text(surf, self.assets, "Point camera at QR code near the flower",
                  "tiny", (110,95,140), Camera.VIEWPORT_X + Camera.VIEWPORT_W//2, 285)

    def on_qr_scanned(self, scanned_name):
        """Called by main.py when OpenCV detects a QR code."""
        if scanned_name.lower() == self.flower["name"].lower():
            self.state.on_correct_scan()
            self.go_to(SuccessScreen(self.app))
        else:
            # Wrong flower — brief flash, keep scanning, no life lost
            self.state.on_wrong_scan(scanned_name)
            self.wrong_flash = 1.5     # show message for 1.5 seconds
            self.wrong_name  = scanned_name


# ── Screen: Time Up (game over — ran out of time) ─────────────────────────────
class TimeUpScreen(Screen):
    """Shown when timer hits 0. Auto-returns to insert card after 4 seconds."""
    def __init__(self, app):
        super().__init__(app)
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += dt
        if self.elapsed >= 4.0:
            self.state.reset()
            self.go_to(InsertCardScreen(self.app))

    def draw(self, surf):
        surf.blit(self.assets.img("bg_wrong"), (0, 0))   # reuse wrong bg or give ID team a separate one
        blit_text(surf, self.assets, "Time's up!", "large", (230,100,90), SCREEN_W//2, 120)
        flower_name = self.state.current_flower["name"] if self.state.current_flower else ""
        blit_text(surf, self.assets, f"The flower was: {flower_name}", "medium",
                  (240,235,250), SCREEN_W//2, 165)
        blit_text(surf, self.assets, f"Score: {self.state.score}", "medium",
                  (240,190,80), SCREEN_W//2, 205)
        blit_text(surf, self.assets, "Try again!", "small", (110,95,140), SCREEN_W//2, 245)


# ── Screen 3b: Success ────────────────────────────────────────────────────────
class SuccessScreen(Screen):
    def draw(self, surf):
        surf.blit(self.assets.img("bg_success"), (0, 0))
        surf.blit(self.assets.img("plus_one"), (SCREEN_W-55, 12))
        flower = self.state.current_flower
        blit_text(surf, self.assets, f'"{flower["name"]}"',    "large", (240,235,250), SCREEN_W//2, 168)
        blit_text(surf, self.assets, flower["fact"],           "small", (110,95,140),  SCREEN_W//2, 193)
        surf.blit(self.assets.img("score_badge"), (SCREEN_W//2-40, 215))
        blit_text(surf, self.assets, str(self.state.score),    "large", (240,190,80),  SCREEN_W//2, 250)
        blit_text(surf, self.assets, f"+{self.state.time_bonus} time bonus",
                  "tiny", (110,95,140), SCREEN_W//2, 278)
        stars = self.state.stars_earned()
        for i in range(3):
            surf.blit(self.assets.img("star_full" if i < stars else "star_empty"),
                      (SCREEN_W//2 - 32 + i*32, 292))

    def on_tap(self):
        self.go_to(CollectionScreen(self.app))


# ── Screen 4: Collection ──────────────────────────────────────────────────────
class CollectionScreen(Screen):
    def draw(self, surf):
        surf.blit(self.assets.img("bg_collection"), (0, 0))
        surf.blit(self.assets.img("score_badge"), (SCREEN_W-90, 52))
        blit_text(surf, self.assets, str(self.state.score), "small", (255,255,255), SCREEN_W-50, 71)
        found, total = len(self.state.collected), len(FLOWERS)
        blit_text(surf, self.assets, f"{found}/{total} found", "small", (160,145,190), 16, 60, anchor="left")

        cols, cell_w = 5, (SCREEN_W-20)//5
        for i, flower in enumerate(FLOWERS):
            cx = 10 + (i % cols)*cell_w + cell_w//2
            cy = 100 + (i // cols)*90 + 30
            is_found = flower["id"] in self.state.collected
            img = self.assets.img(f"flower_{flower['id']}").copy()
            if not is_found:
                img.set_alpha(40)
            surf.blit(img, (cx-40, cy-40))
            blit_text(surf, self.assets,
                      flower["name"] if is_found else "???",
                      "tiny",
                      (240,235,250) if is_found else (110,95,140),
                      cx, cy+44)

    def on_tap(self):
        self.go_to(InsertCardScreen(self.app))


# ── App ───────────────────────────────────────────────────────────────────────
class App:
    def __init__(self):
        pygame.init()
        self.screen_surf = pygame.display.set_mode((SCREEN_W*2, SCREEN_H*2), pygame.RESIZABLE)
        self.canvas  = pygame.Surface((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FlowerFinder")
        self.clock   = pygame.time.Clock()
        self.assets  = Assets()
        self.state   = GameState()
        self.camera  = Camera()          # starts Pi Camera if available
        self.current = InsertCardScreen(self)
        self._demo_events = [
            ("rfid",      FLOWERS[0]),
            ("qr_wrong",  "Rose"),        # wrong scan — flash and keep going
            ("qr_wrong",  "Lavender"),    # another wrong scan
            ("qr_right",  FLOWERS[0]["name"]),  # correct!
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
                    self.camera.stop()
                    pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.camera.stop()
                        pygame.quit(); sys.exit()
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_RIGHT):
                        self._fire_next_demo_event()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self._fire_next_demo_event()

            self.current.update(dt)
            self.current.draw(self.canvas)

            w, h  = self.screen_surf.get_size()
            scale = min(w/SCREEN_W, h/SCREEN_H)
            sw, sh = int(SCREEN_W*scale), int(SCREEN_H*scale)
            scaled = pygame.transform.scale(self.canvas, (sw, sh))
            self.screen_surf.fill((0,0,0))
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
        s = self.current
        if   ev_type == "rfid"      and hasattr(s, "on_rfid_card_read"): s.on_rfid_card_read(ev_data)
        elif ev_type == "qr_wrong"  and hasattr(s, "on_qr_scanned"):     s.on_qr_scanned(ev_data)
        elif ev_type == "qr_right"  and hasattr(s, "on_qr_scanned"):     s.on_qr_scanned(ev_data)
        elif ev_type == "tap"       and hasattr(s, "on_tap"):             s.on_tap()


if __name__ == "__main__":
    App().run()

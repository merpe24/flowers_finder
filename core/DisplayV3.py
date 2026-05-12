"""
FlowerFinder — DisplayV3.py
============================
Hardware based on BLEmbedded.py + read.py + qr_scanner.py
UI: cream/pastel illustrated skin using PNG assets from /assets/

TIMING: Global 30-min countdown. Press START → 30 min begins.
        Collect as many flowers as possible in 30 min.
        No per-flower time limit — just hunt until the clock runs out.

Desktop test keys: R=RFID  Q=correct QR  W=wrong QR  ENTER/click=tap  ESC=quit
"""

import os
import pygame
import threading
import math
import time
import sys
import random
import queue

# ── Try Pi-only imports ───────────────────────────────────────────────────────
try:
    from picamera2 import Picamera2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522, MFRC522 as _MFRC522
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# ── Pin config (from BLEmbedded.py) ──────────────────────────────────────────
GREEN_LED = 17
RED_LED   = 27
BUZZER    = 22

# ── Display config ────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 480, 320
FPS   = 60
CAM_W = 350    # camera native capture width
CAM_H = 320    # camera native capture height

# ── Game constants ────────────────────────────────────────────────────────────
GAME_DURATION = 30 * 60   # 30 minutes in seconds
QR_DEBOUNCE   = 1.5

# ── Colors (cream / pastel palette) ──────────────────────────────────────────
C_CREAM     = (249, 245, 226)
C_TEXT_DARK = ( 80,  60,  40)
C_WHITE     = (255, 255, 255)
C_DIM       = (150, 130, 100)
C_TEAL      = (100, 195, 185)
C_GOLD      = (200, 136,  10)
C_RED_LOGO  = (192,  56,  32)
C_TIMER_G   = ( 60, 180,  60)
C_TIMER_Y   = (220, 170,  40)
C_TIMER_R   = (200,  50,  50)

# ── Flower data ───────────────────────────────────────────────────────────────
# id       — must match text written on RFID card (lowercase, stripped)
# name     — display name (lowercase stripped, same as id)
# hint_img — path relative to /assets/
FLOWERS = [
    {"id": "balloon flower",        "name": "balloon flower",        "hint_img": "Balloon Flower.png"},
    {"id": "blue water lily",       "name": "blue water lily",       "hint_img": "Blue Water Lily.png"},
    {"id": "bougainvillea",         "name": "bougainvillea",         "hint_img": "Bougainvillea.png"},
    {"id": "cape jasmine",          "name": "cape jasmine",          "hint_img": "Cape Jasmine.png"},
    {"id": "celosia",               "name": "celosia",               "hint_img": "Celosia.png"},
    {"id": "cosmos",                "name": "cosmos",                "hint_img": "Cosmos.png"},
    {"id": "golden shower",         "name": "golden shower",    "hint_img": "Golden Shower Tree.png"},
    {"id": "hibiscus",              "name": "hibiscus",              "hint_img": "Hibiscus.png"},
    {"id": "hollyhock",             "name": "hollyhock",             "hint_img": "Hollyhock.png"},
    {"id": "madagascar periwinkle", "name": "madagascar periwinkle", "hint_img": "Madagascar Periwinkle.png"},
    {"id": "orange jasmine",        "name": "orange jasmine",        "hint_img": "Orange Jasmine.png"},
    {"id": "plumeria",              "name": "plumeria",              "hint_img": "Plumeria.png"},
    {"id": "queen's flower",        "name": "queen's flower",        "hint_img": "Queen's Flower.png"},
    {"id": "rain lily",             "name": "rain lily",             "hint_img": "Rain Lily.png"},
    {"id": "red rose",              "name": "red rose",              "hint_img": "Red Rose.png"},
    {"id": "sacred lotus",          "name": "sacred lotus",          "hint_img": "Sacred Lotus.png"},
    {"id": "siam tulip",            "name": "siam tulip",            "hint_img": "Siam Tulip.png"},
    {"id": "sunflower",             "name": "sunflower",             "hint_img": "Sunflower.png"},
    {"id": "wrigtia sirikitiae",    "name": "wrigtia sirikitiae",    "hint_img": "Wrigtia Sirikitiae.png"},
    {"id": "zinnia",                "name": "zinnia",                "hint_img": "Zinnia.png"},
]
FLOWER_MAP = {f["id"]: f for f in FLOWERS}


# ══════════════════════════════════════════════════════════════════════════════
# SOUND & LED  (from BLEmbedded.py — exact same functions)
# ══════════════════════════════════════════════════════════════════════════════

def buzz(duration=0.2):
    if not HARDWARE_AVAILABLE: return
    GPIO.output(BUZZER, GPIO.HIGH)
    time.sleep(duration)
    GPIO.output(BUZZER, GPIO.LOW)

def success_sound():
    threading.Thread(target=_success_sound, daemon=True).start()

def error_sound():
    threading.Thread(target=_error_sound, daemon=True).start()

def timeout_sound():
    threading.Thread(target=_timeout_sound, daemon=True).start()

def _success_sound():
    buzz(0.2); time.sleep(0.1); buzz(0.2)

def _error_sound():
    buzz(0.5)

def _timeout_sound():
    for _ in range(3):
        buzz(0.2); time.sleep(0.1)

def led_flash(pin, duration=1.5):
    if not HARDWARE_AVAILABLE: return
    def _f():
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(pin, GPIO.LOW)
    threading.Thread(target=_f, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# CAMERA  (from qr_scanner.py + BLEmbedded.py)
# ══════════════════════════════════════════════════════════════════════════════

class Camera:
    def __init__(self):
        self.cam      = None
        self.ready    = False
        self._frame   = None
        self._lock    = threading.Lock()
        self._running = False

        if CAMERA_AVAILABLE:
            try:
                self.cam = Picamera2()
                cfg = self.cam.create_preview_configuration({"size": (CAM_W, CAM_H)})
                self.cam.configure(cfg)
                self.cam.start()
                self.ready = True
                print("[Camera] Started OK")
            except Exception as e:
                print(f"[Camera] Failed: {e}")

    def start(self):
        if not self.ready: return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self._running:
            try:
                frame = self.cam.capture_array()
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = frame[:, :, :3]
                surf = pygame.surfarray.make_surface(frame.transpose(1, 0, 2))
                surf = pygame.transform.scale(surf, (CAM_W, CAM_H))
                with self._lock:
                    self._frame = surf
            except Exception:
                pass
            time.sleep(0.033)

    def get_frame(self):
        with self._lock:
            return self._frame

    def capture_for_qr(self):
        if not (self.ready and CV2_AVAILABLE): return None
        try:
            img = self.cam.capture_array()
            if img is None: return None
            if img.ndim == 3 and img.shape[2] == 4:
                img = img[:, :, :3]
            return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        except Exception:
            return None

    def stop(self):
        self._running = False
        if self.ready:
            try: self.cam.stop()
            except: pass


# ══════════════════════════════════════════════════════════════════════════════
# RFID  (from read.py — exact same pattern)
# ══════════════════════════════════════════════════════════════════════════════

class RFID:
    def __init__(self):
        self.reader = None
        if HARDWARE_AVAILABLE:
            try:
                reader = SimpleMFRC522.__new__(SimpleMFRC522)
                reader.READER = _MFRC522(pin_mode=GPIO.BCM)
                self.reader = reader
                print("[RFID] Ready")
            except Exception as e:
                print(f"[RFID] Failed: {e}")

    def read_card(self):
        if not self.reader: return None
        try:
            id, text = self.reader.read()
            if not text or not text.strip():
                print("[RFID] Read error, try again")
                error_sound()
                return None
            fid    = text.replace('\x00', '').strip().lower()
            flower = FLOWER_MAP.get(fid)
            if not flower:
                print(f"[RFID] Unknown flower id: '{fid}'")
                error_sound()
            return flower
        except Exception as e:
            print(f"[RFID] Error: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════════
# QR SCANNER  (from BLEmbedded.py scan loop)
# ══════════════════════════════════════════════════════════════════════════════

class QRScanner:
    def __init__(self, camera, q):
        self.camera   = camera
        self.q        = q
        self._running = False
        self._last_t  = 0
        self.detector = cv2.QRCodeDetector() if CV2_AVAILABLE else None

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            gray = self.camera.capture_for_qr()
            if gray is None:
                time.sleep(0.05)
                continue
            try:
                data, bbox, _ = self.detector.detectAndDecode(gray)
                if bbox is not None and data:
                    now = time.time()
                    if now - self._last_t > QR_DEBOUNCE:
                        self._last_t = now
                        self.q.put(data.strip().lower())
            except Exception:
                pass
            time.sleep(0.05)


# ══════════════════════════════════════════════════════════════════════════════
# GAME STATE
# ══════════════════════════════════════════════════════════════════════════════

class GameState:
    def __init__(self): self.full_reset()

    def full_reset(self):
        self.flower          = None
        self.collected       = []
        self.newly_collected = False
        self.game_active     = False
        self.game_start_time = None

    def start_game(self):
        """Begin the 30-minute global countdown."""
        self.game_active     = True
        self.game_start_time = time.time()

    def stop_game(self):
        """Cancel the current game (back to pre-start menu)."""
        self.game_active     = False
        self.game_start_time = None

    @property
    def time_remaining(self):
        """Seconds left in the 30-min game. Returns GAME_DURATION if not active."""
        if not self.game_active or self.game_start_time is None:
            return float(GAME_DURATION)
        elapsed = time.time() - self.game_start_time
        return max(0.0, GAME_DURATION - elapsed)

    @staticmethod
    def fmt_time(secs):
        """Format seconds as MM:SS string."""
        s = int(secs)
        return f"{s // 60:02d}:{s % 60:02d}"

    def round_reset(self, flower):
        self.flower          = flower
        self.newly_collected = False

    def on_correct(self, flower):
        fid = flower["id"]
        self.newly_collected = fid not in self.collected
        if self.newly_collected:
            self.collected.append(fid)
        self.flower = flower


# ══════════════════════════════════════════════════════════════════════════════
# ASSETS
# ══════════════════════════════════════════════════════════════════════════════

def load_assets(assets_dir):
    specs = {
        "background_1":         (SCREEN_W, SCREEN_H),
        "background_2":         (SCREEN_W, SCREEN_H),
        "start":                (83,  30),
        "reset":                (88,  28),
        "collections":          (125, 28),
        "missioncomplete":      (220, 90),
        "wrong":                (394, 141),
        "Group 8615":           (451, 149),
        "timer":                (121, 121),
        "plus_score":           (44,  44),
        "back_button":          (37,  37),
        "collections_countere": (104, 38),
    }
    assets = {}
    for stem, size in specs.items():
        path = os.path.join(assets_dir, stem + ".png")
        if os.path.exists(path):
            img = pygame.image.load(path).convert_alpha()
            assets[stem] = pygame.transform.scale(img, size)
        else:
            s = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(s, (180, 160, 140, 120), (0, 0, size[0], size[1]),
                             border_radius=6)
            assets[stem] = s
    # Smaller timer badge reused from timer.png
    assets["timer_sm"] = pygame.transform.scale(assets["timer"], (88, 88))
    return assets


# ══════════════════════════════════════════════════════════════════════════════
# DRAWING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fnt(size, bold=False):
    return pygame.font.SysFont("Arial", size, bold=bold)

def rnd(surf, color, r, radius=10, alpha=255):
    s = pygame.Surface((r[2], r[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0, 0, r[2], r[3]), border_radius=radius)
    surf.blit(s, (r[0], r[1]))

def txt(surf, text, font, color, cx, cy):
    r = font.render(str(text), True, color)
    surf.blit(r, (cx - r.get_width() // 2, cy - r.get_height() // 2))

def draw_global_timer_badge(surf, assets, tr, x=359, y=0, w=121, h=121):
    """Draw the round timer badge with MM:SS global time remaining."""
    surf.blit(assets["timer"], (x, y))
    time_str = GameState.fmt_time(tr)
    col = C_TIMER_G if tr > 600 else (C_TIMER_Y if tr > 120 else C_TIMER_R)
    cx, cy = x + w // 2, y + h // 2
    txt(surf, "LEFT",     fnt(9,  True), col, cx, cy - 18)
    txt(surf, time_str,   fnt(26, True), col, cx, cy + 8)

def draw_global_timer_badge_sm(surf, assets, tr, x=392, y=0, w=88, h=88):
    """Small 88×88 variant of the global timer badge (for HintScreen)."""
    surf.blit(assets["timer_sm"], (x, y))
    time_str = GameState.fmt_time(tr)
    col = C_TIMER_G if tr > 600 else (C_TIMER_Y if tr > 120 else C_TIMER_R)
    cx, cy = x + w // 2, y + h // 2
    txt(surf, "LEFT",   fnt(8,  True), col, cx, cy - 13)
    txt(surf, time_str, fnt(20, True), col, cx, cy + 8)

def draw_timer_pill(surf, tr, x=6, y=6):
    """Compact MM:SS pill (used on SuccessScreen top-left)."""
    time_str = GameState.fmt_time(tr)
    rnd(surf, (80, 60, 40), (x, y, 88, 26), radius=12, alpha=210)
    txt(surf, time_str, fnt(14, True), (245, 224, 112),
        x + 44, y + 13)


# ══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ══════════════════════════════════════════════════════════════════════════════

class Screen:
    def __init__(self, app):
        self.app = app
    def update(self, dt): pass
    def draw(self, surf): pass
    def go(self, s): self.app.current = s


# ── 1. Waiting / Start page ───────────────────────────────────────────────────
class WaitingScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        # Pre-game button hitboxes
        self.btn_start       = pygame.Rect(199, 156, 83,  30)
        self.btn_reset       = pygame.Rect(196, 196, 88,  28)
        self.btn_collections = pygame.Rect(178, 233, 125, 28)
        # Active-game hitboxes
        self.btn_collections_active = pygame.Rect(178, 218, 125, 28)
        self.btn_cancel             = pygame.Rect(196, 258, 88,  46)  # cancel/back

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        surf.blit(self.app.assets["background_1"], (0, 0))

        if self.app.state.game_active:
            # ── Active game layout ────────────────────────────────────────
            # Slightly smaller logo to make room
            txt(surf, "FLOWER", fnt(40, True), C_GOLD,     240, 46)
            txt(surf, "FINDER", fnt(36, True), C_RED_LOGO, 240, 84)

            # Big global timer pill
            tr = self.app.state.time_remaining
            time_str = GameState.fmt_time(tr)
            rnd(surf, (80, 60, 40), (140, 106, 200, 66), radius=20, alpha=210)
            txt(surf, "TIME LEFT", fnt(9, True),  (200, 184, 144), 240, 122)
            txt(surf, time_str,    fnt(36, True), (245, 224, 112), 240, 148)

            # Instruction
            txt(surf, "Tap RFID card to hunt a flower!",
                fnt(13, True), C_TEXT_DARK, 240, 190)

            # COLLECTIONS button
            surf.blit(self.app.assets["collections"], (178, 218))

            # Cancel back-button (stop game → return to pre-start)
            surf.blit(self.app.assets["back_button"], (222, 265))

        else:
            # ── Pre-game layout ───────────────────────────────────────────
            txt(surf, "FLOWER", fnt(52, True), C_GOLD,     240, 62)
            txt(surf, "FINDER", fnt(46, True), C_RED_LOGO, 240, 110)

            surf.blit(self.app.assets["start"],       (199, 156))
            surf.blit(self.app.assets["reset"],       (196, 196))
            surf.blit(self.app.assets["collections"], (178, 233))

    def on_tap(self, pos=None):
        if self.app.state.game_active:
            if pos is None or self.btn_cancel.collidepoint(pos):
                # Cancel — stop timer, return to pre-start menu
                self.app.state.stop_game()
                return
            if pos and self.btn_collections_active.collidepoint(pos):
                self.go(CollectionScreen(self.app))
            return

        # Pre-game
        if pos is None:
            self.app.state.start_game()
            return
        if self.btn_start.collidepoint(pos):
            self.app.state.start_game()
        elif self.btn_reset.collidepoint(pos):
            self.app.state.full_reset()
        elif self.btn_collections.collidepoint(pos):
            self.go(CollectionScreen(self.app))


# ── 2. Hint ───────────────────────────────────────────────────────────────────
class HintScreen(Screen):
    GROW_TIME = 0.5
    HOLD_TIME = 3.5

    def __init__(self, app, fl):
        super().__init__(app)
        self.fl = fl
        self.t  = 0.0

    def update(self, dt):
        self.t += dt
        if self.t >= self.HOLD_TIME:
            self._next()

    def _next(self):
        self.go(SearchingScreen(self.app, self.fl))

    def on_tap(self, pos=None):
        self._next()

    def draw(self, surf):
        surf.blit(self.app.assets["background_2"], (0, 0))

        # Image grows in from center
        scale = min(1.0, self.t / self.GROW_TIME)
        max_w, max_h = 200, 200
        w = max(1, int(max_w * scale))
        h = max(1, int(max_h * scale))
        cx, cy = 240, 140

        img = self.app.hint_imgs.get(self.fl["id"])
        if img:
            scaled = pygame.transform.scale(img, (w, h))
            surf.blit(scaled, (cx - w // 2, cy - h // 2))
        else:
            rnd(surf, (184, 168, 136), (cx - w // 2, cy - h // 2, w, h),
                radius=12, alpha=160)

        if scale > 0.4:
            name_alpha = min(255, int((scale - 0.4) / 0.6 * 255))
            name_r = fnt(24, True).render(self.fl["name"], True, C_TEXT_DARK)
            name_r.set_alpha(name_alpha)
            surf.blit(name_r, (240 - name_r.get_width() // 2, 248))

        skip_r = fnt(10).render("tap to skip  →", True, C_DIM)
        surf.blit(skip_r, (SCREEN_W - skip_r.get_width() - 8,
                            SCREEN_H - skip_r.get_height() - 6))

        # Global timer badge — small, top-right
        draw_global_timer_badge_sm(surf, self.app.assets,
                                   self.app.state.time_remaining)


# ── 3. Searching ──────────────────────────────────────────────────────────────
class SearchingScreen(Screen):
    def __init__(self, app, fl):
        super().__init__(app)
        self.fl          = fl
        self.wrong_flash = 0.0
        self.wrong_name  = ""

    def update(self, dt):
        if self.wrong_flash > 0:
            self.wrong_flash -= dt
        # No per-flower timeout — global timer handled in App.run()

    def draw(self, surf):
        # Full-screen camera feed (scale 350×320 → 480×320)
        frame = self.app.camera.get_frame()
        if frame:
            scaled = pygame.transform.scale(frame, (SCREEN_W, SCREEN_H))
            surf.blit(scaled, (0, 0))
        else:
            surf.fill((20, 30, 20))
            txt(surf, "[ camera feed ]",        fnt(12), (40, 100, 60),
                SCREEN_W // 2, SCREEN_H // 2 - 12)
            txt(surf, "Q = correct  W = wrong", fnt(10), (28, 68, 40),
                SCREEN_W // 2, SCREEN_H // 2 + 10)

        # Wrong flash overlay
        if self.wrong_flash > 0:
            surf.blit(self.app.assets["wrong"], (43, 78))

        # Global timer badge top-right (359,0) 121×121
        draw_global_timer_badge(surf, self.app.assets,
                                self.app.state.time_remaining)

    def on_wrong(self, name):
        error_sound()
        led_flash(RED_LED, 1.0)
        self.wrong_flash = 2.0
        self.wrong_name  = name

    def on_correct(self):
        success_sound()
        led_flash(GREEN_LED, 2.0)
        self.app.state.on_correct(self.fl)
        self.go(SuccessScreen(self.app))


# ── 4. Mission Complete ───────────────────────────────────────────────────────
class SuccessScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.confetti = [
            {"x":   random.randint(0, SCREEN_W),
             "y":   random.randint(-SCREEN_H, 0),
             "vy":  random.uniform(60, 140),
             "col": random.choice([C_TEAL, C_GOLD, (230, 80, 80),
                                   (167, 139, 250), (255, 200, 100)]),
             "w":   random.randint(4, 10)}
            for _ in range(35)
        ]

    def update(self, dt):
        self.t += dt
        for c in self.confetti:
            c["y"] += c["vy"] * dt
            if c["y"] > SCREEN_H + 10:
                c["y"] = -10

    def draw(self, surf):
        surf.blit(self.app.assets["background_2"], (0, 0))

        for c in self.confetti:
            pygame.draw.rect(surf, c["col"],
                             (int(c["x"]), int(c["y"]), c["w"], c["w"] // 2))

        # Small global timer pill — top-left
        draw_timer_pill(surf, self.app.state.time_remaining)

        # +1 badge top-right, shown only when newly collected
        if self.app.state.newly_collected:
            surf.blit(self.app.assets["plus_score"], (418, 8))

        # MISSION COMPLETE logo — left side
        surf.blit(self.app.assets["missioncomplete"], (20, 100))

        # Hint image — right side
        fl = self.app.state.flower
        if fl:
            hint = self.app.hint_imgs.get(fl["id"])
            if hint:
                hint_scaled = pygame.transform.scale(hint, (140, 140))
                surf.blit(hint_scaled, (318, 85))
            txt(surf, fl["name"], fnt(13, True), C_TEXT_DARK, 388, 238)

        found = len(self.app.state.collected)
        txt(surf, f"Collected: {found} / {len(FLOWERS)}",
            fnt(12, True), C_TEXT_DARK, SCREEN_W // 2, 270)
        txt(surf, "tap to see collection", fnt(10), C_DIM, SCREEN_W // 2, 300)

    def on_tap(self, pos=None):
        self.go(CollectionScreen(self.app))


# ── 5. Final Results (global 30-min timer expired) ───────────────────────────
class FinalResultsScreen(Screen):
    AUTO_RETURN = 5.0

    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.confetti = [
            {"x":   random.randint(0, SCREEN_W),
             "y":   random.randint(-SCREEN_H, 0),
             "vy":  random.uniform(50, 120),
             "col": random.choice([C_TEAL, C_GOLD, (230, 80, 80),
                                   (167, 139, 250), (255, 200, 100)]),
             "w":   random.randint(4, 10)}
            for _ in range(30)
        ]

    def update(self, dt):
        self.t += dt
        for c in self.confetti:
            c["y"] += c["vy"] * dt
            if c["y"] > SCREEN_H + 10:
                c["y"] = -10
        if self.t >= self.AUTO_RETURN:
            self.app.state.full_reset()
            self.go(WaitingScreen(self.app))

    def draw(self, surf):
        surf.blit(self.app.assets["background_2"], (0, 0))

        for c in self.confetti:
            pygame.draw.rect(surf, c["col"],
                             (int(c["x"]), int(c["y"]), c["w"], c["w"] // 2))

        # TIME'S UP banner (using gameover asset at top)
        surf.blit(self.app.assets["Group 8615"], (15, 22))

        # Score card
        found = len(self.app.state.collected)
        rnd(surf, C_WHITE, (80, 158, 320, 84), radius=18, alpha=200)
        txt(surf, "YOU COLLECTED", fnt(11, True), C_DIM,  240, 178)
        # Big number left, /20 smaller right
        num_r = fnt(38, True).render(str(found), True, C_GOLD)
        den_r = fnt(18, True).render(f"/ {len(FLOWERS)}", True, C_DIM)
        total_w = num_r.get_width() + 8 + den_r.get_width()
        nx = SCREEN_W // 2 - total_w // 2
        surf.blit(num_r, (nx, 195))
        surf.blit(den_r, (nx + num_r.get_width() + 8,
                           195 + num_r.get_height() - den_r.get_height() - 2))

        # Returning countdown pill
        remaining = max(0, int(self.AUTO_RETURN - self.t))
        rnd(surf, (80, 60, 40), (140, 256, 200, 28), radius=14, alpha=165)
        txt(surf, f"returning in {remaining}s...",
            fnt(11), (212, 200, 160), 240, 270)


# ── 6. Flower Collection ──────────────────────────────────────────────────────
_COLL_COLS   = 5
_COLL_ROWS   = 4
_COLL_HEAD_H = 58

class CollectionScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.btn_back = pygame.Rect(0, 0, 65, 58)

    def draw(self, surf):
        surf.blit(self.app.assets["background_2"], (0, 0))

        # Header: back button | FLOWER COLLECTION | counter
        surf.blit(self.app.assets["back_button"], (12, 10))
        txt(surf, "FLOWER COLLECTION", fnt(13, True), C_TEXT_DARK,
            SCREEN_W // 2, 29)
        surf.blit(self.app.assets["collections_countere"], (357, 10))
        found = len(self.app.state.collected)
        count_r = fnt(13, True).render(f"{found}/{len(FLOWERS)}", True, C_WHITE)
        surf.blit(count_r, (357 + 104 - count_r.get_width() - 10,
                            10 + (38 - count_r.get_height()) // 2))

        # 5×4 flower grid
        margin   = 5
        cell_w   = (SCREEN_W - margin * 2) // _COLL_COLS
        cell_h   = (SCREEN_H - _COLL_HEAD_H - margin) // _COLL_ROWS
        img_size = min(cell_w - 10, cell_h - 18, 40)

        for i, fl in enumerate(FLOWERS):
            col_i = i % _COLL_COLS
            row_i = i // _COLL_COLS
            x  = margin + col_i * cell_w
            y  = _COLL_HEAD_H + row_i * cell_h
            cx = x + cell_w // 2
            ok = fl["id"] in self.app.state.collected

            rnd(surf, C_WHITE, (x + 1, y + 1, cell_w - 2, cell_h - 2),
                radius=8, alpha=180 if ok else 55)

            if ok:
                hint = self.app.hint_imgs.get(fl["id"])
                if hint:
                    s = pygame.transform.scale(hint, (img_size, img_size))
                    surf.blit(s, (cx - img_size // 2, y + 2))
                else:
                    pygame.draw.circle(surf, C_TEAL,
                                       (cx, y + 2 + img_size // 2), img_size // 2)
                name_r = fnt(7, True).render(fl["name"], True, C_TEXT_DARK)
                surf.blit(name_r, (cx - name_r.get_width() // 2,
                                   y + cell_h - name_r.get_height() - 2))
            else:
                txt(surf, "?", fnt(18, True), (180, 160, 130), cx,
                    y + cell_h // 2 - 4)

    def on_tap(self, pos=None):
        if pos is None or self.btn_back.collidepoint(pos):
            self.go(WaitingScreen(self.app))


# ══════════════════════════════════════════════════════════════════════════════
# APP — main loop
# ══════════════════════════════════════════════════════════════════════════════

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FlowerFinder")
        self.clock  = pygame.time.Clock()
        self.state  = GameState()

        self.rfid = RFID()

        if HARDWARE_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
            except ValueError:
                pass
            GPIO.setup(GREEN_LED, GPIO.OUT)
            GPIO.setup(RED_LED,   GPIO.OUT)
            GPIO.setup(BUZZER,    GPIO.OUT)
            GPIO.output(GREEN_LED, GPIO.LOW)
            GPIO.output(RED_LED,   GPIO.LOW)
            GPIO.output(BUZZER,    GPIO.LOW)

        self.camera  = Camera()
        self.qr_q    = queue.Queue()
        self.qr_scan = QRScanner(self.camera, self.qr_q)

        assets_dir     = "/home/pie/flowers_finder/assets/Flowers"
        self.assets    = load_assets(assets_dir)
        self.hint_imgs = {}
        for fl in FLOWERS:
            fn = fl.get("hint_img")
            if fn:
                path = os.path.join(assets_dir, fn)
                if os.path.exists(path):
                    img = pygame.image.load(path).convert_alpha()
                    self.hint_imgs[fl["id"]] = pygame.transform.scale(img, (200, 200))
                else:
                    print(f"[Assets] hint_img not found: {path}")
                    self.hint_imgs[fl["id"]] = None
            else:
                self.hint_imgs[fl["id"]] = None

        self.current = WaitingScreen(self)

        self._rfid_q       = queue.Queue()
        self._rfid_running = False

    def _rfid_loop(self):
        while self._rfid_running:
            fl = self.rfid.read_card()
            if fl:
                self._rfid_q.put(fl)

    def run(self):
        self.camera.start()
        self.qr_scan.start()
        self._rfid_running = True
        threading.Thread(target=self._rfid_loop, daemon=True).start()

        prev = time.time()
        while True:
            now  = time.time()
            dt   = min(now - prev, 0.05)
            prev = now

            # ── Global timer expiry ────────────────────────────────────────
            # Trigger FinalResultsScreen from any screen when 30 min runs out
            if (self.state.game_active and
                    self.state.time_remaining <= 0 and
                    not isinstance(self.current, FinalResultsScreen)):
                timeout_sound()
                led_flash(RED_LED, 2.0)
                self.current = FinalResultsScreen(self)

            # ── Pygame events ──────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._quit()
                    # Desktop test shortcuts
                    if event.key == pygame.K_r:
                        # Simulate RFID tap — only works when game is active
                        if self.state.game_active:
                            self._rfid_q.put(random.choice(FLOWERS))
                    if event.key == pygame.K_q:
                        if isinstance(self.current, SearchingScreen):
                            self.current.on_correct()
                    if event.key == pygame.K_w:
                        if isinstance(self.current, SearchingScreen):
                            self.current.on_wrong("rose")
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if hasattr(self.current, "on_tap"):
                            self.current.on_tap()
                # Touchscreen / mouse
                tap_pos = None
                if event.type == pygame.MOUSEBUTTONDOWN:
                    tap_pos = event.pos
                elif event.type == pygame.FINGERDOWN:
                    tap_pos = (int(event.x * SCREEN_W), int(event.y * SCREEN_H))
                if tap_pos is not None:
                    if hasattr(self.current, "on_tap"):
                        self.current.on_tap(tap_pos)

            # ── RFID queue — only accepted on WaitingScreen during active game
            if isinstance(self.current, WaitingScreen) and self.state.game_active:
                try:
                    fl = self._rfid_q.get_nowait()
                    self.state.round_reset(fl)
                    # Drain stale QR reads before hunting
                    while not self.qr_q.empty():
                        try: self.qr_q.get_nowait()
                        except queue.Empty: break
                    self.current = HintScreen(self, fl)
                    print(f"[RFID] Flower: {fl['name'].upper()}")
                except queue.Empty:
                    pass
            else:
                # Drain stale RFID reads on all other screens
                while not self._rfid_q.empty():
                    try: self._rfid_q.get_nowait()
                    except queue.Empty: break

            # ── QR queue — only while searching ───────────────────────────
            if isinstance(self.current, SearchingScreen):
                try:
                    qr_data = self.qr_q.get_nowait()
                    if qr_data == self.current.fl["id"]:
                        print(f"[QR] Correct! {qr_data}")
                        self.current.on_correct()
                    else:
                        wrong = FLOWER_MAP.get(qr_data, {"name": qr_data})
                        print(f"[QR] Wrong: {qr_data}")
                        self.current.on_wrong(wrong["name"])
                except queue.Empty:
                    pass

            # ── Update & draw ──────────────────────────────────────────────
            self.current.update(dt)
            self.current.draw(self.screen)

            # Dev label (desktop only)
            if not HARDWARE_AVAILABLE:
                tr  = self.state.time_remaining
                hw  = f"R=RFID  Q=correct  W=wrong  ENTER=tap  ESC=quit  | time={GameState.fmt_time(tr)}"
                lbl = pygame.font.SysFont("Arial", 9).render(
                    f"{type(self.current).__name__}  |  {hw}", True, (120, 100, 80))
                self.screen.blit(lbl, (4, 2))

            pygame.display.flip()
            self.clock.tick(FPS)

    def _quit(self):
        self._rfid_running = False
        self.qr_scan.stop()
        self.camera.stop()
        if HARDWARE_AVAILABLE: GPIO.cleanup()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    App().run()

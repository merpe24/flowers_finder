"""
FlowerFinder — DisplayV3.py
============================
Hardware based on BLEmbedded.py + read.py + qr_scanner.py
UI: cream/pastel illustrated skin using PNG assets from /assets/
Logic: no score, collect flowers only — +1 badge when newly found

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
CAM_W = 350    # camera native capture width (Camera class uses this)
CAM_H = 320    # camera native capture height

# ── Game constants ────────────────────────────────────────────────────────────
TIME_LIMIT  = 60
QR_DEBOUNCE = 1.5

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
# hint_img — filename inside /assets/ (e.g. "sunflower.jpg"), or None
#            Same image is shown on HintScreen and CollectionScreen.
FLOWERS = [
    {"id": "sunflower",      "name": "Sunflower",      "hint_img": None},
    {"id": "rose",           "name": "Rose",            "hint_img": None},
    {"id": "lavender",       "name": "Lavender",        "hint_img": None},
    {"id": "daisy",          "name": "Daisy",           "hint_img": None},
    {"id": "orchid",         "name": "Orchid",          "hint_img": None},
    {"id": "tulip",          "name": "Tulip",           "hint_img": None},
    {"id": "lily",           "name": "Lily",            "hint_img": None},
    {"id": "jasmine",        "name": "Jasmine",         "hint_img": None},
    {"id": "chrysanthemum",  "name": "Chrysanthemum",   "hint_img": None},
    {"id": "peony",          "name": "Peony",           "hint_img": None},
    {"id": "marigold",       "name": "Marigold",        "hint_img": None},
    {"id": "iris",           "name": "Iris",            "hint_img": None},
    {"id": "poppy",          "name": "Poppy",           "hint_img": None},
    {"id": "dahlia",         "name": "Dahlia",          "hint_img": None},
    {"id": "carnation",      "name": "Carnation",       "hint_img": None},
    {"id": "hibiscus",       "name": "Hibiscus",        "hint_img": None},
    {"id": "pansy",          "name": "Pansy",           "hint_img": None},
    {"id": "bluebell",       "name": "Bluebell",        "hint_img": None},
    {"id": "magnolia",       "name": "Magnolia",        "hint_img": None},
    {"id": "zinnia",         "name": "Zinnia",          "hint_img": None},
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
    buzz(0.2); time.sleep(0.1); buzz(0.2)   # happy double beep

def _error_sound():
    buzz(0.5)                                 # longer sad buzz

def _timeout_sound():
    for _ in range(3):                        # fast triple beep
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
    """
    Pi Camera 2 wrapper.
    Captures frames in background thread for display.
    QR scanning uses gray conversion from BLEmbedded.py.
    """
    def __init__(self):
        self.cam      = None
        self.ready    = False
        self._frame   = None
        self._lock    = threading.Lock()
        self._running = False

        if CAMERA_AVAILABLE:
            try:
                self.cam = Picamera2()
                # Use same config as BLEmbedded.py
                cfg = self.cam.create_preview_configuration(
                    {"size": (CAM_W, CAM_H)}
                )
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
                # Handle 4-channel XRGB from picamera2
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = frame[:, :, :3]
                surf = pygame.surfarray.make_surface(frame.transpose(1, 0, 2))
                surf = pygame.transform.scale(surf, (CAM_W, CAM_H))
                with self._lock:
                    self._frame = surf
            except Exception:
                pass
            time.sleep(0.033)   # ~30fps display

    def get_frame(self):
        with self._lock:
            return self._frame

    def capture_for_qr(self):
        """
        Returns raw numpy array for QR scanning.
        Uses same gray conversion as BLEmbedded.py.
        """
        if not (self.ready and CV2_AVAILABLE): return None
        try:
            img = self.cam.capture_array()
            if img is None: return None
            if img.ndim == 3 and img.shape[2] == 4:
                img = img[:, :, :3]
            gray_img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            return gray_img
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
    """
    Wraps SimpleMFRC522 using the same pattern as read.py.
    Blocking read runs in its own thread.
    """
    def __init__(self):
        self.reader = None
        if HARDWARE_AVAILABLE:
            try:
                # Bypass SimpleMFRC522.__init__ which unconditionally calls
                # GPIO.setmode(GPIO.BOARD), conflicting with our BCM setup.
                reader = SimpleMFRC522.__new__(SimpleMFRC522)
                reader.READER = _MFRC522(pin_mode=GPIO.BCM)
                self.reader = reader
                print("[RFID] Ready")
            except Exception as e:
                print(f"[RFID] Failed: {e}")

    def read_card(self):
        """Blocking read — same as read.py. Returns flower dict or None."""
        if not self.reader: return None
        try:
            id, text = self.reader.read()    # exactly like read.py
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
    """
    Scans QR codes in background thread.
    Uses gray image from camera — same as BLEmbedded.py.
    """
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
                # Same decode call as BLEmbedded.py
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
        self.collected       = []    # list of flower ids found so far
        self.newly_collected = False # True when current flower was just added

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
    """Pre-load and scale all PNG assets. Returns dict keyed by filename stem."""
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
            # Placeholder rectangle so draw calls never crash
            s = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(s, (180, 160, 140, 120), (0, 0, size[0], size[1]),
                             border_radius=6)
            assets[stem] = s
    return assets


# ══════════════════════════════════════════════════════════════════════════════
# DRAWING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fnt(size, bold=False):
    return pygame.font.SysFont("Arial", size, bold=bold)

def rnd(surf, color, r, radius=10, alpha=255):
    """Draw a rounded rectangle with optional alpha onto surf."""
    s = pygame.Surface((r[2], r[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0, 0, r[2], r[3]), border_radius=radius)
    surf.blit(s, (r[0], r[1]))

def txt(surf, text, font, color, cx, cy):
    """Blit text centered at (cx, cy)."""
    r = font.render(str(text), True, color)
    surf.blit(r, (cx - r.get_width() // 2, cy - r.get_height() // 2))


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
        self.started = False   # False = show buttons; True = show "tap card" prompt
        self.t = 0.0
        self.btn_start       = pygame.Rect(199, 156, 83,  30)
        self.btn_reset       = pygame.Rect(196, 196, 88,  28)
        self.btn_collections = pygame.Rect(178, 233, 125, 28)
        # Cancel button shown when started=True — generous hitbox centered where collections was
        self.btn_cancel      = pygame.Rect(200, 218, 80, 58)

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        surf.blit(self.app.assets["background_1"], (0, 0))

        # Logo: "FLOWER" gold, "FINDER" red — centered in area (92,26) size 296×107
        txt(surf, "FLOWER", fnt(52, True), C_GOLD,     240, 62)
        txt(surf, "FINDER", fnt(46, True), C_RED_LOGO, 240, 110)

        if not self.started:
            surf.blit(self.app.assets["start"],       (199, 156))
            surf.blit(self.app.assets["reset"],       (196, 196))
            surf.blit(self.app.assets["collections"], (178, 233))
        else:
            pulse = abs(math.sin(self.t * 2.5))
            col = (int(80 + 40 * pulse), int(60 + 20 * pulse), 40)
            txt(surf, "Tap your RFID card", fnt(18, True), col,   240, 185)
            txt(surf, "to start the game",  fnt(13),       C_DIM, 240, 207)
            # Back button centered where COLLECTIONS button was
            surf.blit(self.app.assets["back_button"], (222, 229))

    def on_tap(self, pos=None):
        if self.started:
            return
        if pos is None:
            self.started = True
            return
        if self.btn_start.collidepoint(pos):
            self.started = True
        elif self.btn_reset.collidepoint(pos):
            self.app.state.full_reset()
        elif self.btn_collections.collidepoint(pos):
            self.go(CollectionScreen(self.app))


# ── 2. Hint ───────────────────────────────────────────────────────────────────
class HintScreen(Screen):
    GROW_TIME = 0.5   # seconds for image to fully scale in
    HOLD_TIME = 3.5   # auto-advance after this many seconds

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

        # Image grows in from center over GROW_TIME seconds
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

        # Flower name fades in after image is mostly visible
        if scale > 0.4:
            name_alpha = min(255, int((scale - 0.4) / 0.6 * 255))
            name_r = fnt(24, True).render(self.fl["name"], True, C_TEXT_DARK)
            name_r.set_alpha(name_alpha)
            surf.blit(name_r, (240 - name_r.get_width() // 2, 248))

        # "tap to skip →" bottom-right corner
        skip_r = fnt(10).render("tap to skip  →", True, C_DIM)
        surf.blit(skip_r, (SCREEN_W - skip_r.get_width() - 8,
                            SCREEN_H - skip_r.get_height() - 6))


# ── 3. Searching ──────────────────────────────────────────────────────────────
class SearchingScreen(Screen):
    def __init__(self, app, fl):
        super().__init__(app)
        self.fl          = fl
        self.start_time  = time.time()
        self.time_left   = float(TIME_LIMIT)
        self.wrong_flash = 0.0
        self.wrong_name  = ""

    def update(self, dt):
        self.time_left = max(0, TIME_LIMIT - (time.time() - self.start_time))
        if self.wrong_flash > 0:
            self.wrong_flash -= dt
        if self.time_left <= 0:
            timeout_sound()
            led_flash(RED_LED, 1.5)
            self.go(TimeUpScreen(self.app))

    def draw(self, surf):
        # Full-screen camera feed (scale from 350×320 → 480×320)
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

        # Wrong flash overlay: blit wrong.png at (43,78), fades after 2s
        if self.wrong_flash > 0:
            surf.blit(self.app.assets["wrong"], (43, 78))

        # Timer badge top-right, number inside at ~(420, 60)
        surf.blit(self.app.assets["timer"], (359, 0))
        t = int(self.time_left)
        col = C_TIMER_G if t > 40 else (C_TIMER_Y if t > 15 else C_TIMER_R)
        txt(surf, str(t), fnt(32, True), col, 420, 60)

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


# ── 4. Time's Up ──────────────────────────────────────────────────────────────
class TimeUpScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        if self.t >= 4.0:
            self.go(WaitingScreen(self.app))

    def draw(self, surf):
        # Last camera frame as background, fall back to bg1
        frame = self.app.camera.get_frame()
        if frame:
            scaled = pygame.transform.scale(frame, (SCREEN_W, SCREEN_H))
            surf.blit(scaled, (0, 0))
        else:
            surf.blit(self.app.assets["background_1"], (0, 0))

        # Slight dark overlay so text reads well over camera
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 80))
        surf.blit(dim, (0, 0))

        # GAME OVER banner at (15, 76) size 451×149
        surf.blit(self.app.assets["Group 8615"], (15, 76))

        name = self.app.state.flower["name"] if self.app.state.flower else "?"
        txt(surf, f"The flower was: {name}",
            fnt(13), (240, 220, 200), SCREEN_W // 2, 246)
        txt(surf, f"returning in {max(0, int(4 - self.t))}s...",
            fnt(11), (200, 180, 160), SCREEN_W // 2, 300)


# ── 5. Mission Complete ───────────────────────────────────────────────────────
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

        # Collection count
        found = len(self.app.state.collected)
        txt(surf, f"Collected: {found} / {len(FLOWERS)}",
            fnt(12, True), C_TEXT_DARK, SCREEN_W // 2, 270)

        txt(surf, "tap to see collection", fnt(10), C_DIM, SCREEN_W // 2, 300)

    def on_tap(self, pos=None):
        self.go(CollectionScreen(self.app))


# ── 6. Flower Collection ──────────────────────────────────────────────────────
_COLL_COLS   = 5
_COLL_ROWS   = 4
_COLL_HEAD_H = 58

class CollectionScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.btn_back = pygame.Rect(12, 10, 37, 37)

    def draw(self, surf):
        surf.blit(self.app.assets["background_2"], (0, 0))

        # Header: back button | FLOWER COLLECTION | counter — no separator line
        surf.blit(self.app.assets["back_button"], (12, 10))
        txt(surf, "FLOWER COLLECTION", fnt(13, True), C_TEXT_DARK,
            SCREEN_W // 2, 29)
        surf.blit(self.app.assets["collections_countere"], (357, 10))
        found = len(self.app.state.collected)
        txt(surf, f"{found}/{len(FLOWERS)}", fnt(13, True), C_WHITE, 409, 29)

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

        # Init RFID first — SimpleMFRC522 calls GPIO.setmode(BCM) internally
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

        # Load PNG assets and hint images
        assets_dir     = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      '..', 'assets')
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

        # RFID thread (blocking read, like read.py)
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

            # ── Pygame events ──────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._quit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._quit()
                    # Desktop test shortcuts
                    if event.key == pygame.K_r:
                        self._rfid_q.put(random.choice(FLOWERS))
                    if event.key == pygame.K_q:
                        if isinstance(self.current, SearchingScreen):
                            self.current.on_correct()
                    if event.key == pygame.K_w:
                        if isinstance(self.current, SearchingScreen):
                            self.current.on_wrong("Rose")
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if hasattr(self.current, "on_tap"):
                            self.current.on_tap()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if hasattr(self.current, "on_tap"):
                        self.current.on_tap(event.pos)

            # ── RFID queue (only while on WaitingScreen) ───────────────────
            if isinstance(self.current, WaitingScreen):
                try:
                    fl = self._rfid_q.get_nowait()
                    self.state.round_reset(fl)
                    while not self.qr_q.empty():
                        try: self.qr_q.get_nowait()
                        except queue.Empty: break
                    self.current = HintScreen(self, fl)
                    print(f"[RFID] Flower: {fl['name'].upper()}")
                except queue.Empty:
                    pass
            else:
                # Drain stale RFID reads while on other screens
                while not self._rfid_q.empty():
                    try: self._rfid_q.get_nowait()
                    except queue.Empty: break

            # ── QR queue (only while searching) ───────────────────────────
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
                hw  = "R=RFID  Q=correct  W=wrong  ENTER=tap  ESC=quit"
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

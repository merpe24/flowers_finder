"""
FlowerFinder — DisplayV3.py
============================
Hardware based on BLEmbedded.py + read.py + qr_scanner.py
UI: dark purple theme, camera fullscreen right, flower info left panel
Logic: no lives, time-only game over, reset button on collection

Desktop test keys: R=RFID  Q=correct QR  W=wrong QR  ENTER=tap  ESC=quit
"""

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
    from mfrc522 import SimpleMFRC522
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# ── Pin config (from BLEmbedded.py) ──────────────────────────────────────────
GREEN_LED = 17
RED_LED   = 27
BUZZER    = 22

# ── Display config ────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 480, 320
FPS      = 60
PANEL_W  = 130          # left info panel width
CAM_X    = PANEL_W
CAM_W    = SCREEN_W - PANEL_W
CAM_H    = SCREEN_H

# ── Game constants ────────────────────────────────────────────────────────────
TIME_LIMIT     = 60
POINTS_BASE    = 100
POINTS_PER_SEC = 1
QR_DEBOUNCE    = 1.5    # seconds between QR reads

# ── Colors ────────────────────────────────────────────────────────────────────
C_BG      = (8,   5,  16)
C_PANEL   = (17,  13,  40)
C_SURFACE = (26,  16,  64)
C_PURPLE  = (196, 181, 253)
C_PURPLE2 = (124,  58, 237)
C_GREEN   = ( 52, 211, 153)
C_RED     = (239,  68,  68)
C_RED2    = (127,  29,  29)
C_GOLD    = (240, 190,  80)
C_PINK    = (230, 130, 180)
C_WHITE   = (226, 232, 240)
C_DIM     = ( 76,  56, 128)
C_DIM2    = ( 42,  31,  80)
C_MID     = (156, 106, 170)

# ── Flower data ───────────────────────────────────────────────────────────────
# id must match text written on RFID card (lowercase, stripped)
FLOWERS = [
    {"id":"sunflower","name":"Sunflower","hint":"Not a Rose",   "fact":"Always faces the sun!", "color":(240,190,60), "center":(180,80,20), "petals":8},
    {"id":"rose",     "name":"Rose",     "hint":"Not Sunflower","fact":"Symbol of love!",       "color":(230,130,180),"center":(157,23,77),"petals":12},
    {"id":"lavender", "name":"Lavender", "hint":"Not a Daisy",  "fact":"Makes you feel calm!",  "color":(167,139,250),"center":(91,33,182),"petals":6},
    {"id":"daisy",    "name":"Daisy",    "hint":"Not Lavender", "fact":"Loves sunny fields!",   "color":(226,232,240),"center":(180,160,50),"petals":10},
    {"id":"orchid",   "name":"Orchid",   "hint":"Not a Tulip",  "fact":"Lives 100 years!",      "color":(216,180,254),"center":(126,34,206),"petals":5},
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
                self.reader = SimpleMFRC522()
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
        self.flower     = None
        self.score      = 0
        self.collected  = []    # list of flower ids
        self.time_bonus = 0

    def round_reset(self, flower):
        self.flower = flower

    def on_correct(self, flower, time_left):
        self.flower     = flower
        self.time_bonus = int(time_left * POINTS_PER_SEC)
        self.score     += POINTS_BASE + self.time_bonus
        if flower["id"] not in self.collected:
            self.collected.append(flower["id"])

    def stars(self):
        if self.time_bonus > 40: return 3
        if self.time_bonus > 20: return 2
        return 1


# ══════════════════════════════════════════════════════════════════════════════
# DRAWING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def fnt(size, bold=False):
    return pygame.font.SysFont("Arial", size, bold=bold)

def rnd(surf, color, r, radius=10, alpha=255):
    s = pygame.Surface((r[2], r[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0,0,r[2],r[3]), border_radius=radius)
    surf.blit(s, (r[0], r[1]))

def txt(surf, text, font, color, cx, cy, anchor="center"):
    r = font.render(str(text), True, color)
    x = cx - r.get_width()//2 if anchor == "center" else cx
    surf.blit(r, (x, cy - r.get_height()//2))

def flower(surf, cx, cy, color, center, petals=8, size=1.0, alpha=255):
    pr = int(14*size); pd = int(18*size)
    for i in range(petals):
        a  = math.radians(360/petals*i)
        px = cx + int(math.cos(a)*pd)
        py = cy + int(math.sin(a)*pd)
        s  = pygame.Surface((pr*2+2, pr*2+2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, alpha), (pr+1,pr+1), pr)
        surf.blit(s, (px-pr-1, py-pr-1))
    pygame.draw.circle(surf, center, (cx,cy), int(8*size))

def star(surf, cx, cy, sz, filled, color):
    pts = []
    for i in range(10):
        a = math.radians(-90+i*36)
        r = sz if i%2==0 else sz*0.45
        pts.append((cx+math.cos(a)*r, cy+math.sin(a)*r))
    if filled: pygame.draw.polygon(surf, color, pts)
    else:       pygame.draw.polygon(surf, color, pts, 1)

def sparkles(surf, sp):
    for x,y,a,p in sp:
        br  = int(55+40*math.sin(a+p*6))
        col = (br, int(br*0.4), int(br*1.3))
        pygame.draw.circle(surf, col, (int(x),int(y)),
                           max(1, int(1.1+math.sin(a*2+p)*0.9)))

def left_panel(surf, fl, score, time_left):
    """Draw the left info panel — used on searching + wrong screens."""
    rnd(surf, C_PANEL, (0,0,PANEL_W,SCREEN_H), radius=0, alpha=235)
    pygame.draw.line(surf, C_DIM2, (PANEL_W-1,0),(PANEL_W-1,SCREEN_H), 1)

    txt(surf,"FIND THIS",    fnt(9),    C_DIM,    PANEL_W//2, 16)
    flower(surf, PANEL_W//2, 70, fl["color"], fl["center"],
           petals=fl["petals"], size=1.5)
    txt(surf, fl["name"],    fnt(13,True),C_PURPLE, PANEL_W//2,116)

    rnd(surf, C_DIM2, (6,128,PANEL_W-12,20), radius=10, alpha=200)
    txt(surf, fl["hint"],    fnt(9),    C_MID,    PANEL_W//2,138)
    txt(surf, fl["fact"],    fnt(9),    C_DIM,    PANEL_W//2,162)

    pygame.draw.line(surf, C_DIM2, (10,178),(PANEL_W-10,178), 1)
    txt(surf,"score",        fnt(8),    C_DIM,    PANEL_W//2,192)
    txt(surf, str(score),    fnt(18,True),C_GOLD,  PANEL_W//2,212)
    txt(surf,"pts",          fnt(8),    C_DIM,    PANEL_W//2,228)

    pygame.draw.line(surf, C_DIM2, (10,240),(PANEL_W-10,240), 1)
    t   = int(time_left)
    col = C_GREEN if t > 40 else ((240,190,80) if t > 15 else C_RED)
    txt(surf,"time left",    fnt(8),    C_DIM,    PANEL_W//2,254)
    txt(surf, str(t),        fnt(32,True), col,   PANEL_W//2,284)
    txt(surf,"sec",          fnt(8),    col,      PANEL_W//2,308)

def camera_panel(surf, app, wrong_flash=0.0, wrong_name=""):
    """Draw camera feed (or placeholder) on right side."""
    frame = app.camera.get_frame()
    if frame:
        surf.blit(frame, (CAM_X, 0))
    else:
        rnd(surf, (12,18,12), (CAM_X,0,CAM_W,CAM_H), radius=0)
        for gx in range(CAM_X, SCREEN_W, 44):
            pygame.draw.line(surf,(18,38,18),(gx,0),(gx,CAM_H),1)
        for gy in range(0, CAM_H, 44):
            pygame.draw.line(surf,(18,38,18),(CAM_X,gy),(SCREEN_W,gy),1)
        txt(surf,"[ camera feed ]",     fnt(12),(40,100,60),
            CAM_X+CAM_W//2, CAM_H//2-12)
        txt(surf,"Q = correct  W = wrong", fnt(10),(28,68,40),
            CAM_X+CAM_W//2, CAM_H//2+10)

    # Viewfinder corners
    co, sz = (60,180,100), 14
    for fx,fy in [(CAM_X+4,4),(SCREEN_W-4,4),(CAM_X+4,SCREEN_H-4),(SCREEN_W-4,SCREEN_H-4)]:
        dx = 1 if fx < SCREEN_W//2 else -1
        dy = 1 if fy < SCREEN_H//2 else -1
        pygame.draw.line(surf,co,(fx,fy),(fx+sz*dx,fy),2)
        pygame.draw.line(surf,co,(fx,fy),(fx,fy+sz*dy),2)

    # Wrong flash overlay
    if wrong_flash > 0:
        a  = min(230, int(wrong_flash*260))
        fl = pygame.Surface((CAM_W,50), pygame.SRCALPHA)
        fl.fill((180,18,18,a))
        surf.blit(fl,(CAM_X,SCREEN_H-50))
        txt(surf,f"Not {wrong_name}!  Keep looking...",
            fnt(13,True),(255,180,180), CAM_X+CAM_W//2, SCREEN_H-25)

    txt(surf,"point camera at QR code", fnt(10),(38,95,55),
        CAM_X+CAM_W//2, SCREEN_H-6)


# ══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ══════════════════════════════════════════════════════════════════════════════

class Screen:
    def __init__(self, app):
        self.app = app
    def update(self, dt): pass
    def draw(self, surf): pass
    def go(self, s): self.app.current = s


# ── 1. Waiting for RFID ───────────────────────────────────────────────────────
class WaitingScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t  = 0.0
        self.sp = [(random.randint(10,SCREEN_W-10),
                    random.randint(10,SCREEN_H-10),
                    random.random()*6.28, random.random())
                   for _ in range(14)]

    def update(self, dt):
        self.t += dt
        self.sp = [(x,y,a+dt*0.7,p) for x,y,a,p in self.sp]

    def draw(self, surf):
        surf.fill(C_BG)
        sparkles(surf, self.sp)

        # Glow
        glow = pygame.Surface((180,180),pygame.SRCALPHA)
        pygame.draw.circle(glow,(*C_PURPLE2,16),(90,90),90)
        surf.blit(glow,(150,28))

        txt(surf,"F L O W E R  F I N D E R",fnt(10),C_DIM,SCREEN_W//2,26)
        txt(surf,"FlowerFinder",fnt(30,True),C_PURPLE,SCREEN_W//2,58)

        # Bobbing card
        bob = int(math.sin(self.t*1.5)*5)
        cx, cy = SCREEN_W//2, 146+bob
        rnd(surf,C_PANEL,(cx-80,cy-52,160,104),radius=14,alpha=235)
        pygame.draw.rect(surf,C_PURPLE2,(cx-80,cy-52,160,104),width=1,border_radius=14)
        pygame.draw.rect(surf,C_GOLD,(cx-62,cy-28,26,18),border_radius=3)
        for i,w in enumerate([70,52,60]):
            pygame.draw.line(surf,C_DIM2,(cx-62,cy+8+i*11),(cx-62+w,cy+8+i*11),2)
        flower(surf,cx+48,cy-8,C_PINK,(157,23,77),petals=6,size=0.55)

        # Pulsing arrows
        for i in range(3):
            a = max(0, int(120+90*math.sin(self.t*2-i*0.6)) - i*50)
            s = pygame.Surface((12,8),pygame.SRCALPHA)
            pygame.draw.polygon(s,(*C_PURPLE,a),[(0,0),(12,0),(6,8)])
            surf.blit(s,(SCREEN_W//2-6,212+i*12))

        txt(surf,"แตะการ์ด RFID เพื่อเริ่มเกม",fnt(14),C_MID, SCREEN_W//2,252)
        txt(surf,"tap your RFID card to begin",  fnt(11),C_DIM, SCREEN_W//2,270)

        # Bottom bar
        rnd(surf,C_PANEL,(0,298,SCREEN_W,22),radius=0,alpha=200)
        found = len(self.app.state.collected)
        txt(surf,
            f"Score: {self.app.state.score}  |  Found: {found}/{len(FLOWERS)}  |  Top: Mia 340  Leo 280",
            fnt(10),C_DIM,SCREEN_W//2,309)


# ── 2. Searching ──────────────────────────────────────────────────────────────
class SearchingScreen(Screen):
    def __init__(self, app, fl):
        super().__init__(app)
        self.fl          = fl
        self.start_time  = time.time()
        self.time_left   = float(TIME_LIMIT)
        self.wrong_flash = 0.0
        self.wrong_name  = ""

    def update(self, dt):
        self.time_left = max(0, TIME_LIMIT - (time.time()-self.start_time))
        if self.wrong_flash > 0: self.wrong_flash -= dt
        if self.time_left <= 0:
            timeout_sound()
            led_flash(RED_LED, 1.5)
            self.go(TimeUpScreen(self.app))

    def draw(self, surf):
        surf.fill(C_BG)
        camera_panel(surf, self.app, self.wrong_flash, self.wrong_name)
        left_panel(surf, self.fl, self.app.state.score, self.time_left)

    def on_wrong(self, name):
        error_sound()
        led_flash(RED_LED, 1.0)
        self.wrong_flash = 2.0
        self.wrong_name  = name

    def on_correct(self):
        success_sound()
        led_flash(GREEN_LED, 2.0)
        self.app.state.on_correct(self.fl, self.time_left)
        self.go(SuccessScreen(self.app))


# ── 3. Time's Up ──────────────────────────────────────────────────────────────
class TimeUpScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        if self.t >= 4.0:
            self.go(WaitingScreen(self.app))

    def draw(self, surf):
        surf.fill(C_BG)
        # Red glow
        g = pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
        g.fill((*C_RED2,28))
        surf.blit(g,(0,0))

        name = self.app.state.flower["name"] if self.app.state.flower else "?"
        txt(surf,"Time's Up!",        fnt(38,True),C_RED,   SCREEN_W//2,96)
        pygame.draw.line(surf,C_RED2,(80,116),(400,116),1)
        txt(surf,"The flower was",    fnt(13),     C_MID,   SCREEN_W//2,146)
        txt(surf,name,               fnt(22,True), C_WHITE, SCREEN_W//2,175)
        txt(surf,"score",            fnt(11),      C_DIM,   SCREEN_W//2,212)
        txt(surf,f"{self.app.state.score} pts", fnt(28,True),C_GOLD,SCREEN_W//2,246)
        rnd(surf,C_PANEL,(160,266,160,34),radius=17,alpha=200)
        pygame.draw.rect(surf,C_RED2,(160,266,160,34),width=1,border_radius=17)
        txt(surf,f"returning in {max(0,int(4-self.t))}s...",
            fnt(12),C_MID,SCREEN_W//2,283)


# ── 4. Mission Complete ───────────────────────────────────────────────────────
class SuccessScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.confetti = [
            {"x":random.randint(0,SCREEN_W),"y":random.randint(-SCREEN_H,0),
             "vy":random.uniform(60,140),
             "col":random.choice([C_GREEN,C_GOLD,(167,139,250),C_PINK,C_WHITE]),
             "w":random.randint(4,10)}
            for _ in range(35)
        ]

    def update(self, dt):
        self.t += dt
        for c in self.confetti:
            c["y"] += c["vy"]*dt
            if c["y"] > SCREEN_H+10: c["y"] = -10

    def draw(self, surf):
        surf.fill(C_BG)
        for c in self.confetti:
            pygame.draw.rect(surf,c["col"],(int(c["x"]),int(c["y"]),c["w"],c["w"]//2))

        rnd(surf,(16,185,129),(SCREEN_W-54,10,42,24),radius=12,alpha=220)
        txt(surf,"+1",fnt(14,True),(209,250,229),SCREEN_W-33,22)

        fl = self.app.state.flower
        if fl:
            flower(surf,SCREEN_W//2+100,86,fl["color"],fl["center"],
                   petals=fl["petals"],size=1.6)

        sc = 1.0+0.03*math.sin(self.t*3)
        txt(surf,"MISSION",   fnt(int(24*sc),True),C_GREEN,SCREEN_W//2-40,66)
        txt(surf,"COMPLETE!", fnt(int(24*sc),True),C_GREEN,SCREEN_W//2-40,94)

        if fl:
            txt(surf,f'"{fl["name"]}"',fnt(17),C_WHITE,SCREEN_W//2-40,126)
            txt(surf,fl["fact"],        fnt(10),C_DIM,  SCREEN_W//2-40,146)

        rnd(surf,C_PANEL,(80,162,260,80),radius=12,alpha=230)
        pygame.draw.rect(surf,C_DIM2,(80,162,260,80),width=1,border_radius=12)
        txt(surf,"your score",         fnt(9), C_DIM,  SCREEN_W//2,178)
        txt(surf,str(self.app.state.score),fnt(30,True),C_GOLD,SCREEN_W//2,210)
        txt(surf,f"+{self.app.state.time_bonus} time bonus",
            fnt(9),C_DIM,SCREEN_W//2,234)

        s = self.app.state.stars()
        for i in range(3):
            star(surf,SCREEN_W//2-24+i*24,258,9,i<s,C_GOLD)

        txt(surf,"tap to see collection",fnt(10),C_DIM,SCREEN_W//2,292)

    def on_tap(self):
        self.go(CollectionScreen(self.app))


# ── 5. Flower Collection ──────────────────────────────────────────────────────
class CollectionScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t         = 0.0
        self.btn_play  = pygame.Rect(14, 222,212,36)
        self.btn_reset = pygame.Rect(238,222,228,36)

    def update(self, dt): self.t += dt

    def draw(self, surf):
        surf.fill(C_BG)

        # Header
        rnd(surf,C_PANEL,(0,0,SCREEN_W,46),radius=0,alpha=230)
        pygame.draw.line(surf,C_DIM2,(0,46),(SCREEN_W,46),1)
        txt(surf,"Collection",fnt(18,True),C_PURPLE,196,24)

        # Score badge
        rnd(surf,C_PANEL,(316,8,154,30),radius=6,alpha=220)
        pygame.draw.rect(surf,C_GOLD,(316,8,154,30),width=1,border_radius=6)
        txt(surf,f"Score  {self.app.state.score} pts",fnt(11,True),C_GOLD,393,23)

        # Progress
        found = len(self.app.state.collected)
        total = len(FLOWERS)
        txt(surf,f"{found}/{total} found",fnt(10),C_MID,20,60,anchor="left")
        rnd(surf,C_PANEL,(16,68,150,6),radius=3)
        if total: rnd(surf,C_PURPLE2,(16,68,int(150*found/total),6),radius=3)

        # Flower grid
        cols, cell_w, cell_h = 5,(SCREEN_W-20)//5, 82
        for i, fl in enumerate(FLOWERS):
            cx = 10+(i%cols)*cell_w+cell_w//2
            cy = 94+(i//cols)*cell_h
            ok  = fl["id"] in self.app.state.collected
            bob = math.sin(self.t*1.5+i*0.8)*3 if ok else 0
            rnd(surf,C_PANEL,
                (10+(i%cols)*cell_w,82+(i//cols)*cell_h,cell_w-6,cell_h-4),
                radius=10, alpha=210 if ok else 70)
            if ok:
                flower(surf,cx,int(cy+bob),fl["color"],fl["center"],
                       petals=fl["petals"],size=0.9)
                txt(surf,fl["name"],fnt(9),C_PURPLE,cx,cy+38)
            else:
                flower(surf,cx,cy,C_DIM,C_DIM2,petals=fl["petals"],size=0.9,alpha=50)
                txt(surf,"???",fnt(9),C_DIM2,cx,cy+38)

        # Buttons
        rnd(surf,C_PANEL,(14,222,212,36),radius=18,alpha=220)
        pygame.draw.rect(surf,C_PURPLE2,(14,222,212,36),width=1,border_radius=18)
        txt(surf,"Play again",fnt(12),C_PURPLE,120,240)

        rnd(surf,C_PANEL,(238,222,228,36),radius=18,alpha=220)
        pygame.draw.rect(surf,C_RED,(238,222,228,36),width=1,border_radius=18)
        txt(surf,"Reset game",fnt(12),C_RED,352,240)

        txt(surf,f"flowers found: {found}/{total}  |  score: {self.app.state.score} pts",
            fnt(9),C_DIM2,SCREEN_W//2,294)

    def on_tap(self, pos=None):
        if pos and self.btn_reset.collidepoint(pos):
            self.app.state.full_reset()
        self.go(WaitingScreen(self.app))


# ══════════════════════════════════════════════════════════════════════════════
# APP — main loop
# ══════════════════════════════════════════════════════════════════════════════

class App:
    def __init__(self):
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FlowerFinder")
        self.clock   = pygame.time.Clock()
        self.state   = GameState()

        # Hardware
        self.camera  = Camera()
        self.rfid    = RFID()
        self.qr_q    = queue.Queue()
        self.qr_scan = QRScanner(self.camera, self.qr_q)

        self.current = WaitingScreen(self)

        # GPIO init (from BLEmbedded.py)
        if HARDWARE_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(GREEN_LED, GPIO.OUT)
            GPIO.setup(RED_LED,   GPIO.OUT)
            GPIO.setup(BUZZER,    GPIO.OUT)
            GPIO.output(GREEN_LED, GPIO.LOW)
            GPIO.output(RED_LED,   GPIO.LOW)
            GPIO.output(BUZZER,    GPIO.LOW)

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
            now = time.time()
            dt  = min(now-prev, 0.05)
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
                        self._rfid_q.put(FLOWERS[0])
                    if event.key == pygame.K_q:
                        if isinstance(self.current, SearchingScreen):
                            self.current.on_correct()
                    if event.key == pygame.K_w:
                        if isinstance(self.current, SearchingScreen):
                            self.current.on_wrong("Rose")
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if hasattr(self.current,"on_tap"):
                            self.current.on_tap()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if hasattr(self.current,"on_tap"):
                        self.current.on_tap(event.pos)

            # ── RFID queue ─────────────────────────────────────────────────
            try:
                fl = self._rfid_q.get_nowait()
                self.state.round_reset(fl)
                while not self.qr_q.empty():
                    try: self.qr_q.get_nowait()
                    except queue.Empty: break
                self.current = SearchingScreen(self, fl)
                print(f"[RFID] Flower: {fl['name'].upper()}")
            except queue.Empty:
                pass

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

            # Dev label
            hw = "Pi HW" if HARDWARE_AVAILABLE else "desktop: R=RFID  Q=correct  W=wrong  ENTER=tap"
            f  = pygame.font.SysFont("Arial",10)
            self.screen.blit(
                f.render(f"{type(self.current).__name__}  |  {hw}  |  ESC",True,(46,36,74)),
                (4,2))

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

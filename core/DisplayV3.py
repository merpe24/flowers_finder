"""
FlowerFinder — DisplayV3.py
UI v2: camera fullscreen, no lives, reset button on collection
"""

import pygame
import threading
import math
import time
import sys
import random
import queue

try:
    from picamera2 import Picamera2
    import numpy as np
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

try:
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522
    import cv2
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# ── GPIO ──────────────────────────────────────────────────────────────────────
GREEN_LED = 17
RED_LED   = 27

# ── Screen ────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 480, 320
FPS = 60

# Camera fills the right side of searching screen
CAM_X, CAM_Y = 130, 0
CAM_W, CAM_H = 350, 320

# ── Game constants ────────────────────────────────────────────────────────────
TIME_LIMIT     = 60
POINTS_BASE    = 100
POINTS_PER_SEC = 1

# ── Colors ────────────────────────────────────────────────────────────────────
C_BG       = (8,   5,  16)
C_SURFACE  = (26,  16,  64)
C_SURFACE2 = (17,  13,  40)
C_PURPLE   = (196, 181, 253)
C_PURPLE2  = (124,  58, 237)
C_GREEN    = ( 52, 211, 153)
C_GREEN2   = ( 16, 185, 129)
C_RED      = (239,  68,  68)
C_RED2     = (127,  29,  29)
C_GOLD     = (240, 190,  80)
C_PINK     = (230, 130, 180)
C_WHITE    = (226, 232, 240)
C_DIM      = ( 76,  56, 128)
C_DIM2     = ( 42,  31,  80)
C_MID      = (156, 106, 170)

# ── Flower data ───────────────────────────────────────────────────────────────
FLOWERS = [
    {"id":"sunflower","name":"Sunflower","hint":"Not a Rose",   "fact":"Always faces the sun!", "color":(240,190,60), "center":(180,80,20), "petals":8},
    {"id":"rose",     "name":"Rose",     "hint":"Not Sunflower","fact":"Symbol of love!",       "color":(230,130,180),"center":(157,23,77),"petals":12},
    {"id":"lavender", "name":"Lavender", "hint":"Not a Daisy",  "fact":"Makes you feel calm!",  "color":(167,139,250),"center":(91,33,182),"petals":6},
    {"id":"daisy",    "name":"Daisy",    "hint":"Not Lavender", "fact":"Loves sunny fields!",   "color":(226,232,240),"center":(180,160,50),"petals":10},
    {"id":"orchid",   "name":"Orchid",   "hint":"Not a Tulip",  "fact":"Lives 100 years!",      "color":(216,180,254),"center":(126,34,206),"petals":5},
]
FLOWER_MAP = {f["id"]: f for f in FLOWERS}


# ── Drawing helpers ───────────────────────────────────────────────────────────

def fnt(size, bold=False):
    return pygame.font.SysFont("Arial", size, bold=bold)

def rnd_rect(surf, color, r, radius=10, alpha=255):
    s = pygame.Surface((r[2], r[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0,0,r[2],r[3]), border_radius=radius)
    surf.blit(s, (r[0], r[1]))

def txt(surf, text, font, color, cx, cy, anchor="center"):
    r = font.render(str(text), True, color)
    x = cx - r.get_width()//2 if anchor == "center" else cx
    surf.blit(r, (x, cy - r.get_height()//2))

def draw_flower(surf, cx, cy, color, center_color, petals=8, size=1.0, alpha=255):
    pr = int(14*size)
    pd = int(18*size)
    for i in range(petals):
        a  = math.radians(360/petals*i)
        px = cx + int(math.cos(a)*pd)
        py = cy + int(math.sin(a)*pd)
        s  = pygame.Surface((pr*2+2, pr*2+2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, alpha), (pr+1,pr+1), pr)
        surf.blit(s, (px-pr-1, py-pr-1))
    pygame.draw.circle(surf, center_color, (cx,cy), int(8*size))

def draw_star(surf, cx, cy, size, filled, color):
    pts = []
    for i in range(10):
        a = math.radians(-90 + i*36)
        r = size if i%2==0 else size*0.45
        pts.append((cx+math.cos(a)*r, cy+math.sin(a)*r))
    if filled: pygame.draw.polygon(surf, color, pts)
    else:       pygame.draw.polygon(surf, color, pts, 1)

def draw_sparkles(surf, sparkles):
    for x,y,a,p in sparkles:
        br = int(60 + 40*math.sin(a+p*6))
        col = (br, int(br*0.5), int(br*1.3))
        r = max(1, int(1.2 + math.sin(a*2+p)*1.0))
        pygame.draw.circle(surf, col, (int(x),int(y)), r)


# ══════════════════════════════════════════════════════════════════════════════
# HARDWARE
# ══════════════════════════════════════════════════════════════════════════════

class HardwareManager:
    def __init__(self, q):
        self.q     = q
        self.running = False
        self.cam   = None
        self.cam_ready = False

        if HARDWARE_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(GREEN_LED, GPIO.OUT)
            GPIO.setup(RED_LED,   GPIO.OUT)
            GPIO.output(GREEN_LED, GPIO.LOW)
            GPIO.output(RED_LED,   GPIO.LOW)
            self.rfid = SimpleMFRC522()
            self.qr   = cv2.QRCodeDetector()

        if CAMERA_AVAILABLE:
            try:
                self.cam = Picamera2()
                cfg = self.cam.create_preview_configuration({"size":(CAM_W, CAM_H)})
                self.cam.configure(cfg)
                self.cam.start()
                self.cam_ready = True
            except Exception as e:
                print(f"[Cam] {e}")

        self._last_qr = 0

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.cam_ready: self.cam.stop()
        if HARDWARE_AVAILABLE: GPIO.cleanup()

    def get_frame(self):
        if not self.cam_ready: return None
        try:
            frame = self.cam.capture_array()
            surf  = pygame.surfarray.make_surface(frame.transpose(1,0,2))
            return pygame.transform.scale(surf, (CAM_W, CAM_H))
        except: return None

    def flash(self, pin, t=1.5):
        if HARDWARE_AVAILABLE:
            def _f():
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(t)
                GPIO.output(pin, GPIO.LOW)
            threading.Thread(target=_f, daemon=True).start()

    def _loop(self):
        while self.running:
            self.q.put(("state","waiting"))
            flower = self._rfid()
            if not flower: continue
            self.q.put(("rfid", flower))

            start = time.time()
            found = False
            while self.running and not found:
                tl = TIME_LIMIT - (time.time()-start)
                self.q.put(("timer", max(0, tl)))
                if tl <= 0:
                    self.q.put(("timeout", None))
                    self.flash(RED_LED, 1.5)
                    break
                qr = self._qr()
                if qr and (time.time()-self._last_qr) > 1.5:
                    self._last_qr = time.time()
                    if qr == flower["id"]:
                        self.q.put(("correct",{"flower":flower,"time_left":tl}))
                        self.flash(GREEN_LED, 2.0)
                        found = True
                    else:
                        wf = FLOWER_MAP.get(qr, {"name": qr})
                        self.q.put(("wrong", wf["name"]))
                        self.flash(RED_LED, 0.8)
                time.sleep(0.05)

    def _rfid(self):
        if not HARDWARE_AVAILABLE: return None
        try:
            _, text = self.rfid.read()
            if not text: return None
            fid = text.replace('\x00','').strip().lower()
            return FLOWER_MAP.get(fid)
        except: return None

    def _qr(self):
        if not (self.cam_ready and HARDWARE_AVAILABLE): return None
        try:
            img = self.cam.capture_array()
            data, bbox, _ = self.qr.detectAndDecode(img)
            return data.strip().lower() if (bbox is not None and data) else None
        except: return None


# ══════════════════════════════════════════════════════════════════════════════
# GAME STATE
# ══════════════════════════════════════════════════════════════════════════════

class GameState:
    def __init__(self): self.reset()
    def reset(self):
        self.flower     = None
        self.score      = 0
        self.time_left  = TIME_LIMIT
        self.collected  = []
        self.time_bonus = 0
    def on_correct(self, flower, tl):
        self.flower     = flower
        self.time_left  = tl
        self.time_bonus = int(tl * POINTS_PER_SEC)
        self.score     += POINTS_BASE + self.time_bonus
        if flower["id"] not in self.collected:
            self.collected.append(flower["id"])
    def stars(self):
        if self.time_bonus > 40: return 3
        if self.time_bonus > 20: return 2
        return 1


# ══════════════════════════════════════════════════════════════════════════════
# SCREENS
# ══════════════════════════════════════════════════════════════════════════════

class Screen:
    def __init__(self, app):
        self.app = app
    def update(self, dt): pass
    def draw(self, surf): pass
    def go(self, s): self.app.current = s


# ── 1. Waiting ────────────────────────────────────────────────────────────────
class WaitingScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        self.sp = [(random.randint(10,SCREEN_W-10),
                    random.randint(10,SCREEN_H-10),
                    random.random()*6.28,
                    random.random()) for _ in range(14)]

    def update(self, dt):
        self.t += dt
        self.sp = [(x,y,a+dt*0.7,p) for x,y,a,p in self.sp]

    def draw(self, surf):
        surf.fill(C_BG)
        draw_sparkles(surf, self.sp)

        # Glow circle bg
        glow = pygame.Surface((200,200), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*C_PURPLE2, 18), (100,100), 100)
        surf.blit(glow, (140, 30))

        # Title
        txt(surf, "F L O W E R  F I N D E R", fnt(10), C_DIM, SCREEN_W//2, 28)
        txt(surf, "FlowerFinder", fnt(30, True), C_PURPLE, SCREEN_W//2, 60)

        # Card
        bob = int(math.sin(self.t*1.5)*5)
        cx, cy = SCREEN_W//2, 148 + bob
        rnd_rect(surf, C_SURFACE2, (cx-80,cy-52,160,104), radius=14, alpha=235)
        pygame.draw.rect(surf, C_PURPLE2, (cx-80,cy-52,160,104), width=1, border_radius=14)
        # Chip
        pygame.draw.rect(surf, C_GOLD, (cx-62,cy-28,26,18), border_radius=3)
        # Lines
        for i,w in enumerate([70,52,60]):
            pygame.draw.line(surf, C_DIM2, (cx-62,cy+8+i*11), (cx-62+w,cy+8+i*11), 2)
        # Small flower
        draw_flower(surf, cx+48, cy-8, C_PINK, (157,23,77), petals=6, size=0.55)

        # Arrows
        for i in range(3):
            a = max(0, int(120+90*math.sin(self.t*2-i*0.6)) - i*50)
            s = pygame.Surface((12,8), pygame.SRCALPHA)
            pygame.draw.polygon(s, (*C_PURPLE, a), [(0,0),(12,0),(6,8)])
            surf.blit(s, (SCREEN_W//2-6, 214+i*12))

        txt(surf, "แตะการ์ด RFID เพื่อเริ่มเกม", fnt(14), C_MID, SCREEN_W//2, 255)
        txt(surf, "tap your RFID card to begin", fnt(11), C_DIM, SCREEN_W//2, 272)

        # Leaderboard bar
        rnd_rect(surf, C_SURFACE2, (0,298,SCREEN_W,22), radius=0, alpha=200)
        found = len(self.app.state.collected)
        txt(surf, f"Score: {self.app.state.score}  |  Found: {found}/{len(FLOWERS)}  |  Top: Mia 340  Leo 280",
            fnt(10), C_DIM, SCREEN_W//2, 309)


# ── 2. Searching ──────────────────────────────────────────────────────────────
class SearchingScreen(Screen):
    def __init__(self, app, flower):
        super().__init__(app)
        self.flower      = flower
        self.time_left   = TIME_LIMIT
        self.wrong_flash = 0.0
        self.wrong_name  = ""
        self.t           = 0.0

    def update(self, dt):
        self.t += dt
        if self.wrong_flash > 0: self.wrong_flash -= dt

    def draw(self, surf):
        surf.fill(C_BG)

        # ── Camera panel (full right) ──
        frame = self.app.hw.get_frame()
        if frame:
            surf.blit(frame, (CAM_X, CAM_Y))
        else:
            rnd_rect(surf, (13,20,13), (CAM_X,0,CAM_W,CAM_H), radius=0)
            # Grid lines (camera placeholder look)
            for gx in range(CAM_X, SCREEN_W, 40):
                pygame.draw.line(surf, (20,40,20), (gx,0), (gx,CAM_H), 1)
            for gy in range(0, CAM_H, 40):
                pygame.draw.line(surf, (20,40,20), (CAM_X,gy), (SCREEN_W,gy), 1)
            txt(surf,"[ camera feed ]",fnt(12),(40,100,60),CAM_X+CAM_W//2,CAM_H//2-10)
            txt(surf,"Q = correct  W = wrong",fnt(10),(30,70,45),CAM_X+CAM_W//2,CAM_H//2+10)

        # Viewfinder corners
        co = (60,180,100)
        sz = 14
        for fx,fy in [(CAM_X+4,4),(SCREEN_W-4,4),(CAM_X+4,CAM_H-4),(SCREEN_W-4,CAM_H-4)]:
            dx = 1 if fx < SCREEN_W//2 else -1
            dy = 1 if fy < CAM_H//2 else -1
            pygame.draw.line(surf,co,(fx,fy),(fx+sz*dx,fy),2)
            pygame.draw.line(surf,co,(fx,fy),(fx,fy+sz*dy),2)

        # Wrong flash overlay at bottom of camera
        if self.wrong_flash > 0:
            a  = min(220, int(self.wrong_flash*280))
            fl = pygame.Surface((CAM_W, 48), pygame.SRCALPHA)
            fl.fill((180,20,20, a))
            surf.blit(fl, (CAM_X, CAM_H-48))
            txt(surf, f"Not {self.wrong_name}!  Keep looking...",
                fnt(13, True),(255,180,180), CAM_X+CAM_W//2, CAM_H-24)

        # Scan label
        txt(surf,"point camera at QR code",fnt(10),(40,100,60),CAM_X+CAM_W//2, SCREEN_H-8)

        # ── Left info panel ──
        rnd_rect(surf, C_SURFACE2, (0,0,130,SCREEN_H), radius=0, alpha=230)
        pygame.draw.line(surf, C_DIM2, (129,0),(129,SCREEN_H), 1)

        txt(surf,"FIND THIS",fnt(9),C_DIM,65,18)
        draw_flower(surf, 65, 74, self.flower["color"], self.flower["center"],
                    petals=self.flower["petals"], size=1.5)
        txt(surf, self.flower["name"], fnt(13,True), C_PURPLE, 65, 118)

        rnd_rect(surf, C_DIM2, (6,130,118,20), radius=10, alpha=200)
        txt(surf, self.flower["hint"], fnt(9), C_MID, 65, 140)

        txt(surf, self.flower["fact"], fnt(9), C_DIM, 65, 162)

        # Divider
        pygame.draw.line(surf, C_DIM2, (12,178),(118,178), 1)

        # Score
        txt(surf,"score",fnt(8),C_DIM,65,192)
        txt(surf,str(self.app.state.score),fnt(18,True),C_GOLD,65,212)
        txt(surf,"pts",fnt(8),C_DIM,65,228)

        # Divider
        pygame.draw.line(surf, C_DIM2, (12,240),(118,240), 1)

        # Timer
        t = int(self.time_left)
        col = C_GREEN if t > 40 else (C_GOLD if t > 15 else C_RED)
        txt(surf,"time left",fnt(8),C_DIM,65,254)
        txt(surf,str(t),fnt(32,True),col,65,284)
        txt(surf,"sec",fnt(8),col,65,308)

    def on_wrong(self, name):
        self.wrong_flash = 1.8
        self.wrong_name  = name

    def on_timer(self, tl):
        self.time_left = tl


# ── 3. Time Up ────────────────────────────────────────────────────────────────
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
        glow = pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
        glow.fill((*C_RED2, 30))
        surf.blit(glow,(0,0))
        name = self.app.state.flower["name"] if self.app.state.flower else "?"
        txt(surf,"Time's Up!",    fnt(38,True),C_RED,     SCREEN_W//2, 98)
        pygame.draw.line(surf,C_RED2,(80,118),(400,118),1)
        txt(surf,"The flower was",fnt(13),     C_MID,     SCREEN_W//2,148)
        txt(surf,name,            fnt(22,True),C_WHITE,   SCREEN_W//2,176)
        txt(surf,"score",         fnt(11),     C_DIM,     SCREEN_W//2,212)
        txt(surf,f"{self.app.state.score} pts",fnt(28,True),C_GOLD,SCREEN_W//2,246)
        rnd_rect(surf, C_SURFACE2, (160,268,160,34), radius=17, alpha=200)
        pygame.draw.rect(surf,C_RED2,(160,268,160,34),width=1,border_radius=17)
        txt(surf,f"returning in {max(0,int(4-self.t))}s...",
            fnt(12),C_MID,SCREEN_W//2,285)


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
            pygame.draw.rect(surf, c["col"], (int(c["x"]),int(c["y"]),c["w"],c["w"]//2))

        # +1 badge
        rnd_rect(surf, C_GREEN2, (SCREEN_W-54,10,42,24), radius=12, alpha=220)
        txt(surf,"+1",fnt(14,True),(209,250,229),SCREEN_W-33,22)

        # Flower
        fl = self.app.state.flower
        if fl:
            draw_flower(surf, SCREEN_W//2+100, 90,
                       fl["color"], fl["center"], petals=fl["petals"], size=1.6)

        sc = 1.0+0.03*math.sin(self.t*3)
        txt(surf,"MISSION",   fnt(int(24*sc),True),C_GREEN,SCREEN_W//2-40,68)
        txt(surf,"COMPLETE!", fnt(int(24*sc),True),C_GREEN,SCREEN_W//2-40,96)

        if fl:
            txt(surf,f'"{fl["name"]}"',fnt(17),(226,232,240),SCREEN_W//2-40,128)
            txt(surf,fl["fact"],        fnt(10),C_DIM,         SCREEN_W//2-40,148)

        # Score card
        rnd_rect(surf,C_SURFACE2,(80,162,260,80),radius=12,alpha=230)
        pygame.draw.rect(surf,C_DIM2,(80,162,260,80),width=1,border_radius=12)
        txt(surf,"your score",fnt(9),C_DIM,SCREEN_W//2,178)
        txt(surf,str(self.app.state.score),fnt(30,True),C_GOLD,SCREEN_W//2,210)
        txt(surf,f"+{self.app.state.time_bonus} time bonus",fnt(9),C_DIM,SCREEN_W//2,236)

        # Stars
        s = self.app.state.stars()
        for i in range(3):
            draw_star(surf, SCREEN_W//2-24+i*24, 262, 9, i<s, C_GOLD)

        txt(surf,"tap to see collection",fnt(10),C_DIM,SCREEN_W//2,295)
        txt(surf,"click or press ENTER",fnt(9),C_DIM2,SCREEN_W//2,310)

    def on_tap(self):
        self.go(CollectionScreen(self.app))


# ── 5. Collection ─────────────────────────────────────────────────────────────
class CollectionScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.t = 0.0
        # Button rects for click detection
        self.btn_play  = pygame.Rect(14,  224, 212, 36)
        self.btn_reset = pygame.Rect(238, 224, 228, 36)

    def update(self, dt): self.t += dt

    def draw(self, surf):
        surf.fill(C_BG)

        # Header
        rnd_rect(surf, C_SURFACE2, (0,0,SCREEN_W,46), radius=0, alpha=230)
        pygame.draw.line(surf, C_DIM2, (0,46),(SCREEN_W,46), 1)
        txt(surf,"Collection",fnt(18,True),C_PURPLE, 200,24)

        # Score box
        rnd_rect(surf,C_SURFACE2,(318,8,152,30),radius=6,alpha=220)
        pygame.draw.rect(surf,C_GOLD,(318,8,152,30),width=1,border_radius=6)
        txt(surf,f"Score  {self.app.state.score} pts",fnt(11,True),C_GOLD,394,23)

        # Progress
        found = len(self.app.state.collected)
        total = len(FLOWERS)
        txt(surf,f"{found}/{total} found",fnt(10),C_MID,20,60,anchor="left")
        rnd_rect(surf,C_SURFACE2,(16,68,150,6),radius=3)
        if total: rnd_rect(surf,C_PURPLE2,(16,68,int(150*found/total),6),radius=3)

        # Flower grid
        cols, cell_w, cell_h = 5, (SCREEN_W-20)//5, 82
        for i, flower in enumerate(FLOWERS):
            cx = 10 + (i%cols)*cell_w + cell_w//2
            cy = 94  + (i//cols)*cell_h
            ok = flower["id"] in self.app.state.collected
            bob = math.sin(self.t*1.5+i*0.8)*3 if ok else 0
            rnd_rect(surf, C_SURFACE2,
                     (10+(i%cols)*cell_w, 82+(i//cols)*cell_h, cell_w-6, cell_h-4),
                     radius=10, alpha=210 if ok else 70)
            if ok:
                draw_flower(surf,cx,int(cy+bob),
                            flower["color"],flower["center"],
                            petals=flower["petals"],size=0.9)
                txt(surf,flower["name"],fnt(9),C_PURPLE,cx,cy+38)
            else:
                draw_flower(surf,cx,cy,C_DIM,C_DIM2,petals=flower["petals"],size=0.9,alpha=50)
                txt(surf,"???",fnt(9),C_DIM2,cx,cy+38)

        # ── Buttons ──
        # Play again
        rnd_rect(surf,C_SURFACE2,(14,224,212,36),radius=18,alpha=220)
        pygame.draw.rect(surf,C_PURPLE2,(14,224,212,36),width=1,border_radius=18)
        txt(surf,"Play again",fnt(12),C_PURPLE,120,242)

        # Reset game
        rnd_rect(surf,C_SURFACE2,(238,224,228,36),radius=18,alpha=220)
        pygame.draw.rect(surf,C_RED,(238,224,228,36),width=1,border_radius=18)
        txt(surf,"Reset game",fnt(12),C_RED,352,242)

        # Stats
        txt(surf,f"flowers found this session: {found}  |  total score: {self.app.state.score} pts",
            fnt(9),C_DIM2,SCREEN_W//2,294)
        txt(surf,"play again = next round   |   reset = clear everything",
            fnt(8),C_DIM2,SCREEN_W//2,310)

    def on_tap(self, pos=None):
        if pos and self.btn_reset.collidepoint(pos):
            self.app.state.reset()
            self.go(WaitingScreen(self.app))
        else:
            self.go(WaitingScreen(self.app))


# ══════════════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════════════

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FlowerFinder")
        self.clock   = pygame.time.Clock()
        self.state   = GameState()
        self.q       = queue.Queue()
        self.hw      = HardwareManager(self.q)
        self.current = WaitingScreen(self)

    def run(self):
        self.hw.start()
        prev = time.time()
        while True:
            now = time.time()
            dt  = min(now-prev, 0.05)
            prev = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.hw.stop(); pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.hw.stop(); pygame.quit(); sys.exit()
                    # Desktop testing shortcuts
                    if event.key == pygame.K_r:
                        self.q.put(("rfid", FLOWERS[0]))
                    if event.key == pygame.K_q and hasattr(self.current,"flower"):
                        self.q.put(("correct",{"flower":self.current.flower,"time_left":self.current.time_left}))
                    if event.key == pygame.K_w and hasattr(self.current,"flower"):
                        self.q.put(("wrong","Rose"))
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if hasattr(self.current,"on_tap"):
                            self.current.on_tap()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = event.pos
                    if hasattr(self.current,"on_tap"):
                        self.current.on_tap(pos)

            self._poll_queue()
            self.current.update(dt)
            self.current.draw(self.screen)

            # Dev label
            hw_str = "Pi hardware" if HARDWARE_AVAILABLE else "desktop  R=RFID  Q=correct  W=wrong  ENTER=tap"
            f = pygame.font.SysFont("Arial",10)
            t = f.render(f"{type(self.current).__name__}  |  {hw_str}  |  ESC",True,(50,40,80))
            self.screen.blit(t,(4,2))

            pygame.display.flip()
            self.clock.tick(FPS)

    def _poll_queue(self):
        while True:
            try: ev, data = self.q.get_nowait()
            except queue.Empty: break

            if ev == "rfid":
                self.state.flower = data
                self.current = SearchingScreen(self, data)

            elif ev == "timer":
                if isinstance(self.current, SearchingScreen):
                    self.current.on_timer(data)

            elif ev == "wrong":
                if isinstance(self.current, SearchingScreen):
                    self.current.on_wrong(data)

            elif ev == "correct":
                self.state.on_correct(data["flower"], data["time_left"])
                self.current = SuccessScreen(self)

            elif ev == "timeout":
                self.current = TimeUpScreen(self)

if __name__ == "__main__":
    App().run()

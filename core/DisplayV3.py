"""
FlowerFinder - Display Controller
Screens: Insert Card → Searching (Camera/Radar) → Wrong / Success / Time Up → Collection
Target: 480x320 TFT (scales to any window for desktop testing)
"""

import pygame
import math
import time
import sys
import os
import random

# ── Config ────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 480, 320
FPS = 60
FONT_PATH = None  # swap for a custom font path on Pi
ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

# Camera viewport position on the searching screen
CAM_X, CAM_Y, CAM_W, CAM_H = 185, 10, 285, 265

try:
    from picamera2 import Picamera2
    import numpy as np
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

# ── Game constants ────────────────────────────────────────────────────────────
TIME_LIMIT     = 60
POINTS_BASE    = 100
POINTS_PER_SEC = 1
POINTS_WRONG   = -10

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = (15,  12,  30)
BG2         = (28,  22,  50)
ACCENT      = (200, 120, 220)
ACCENT2     = (120, 200, 160)
WARN        = (230, 100,  90)
GOLD        = (240, 190,  80)
TEXT_PRI    = (240, 235, 250)
TEXT_SEC    = (160, 145, 190)
TEXT_HINT   = (110,  95, 140)
RADAR_RING  = ( 80, 180, 120)
RADAR_SWEEP = (120, 220, 150)
WHITE       = (255, 255, 255)
PINK        = (230, 130, 180)

# ── Flower data ───────────────────────────────────────────────────────────────
FLOWERS = [
    {"id": "sunflower", "name": "Sunflower", "hint": "Not a Rose",    "fact": "Always faces the sun!",  "emoji_color": GOLD,   "petals": 8,  "center": (220,  90,  50)},
    {"id": "rose",      "name": "Rose",      "hint": "Not Sunflower", "fact": "Symbol of love!",        "emoji_color": PINK,   "petals": 12, "center": (180,  60,  80)},
    {"id": "lavender",  "name": "Lavender",  "hint": "Not a Daisy",   "fact": "Makes you feel calm!",   "emoji_color": ACCENT, "petals": 6,  "center": (100,  70, 160)},
    {"id": "daisy",     "name": "Daisy",     "hint": "Not Lavender",  "fact": "Loves sunny fields!",    "emoji_color": WHITE,  "petals": 10, "center": (200, 180,  60)},
    {"id": "orchid",    "name": "Orchid",    "hint": "Not a Tulip",   "fact": "Lives 100 years!",       "emoji_color": PINK,   "petals": 5,  "center": (160,  80, 120)},
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_font(size, bold=False):
    return pygame.font.SysFont("Arial", size, bold=bold)

def draw_rounded_rect(surf, color, rect, radius=14, alpha=255):
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0, 0, rect[2], rect[3]), border_radius=radius)
    surf.blit(s, (rect[0], rect[1]))

def draw_text_center(surf, text, font, color, cx, cy):
    t = font.render(str(text), True, color)
    surf.blit(t, (cx - t.get_width()//2, cy - t.get_height()//2))

def draw_text(surf, text, font, color, x, y):
    t = font.render(str(text), True, color)
    surf.blit(t, (x, y))
    return t.get_width()

def draw_flower(surf, cx, cy, petals, petal_color, center_color, size=1.0, alpha=255):
    pr = int(18 * size)
    cr = int(9 * size)
    pd = int(22 * size)
    flower_surf = pygame.Surface((pr*4, pr*4), pygame.SRCALPHA)
    fc = (pr*2, pr*2)
    for i in range(petals):
        angle = math.radians(360 / petals * i)
        px = fc[0] + int(math.cos(angle) * pd)
        py = fc[1] + int(math.sin(angle) * pd)
        pygame.draw.circle(flower_surf, (*petal_color, alpha), (px, py), pr)
    pygame.draw.circle(flower_surf, (*center_color, alpha), fc, cr)
    surf.blit(flower_surf, (cx - pr*2, cy - pr*2))

def draw_heart(surf, cx, cy, size, color):
    points = []
    for i in range(360):
        a = math.radians(i)
        x = size * (16 * math.sin(a)**3)
        y = -size * (13*math.cos(a) - 5*math.cos(2*a) - 2*math.cos(3*a) - math.cos(4*a))
        points.append((cx + x/4, cy + y/4))
    if len(points) > 2:
        pygame.draw.polygon(surf, color, points)

def draw_star(surf, cx, cy, size, color):
    points = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        r = size if i % 2 == 0 else size * 0.45
        points.append((cx + math.cos(angle)*r, cy + math.sin(angle)*r))
    pygame.draw.polygon(surf, color, points)


# ── Camera ────────────────────────────────────────────────────────────────────

class Camera:
    def __init__(self):
        self.cam   = None
        self.ready = False
        if CAMERA_AVAILABLE:
            try:
                self.cam = Picamera2()
                cfg = self.cam.create_preview_configuration({"size": (CAM_W, CAM_H)})
                self.cam.configure(cfg)
                self.cam.start()
                self.ready = True
            except Exception as e:
                print(f"[Camera] {e}")

    def get_frame(self):
        if self.ready:
            try:
                frame = self.cam.capture_array()
                surf  = pygame.surfarray.make_surface(frame.transpose(1,0,2))
                return pygame.transform.scale(surf, (CAM_W, CAM_H))
            except Exception:
                pass
        return None

    def stop(self):
        if self.ready:
            self.cam.stop()


# ── Game state ────────────────────────────────────────────────────────────────

class GameState:
    def __init__(self): self.reset()

    def reset(self):
        self.current_flower  = None
        self.score           = 0
        self.time_left       = TIME_LIMIT
        self.collected       = []   # list of flower dicts
        self.last_wrong_scan = None
        self.time_bonus      = 0
        self.lives           = 3

    def start_round(self, flower):
        self.current_flower = flower
        self.time_left      = TIME_LIMIT
        self.lives          = 3

    def on_correct_scan(self):
        self.time_bonus = int(self.time_left * POINTS_PER_SEC)
        self.score     += POINTS_BASE + self.time_bonus
        ids = [f["id"] for f in self.collected]
        if self.current_flower["id"] not in ids:
            self.collected.append(self.current_flower)

    def on_wrong_scan(self, name):
        self.last_wrong_scan = name
        self.score = max(0, self.score + POINTS_WRONG)
        self.lives = max(0, self.lives - 1)

    def stars_earned(self):
        if self.time_bonus > 40: return 3
        if self.time_bonus > 20: return 2
        return 1


# ── Base screen ───────────────────────────────────────────────────────────────

class Screen:
    def __init__(self, app):
        self.app = app

    def update(self, dt): pass
    def draw(self, surf): pass
    def on_event(self, event): pass


# ── Screen 1: Insert Card ─────────────────────────────────────────────────────

class InsertCardScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.pulse    = 0.0
        self.card_bob = 0.0
        self.f_large  = load_font(28, bold=True)
        self.f_med    = load_font(18)
        self.f_small  = load_font(14)
        self.f_hint   = load_font(13)
        self.sparkles = [
            (random.randint(20, SCREEN_W-20), random.randint(20, SCREEN_H-20),
             random.random()*6.28, random.random())
            for _ in range(18)
        ]

    def update(self, dt):
        self.pulse    += dt * 2.0
        self.card_bob += dt * 1.5
        for i, (x, y, a, p) in enumerate(self.sparkles):
            self.sparkles[i] = (x, y, a + dt * 0.8, p)

    def draw(self, surf):
        surf.fill(BG)

        for x, y, a, p in self.sparkles:
            br  = int(80 + 50 * math.sin(a + p * 6))
            col = (br, int(br * 0.6), int(br * 1.2))
            r   = int(1.5 + math.sin(a * 2 + p) * 1.2)
            pygame.draw.circle(surf, col, (int(x), int(y)), max(1, r))

        draw_text_center(surf, "FLOWER FINDER", load_font(32, bold=True), ACCENT, SCREEN_W//2, 38)

        bob = int(math.sin(self.card_bob) * 5)
        card_x, card_y = SCREEN_W//2 - 90, 68 + bob
        draw_rounded_rect(surf, BG2, (card_x, card_y, 180, 110), radius=16, alpha=220)
        pygame.draw.rect(surf, ACCENT, (card_x, card_y, 180, 110), width=2, border_radius=16)
        pygame.draw.rect(surf, GOLD,   (card_x+16, card_y+28, 28, 20), border_radius=4)
        pygame.draw.rect(surf, BG2,    (card_x+16, card_y+28, 28, 20), width=1, border_radius=4)
        for i, w in enumerate([80, 60, 70]):
            pygame.draw.line(surf, TEXT_HINT,
                             (card_x+16, card_y+60+i*12),
                             (card_x+16+w, card_y+60+i*12), 2)
        draw_text(surf, "Not Rose", self.f_hint, PINK, card_x + 60, card_y + 55)
        draw_flower(surf, card_x + 148, card_y + 55, 6, PINK, (200, 80, 100), size=0.6, alpha=180)

        pulse_alpha = int(160 + 90 * math.sin(self.pulse))
        for i in range(3):
            a   = max(0, pulse_alpha - i * 55)
            col = (*ACCENT, a)
            s   = pygame.Surface((14, 10), pygame.SRCALPHA)
            pygame.draw.polygon(s, col, [(0,0),(14,0),(7,10)])
            surf.blit(s, (SCREEN_W//2 - 7, 196 + i*14))

        draw_text_center(surf, "Insert your RFID card", self.f_med,   TEXT_SEC,  SCREEN_W//2, 242)
        draw_text_center(surf, "to find a flower!",     self.f_small, TEXT_HINT, SCREEN_W//2, 266)

        draw_rounded_rect(surf, BG2, (20, 286, 440, 26), radius=8, alpha=160)
        draw_text_center(surf, "TOP: Mia 340 pts  |  Leo 280 pts  |  Sam 210 pts",
                         self.f_hint, TEXT_HINT, SCREEN_W//2, 299)

    def on_rfid_card_read(self, flower):
        self.app.state.start_round(flower)
        self.app.current = SearchingScreen(self.app, flower)


# ── Screen 2: Searching ───────────────────────────────────────────────────────

class SearchingScreen(Screen):
    def __init__(self, app, flower):
        super().__init__(app)
        self.flower      = flower
        self.elapsed     = 0.0
        self.sweep_angle = 0.0
        self.rings       = []
        self.wrong_flash = 0.0
        self.wrong_name  = ""
        self.f_large = load_font(26, bold=True)
        self.f_small = load_font(13)
        self.f_tiny  = load_font(12)

    @property
    def time_left(self):
        return max(0.0, TIME_LIMIT - self.elapsed)

    def update(self, dt):
        self.elapsed     += dt
        self.sweep_angle += dt * 120
        if random.random() < dt * 2:
            self.rings.append([0.0, 1.0])
        self.rings = [[r + dt*60, max(0, a - dt*1.2)] for r, a in self.rings if a > 0]
        if self.wrong_flash > 0:
            self.wrong_flash -= dt
        self.app.state.time_left = self.time_left
        if self.time_left <= 0:
            self.app.current = TimeUpScreen(self.app)

    def draw(self, surf):
        surf.fill(BG)

        # ── Left panel: flower target ──
        panel_w = 170
        draw_rounded_rect(surf, BG2, (10, 10, panel_w, 300), radius=14, alpha=200)
        draw_text_center(surf, "FIND THIS",              self.f_tiny,  TEXT_HINT, 10 + panel_w//2, 30)
        draw_text_center(surf, self.flower["name"].upper(), self.f_large, ACCENT,  10 + panel_w//2, 58)
        fc = self.flower
        draw_flower(surf, 10 + panel_w//2, 130, fc["petals"], fc["emoji_color"], fc["center"], size=1.8)
        draw_rounded_rect(surf, (40, 30, 60), (20, 190, panel_w-20, 30), radius=8, alpha=180)
        draw_text_center(surf, fc["hint"], self.f_small, TEXT_SEC, 10+panel_w//2, 205)
        fact_words = fc["fact"].split()
        line, lines = [], []
        for w in fact_words:
            line.append(w)
            if len(" ".join(line)) > 18:
                lines.append(" ".join(line[:-1]))
                line = [w]
        if line: lines.append(" ".join(line))
        for i, l in enumerate(lines):
            draw_text_center(surf, l, self.f_tiny, TEXT_HINT, 10+panel_w//2, 240+i*16)

        # ── Right panel: live camera or radar fallback ──
        cam_frame = self.app.camera.get_frame()
        if cam_frame is not None:
            surf.blit(cam_frame, (CAM_X, CAM_Y))
            pygame.draw.rect(surf, (60,160,100), (CAM_X, CAM_Y, CAM_W, CAM_H), 1)
            if self.wrong_flash > 0:
                a  = min(200, int(self.wrong_flash * 300))
                fl = pygame.Surface((CAM_W, 34), pygame.SRCALPHA)
                fl.fill((200, 60, 60, a))
                surf.blit(fl, (CAM_X, CAM_Y + CAM_H - 34))
                draw_text_center(surf, f"Not {self.wrong_name}!  Keep looking...",
                                 self.f_tiny, (255,210,210),
                                 CAM_X + CAM_W//2, CAM_Y + CAM_H - 17)
            draw_text_center(surf, "Point camera at QR code",
                             self.f_tiny, TEXT_HINT, CAM_X + CAM_W//2, CAM_Y + CAM_H + 14)
        else:
            # Radar animation (desktop / no camera)
            cx, cy, r_max = 330, 160, 110
            for ring_r, alpha in self.rings:
                if ring_r < r_max:
                    rs = pygame.Surface((r_max*2+4, r_max*2+4), pygame.SRCALPHA)
                    pygame.draw.circle(rs, (*RADAR_RING, int(alpha*180)),
                                       (r_max+2, r_max+2), int(ring_r), 1)
                    surf.blit(rs, (cx-r_max-2, cy-r_max-2))
            for rr in [r_max*0.33, r_max*0.66, r_max]:
                s = pygame.Surface((int(rr)*2+4, int(rr)*2+4), pygame.SRCALPHA)
                pygame.draw.circle(s, (*RADAR_RING, 55), (int(rr)+2, int(rr)+2), int(rr), 1)
                surf.blit(s, (int(cx-rr-2), int(cy-rr-2)))
            pygame.draw.line(surf, (*RADAR_RING, 40), (cx-r_max, cy), (cx+r_max, cy), 1)
            pygame.draw.line(surf, (*RADAR_RING, 40), (cx, cy-r_max), (cx, cy+r_max), 1)
            sweep_surf = pygame.Surface((r_max*2+4, r_max*2+4), pygame.SRCALPHA)
            sweep_rad  = math.radians(self.sweep_angle % 360)
            pts = [(r_max+2, r_max+2)]
            for i in range(30):
                ang = sweep_rad - math.radians(i * 2.5)
                pts.append((r_max+2 + int(math.cos(ang)*r_max), r_max+2 + int(math.sin(ang)*r_max)))
            if len(pts) > 2:
                pygame.draw.polygon(sweep_surf, (*RADAR_SWEEP, 0), pts)
                for i in range(28):
                    ang = sweep_rad - math.radians(i * 2.5)
                    a2  = int(70 * (1 - i/28.0))
                    pygame.draw.line(sweep_surf, (*RADAR_SWEEP, a2),
                                     (r_max+2, r_max+2),
                                     (r_max+2 + int(math.cos(ang)*r_max),
                                      r_max+2 + int(math.sin(ang)*r_max)), 2)
            surf.blit(sweep_surf, (cx-r_max-2, cy-r_max-2))
            edge_x = cx + int(math.cos(sweep_rad) * r_max)
            edge_y = cy + int(math.sin(sweep_rad) * r_max)
            pygame.draw.line(surf, (*RADAR_SWEEP, 200), (cx, cy), (edge_x, edge_y), 2)
            pygame.draw.circle(surf, RADAR_SWEEP, (cx, cy), 5)
            if self.wrong_flash > 0:
                a  = min(180, int(self.wrong_flash * 200))
                fl = pygame.Surface((r_max*2, 30), pygame.SRCALPHA)
                fl.fill((200, 60, 60, a))
                surf.blit(fl, (cx-r_max, cy + r_max - 30))
                draw_text_center(surf, f"Not {self.wrong_name}!",
                                 self.f_tiny, (255,210,210), cx, cy + r_max - 15)
            draw_text_center(surf, "Point camera at QR code",
                             self.f_tiny, TEXT_HINT, cx, cy + r_max + 16)

        # ── Timer (pie clock, top-right) ──
        tr     = 28
        tx, ty = SCREEN_W - tr - 14, tr + 10
        ratio  = self.time_left / TIME_LIMIT
        tcol   = ACCENT2 if ratio > 0.4 else (GOLD if ratio > 0.2 else WARN)
        if ratio > 0:
            pie = pygame.Surface((tr*2+4, tr*2+4), pygame.SRCALPHA)
            pygame.draw.circle(pie, (*BG2, 200), (tr+2, tr+2), tr)
            for a in range(int(360*(1-ratio))):
                ang = math.radians(-90 + a)
                pygame.draw.circle(pie, (*tcol, 100),
                                   (tr+2 + int(math.cos(ang)*tr*0.7),
                                    tr+2 + int(math.sin(ang)*tr*0.7)), 2)
            surf.blit(pie, (tx-tr-2, ty-tr-2))
        pygame.draw.circle(surf, tcol, (tx, ty), tr, 2)
        draw_text_center(surf, f"{int(self.time_left)}", load_font(15, bold=True), tcol, tx, ty)

    def on_qr_scanned(self, scanned_name):
        state = self.app.state
        if scanned_name.lower() == self.flower["name"].lower():
            state.on_correct_scan()
            self.app.current = SuccessScreen(self.app, self.flower,
                                             state.score, state.time_bonus)
        else:
            state.on_wrong_scan(scanned_name)
            if state.lives <= 0:
                self.app.current = WrongScanScreen(self.app, self.flower,
                                                   scanned_name, lives_left=0)
            else:
                self.wrong_flash = 1.5
                self.wrong_name  = scanned_name


# ── Screen 3a: Wrong Scan ─────────────────────────────────────────────────────

class WrongScanScreen(Screen):
    def __init__(self, app, flower, scanned_name, lives_left=2):
        super().__init__(app)
        self.flower     = flower
        self.scanned    = scanned_name
        self.lives_left = lives_left
        self.timer      = 0.0
        self.shake      = 1.0
        self.f_big   = load_font(36, bold=True)
        self.f_med   = load_font(20)
        self.f_small = load_font(14)
        self.particles = [
            {"x": SCREEN_W//2 + random.randint(-60, 60),
             "y": SCREEN_H//2 + random.randint(-40, 40),
             "vx": random.uniform(-80, 80), "vy": random.uniform(-120, -20),
             "life": 1.0, "size": random.randint(3, 8)}
            for _ in range(20)
        ]

    def update(self, dt):
        self.timer += dt
        self.shake  = max(0, self.shake - dt * 8)
        for p in self.particles:
            p["x"]   += p["vx"] * dt
            p["y"]   += p["vy"] * dt
            p["vy"]  += 200 * dt
            p["life"] -= dt * 0.8
        if self.timer >= 4.0 and self.lives_left > 0:
            self.app.current = SearchingScreen(self.app, self.flower)

    def draw(self, surf):
        surf.fill(BG)
        flash = max(0, int(60 * math.sin(self.timer * 4) * max(0, 1 - self.timer * 0.8)))
        if flash > 0:
            s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            s.fill((*WARN, flash))
            surf.blit(s, (0, 0))
        for p in self.particles:
            if p["life"] > 0:
                pygame.draw.circle(surf, (*WARN, int(p["life"]*200)),
                                   (int(p["x"]), int(p["y"])), max(1, int(p["size"]*p["life"])))
        ox  = int(math.sin(self.timer * 12) * self.shake * 6)
        cx  = SCREEN_W//2 + ox
        sz  = 30
        pygame.draw.line(surf, WARN, (cx-sz, 70),  (cx+sz, 130), 8)
        pygame.draw.line(surf, WARN, (cx+sz, 70),  (cx-sz, 130), 8)
        draw_text_center(surf, "Wrong flower!",            self.f_big,  WARN,     cx, 160)
        draw_text_center(surf, f'That was "{self.scanned}"', self.f_med, TEXT_SEC, cx, 200)
        draw_text_center(surf, f"Looking for: {self.flower['name']}", self.f_small, TEXT_HINT, cx, 225)
        draw_text_center(surf, "Lives:", self.f_small, TEXT_SEC, SCREEN_W//2 - 70, 266)
        for i in range(3):
            col = WARN if i < self.lives_left else TEXT_HINT
            draw_heart(surf, SCREEN_W//2 + 10 + i*30, 258, 10, col)
        msg = "Keep scanning — you've got this!" if self.lives_left > 0 else "No lives left — returning to start..."
        draw_text_center(surf, msg, self.f_small, TEXT_HINT if self.lives_left > 0 else WARN,
                         SCREEN_W//2, 292)

    def on_tap(self):
        if self.lives_left > 0:
            self.app.current = SearchingScreen(self.app, self.flower)
        else:
            self.app.state.reset()
            self.app.current = InsertCardScreen(self.app)


# ── Screen 3b: Success ────────────────────────────────────────────────────────

class SuccessScreen(Screen):
    def __init__(self, app, flower, score, time_bonus):
        super().__init__(app)
        self.flower     = flower
        self.score      = score
        self.time_bonus = time_bonus
        self.timer      = 0.0
        self.confetti   = [
            {"x": random.randint(0, SCREEN_W), "y": random.randint(-SCREEN_H, 0),
             "vx": random.uniform(-30, 30), "vy": random.uniform(60, 140),
             "rot": random.uniform(0, 360), "rspd": random.uniform(-180, 180),
             "col": random.choice([ACCENT2, GOLD, ACCENT, PINK, WHITE]),
             "w": random.randint(6, 14), "h": random.randint(4, 8)}
            for _ in range(40)
        ]
        self.f_big   = load_font(34, bold=True)
        self.f_med   = load_font(20)
        self.f_small = load_font(14)
        self.f_tiny  = load_font(12)

    def update(self, dt):
        self.timer += dt
        for c in self.confetti:
            c["x"]   += c["vx"] * dt
            c["y"]   += c["vy"] * dt
            c["rot"] += c["rspd"] * dt
            if c["y"] > SCREEN_H + 20:
                c["y"] = -20
                c["x"] = random.randint(0, SCREEN_W)

    def draw(self, surf):
        surf.fill(BG)
        for c in self.confetti:
            cs = pygame.Surface((c["w"], c["h"]), pygame.SRCALPHA)
            cs.fill((*c["col"], 200))
            surf.blit(pygame.transform.rotate(cs, c["rot"]), (int(c["x"]), int(c["y"])))
        badge_x, badge_y = SCREEN_W - 55, 12
        draw_rounded_rect(surf, ACCENT2, (badge_x, badge_y, 44, 28), radius=14, alpha=230)
        draw_text_center(surf, "+1", load_font(18, bold=True), BG, badge_x+22, badge_y+14)
        scale    = 1.0 + 0.04 * math.sin(self.timer * 3)
        f_scaled = load_font(int(34*scale), bold=True)
        draw_text_center(surf, "MISSION",   f_scaled, ACCENT2, SCREEN_W//2, 80)
        draw_text_center(surf, "COMPLETE!", f_scaled, ACCENT2, SCREEN_W//2, 118)
        fc = self.flower
        draw_flower(surf, SCREEN_W//2 + 80, 100, fc["petals"], fc["emoji_color"], fc["center"], size=1.4)
        draw_text_center(surf, f'"{fc["name"]}"', self.f_med,   TEXT_PRI,  SCREEN_W//2, 168)
        draw_text_center(surf, fc["fact"],         self.f_small, TEXT_HINT, SCREEN_W//2, 193)
        draw_rounded_rect(surf, BG2, (SCREEN_W//2-130, 212, 260, 70), radius=12, alpha=200)
        draw_text_center(surf, "Score",            self.f_tiny,              TEXT_HINT, SCREEN_W//2, 228)
        draw_text_center(surf, f"{self.score} pts", load_font(28, bold=True), GOLD,      SCREEN_W//2, 258)
        draw_text(surf, f"+{self.time_bonus} time bonus", self.f_tiny, TEXT_HINT, SCREEN_W//2-48, 284)
        stars = self.app.state.stars_earned()
        for i in range(3):
            draw_star(surf, SCREEN_W//2 - 30 + i*30, 302, 9, GOLD if i < stars else TEXT_HINT)
        draw_text_center(surf, "Tap to continue", self.f_tiny, TEXT_HINT, SCREEN_W//2, 316)

    def on_tap(self):
        self.app.current = CollectionScreen(self.app)


# ── Screen: Time Up ───────────────────────────────────────────────────────────

class TimeUpScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.elapsed = 0.0

    def update(self, dt):
        self.elapsed += dt
        if self.elapsed >= 4.0:
            self.app.state.reset()
            self.app.current = InsertCardScreen(self.app)

    def draw(self, surf):
        surf.fill(BG)
        glow = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        glow.fill((200, 50, 50, 40))
        surf.blit(glow, (0, 0))
        draw_text_center(surf, "Time's Up!",     load_font(34, bold=True), WARN,     SCREEN_W//2, 100)
        name = self.app.state.current_flower["name"] if self.app.state.current_flower else ""
        draw_text_center(surf, f"The flower was: {name}", load_font(18), TEXT_PRI, SCREEN_W//2, 155)
        draw_text_center(surf, f"Score: {self.app.state.score}", load_font(22, bold=True), GOLD, SCREEN_W//2, 200)
        draw_text_center(surf, "Try again!",     load_font(15),            TEXT_SEC, SCREEN_W//2, 245)
        draw_text_center(surf, f"Returning in {max(0, int(4-self.elapsed))}s...",
                         load_font(12), TEXT_HINT, SCREEN_W//2, 285)


# ── Screen 4: Collection ──────────────────────────────────────────────────────

class CollectionScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.timer   = 0.0
        self.f_small = load_font(13)
        self.f_tiny  = load_font(11)

    def update(self, dt): self.timer += dt

    def draw(self, surf):
        surf.fill(BG)
        draw_rounded_rect(surf, BG2, (0, 0, SCREEN_W, 44), radius=0, alpha=200)
        draw_text_center(surf, "FLOWER COLLECTION", load_font(22, bold=True), ACCENT, SCREEN_W//2, 22)

        score         = self.app.state.score
        collected_ids = [f["id"] for f in self.app.state.collected]
        found         = len(collected_ids)
        total         = len(FLOWERS)

        draw_rounded_rect(surf, (50, 40, 20), (SCREEN_W-90, 52, 80, 38), radius=10, alpha=200)
        pygame.draw.rect(surf, GOLD, (SCREEN_W-90, 52, 80, 38), width=1, border_radius=10)
        draw_text_center(surf, "SCORE", self.f_tiny,  GOLD,  SCREEN_W-50, 65)
        draw_text_center(surf, str(score), self.f_small, WHITE, SCREEN_W-50, 80)

        draw_text(surf, f"{found}/{total} found", self.f_small, TEXT_SEC, 16, 56)
        bar_w = 140
        draw_rounded_rect(surf, BG2, (16, 76, bar_w, 10), radius=5)
        if total > 0:
            draw_rounded_rect(surf, ACCENT2, (16, 76, int(bar_w * found / total), 10), radius=5)

        cols, cell_w, cell_h, start_y = 5, (SCREEN_W - 20)//5, 90, 100
        for i, flower in enumerate(FLOWERS):
            col_i = i % cols
            row   = i // cols
            cx    = 10 + col_i * cell_w + cell_w // 2
            cy    = start_y + row * cell_h + cell_h // 2 - 10
            is_collected = flower["id"] in collected_ids
            bob   = math.sin(self.timer * 1.5 + i * 0.8) * 3 if is_collected else 0
            draw_rounded_rect(surf, BG2,
                              (10 + col_i*cell_w, start_y + row*cell_h, cell_w-6, cell_h-6),
                              radius=10, alpha=200 if is_collected else 80)
            if is_collected:
                draw_flower(surf, cx, int(cy + bob), flower["petals"],
                            flower["emoji_color"], flower["center"], size=1.1)
                draw_text_center(surf, flower["name"], self.f_tiny, TEXT_PRI, cx, cy+40)
            else:
                draw_flower(surf, cx, int(cy), flower["petals"],
                            TEXT_HINT, (60, 55, 80), size=1.1, alpha=60)
                draw_text_center(surf, "???", self.f_tiny, TEXT_HINT, cx, cy+40)

        draw_text_center(surf, "Tap to play again", self.f_tiny, TEXT_HINT, SCREEN_W//2, SCREEN_H - 8)

    def on_tap(self):
        self.app.state.reset()
        self.app.current = InsertCardScreen(self.app)


# ── App ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        pygame.init()
        self.screen_surf = pygame.display.set_mode((SCREEN_W*2, SCREEN_H*2), pygame.RESIZABLE)
        self.canvas      = pygame.Surface((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("FlowerFinder — Display V3")
        self.clock   = pygame.time.Clock()
        self.state   = GameState()
        self.camera  = Camera()
        self.current = InsertCardScreen(self)
        self._demo_screens = [
            ("insert",  lambda: InsertCardScreen(self)),
            ("search",  lambda: SearchingScreen(self, FLOWERS[0])),
            ("wrong",   lambda: WrongScanScreen(self, FLOWERS[0], "Rose", lives_left=2)),
            ("timeup",  lambda: TimeUpScreen(self)),
            ("success", lambda: SuccessScreen(self, FLOWERS[0], score=180, time_bonus=42)),
            ("collect", lambda: CollectionScreen(self)),
        ]
        self._demo_index = 0

    def run(self):
        prev_time = time.time()
        while True:
            now = time.time()
            dt  = min(now - prev_time, 0.05)
            prev_time = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.camera.stop(); pygame.quit(); sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.camera.stop(); pygame.quit(); sys.exit()
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_RIGHT):
                        self._load_demo(self._demo_index + 1)
                    if event.key == pygame.K_LEFT:
                        self._load_demo(self._demo_index - 1)
                    # Simulate hardware inputs
                    if event.key == pygame.K_r and hasattr(self.current, "on_rfid_card_read"):
                        self.current.on_rfid_card_read(FLOWERS[0])
                    if event.key == pygame.K_q and hasattr(self.current, "on_qr_scanned"):
                        self.current.on_qr_scanned(FLOWERS[0]["name"])
                    if event.key == pygame.K_w and hasattr(self.current, "on_qr_scanned"):
                        self.current.on_qr_scanned("Rose")
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if hasattr(self.current, "on_tap"):
                        self.current.on_tap()
                    else:
                        self._load_demo(self._demo_index + 1)

            self.current.update(dt)
            self.current.draw(self.canvas)

            # Scale canvas to window
            w, h  = self.screen_surf.get_size()
            scale = min(w / SCREEN_W, h / SCREEN_H)
            sw, sh = int(SCREEN_W * scale), int(SCREEN_H * scale)
            scaled = pygame.transform.scale(self.canvas, (sw, sh))
            self.screen_surf.fill((5, 5, 15))
            self.screen_surf.blit(scaled, ((w-sw)//2, (h-sh)//2))

            name  = self._demo_screens[self._demo_index][0]
            label = pygame.font.SysFont("Arial", 12).render(
                f"Screen: {name}  |  ← → navigate  |  R=RFID  Q=QR-correct  W=QR-wrong  |  ESC quit",
                True, (80, 75, 100))
            self.screen_surf.blit(label, (8, 4))

            pygame.display.flip()
            self.clock.tick(FPS)

    def _load_demo(self, idx):
        self._demo_index = idx % len(self._demo_screens)
        _, factory = self._demo_screens[self._demo_index]
        self.current = factory()


if __name__ == "__main__":
    App().run()

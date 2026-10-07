# ============================================================
# ЛЧМ + ChaCha20 | 1×1 км
# Полная версия + отражение сигнала от запретных зон
# ============================================================
import pygame
import math
import random
import sys
import json
from collections import deque

# -------------------- Экран --------------------
WIDTH, HEIGHT = 1280, 840
FPS = 60

# -------------------- Мир --------------------
WORLD_W, WORLD_H = 1000.0, 1000.0
BASE_SCALE = min((WIDTH - 80) / WORLD_W, (HEIGHT - 100) / WORLD_H)

zoom = 1.0
cam_x, cam_y = WORLD_W / 2, WORLD_H / 2
ZOOM_MIN, ZOOM_MAX = 0.3, 5.0

def world_to_screen(wx, wy):
    sx = WIDTH / 2 + (wx - cam_x) * BASE_SCALE * zoom
    sy = HEIGHT / 2 + (wy - cam_y) * BASE_SCALE * zoom
    return int(sx), int(sy)

def screen_to_world(sx, sy):
    wx = cam_x + (sx - WIDTH / 2) / (BASE_SCALE * zoom)
    wy = cam_y + (sy - HEIGHT / 2) / (BASE_SCALE * zoom)
    return wx, wy

# -------------------- Цвета --------------------
BG_COLOR     = (15, 18, 26)
GRID_COLOR   = (30, 38, 52)
TEXT_COLOR   = (220, 230, 240)
ACCENT_COLOR = (80, 180, 255)
PANEL_BG     = (8, 12, 20, 225)
NOGO_COLOR   = (180, 40, 40, 90)
SAFE_COLOR   = (60, 200, 90)
WP_COLOR     = (255, 200, 60)

AGENT_COLORS = [(100, 160, 220), (220, 100, 160), (160, 220, 100), (230, 180, 90)]
AGENT_TX_COLOR = (255, 120, 60)
AGENT_RX_COLOR = (80, 230, 120)
WAVE_COLOR     = (100, 200, 255)
REFLECT_COLOR  = (180, 140, 255)   # фиолетовый — отражённая волна

# -------------------- Физика --------------------
AGENT_RADIUS_M    = 11.0
WAVE_SPEED_M      = 85.0
WAVE_MAX_RADIUS_M = 480.0
GREEN_FLASH_SEC   = 1.6
TX_PULSE_INTERVAL = 2.0
AGENT_SPEED_MIN   = 7.0
AGENT_SPEED_MAX   = 16.0
BASE_SCENARIO_SPEED = 11.0

TX_POWER_DRAIN = 4.5
RX_DRAIN       = 0.15
IDLE_DRAIN     = 0.008
MOVE_DRAIN     = 0.025

VECTOR_BASE_LEN_M = 36.0
VECTOR_SPEED_GAIN = 1.5
VECTOR_HEAD_LEN_M = 12.0
VECTOR_HEAD_WID_M = 7.0
VECTOR_COLOR = (255, 50, 50)
VECTOR_OUTLINE = (0, 0, 0)
VECTOR_LINE_WIDTH = 3

SAFETY_MARGIN = 38.0

# -------------------- Отражение --------------------
REFLECT_COEFF   = 0.55      # < 1 → без усиления
MAX_BOUNCES     = 1
reflect_enabled = True

# -------------------- Состояние --------------------
show_vectors = True
show_heatmap = True
show_log = True
show_graph = True
show_results = True
speed_mult = 1.0
scenario_name = "случайный"
formation_mode = False
waypoint_mode = False
sim_time = 0.0

event_log = deque(maxlen=60)
snr_history = deque(maxlen=350)

dragging = False
drag_start = (0, 0)
cam_start = (0.0, 0.0)
SAVE_FILE = "scenario.json"

NOGO_ZONES = [
    (380, 380, 620, 480),
    (100, 700, 280, 880),
    (720, 100, 900, 250),
]


# ============================================================
# Геометрия / безопасность
# ============================================================
def expand_zone(x1, y1, x2, y2, margin=SAFETY_MARGIN):
    return (x1 - margin, y1 - margin, x2 + margin, y2 + margin)


def point_in_rect(x, y, x1, y1, x2, y2):
    return x1 <= x <= x2 and y1 <= y <= y2


def point_in_nogo(x, y, margin=0.0):
    for x1, y1, x2, y2 in NOGO_ZONES:
        if point_in_rect(x, y, x1 - margin, y1 - margin, x2 + margin, y2 + margin):
            return True
    return False


def is_safe(x, y, margin=SAFETY_MARGIN):
    if x < 35 or x > WORLD_W - 35 or y < 35 or y > WORLD_H - 35:
        return False
    return not point_in_nogo(x, y, margin)


def dist_to_zone(x, y, x1, y1, x2, y2):
    dx = max(x1 - x, 0, x - x2)
    dy = max(y1 - y, 0, y - y2)
    return math.hypot(dx, dy)


def repulsive_force(x, y):
    fx, fy = 0.0, 0.0
    for x1, y1, x2, y2 in NOGO_ZONES:
        ex1, ey1, ex2, ey2 = expand_zone(x1, y1, x2, y2)
        d = dist_to_zone(x, y, ex1, ey1, ex2, ey2)
        if d < SAFETY_MARGIN + 10:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy) + 1e-6
            strength = max(0.0, (SAFETY_MARGIN + 10 - d) / SAFETY_MARGIN) * 22.0
            fx += (dx / dist) * strength
            fy += (dy / dist) * strength
    return fx, fy


def push_out_of_zones(x, y, margin=SAFETY_MARGIN):
    for _ in range(6):
        moved = False
        for x1, y1, x2, y2 in NOGO_ZONES:
            ex1, ey1, ex2, ey2 = expand_zone(x1, y1, x2, y2, margin)
            if point_in_rect(x, y, ex1, ey1, ex2, ey2):
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                dx, dy = x - cx, y - cy
                dist = math.hypot(dx, dy) + 1e-6
                hw = (x2 - x1) / 2.0 + margin + 4
                hh = (y2 - y1) / 2.0 + margin + 4
                scale_x = hw / max(abs(dx), 1e-6)
                scale_y = hh / max(abs(dy), 1e-6)
                scale = min(scale_x, scale_y)
                if dist * scale < dist + 1:
                    scale = (dist + margin * 0.4) / dist
                x = cx + dx * scale
                y = cy + dy * scale
                moved = True
        if not moved:
            break
    x = max(40.0, min(WORLD_W - 40.0, x))
    y = max(40.0, min(WORLD_H - 40.0, y))
    return x, y


def make_safe_path(ax, ay, bx, by, num_points=16):
    dist = math.hypot(bx - ax, by - ay)
    n = max(10, min(22, int(dist / 45) + 8))
    n = max(n, num_points)
    path = []
    for i in range(1, n + 1):
        t = i / n
        x = ax + (bx - ax) * t
        y = ay + (by - ay) * t
        x, y = push_out_of_zones(x, y)
        path.append((x, y))
    return path


def build_avoiding_route(start_x, start_y, agent_id):
    candidates = []
    for x in range(70, 931, 100):
        candidates.append((float(x), 70.0))
        candidates.append((float(x), 930.0))
    for y in range(170, 861, 100):
        candidates.append((70.0, float(y)))
        candidates.append((930.0, float(y)))

    extra = [
        (200, 200), (500, 150), (800, 200),
        (180, 500), (820, 500),
        (200, 800), (500, 850), (800, 800),
        (350, 300), (650, 300), (350, 700), (650, 700),
    ]
    candidates.extend(extra)

    safe_pts = [p for p in candidates if is_safe(p[0], p[1])]
    if len(safe_pts) < 6:
        safe_pts = [(70, 70), (930, 70), (930, 930), (70, 930)]

    rng = random.Random(agent_id * 41 + 3)
    cx, cy = WORLD_W / 2, WORLD_H / 2
    safe_pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))

    step = max(1, len(safe_pts) // 9)
    offset = rng.randint(0, max(0, step - 1))
    chosen = []
    for i in range(offset, len(safe_pts), step):
        chosen.append(safe_pts[i])
        if len(chosen) >= 9:
            break
    if len(chosen) < 4:
        chosen = safe_pts[::max(1, len(safe_pts) // 8)][:9]

    raw = list(chosen)
    if math.hypot(raw[0][0] - start_x, raw[0][1] - start_y) > 80:
        raw.insert(0, (start_x, start_y))
    raw.append(raw[0])

    route = [raw[0]]
    for i in range(len(raw) - 1):
        a = raw[i]
        b = raw[i + 1]
        seg = make_safe_path(a[0], a[1], b[0], b[1])
        route.extend(seg)

    if len(route) > 1 and math.hypot(route[-1][0] - route[0][0],
                                     route[-1][1] - route[0][1]) < 10:
        route.pop()

    cleaned = [route[0]]
    for p in route[1:]:
        if math.hypot(p[0] - cleaned[-1][0], p[1] - cleaned[-1][1]) > 10:
            cleaned.append(p)
    return cleaned


def random_safe_position(existing=None, min_dist=90.0):
    existing = existing or []
    for _ in range(100):
        x = random.uniform(80, WORLD_W - 80)
        y = random.uniform(80, WORLD_H - 80)
        if not is_safe(x, y):
            continue
        if all(math.hypot(x - ex, y - ey) >= min_dist for ex, ey in existing):
            return x, y
    return random.uniform(100, 300), random.uniform(100, 300)


def respawn_agents(agents):
    placed = []
    for a in agents:
        x, y = random_safe_position(placed, min_dist=90.0)
        a.x, a.y = x, y
        placed.append((x, y))
        sp = random.uniform(AGENT_SPEED_MIN, AGENT_SPEED_MAX)
        ang = random.uniform(0, 2 * math.pi)
        a.vx = sp * math.cos(ang)
        a.vy = sp * math.sin(ang)
        a.reset_rx()
        a.known_positions.clear()
        if waypoint_mode:
            a.rebuild_route()
    event_log.appendleft((sim_time, "Координаты аппаратов перегенерированы (N)"))


# ============================================================
# Абонент
# ============================================================
class Agent:
    def __init__(self, aid, x, y, color):
        self.id = aid
        self.x, self.y = float(x), float(y)
        sp = random.uniform(AGENT_SPEED_MIN, AGENT_SPEED_MAX)
        ang = random.uniform(0, 2 * math.pi)
        self.vx = sp * math.cos(ang)
        self.vy = sp * math.sin(ang)
        self.color = color
        self.rx_timer = 0.0
        self.tx_active = False
        self.moving = True

        self.received = False
        self.decrypted = False
        self.last_snr = 0.0
        self.last_dist = 0.0
        self.last_delivery = None
        self.last_decoded_id = None
        self.last_decoded_x = None
        self.last_decoded_y = None
        self.last_decoded_ok = False

        self.battery = 100.0
        self.form_dx = 0.0
        self.form_dy = 0.0
        self.wp_list = []
        self.wp_idx = 0
        self.known_positions = {}

    def rebuild_route(self):
        self.wp_list = build_avoiding_route(self.x, self.y, self.id)
        self.wp_idx = 0

    def update(self, dt, leader=None):
        drain = IDLE_DRAIN * dt
        if self.moving:
            drain += MOVE_DRAIN * dt
        if self.tx_active:
            drain += 0.4 * dt
        self.battery = max(0.0, self.battery - drain)
        if self.battery <= 0.0:
            self.moving = False
            self.tx_active = False

        if not self.moving or self.battery <= 0:
            if self.rx_timer > 0:
                self.rx_timer -= dt
            return

        desired_vx, desired_vy = self.vx, self.vy

        if formation_mode and leader and self.id != leader.id:
            tx = leader.x + self.form_dx
            ty = leader.y + self.form_dy
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            if dist > 3.0:
                sp = min(14.0, dist * 0.9)
                desired_vx = dx / dist * sp
                desired_vy = dy / dist * sp
            else:
                desired_vx = leader.vx * 0.95
                desired_vy = leader.vy * 0.95

        elif waypoint_mode and self.wp_list:
            wx, wy = self.wp_list[self.wp_idx]
            dx, dy = wx - self.x, wy - self.y
            dist = math.hypot(dx, dy)
            if dist < 22.0:
                self.wp_idx = (self.wp_idx + 1) % len(self.wp_list)
            else:
                sp = 11.0
                desired_vx = dx / dist * sp
                desired_vy = dy / dist * sp

        rx, ry = repulsive_force(self.x, self.y)
        desired_vx += rx
        desired_vy += ry

        self.vx = self.vx * 0.65 + desired_vx * 0.35
        self.vy = self.vy * 0.65 + desired_vy * 0.35

        sp = math.hypot(self.vx, self.vy)
        if sp > 16.0:
            self.vx = self.vx / sp * 16.0
            self.vy = self.vy / sp * 16.0

        self.x += self.vx * speed_mult * dt
        self.y += self.vy * speed_mult * dt

        if self.x < AGENT_RADIUS_M or self.x > WORLD_W - AGENT_RADIUS_M:
            self.vx *= -1
            self.x = max(AGENT_RADIUS_M, min(WORLD_W - AGENT_RADIUS_M, self.x))
        if self.y < AGENT_RADIUS_M or self.y > WORLD_H - AGENT_RADIUS_M:
            self.vy *= -1
            self.y = max(AGENT_RADIUS_M, min(WORLD_H - AGENT_RADIUS_M, self.y))

        for x1, y1, x2, y2 in NOGO_ZONES:
            if point_in_rect(self.x, self.y,
                             x1 - AGENT_RADIUS_M, y1 - AGENT_RADIUS_M,
                             x2 + AGENT_RADIUS_M, y2 + AGENT_RADIUS_M):
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                dx, dy = self.x - cx, self.y - cy
                d = math.hypot(dx, dy) + 1e-6
                push = max(x2 - x1, y2 - y1) / 2 + AGENT_RADIUS_M + SAFETY_MARGIN * 0.5
                self.x = cx + dx / d * push
                self.y = cy + dy / d * push
                self.vx *= -0.35
                self.vy *= -0.35

        if self.rx_timer > 0:
            self.rx_timer -= dt

    def current_color(self):
        if self.battery < 8:
            return (80, 30, 30)
        if self.tx_active:
            return AGENT_TX_COLOR
        if self.rx_timer > 0:
            return AGENT_RX_COLOR
        return self.color

    def draw_circle(self, screen):
        sx, sy = world_to_screen(self.x, self.y)
        r = max(2, int(AGENT_RADIUS_M * BASE_SCALE * zoom))
        if self.rx_timer > 0:
            gr = r + 5 + int(2 * math.sin(pygame.time.get_ticks() / 70))
            g = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
            pygame.draw.circle(g, (*AGENT_RX_COLOR, 75), (gr, gr), gr)
            screen.blit(g, (sx - gr, sy - gr))
        pygame.draw.circle(screen, self.current_color(), (sx, sy), r)
        pygame.draw.circle(screen, (255, 255, 255), (sx, sy), r, 1)
        if r > 4:
            bw = r * 2 - 2
            bh = 3
            bx, by = sx - bw // 2, sy + r + 3
            pygame.draw.rect(screen, (40, 40, 40), (bx, by, bw, bh))
            fill = int(bw * self.battery / 100)
            col = (80, 220, 100) if self.battery > 30 else (220, 80, 60)
            pygame.draw.rect(screen, col, (bx, by, fill, bh))

    def draw_velocity_vector(self, screen):
        sp = math.hypot(self.vx, self.vy)
        if sp < 1e-5:
            return
        ux, uy = self.vx / sp, self.vy / sp
        length = VECTOR_BASE_LEN_M + sp * speed_mult * VECTOR_SPEED_GAIN
        x0 = self.x + ux * AGENT_RADIUS_M
        y0 = self.y + uy * AGENT_RADIUS_M
        x1 = self.x + ux * (AGENT_RADIUS_M + length)
        y1 = self.y + uy * (AGENT_RADIUS_M + length)
        sx0, sy0 = world_to_screen(x0, y0)
        sx1, sy1 = world_to_screen(x1, y1)
        pygame.draw.line(screen, VECTOR_OUTLINE, (sx0, sy0), (sx1, sy1), VECTOR_LINE_WIDTH + 3)
        pygame.draw.line(screen, VECTOR_COLOR, (sx0, sy0), (sx1, sy1), VECTOR_LINE_WIDTH)
        hl = VECTOR_HEAD_LEN_M * BASE_SCALE * zoom
        hw = VECTOR_HEAD_WID_M * BASE_SCALE * zoom
        px, py = -uy, ux
        tip = (sx1, sy1)
        bl = (int(sx1 - ux * hl + px * hw), int(sy1 - uy * hl + py * hw))
        br = (int(sx1 - ux * hl - px * hw), int(sy1 - uy * hl - py * hw))
        pygame.draw.polygon(screen, VECTOR_OUTLINE, [tip, bl, br])
        pygame.draw.polygon(screen, VECTOR_COLOR, [tip, bl, br])

    def draw_label(self, screen, font):
        sx, sy = world_to_screen(self.x, self.y)
        label = font.render(f"A{self.id}", True, (8, 8, 8))
        w, h = label.get_size()
        bg = pygame.Surface((w + 5, h + 2), pygame.SRCALPHA)
        bg.fill((255, 255, 255, 200))
        screen.blit(bg, (sx - w // 2 - 2, sy - h // 2 - 1))
        screen.blit(label, (sx - w // 2, sy - h // 2))

    def set_velocity(self, vx, vy):
        self.vx, self.vy = vx, vy

    def reset_rx(self):
        self.received = False
        self.decrypted = False
        self.last_snr = 0.0
        self.last_dist = 0.0
        self.last_delivery = None
        self.last_decoded_id = None
        self.last_decoded_x = None
        self.last_decoded_y = None
        self.last_decoded_ok = False

    def to_dict(self):
        return {"id": self.id, "x": self.x, "y": self.y,
                "vx": self.vx, "vy": self.vy, "moving": self.moving,
                "battery": self.battery}

    def from_dict(self, d):
        self.x, self.y = d["x"], d["y"]
        self.vx, self.vy = d["vx"], d["vy"]
        self.moving = d.get("moving", True)
        self.battery = d.get("battery", 100.0)


# ============================================================
# Волна (с отражением)
# ============================================================
class Wave:
    def __init__(self, x, y, tx_id, tx_time, payload_x, payload_y,
                 strength=1.0, bounce=0):
        self.x, self.y = x, y
        self.tx_id = tx_id
        self.tx_time = tx_time
        self.payload_x = payload_x
        self.payload_y = payload_y
        self.radius = 0.0
        self.alive = True
        self.hit = {tx_id} if bounce == 0 else set()
        self.strength = max(0.05, strength)
        self.bounce = bounce
        self.reflected_from = set()

    def attenuation_at(self, dist):
        if dist < 1:
            return self.strength
        return self.strength * math.exp(-dist / 270.0) * max(0.0, 1.0 - dist / WAVE_MAX_RADIUS_M)

    def try_reflect(self, new_waves):
        if not reflect_enabled or self.bounce >= MAX_BOUNCES:
            return

        for zi, (zx1, zy1, zx2, zy2) in enumerate(NOGO_ZONES):
            if zi in self.reflected_from:
                continue

            cx = max(zx1, min(self.x, zx2))
            cy = max(zy1, min(self.y, zy2))
            dist = math.hypot(self.x - cx, self.y - cy)

            if self.radius >= dist and self.radius - WAVE_SPEED_M * 0.05 <= dist + 8:
                incident = self.attenuation_at(dist)
                reflected_str = incident * REFLECT_COEFF

                if reflected_str < 0.08:
                    self.reflected_from.add(zi)
                    continue

                if dist < 1e-3:
                    rx, ry = cx, cy
                else:
                    dx, dy = self.x - cx, self.y - cy
                    d = math.hypot(dx, dy) + 1e-6
                    rx = cx + dx / d * 6
                    ry = cy + dy / d * 6

                new_waves.append(Wave(
                    rx, ry,
                    self.tx_id, self.tx_time,
                    self.payload_x, self.payload_y,
                    strength=reflected_str,
                    bounce=self.bounce + 1
                ))
                self.reflected_from.add(zi)

                event_log.appendleft(
                    (sim_time,
                     f"отражение от зоны #{zi+1}  str={reflected_str:.2f}  "
                     f"в ({rx:.0f},{ry:.0f})")
                )

    def update(self, dt, agents, new_waves):
        self.radius += WAVE_SPEED_M * dt
        self.try_reflect(new_waves)

        for a in agents:
            if a.id in self.hit:
                continue
            d = math.hypot(a.x - self.x, a.y - self.y)
            if d <= self.radius:
                self.hit.add(a.id)
                local_str = self.attenuation_at(d)
                if local_str < 0.06:
                    continue

                a.rx_timer = GREEN_FLASH_SEC
                a.received = True
                a.last_dist = d
                a.battery = max(0.0, a.battery - RX_DRAIN)

                snr = max(0.0, 31.0 - 20 * math.log10(max(d, 1.0)) - d * 0.011)
                snr *= local_str
                a.last_snr = snr
                p = min(0.97, 0.28 + snr / 34.0)
                success = random.random() < p
                a.decrypted = success
                a.last_decoded_ok = success

                src = f"A{self.tx_id}" + ("~" if self.bounce > 0 else "")
                if success:
                    dec_x, dec_y = self.payload_x, self.payload_y
                    a.last_delivery = sim_time - self.tx_time
                    a.known_positions[self.tx_id] = (dec_x, dec_y)
                    a.last_decoded_id = self.tx_id
                    a.last_decoded_x = dec_x
                    a.last_decoded_y = dec_y
                    event_log.appendleft(
                        (sim_time,
                         f"A{a.id} ← {src}  ({dec_x:6.1f},{dec_y:6.1f})  "
                         f"SNR={snr:4.1f}  {a.last_delivery*1000:.0f}мс  OK"
                         + ("  [отраж]" if self.bounce else ""))
                    )
                else:
                    noise = 80 + random.uniform(0, 120)
                    angle = random.uniform(0, 2 * math.pi)
                    dec_x = self.payload_x + noise * math.cos(angle)
                    dec_y = self.payload_y + noise * math.sin(angle)
                    if random.random() < 0.35:
                        dec_x = random.uniform(-50, WORLD_W + 50)
                        dec_y = random.uniform(-50, WORLD_H + 50)
                    a.last_delivery = None
                    a.last_decoded_id = self.tx_id
                    a.last_decoded_x = dec_x
                    a.last_decoded_y = dec_y
                    event_log.appendleft(
                        (sim_time,
                         f"A{a.id} ← {src}  ({dec_x:6.1f},{dec_y:6.1f})  "
                         f"SNR={snr:4.1f}  МУСОР"
                         + ("  [отраж]" if self.bounce else ""))
                    )

        max_r = WAVE_MAX_RADIUS_M * (0.7 if self.bounce else 1.0)
        if self.radius > max_r:
            self.alive = False

    def signal_at(self, wx, wy):
        d = math.hypot(wx - self.x, wy - self.y)
        if d > self.radius or d < 1:
            return 0.0
        return self.attenuation_at(d) * max(0.0, 1.0 - d / self.radius)

    def draw(self, screen):
        base_alpha = 190 if self.bounce == 0 else 120
        alpha = max(0, int(base_alpha * (1 - self.radius / WAVE_MAX_RADIUS_M) * min(1.0, self.strength)))
        sx, sy = world_to_screen(self.x, self.y)
        r = int(self.radius * BASE_SCALE * zoom)
        if r < 2:
            return
        col = WAVE_COLOR if self.bounce == 0 else REFLECT_COLOR
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(s, (*col, alpha), (sx, sy), r, 2)
        screen.blit(s, (0, 0))


# ============================================================
# Отрисовка
# ============================================================
def draw_dashed_rect(screen, color, rect, dash=8, gap=6, width=2):
    x, y, w, h = rect
    cx = x
    while cx < x + w:
        x2 = min(cx + dash, x + w)
        pygame.draw.line(screen, color, (cx, y), (x2, y), width)
        cx += dash + gap
    cx = x
    while cx < x + w:
        x2 = min(cx + dash, x + w)
        pygame.draw.line(screen, color, (cx, y + h), (x2, y + h), width)
        cx += dash + gap
    cy = y
    while cy < y + h:
        y2 = min(cy + dash, y + h)
        pygame.draw.line(screen, color, (x, cy), (x, y2), width)
        cy += dash + gap
    cy = y
    while cy < y + h:
        y2 = min(cy + dash, y + h)
        pygame.draw.line(screen, color, (x + w, cy), (x + w, y2), width)
        cy += dash + gap


def draw_nogo_zones(screen):
    for x1, y1, x2, y2 in NOGO_ZONES:
        sx1, sy1 = world_to_screen(x1, y1)
        sx2, sy2 = world_to_screen(x2, y2)
        w, h = max(2, sx2 - sx1), max(2, sy2 - sy1)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill(NOGO_COLOR)
        for i in range(-h, w, 12):
            pygame.draw.line(s, (200, 60, 60, 120), (i, 0), (i + h, h), 1)
        screen.blit(s, (sx1, sy1))
        pygame.draw.rect(screen, (220, 70, 70), (sx1, sy1, w, h), 1)

        ex1, ey1, ex2, ey2 = expand_zone(x1, y1, x2, y2)
        esx1, esy1 = world_to_screen(ex1, ey1)
        esx2, esy2 = world_to_screen(ex2, ey2)
        ew, eh = max(2, esx2 - esx1), max(2, esy2 - esy1)
        draw_dashed_rect(screen, SAFE_COLOR, (esx1, esy1, ew, eh), dash=10, gap=7, width=2)


def draw_waypoints(screen, agents):
    if not waypoint_mode:
        return
    for a in agents:
        if not a.wp_list or len(a.wp_list) < 2:
            continue
        pts = [world_to_screen(wx, wy) for wx, wy in a.wp_list]
        pygame.draw.lines(screen, (WP_COLOR[0], WP_COLOR[1], WP_COLOR[2], 160), True, pts, 2)
        for i, (sx, sy) in enumerate(pts):
            col = (255, 240, 100) if i == a.wp_idx else (160, 130, 40)
            pygame.draw.circle(screen, col, (sx, sy), 4)
            pygame.draw.circle(screen, (20, 20, 20), (sx, sy), 4, 1)


def draw_heatmap(screen, waves):
    if not waves:
        return
    cols, rows = 46, 34
    cw, ch = WIDTH // cols, HEIGHT // rows
    s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for iy in range(rows):
        for ix in range(cols):
            sx = ix * cw + cw // 2
            sy = iy * ch + ch // 2
            wx, wy = screen_to_world(sx, sy)
            if not (0 <= wx <= WORLD_W and 0 <= wy <= WORLD_H):
                continue
            strength = max((w.signal_at(wx, wy) for w in waves), default=0.0)
            if strength < 0.025:
                continue
            t = min(1.0, strength * 1.5)
            if t < 0.25:
                r, g, b = 0, int(60 + t * 500), 180
            elif t < 0.5:
                r, g, b = 0, 200, int(180 - (t - 0.25) * 400)
            elif t < 0.75:
                r, g, b = int((t - 0.5) * 700), 220, 0
            else:
                r, g, b = 255, int(200 - (t - 0.75) * 500), 0
            pygame.draw.rect(s, (r, g, b, int(35 + t * 85)),
                             (ix * cw, iy * ch, cw + 1, ch + 1))
    screen.blit(s, (0, 0))


def draw_results_panel(screen, agents, font, small):
    if not show_results:
        return
    pw, ph = 290, 235
    px, py = WIDTH - pw - 8, 72
    s = pygame.Surface((pw, ph), pygame.SRCALPHA)
    s.fill(PANEL_BG)
    pygame.draw.rect(s, (50, 80, 120), (0, 0, pw, ph), 1)
    s.blit(font.render("Декодирование координат", True, ACCENT_COLOR), (8, 5))
    s.blit(small.render("ID  Статус   от     X       Y", True, (140, 160, 180)), (8, 26))
    pygame.draw.line(s, (40, 60, 90), (6, 42), (pw - 6, 42), 1)
    y = 48
    for a in agents:
        s.blit(small.render(f"A{a.id}", True, a.color), (8, y))
        if not a.received:
            s.blit(small.render("—", True, (90, 100, 110)), (40, y))
            s.blit(small.render("нет данных", True, (90, 100, 110)), (90, y))
        else:
            st, col = ("OK", (80, 230, 120)) if a.last_decoded_ok else ("МУСОР", (255, 100, 90))
            s.blit(small.render(st, True, col), (38, y))
            src = f"A{a.last_decoded_id}" if a.last_decoded_id else "?"
            s.blit(small.render(src, True, (200, 210, 220)), (95, y))
            if a.last_decoded_x is not None:
                s.blit(small.render(f"{a.last_decoded_x:6.1f}", True, (200, 210, 220)), (145, y))
                s.blit(small.render(f"{a.last_decoded_y:6.1f}", True, (200, 210, 220)), (205, y))
        y += 20
    y += 6
    s.blit(small.render("Известные позиции (OK):", True, (140, 160, 180)), (8, y))
    y += 16
    for a in agents:
        if a.known_positions:
            parts = [f"A{k}:({v[0]:.0f},{v[1]:.0f})" for k, v in a.known_positions.items()]
            txt = f"A{a.id}→ " + " ".join(parts)
            s.blit(small.render(txt[:42], True, (160, 190, 160)), (8, y))
            y += 14
    screen.blit(s, (px, py))


def draw_log_panel(screen, font, small):
    if not show_log:
        return
    pw, ph = 520, 160
    px, py = 8, HEIGHT - ph - 8
    s = pygame.Surface((pw, ph), pygame.SRCALPHA)
    s.fill(PANEL_BG)
    pygame.draw.rect(s, (50, 80, 120), (0, 0, pw, ph), 1)
    s.blit(font.render("Журнал декодирования", True, ACCENT_COLOR), (8, 4))
    y = 24
    for t, txt in list(event_log)[:8]:
        if "МУСОР" in txt:
            col = (255, 140, 120)
        elif "OK" in txt:
            col = (140, 230, 160)
        elif "отраж" in txt:
            col = (200, 160, 255)
        else:
            col = (185, 195, 210)
        s.blit(small.render(f"[{t:6.1f}] {txt}", True, col), (8, y))
        y += 15
    screen.blit(s, (px, py))


def draw_graph_panel(screen, font, small):
    if not show_graph or len(snr_history) < 3:
        return
    pw, ph = 280, 125
    px, py = WIDTH - pw - 8, HEIGHT - ph - 8
    s = pygame.Surface((pw, ph), pygame.SRCALPHA)
    s.fill(PANEL_BG)
    pygame.draw.rect(s, (50, 80, 120), (0, 0, pw, ph), 1)
    s.blit(font.render("SNR", True, ACCENT_COLOR), (8, 3))
    data = list(snr_history)
    n = len(data)
    max_snr = max(1.0, max(d[1] for d in data))
    gx, gy, gw, gh = 10, 22, pw - 20, ph - 34
    pygame.draw.line(s, (50, 70, 100), (gx, gy + gh), (gx + gw, gy + gh), 1)
    pts = []
    for i, (_, snr, _) in enumerate(data):
        x = gx + int(i / (n - 1) * gw)
        y = gy + gh - int(snr / max_snr * gh)
        pts.append((x, y))
    if len(pts) > 1:
        pygame.draw.lines(s, (80, 200, 255), False, pts, 2)
    screen.blit(s, (px, py))


def save_scenario(agents, current_tx_idx):
    data = {
        "agents": [a.to_dict() for a in agents],
        "tx_idx": current_tx_idx,
        "speed_mult": speed_mult,
        "scenario": scenario_name,
        "cam_x": cam_x, "cam_y": cam_y, "zoom": zoom,
        "formation": formation_mode, "waypoints": waypoint_mode,
        "reflect": reflect_enabled,
    }
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    event_log.appendleft((sim_time, f"Сохранено → {SAVE_FILE}"))


def load_scenario(agents):
    global speed_mult, scenario_name, cam_x, cam_y, zoom
    global formation_mode, waypoint_mode, current_tx_idx, reflect_enabled
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for a, d in zip(agents, data["agents"]):
            a.from_dict(d)
        current_tx_idx = data.get("tx_idx", 0)
        speed_mult = data.get("speed_mult", 1.0)
        scenario_name = data.get("scenario", "загружен")
        cam_x = data.get("cam_x", WORLD_W / 2)
        cam_y = data.get("cam_y", WORLD_H / 2)
        zoom = data.get("zoom", 1.0)
        formation_mode = data.get("formation", False)
        waypoint_mode = data.get("waypoints", False)
        reflect_enabled = data.get("reflect", True)
        if waypoint_mode:
            for a in agents:
                a.rebuild_route()
        event_log.appendleft((sim_time, f"Загружено ← {SAVE_FILE}"))
        return current_tx_idx
    except Exception as e:
        event_log.appendleft((sim_time, f"Ошибка: {e}"))
        return 0


# ============================================================
# Главный цикл
# ============================================================
def main():
    global zoom, cam_x, cam_y, dragging, drag_start, cam_start
    global show_vectors, show_heatmap, show_log, show_graph, show_results
    global speed_mult, scenario_name, sim_time, current_tx_idx
    global formation_mode, waypoint_mode, reflect_enabled

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("ЛЧМ + ChaCha20 | 1×1 км | отражение сигнала")
    clock = pygame.time.Clock()

    font  = pygame.font.SysFont("Arial", 13, bold=True)
    small = pygame.font.SysFont("Consolas", 12)
    hud   = pygame.font.SysFont("Consolas", 12)
    title = pygame.font.SysFont("Arial", 15, bold=True)

    agents = [
        Agent(1, 180, 180, AGENT_COLORS[0]),
        Agent(2, 820, 180, AGENT_COLORS[1]),
        Agent(3, 820, 820, AGENT_COLORS[2]),
        Agent(4, 180, 820, AGENT_COLORS[3]),
    ]
    agents[1].form_dx, agents[1].form_dy = 120, 0
    agents[2].form_dx, agents[2].form_dy = 120, 120
    agents[3].form_dx, agents[3].form_dy = 0, 120

    current_tx_idx = 0
    transmitting = False
    tx_pulse_timer = 0.0
    waves = []

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        sim_time += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    transmitting = not transmitting
                    if transmitting:
                        tx_pulse_timer = TX_PULSE_INTERVAL
                        for a in agents:
                            a.reset_rx()
                elif event.key == pygame.K_m:
                    st = not agents[0].moving
                    for a in agents:
                        a.moving = st
                elif event.key == pygame.K_v:
                    show_vectors = not show_vectors
                elif event.key == pygame.K_h:
                    show_heatmap = not show_heatmap
                elif event.key == pygame.K_j:
                    show_log = not show_log
                elif event.key == pygame.K_g:
                    show_graph = not show_graph
                elif event.key == pygame.K_p:
                    show_results = not show_results
                elif event.key == pygame.K_f:
                    formation_mode = not formation_mode
                    if formation_mode:
                        waypoint_mode = False
                        leader = agents[0]
                        for a in agents[1:]:
                            a.form_dx = a.x - leader.x
                            a.form_dy = a.y - leader.y
                        event_log.appendleft((sim_time, "Строй ВКЛ"))
                    else:
                        event_log.appendleft((sim_time, "Строй ВЫКЛ"))
                elif event.key == pygame.K_w:
                    waypoint_mode = not waypoint_mode
                    if waypoint_mode:
                        formation_mode = False
                        for a in agents:
                            a.rebuild_route()
                        event_log.appendleft((sim_time, f"Маршруты ВКЛ (буфер {SAFETY_MARGIN:.0f} м)"))
                    else:
                        event_log.appendleft((sim_time, "Маршруты ВЫКЛ"))
                elif event.key == pygame.K_o:
                    reflect_enabled = not reflect_enabled
                    event_log.appendleft(
                        (sim_time, f"Отражение {'ВКЛ' if reflect_enabled else 'ВЫКЛ'}")
                    )
                elif event.key == pygame.K_n:
                    respawn_agents(agents)
                elif event.key == pygame.K_1:
                    for a in agents:
                        a.set_velocity(BASE_SCENARIO_SPEED, 0)
                    scenario_name = "→ вправо"
                elif event.key == pygame.K_2:
                    for a in agents:
                        a.set_velocity(-BASE_SCENARIO_SPEED, 0)
                    scenario_name = "← влево"
                elif event.key == pygame.K_3:
                    for a in agents:
                        a.set_velocity(0, -BASE_SCENARIO_SPEED)
                    scenario_name = "↑ вверх"
                elif event.key == pygame.K_4:
                    for a in agents:
                        a.set_velocity(0, BASE_SCENARIO_SPEED)
                    scenario_name = "↓ вниз"
                elif event.key == pygame.K_r:
                    for a in agents:
                        sp = random.uniform(AGENT_SPEED_MIN, AGENT_SPEED_MAX)
                        ang = random.uniform(0, 2 * math.pi)
                        a.set_velocity(sp * math.cos(ang), sp * math.sin(ang))
                    scenario_name = "случайный"
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    speed_mult = min(3.0, speed_mult + 0.15)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    speed_mult = max(0.15, speed_mult - 0.15)
                elif event.key == pygame.K_s:
                    save_scenario(agents, current_tx_idx)
                elif event.key == pygame.K_l:
                    current_tx_idx = load_scenario(agents)
                elif event.key == pygame.K_c:
                    cam_x, cam_y = WORLD_W / 2, WORLD_H / 2
                    zoom = 1.0
                elif event.key == pygame.K_b:
                    for a in agents:
                        a.battery = 100.0
                    event_log.appendleft((sim_time, "Батареи 100%"))

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                before = screen_to_world(mx, my)
                zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom * (1.15 if event.y > 0 else 1 / 1.15)))
                after = screen_to_world(mx, my)
                cam_x += before[0] - after[0]
                cam_y += before[1] - after[1]

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (2, 3):
                    dragging = True
                    drag_start = event.pos
                    cam_start = (cam_x, cam_y)
                elif event.button == 1:
                    wx, wy = screen_to_world(*event.pos)
                    best_i, best_d = None, 1e9
                    for i, a in enumerate(agents):
                        d = math.hypot(a.x - wx, a.y - wy)
                        if d < best_d:
                            best_d, best_i = d, i
                    if best_i is not None and best_d < 40:
                        current_tx_idx = best_i

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button in (2, 3):
                    dragging = False

            elif event.type == pygame.MOUSEMOTION and dragging:
                dx = event.pos[0] - drag_start[0]
                dy = event.pos[1] - drag_start[1]
                cam_x = cam_start[0] - dx / (BASE_SCALE * zoom)
                cam_y = cam_start[1] - dy / (BASE_SCALE * zoom)

        # ----- логика -----
        for a in agents:
            a.tx_active = False
        agents[current_tx_idx].tx_active = transmitting and agents[current_tx_idx].battery > 1

        leader = agents[0] if formation_mode else None
        for a in agents:
            a.update(dt, leader)

        if transmitting and agents[current_tx_idx].battery > 1:
            tx_pulse_timer += dt
            if tx_pulse_timer >= TX_PULSE_INTERVAL:
                tx_pulse_timer = 0.0
                tx = agents[current_tx_idx]
                tx.battery = max(0.0, tx.battery - TX_POWER_DRAIN)
                waves.append(Wave(tx.x, tx.y, tx.id, sim_time, tx.x, tx.y))
                event_log.appendleft(
                    (sim_time, f"TX A{tx.id} → ({tx.x:.1f}, {tx.y:.1f})  bat {tx.battery:.0f}%")
                )

        new_waves = []
        for w in waves:
            w.update(dt, agents, new_waves)
        waves = [w for w in waves if w.alive]
        waves.extend(new_waves)

        if int(sim_time * 4) != int((sim_time - dt) * 4):
            rec = [a for a in agents if a.received]
            if rec:
                avg = sum(a.last_snr for a in rec) / len(rec)
                succ = sum(1 for a in rec if a.decrypted) / len(rec)
            else:
                avg, succ = 0.0, 0.0
            snr_history.append((sim_time, avg, succ))

        # ----- рендер -----
        screen.fill(BG_COLOR)

        for m in range(0, int(WORLD_W) + 1, 100):
            x1, y1 = world_to_screen(m, 0)
            x2, y2 = world_to_screen(m, WORLD_H)
            pygame.draw.line(screen, GRID_COLOR, (x1, y1), (x2, y2))
        for m in range(0, int(WORLD_H) + 1, 100):
            x1, y1 = world_to_screen(0, m)
            x2, y2 = world_to_screen(WORLD_W, m)
            pygame.draw.line(screen, GRID_COLOR, (x1, y1), (x2, y2))

        x0, y0 = world_to_screen(0, 0)
        x1, y1 = world_to_screen(WORLD_W, WORLD_H)
        pygame.draw.rect(screen, (50, 65, 90), (x0, y0, x1 - x0, y1 - y0), 2)

        draw_nogo_zones(screen)
        if show_heatmap:
            draw_heatmap(screen, waves)
        draw_waypoints(screen, agents)

        for w in waves:
            w.draw(screen)
        for a in agents:
            a.draw_circle(screen)
        if show_vectors:
            for a in agents:
                a.draw_velocity_vector(screen)
        for a in agents:
            a.draw_label(screen, font)

        tx = agents[current_tx_idx]
        sx, sy = world_to_screen(tx.x, tx.y)
        r = max(2, int(AGENT_RADIUS_M * BASE_SCALE * zoom))
        pygame.draw.circle(screen, ACCENT_COLOR, (sx, sy), r + 5, 2)

        draw_results_panel(screen, agents, font, small)
        draw_log_panel(screen, font, small)
        draw_graph_panel(screen, font, small)

        hud_bg = pygame.Surface((WIDTH, 68), pygame.SRCALPHA)
        hud_bg.fill((0, 0, 0, 180))
        screen.blit(hud_bg, (0, 0))
        screen.blit(title.render(
            f"1×1 км  зум {zoom:.2f}×  |  буфер {SAFETY_MARGIN:.0f} м  |  ЛЧМ + ChaCha20",
            True, ACCENT_COLOR), (8, 3))
        screen.blit(hud.render(
            "ПРОБЕЛ TX  M движ  V вект  H тепло  J лог  G граф  P панель  "
            "F строй  W маршрут  O отражение  N новые  1-4 сцен  R rnd  +/-  S/L  B бат  C центр",
            True, TEXT_COLOR), (8, 24))
        mode = []
        if formation_mode: mode.append("СТРОЙ")
        if waypoint_mode: mode.append(f"МАРШРУТ")
        mode_s = " ".join(mode) if mode else scenario_name
        screen.blit(hud.render(
            f"TX:A{tx.id}  |  {'ПЕРЕДАЧА' if transmitting else 'стоп'}  |  "
            f"{mode_s}  |  Отраж: {'ВКЛ' if reflect_enabled else 'ВЫКЛ'}  |  "
            f"×{speed_mult:.2f}  |  волн:{len(waves)}",
            True, (170, 210, 255)), (8, 46))

        for a in agents:
            if a.rx_timer > 0:
                sx, sy = world_to_screen(a.x, a.y)
                r = max(2, int(AGENT_RADIUS_M * BASE_SCALE * zoom))
                txt = "DATA OK" if a.decrypted else "МУСОР"
                col = (10, 40, 10) if a.decrypted else (50, 10, 10)
                tag = font.render(txt, True, col)
                bg = pygame.Surface((tag.get_width() + 6, tag.get_height() + 3))
                bg.fill(AGENT_RX_COLOR if a.decrypted else (240, 90, 90))
                bg.set_alpha(210)
                screen.blit(bg, (sx - tag.get_width() // 2 - 3, sy - r - 20))
                screen.blit(tag, (sx - tag.get_width() // 2, sy - r - 18))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
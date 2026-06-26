# === ИМПОРТЫ ===
import pygame
import sys
import math
import random
from typing import List, Tuple, Optional, Dict, Any

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# === КОНСТАНТЫ ===
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
TARGET_FPS = 60

# Палитра (7 цветов)
COLOR_BG = (10, 12, 20)
COLOR_BG2 = (22, 28, 45)
COLOR_PRIMARY = (230, 240, 255)
COLOR_ACCENT = (255, 215, 100)
COLOR_DANGER = (255, 60, 80)
COLOR_SUCCESS = (100, 255, 150)
COLOR_TEXT = (240, 245, 255)

# Цвета режимов
COLOR_RED = (255, 50, 80)
COLOR_BLUE = (60, 140, 255)
COLOR_GREEN = (80, 255, 140)
MODE_COLORS = {
    'RED': COLOR_RED,
    'BLUE': COLOR_BLUE,
    'GREEN': COLOR_GREEN,
}

# Физика режимов
RED_ACCEL = 2400.0
RED_DECEL = 3.5
RED_MAX_SPEED = 520.0
RED_RECOIL = 0.05

BLUE_ACCEL = 900.0
BLUE_DECEL = 32.0
BLUE_MAX_SPEED = 280.0
BLUE_RECOIL = 0.15
BLUE_AOE_RADIUS = 80.0

GREEN_ACCEL = 1400.0
GREEN_DECEL = 5.5
GREEN_MAX_SPEED = 420.0
GREEN_RECOIL = 0.0
GREEN_LATERAL_DRIFT = 0.12

# Игрок
PLAYER_RADIUS = 14
PLAYER_MAX_HP = 100
PLAYER_INVULN_TIME = 1.2
PLAYER_SQUASH_DURATION = 0.15

# Dash (v4.0: ЛКМ стрельба, ПКМ/Space Dash)
DASH_SPEED = 900.0
DASH_DURATION = 0.15
DASH_COOLDOWN = 1.5
DASH_KILL_REDUCTION = 0.3  # Уменьшение кулдауна за убийство
DASH_INVULN_FRAMES = 0.2

# Стрельба
FIRE_COOLDOWN = 0.14
BULLET_SPEED = 820.0
BULLET_LIFETIME = 1.6
BULLET_RADIUS = 4
BULLET_DAMAGE = 25

# Chromatic Impulse (Category 1 - Глубина)
IMPULSE_KILL_THRESHOLD = 5  # 5 убийств одного цвета = piercing

# Echo Chamber (Category 3 - Уникальность)
ECHO_REFRACTION_THRESHOLD = 3  # 3 Refraction подряд
ECHO_DURATION = 5.0  # 5 секунд замедления
ECHO_SLOWDOWN_MULT = 0.7  # 30% замедление

# Враги
CHASER_SPEED = 155.0
CHASER_HP = 50
CHASER_RADIUS = 13
CHASER_DAMAGE = 15

SHOOTER_SPEED = 95.0
SHOOTER_HP = 40
SHOOTER_RADIUS = 14
SHOOTER_FIRE_INTERVAL = 1.6
SHOOTER_BULLET_SPEED = 310.0
SHOOTER_BULLET_DAMAGE = 10
SHOOTER_BULLET_RADIUS = 5
SHOOTER_PANIC_DISTANCE = 150.0  # Дистанция паники

KAMIKAZE_SPEED = 290.0
KAMIKAZE_HP = 30
KAMIKAZE_RADIUS = 12
KAMIKAZE_EXPLOSION_RADIUS = 65
KAMIKAZE_EXPLOSION_DAMAGE = 30
KAMIKAZE_WARN_TIME = 1.0
KAMIKAZE_WARN_RADIUS = 80.0

DISSONANCE_HP = 250
DISSONANCE_RADIUS = 15
DISSONANCE_SPEED = 120.0
DISSONANCE_NORMAL_DAMAGE_MULT = 0.2
DISSONANCE_HOMING_STRENGTH = 0.3  # Сила наведения отражённых пуль

# Волны
BASE_ENEMIES_PER_WAVE = 4
WAVE_MULTIPLIER = 1.18
WAVE_SPAWN_INTERVAL = 0.6
BREATHER_WAVE_INTERVAL = 5
BREATHER_ENEMY_MULT = 0.5

# Частицы (v4.0: оптимизация)
MAX_PARTICLES = 300  # Лимит частиц для стабильного FPS
PARTICLE_LIFETIME = 0.8
ENEMY_DEATH_PARTICLES = 18
SHOOT_PARTICLES = 10
PLAYER_DEATH_PARTICLES = 35
HIT_PARTICLES = 6
REFRACTION_PARTICLES = 25

# Screen shake
SHAKE_DURATION = 0.25
SHAKE_DECAY = 8.0

# Flash
FLASH_DURATION = 0.12

# Hit-stop
HITSTOP_DURATION = 0.07

# Chromatic buffer
BUFFER_WINDOW = 0.12
PERFECT_REFRACTION_WINDOW = 0.15

# Ритм
RHYTHM_CYCLE = ['RED', 'BLUE', 'GREEN']
RHYTHM_PITCH_BOOST = 0.05

# Power-ups
POWERUP_SPEED = 50.0
POWERUP_RADIUS = 11
POWERUP_LIFETIME = 12.0
POWERUP_HEAL_AMOUNT = 30
POWERUP_INVULN_DURATION = 5.0
POWERUP_SPAWN_CHANCE = 0.12

# UI
HP_BAR_WIDTH = 280
HP_BAR_HEIGHT = 18
HP_BAR_MARGIN = 20

# Призматический кристалл
CRYSTAL_STAGE_1 = 3
CRYSTAL_STAGE_2 = 7

# Хроматический Резонанс
RESONANCE_RADIUS = 100.0
RESONANCE_LIFETIME = 8.0
RESONANCE_KILL_THRESHOLD = 3
RESONANCE_SPEED_BOOST = 0.25
RESONANCE_DAMAGE_BOOST = 0.50
RESONANCE_DRIFT_SPEED = 20.0
RESONANCE_SURFACE_POOL_SIZE = 5  # Пул Surface для оптимизации

# === УТИЛИТЫ ===
def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def vec_length(x: float, y: float) -> float:
    return math.sqrt(x * x + y * y)

def vec_normalize(x: float, y: float) -> Tuple[float, float]:
    length = vec_length(x, y)
    if length < 0.0001:
        return 0.0, 0.0
    return x / length, y / length

def vec_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return vec_length(x2 - x1, y2 - y1)

def random_in_circle(radius: float) -> Tuple[float, float]:
    angle = random.uniform(0, math.pi * 2)
    r = radius * math.sqrt(random.uniform(0, 1))
    return math.cos(angle) * r, math.sin(angle) * r

def circle_collision(x1: float, y1: float, r1: float,
                     x2: float, y2: float, r2: float) -> bool:
    dx = x2 - x1
    dy = y2 - y1
    dist_sq = dx * dx + dy * dy
    rad_sum = r1 + r2
    return dist_sq <= rad_sum * rad_sum

def color_lerp(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return (
        int(lerp(c1[0], c2[0], t)),
        int(lerp(c1[1], c2[1], t)),
        int(lerp(c1[2], c2[2], t)),
    )

def color_add(c: Tuple[int, int, int], v: int) -> Tuple[int, int, int]:
    return (
        clamp(c[0] + v, 0, 255),
        clamp(c[1] + v, 0, 255),
        clamp(c[2] + v, 0, 255),
    )

# === ЗВУКОВОЙ МЕНЕДЖЕР ===
class SoundManager:
    """Менеджер звуков с процедурным синтезом и fallback без numpy."""
    
    def __init__(self):
        self.enabled = False
        self.sounds: Dict[str, Any] = {}
        self.current_time = 0.0
        
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.enabled = True
            self._generate_sounds()
        except Exception:
            self.enabled = False
    
    def _generate_sounds(self) -> None:
        """Генерация всех игровых звуков через numpy или math.sin."""
        if not self.enabled:
            return
        
        # Звуки стрельбы
        self.sounds['shoot_red'] = self._synth(1200, 400, 60, 'sine', 0.25)
        self.sounds['shoot_blue'] = self._synth(200, 80, 150, 'sine', 0.2)
        self.sounds['shoot_green'] = self._synth(800, 1200, 100, 'sine', 0.2)
        
        # Звуки событий
        self.sounds['refraction'] = self._synth(2000, 500, 80, 'sine', 0.35)
        self.sounds['hit'] = self._synth(150, 50, 200, 'sine', 0.3)
        self.sounds['death'] = self._synth(300, 50, 400, 'saw', 0.4)
        self.sounds['enemy_death'] = self._synth(500, 100, 120, 'sine', 0.2)
        self.sounds['pickup'] = self._synth_arpeggio([262, 330, 392], 60, 0.2)
        self.sounds['wave'] = self._synth(100, 400, 300, 'sine', 0.25)
        self.sounds['refraction_perfect'] = self._synth(2500, 800, 100, 'sine', 0.4)
        self.sounds['combo'] = self._synth(600, 1200, 100, 'sine', 0.25)
        self.sounds['dash'] = self._synth(400, 800, 80, 'sine', 0.3)
        
        # Звуки смены цвета (Звуковая Сигнатура - Category 2)
        self.sounds['mode_red'] = self._synth(600, 800, 50, 'sine', 0.2)
        self.sounds['mode_blue'] = self._synth(300, 200, 80, 'sine', 0.2)
        self.sounds['mode_green'] = self._synth(500, 700, 60, 'sine', 0.2)
        
        # Музыкальные звуки (v4.0: полноценная система)
        self.sounds['bass_note'] = self._synth(80, 80, 200, 'sine', 0.3)
        self.sounds['percussion_hit'] = self._synth(2000, 1000, 50, 'noise', 0.2)
        self.sounds['melody_c'] = self._synth(262, 262, 150, 'sine', 0.25)
        self.sounds['melody_e'] = self._synth(330, 330, 150, 'sine', 0.25)
        self.sounds['melody_g'] = self._synth(392, 392, 150, 'sine', 0.25)
    
    def _synth(self, freq_start: float, freq_end: float, duration_ms: int,
               wave_type: str, volume: float) -> Optional[Any]:
        """Синтез звука с ADSR-огибающей."""
        if not self.enabled:
            return None
        
        sample_rate = 44100
        n_samples = int(sample_rate * duration_ms / 1000)
        
        if NUMPY_AVAILABLE:
            t = np.linspace(0, duration_ms / 1000, n_samples, False)
            freq = np.linspace(freq_start, freq_end, n_samples)
            
            if wave_type == 'sine':
                wave = np.sin(2 * np.pi * freq * t)
            elif wave_type == 'square':
                wave = np.sign(np.sin(2 * np.pi * freq * t))
            elif wave_type == 'saw':
                wave = 2 * (freq * t - np.floor(freq * t + 0.5))
            elif wave_type == 'noise':
                wave = np.random.uniform(-1, 1, n_samples)
            else:
                wave = np.sin(2 * np.pi * freq * t)
            
            # ADSR envelope
            attack = int(n_samples * 0.04)
            release = int(n_samples * 0.25)
            envelope = np.ones(n_samples)
            if attack > 0:
                envelope[:attack] = np.linspace(0, 1, attack)
            if release > 0:
                envelope[-release:] = np.linspace(1, 0, release)
            
            wave = wave * envelope * volume
            wave_16 = np.int16(wave * 32767)
            stereo = np.column_stack((wave_16, wave_16))
            
            try:
                return pygame.sndarray.make_sound(stereo.copy())
            except Exception:
                return None
        else:
            # Fallback: простой синус через math.sin
            samples = []
            attack_samples = int(n_samples * 0.04)
            release_start = int(n_samples * 0.75)
            
            for i in range(n_samples):
                t = i / sample_rate
                progress = i / n_samples
                freq = freq_start + (freq_end - freq_start) * progress
                value = math.sin(2 * math.pi * freq * t)
                
                # Envelope
                if i < attack_samples:
                    env = i / attack_samples
                elif i > release_start:
                    env = (n_samples - i) / (n_samples - release_start)
                else:
                    env = 1.0
                
                value *= env * volume
                val_int = int(value * 16384)
                samples.extend([val_int, val_int])
            
            try:
                return pygame.mixer.Sound(buffer=bytes(samples))
            except Exception:
                return None
    
    def _synth_arpeggio(self, freqs: List[float], note_ms: int, volume: float) -> Optional[Any]:
        """Арпеджио из нескольких нот."""
        if not self.enabled:
            return None
        
        sample_rate = 44100
        total_samples = int(sample_rate * note_ms / 1000 * len(freqs))
        
        if NUMPY_AVAILABLE:
            wave = np.zeros(total_samples)
            for i, freq in enumerate(freqs):
                start = int(i * sample_rate * note_ms / 1000)
                end = int((i + 1) * sample_rate * note_ms / 1000)
                if end > total_samples:
                    end = total_samples
                length = end - start
                t = np.linspace(0, note_ms / 1000, length, False)
                note = np.sin(2 * np.pi * freq * t)
                # Envelope
                release = int(length * 0.4)
                env = np.ones(length)
                env[-release:] = np.linspace(1, 0, release)
                wave[start:end] = note * env * volume
            
            wave_16 = np.int16(wave * 32767)
            stereo = np.column_stack((wave_16, wave_16))
            try:
                return pygame.sndarray.make_sound(stereo.copy())
            except Exception:
                return None
        return None
    
    def play(self, name: str, volume: float = 1.0) -> None:
        if not self.enabled or name not in self.sounds:
            return
        sound = self.sounds[name]
        if sound:
            try:
                sound.set_volume(volume)
                sound.play()
            except Exception:
                pass

# === ЧАСТИЦА ===
class Particle:
    """Отдельная частица с физикой."""
    
    def __init__(self, x: float, y: float, vx: float, vy: float,
                 color: Tuple[int, int, int], lifetime: float,
                 size: float = 3.0, gravity: float = 0.0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.size = size
        self.gravity = gravity
    
    def update(self, dt: float) -> bool:
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.96
        self.vy *= 0.96
        self.lifetime -= dt
        return self.lifetime > 0
    
    def draw(self, surface: pygame.Surface) -> None:
        t = self.lifetime / self.max_lifetime
        alpha = int(255 * t)
        size = int(self.size * (0.3 + 0.7 * t))
        if size < 1:
            size = 1
        color = color_lerp(COLOR_BG, self.color, t)
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), size)

# === МЕНЕДЖЕР ЧАСТИЦ (v4.0: оптимизация) ===
class ParticleManager:
    """Управляет всеми частицами с лимитом для стабильного FPS."""
    
    def __init__(self):
        self.particles: List[Particle] = []
    
    def emit_burst(self, x: float, y: float, count: int,
                   color: Tuple[int, int, int], speed: float = 250.0,
                   lifetime: float = 0.8, size: float = 3.5,
                   gravity: float = 50.0) -> None:
        """Создаёт взрыв частиц."""
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            s = speed * random.uniform(0.3, 1.0)
            vx = math.cos(angle) * s
            vy = math.sin(angle) * s
            self.particles.append(Particle(x, y, vx, vy, color, lifetime, size, gravity))
        
        # v4.0: лимит частиц
        if len(self.particles) > MAX_PARTICLES:
            # Удаляем самые старые (LIFO)
            self.particles = self.particles[-MAX_PARTICLES:]
    
    def emit_directional(self, x: float, y: float, count: int,
                         direction: Tuple[float, float], spread: float,
                         color: Tuple[int, int, int], speed: float = 300.0,
                         lifetime: float = 0.5, size: float = 2.5) -> None:
        base_angle = math.atan2(direction[1], direction[0])
        for _ in range(count):
            angle = base_angle + random.uniform(-spread, spread)
            s = speed * random.uniform(0.5, 1.2)
            vx = math.cos(angle) * s
            vy = math.sin(angle) * s
            self.particles.append(Particle(x, y, vx, vy, color, lifetime, size, 0))
        
        if len(self.particles) > MAX_PARTICLES:
            self.particles = self.particles[-MAX_PARTICLES:]
    
    def emit_spiral(self, x: float, y: float, count: int,
                    color: Tuple[int, int, int], speed: float = 200.0) -> None:
        for i in range(count):
            angle = (i / count) * math.pi * 2
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self.particles.append(Particle(x, y, vx, vy, color, 1.2, 4.0, 0))
        
        if len(self.particles) > MAX_PARTICLES:
            self.particles = self.particles[-MAX_PARTICLES:]
    
    def update(self, dt: float) -> None:
        self.particles = [p for p in self.particles if p.update(dt)]
    
    def draw(self, surface: pygame.Surface) -> None:
        for p in self.particles:
            p.draw(surface)
    
    def clear(self) -> None:
        self.particles.clear()

# === SCREEN SHAKE ===
class ScreenShake:
    """Направленный screen shake с экспоненциальным затуханием."""
    
    def __init__(self):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.duration = 0.0
        self.intensity = 0.0
        self.dir_x = 0.0
        self.dir_y = 0.0
    
    def trigger(self, intensity: float, duration: float = SHAKE_DURATION,
                direction: Optional[Tuple[float, float]] = None) -> None:
        self.intensity = max(self.intensity, intensity)
        self.duration = max(self.duration, duration)
        if direction:
            self.dir_x, self.dir_y = vec_normalize(*direction)
        else:
            self.dir_x = 0.0
            self.dir_y = 0.0
    
    def update(self, dt: float) -> None:
        if self.duration <= 0:
            self.offset_x = 0.0
            self.offset_y = 0.0
            return
        
        self.duration -= dt
        
        if self.dir_x == 0 and self.dir_y == 0:
            # Random shake
            self.offset_x = random.uniform(-self.intensity, self.intensity)
            self.offset_y = random.uniform(-self.intensity, self.intensity)
        else:
            # Directional shake
            self.offset_x = self.dir_x * self.intensity * math.sin(self.duration * 40)
            self.offset_y = self.dir_y * self.intensity * math.sin(self.duration * 40)
        
        # Exponential decay
        self.intensity *= math.exp(-SHAKE_DECAY * dt)
    
    def apply(self, surface: pygame.Surface, temp_surface: pygame.Surface) -> None:
        """Применяет смещение к отрисовке."""
        surface.blit(temp_surface, (int(self.offset_x), int(self.offset_y)))

# === ВСПЛЫВАЮЩИЙ ТЕКСТ ===
class FloatingText:
    """Всплывающий текст с затуханием."""
    
    def __init__(self, x: float, y: float, text: str,
                 color: Tuple[int, int, int], lifetime: float = 1.0,
                 font_size: int = 18):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.vy = -70.0
        self.font_size = font_size
        self.font = pygame.font.SysFont("consolas", font_size, bold=True)
    
    def update(self, dt: float) -> bool:
        self.y += self.vy * dt
        self.vy *= 0.92
        self.lifetime -= dt
        return self.lifetime > 0
    
    def draw(self, surface: pygame.Surface) -> None:
        t = self.lifetime / self.max_lifetime
        alpha = int(255 * t)
        color = color_lerp(COLOR_BG, self.color, t)
        text_surf = self.font.render(self.text, True, color)
        text_surf.set_alpha(alpha)
        rect = text_surf.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(text_surf, rect)

# === ПРИЗМАТИЧЕСКИЙ КРИСТАЛЛ ===
class PrismaticCrystal:
    """Диегетический UI для комбо. Физическое состояние на спине игрока."""
    
    def __init__(self):
        self.rotation = 0.0
        self.pulse_phase = 0.0
        self.trail: List[Tuple[float, float, float, Tuple[int, int, int]]] = []
        self.wave_radius = 0.0
        self.wave_active = False
    
    def update(self, dt: float, player_x: float, player_y: float,
               player_mode: str, combo: int) -> None:
        self.rotation += dt * (2.0 + combo * 0.3)
        self.pulse_phase += dt * (3.0 + combo * 0.5)
        
        if combo >= CRYSTAL_STAGE_1:
            offset_x = math.cos(self.rotation) * 15
            offset_y = math.sin(self.rotation) * 15
            crystal_x = player_x + offset_x
            crystal_y = player_y + offset_y
            color = MODE_COLORS[player_mode]
            self.trail.append((crystal_x, crystal_y, 1.0, color))
        
        for i in range(len(self.trail)):
            x, y, alpha, color = self.trail[i]
            self.trail[i] = (x, y, alpha * 0.85, color)
        self.trail = [t for t in self.trail if t[2] > 0.05]
        if len(self.trail) > 6:
            self.trail = self.trail[-6:]
        
        if self.wave_active:
            self.wave_radius += dt * 300
            if self.wave_radius > 80:
                self.wave_active = False
                self.wave_radius = 0
    
    def trigger_wave(self) -> None:
        self.wave_active = True
        self.wave_radius = 0
    
    def draw(self, surface: pygame.Surface, player_x: float, player_y: float,
             player_mode: str, combo: int, time: float) -> None:
        color = MODE_COLORS[player_mode]
        
        for x, y, alpha, trail_color in self.trail:
            if alpha > 0.05:
                size = int(5 * alpha)
                trail_surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(trail_surf, (*trail_color, int(100 * alpha)),
                                   (size + 1, size + 1), size)
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        if combo < CRYSTAL_STAGE_1:
            offset_x = -10
            offset_y = 0
            crystal_x = player_x + offset_x
            crystal_y = player_y + offset_y
            
            size = 6
            dim_color = color_lerp(COLOR_BG, color, 0.4)
            points = [
                (crystal_x, crystal_y - size),
                (crystal_x + size, crystal_y),
                (crystal_x, crystal_y + size),
                (crystal_x - size, crystal_y),
            ]
            pygame.draw.polygon(surface, dim_color, points)
            pygame.draw.polygon(surface, color_lerp(COLOR_BG, color, 0.7), points, 1)
        else:
            offset_angle = self.rotation * 0.5
            offset_x = math.cos(offset_angle + math.pi) * 18
            offset_y = math.sin(offset_angle + math.pi) * 18
            crystal_x = player_x + offset_x
            crystal_y = player_y + offset_y
            
            size = 7
            angle = self.rotation
            points = []
            for i in range(4):
                a = angle + i * (math.pi / 2)
                px = crystal_x + math.cos(a) * size
                py = crystal_y + math.sin(a) * size
                points.append((px, py))
            
            if combo >= CRYSTAL_STAGE_2:
                pulse = 0.5 + 0.5 * math.sin(self.pulse_phase)
                glow_size = int(size + 4 * pulse)
                glow_surf = pygame.Surface((glow_size * 4, glow_size * 4), pygame.SRCALPHA)
                glow_color = (*color, int(80 * pulse))
                pygame.draw.circle(glow_surf, glow_color,
                                   (glow_size * 2, glow_size * 2), glow_size * 2)
                surface.blit(glow_surf, (int(crystal_x - glow_size * 2),
                                         int(crystal_y - glow_size * 2)))
            
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, COLOR_PRIMARY, points, 1)
        
        if self.wave_active and combo >= CRYSTAL_STAGE_2:
            t = 1 - (self.wave_radius / 80)
            alpha = int(200 * t)
            if alpha > 0:
                wave_surf = pygame.Surface((200, 200), pygame.SRCALPHA)
                pygame.draw.circle(wave_surf, (*color, alpha),
                                   (100, 100), int(self.wave_radius), 3)
                surface.blit(wave_surf, (int(player_x - 100), int(player_y - 100)))

# === ХРОМАТИЧЕСКИЙ РЕЗОНАНС (v4.0: оптимизация через пул Surface) ===
class ChromaticResonance:
    """Цветные пятна на полу от убийств одного цвета."""
    
    # Статический пул Surface для переиспользования
    _surface_pool: List[pygame.Surface] = []
    _pool_initialized = False
    
    def __init__(self, x: float, y: float, color_mode: str):
        self.x = x
        self.y = y
        self.color_mode = color_mode
        self.color = MODE_COLORS[color_mode]
        self.radius = RESONANCE_RADIUS
        self.lifetime = RESONANCE_LIFETIME
        self.max_lifetime = RESONANCE_LIFETIME
        self.pulse_phase = 0.0
        
        # Дрейф от игрока
        self.drift_x = random.uniform(-1, 1)
        self.drift_y = random.uniform(-1, 1)
        self.drift_x, self.drift_y = vec_normalize(self.drift_x, self.drift_y)
        
        # Инициализация пула Surface (один раз)
        if not ChromaticResonance._pool_initialized:
            size = int(RESONANCE_RADIUS * 4)
            for _ in range(RESONANCE_SURFACE_POOL_SIZE):
                surf = pygame.Surface((size, size), pygame.SRCALPHA)
                ChromaticResonance._surface_pool.append(surf)
            ChromaticResonance._pool_initialized = True
        
        # Берём Surface из пула
        self.surface_index = len(ChromaticResonance._surface_pool) - 1
        self.reuse_surface = ChromaticResonance._surface_pool[self.surface_index] if ChromaticResonance._surface_pool else None
    
    def update(self, dt: float) -> bool:
        self.lifetime -= dt
        self.pulse_phase += dt * 2
        
        # Дрейф
        self.x += self.drift_x * RESONANCE_DRIFT_SPEED * dt
        self.y += self.drift_y * RESONANCE_DRIFT_SPEED * dt
        
        # Границы
        self.x = clamp(self.x, self.radius, SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y, self.radius, SCREEN_HEIGHT - self.radius)
        
        return self.lifetime > 0
    
    def draw(self, surface: pygame.Surface) -> None:
        t = self.lifetime / self.max_lifetime
        alpha = int(120 * t)
        
        # Пульсация
        pulse = 0.8 + 0.2 * math.sin(self.pulse_phase)
        draw_radius = int(self.radius * pulse)
        
        # Glow
        glow_surf = pygame.Surface((draw_radius * 4, draw_radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*self.color, int(alpha * 0.3)),
                           (draw_radius * 2, draw_radius * 2), draw_radius * 2)
        surface.blit(glow_surf, (int(self.x - draw_radius * 2), int(self.y - draw_radius * 2)))
        
        # Основной круг (v4.0: переиспользуем Surface если возможно)
        if self.reuse_surface:
            self.reuse_surface.fill((0, 0, 0, 0))  # Очищаем
            pygame.draw.circle(self.reuse_surface, (*self.color, alpha),
                               (draw_radius * 2, draw_radius * 2), draw_radius)
            surface.blit(self.reuse_surface, (int(self.x - draw_radius * 2), int(self.y - draw_radius * 2)))
        else:
            # Fallback: создаём новый Surface
            resonance_surf = pygame.Surface((draw_radius * 2, draw_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(resonance_surf, (*self.color, alpha),
                               (draw_radius, draw_radius), draw_radius)
            surface.blit(resonance_surf, (int(self.x - draw_radius), int(self.y - draw_radius)))
        
        # Контур
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), draw_radius, 2)

# === ИГРОК (v4.0: ЛКМ стрельба, ПКМ/Space Dash) ===
class Player:
    """Игрок с тремя физическими режимами и Dash через Space/ПКМ."""
    
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.radius = PLAYER_RADIUS
        self.hp = PLAYER_MAX_HP
        self.max_hp = PLAYER_MAX_HP
        self.mode = 'RED'
        self.invuln_timer = 0.0
        self.fire_cooldown = 0.0
        self.facing_x = 0.0
        self.facing_y = -1.0
        self.trail: List[Tuple[float, float, float]] = []
        self.squash_timer = 0.0
        self.squash_scale = 1.0
        self.invuln_flash = 0.0
        
        # Dash (v4.0: Space/ПКМ)
        self.dash_cooldown = 0.0
        self.is_dashing = False
        self.dash_timer = 0.0
        self.dash_invuln = False
        
        # Chromatic Impulse (Category 1 - Глубина)
        self.impulse_active = False
        self.impulse_timer = 0.0
    
    def set_mode(self, mode: str, game: Any) -> None:
        """Смена режима с визуальным эффектом и звуком."""
        if mode != self.mode:
            self.mode = mode
            if mode == 'BLUE':
                self.squash_timer = PLAYER_SQUASH_DURATION
            
            # Звук смены цвета (Звуковая Сигнатура - Category 2)
            sound_map = {'RED': 'mode_red', 'BLUE': 'mode_blue', 'GREEN': 'mode_green'}
            game.sound_manager.play(sound_map[mode], 0.4)
    
    def start_dash(self, game: Any) -> None:
        """Активация рывка с i-frames."""
        if self.dash_cooldown > 0 or self.is_dashing:
            return
        
        if vec_length(self.facing_x, self.facing_y) < 0.1:
            return  # Нет направления
        
        self.is_dashing = True
        self.dash_timer = DASH_DURATION
        self.dash_invuln = True
        self.dash_cooldown = DASH_COOLDOWN
        
        # Визуальный эффект
        self.squash_timer = 0.2
        self.squash_scale = 1.3
        
        # Звук
        game.sound_manager.play('dash', 0.5)
        
        # Частицы
        game.particles.emit_burst(self.x, self.y, 15, MODE_COLORS[self.mode], 300.0, 0.5, 3.0)
    
    def update(self, dt: float, keys: Any, sound_manager: SoundManager, 
               current_time: float, game: Any) -> None:
        # Таймеры
        if self.invuln_timer > 0:
            self.invuln_timer -= dt
            self.invuln_flash += dt * 8
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt
        if self.dash_cooldown > 0:
            self.dash_cooldown -= dt
        if self.squash_timer > 0:
            self.squash_timer -= dt
            t = self.squash_timer / PLAYER_SQUASH_DURATION
            if t > 0.5:
                self.squash_scale = lerp(0.8, 1.1, (1 - t) * 2)
            else:
                self.squash_scale = lerp(1.1, 1.0, (0.5 - t) * 2)
        else:
            self.squash_scale = 1.0
        
        # Chromatic Impulse таймер
        if self.impulse_active:
            self.impulse_timer -= dt
            if self.impulse_timer <= 0:
                self.impulse_active = False
        
        # Ввод
        dx = 0.0
        dy = 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1.0
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1.0
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1.0
        
        # v4.0: Dash через Space (клавиатура)
        if keys[pygame.K_SPACE]:
            self.start_dash(game)
        
        if dx != 0 or dy != 0:
            dx, dy = vec_normalize(dx, dy)
            self.facing_x = dx
            self.facing_y = dy
        
        # Обновление активного Dash
        if self.is_dashing:
            self.dash_timer -= dt
            self.dash_invuln = True
            
            # Движение в направлении рывка с высокой скоростью
            self.vx = self.facing_x * DASH_SPEED
            self.vy = self.facing_y * DASH_SPEED
            
            # Trail эффект
            if len(self.trail) < 8:
                self.trail.append((self.x, self.y, 1.5))
            
            if self.dash_timer <= 0:
                self.is_dashing = False
                self.dash_invuln = False
                # Замедление после рывка
                self.vx *= 0.5
                self.vy *= 0.5
        else:
            # Физика в зависимости от режима
            if self.mode == 'RED':
                if dx != 0 or dy != 0:
                    self.vx += dx * RED_ACCEL * dt
                    self.vy += dy * RED_ACCEL * dt
                else:
                    decay = math.exp(-RED_DECEL * dt)
                    self.vx *= decay
                    self.vy *= decay
                speed = vec_length(self.vx, self.vy)
                if speed > RED_MAX_SPEED:
                    self.vx = (self.vx / speed) * RED_MAX_SPEED
                    self.vy = (self.vy / speed) * RED_MAX_SPEED
                    
            elif self.mode == 'BLUE':
                if dx != 0 or dy != 0:
                    self.vx += dx * BLUE_ACCEL * dt
                    self.vy += dy * BLUE_ACCEL * dt
                else:
                    decay = math.exp(-BLUE_DECEL * dt)
                    self.vx *= decay
                    self.vy *= decay
                speed = vec_length(self.vx, self.vy)
                if speed > BLUE_MAX_SPEED:
                    self.vx = (self.vx / speed) * BLUE_MAX_SPEED
                    self.vy = (self.vy / speed) * BLUE_MAX_SPEED
                    
            elif self.mode == 'GREEN':
                if dx != 0 or dy != 0:
                    self.vx += dx * GREEN_ACCEL * dt
                    self.vy += dy * GREEN_ACCEL * dt
                else:
                    decay = math.exp(-GREEN_DECEL * dt)
                    self.vx *= decay
                    self.vy *= decay
                speed = vec_length(self.vx, self.vy)
                if speed > 10 and speed > GREEN_MAX_SPEED:
                    self.vx = (self.vx / speed) * GREEN_MAX_SPEED
                    self.vy = (self.vy / speed) * GREEN_MAX_SPEED
                elif speed > 10:
                    perp_x = -self.vy
                    perp_y = self.vx
                    drift_strength = GREEN_LATERAL_DRIFT * math.sin(current_time * 5)
                    self.vx += perp_x * drift_strength * dt * 60
                    self.vy += perp_y * drift_strength * dt * 60
        
        # Обновление позиции
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        # Границы
        self.x = clamp(self.x, self.radius, SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y, self.radius, SCREEN_HEIGHT - self.radius)
        
        # Trail
        speed = vec_length(self.vx, self.vy)
        if speed > 50:
            self.trail.append((self.x, self.y, 1.0))
        if len(self.trail) > 5:
            self.trail.pop(0)
        for i in range(len(self.trail)):
            x, y, alpha = self.trail[i]
            self.trail[i] = (x, y, alpha * 0.75)
        self.trail = [t for t in self.trail if t[2] > 0.05]
    
    def shoot(self, game: Any) -> bool:
        """Стрельба с отдачей."""
        if self.fire_cooldown > 0:
            return False
        
        self.fire_cooldown = FIRE_COOLDOWN
        
        # Направление стрельбы
        if vec_length(self.facing_x, self.facing_y) < 0.1:
            aim_x, aim_y = 1.0, 0.0
        else:
            aim_x, aim_y = self.facing_x, self.facing_y
        
        # v4.0: Chromatic Impulse - piercing выстрел
        is_piercing = self.impulse_active
        
        # Создаём пулю
        bullet = PlayerBullet(
            self.x + aim_x * self.radius * 1.3,
            self.y + aim_y * self.radius * 1.3,
            aim_x, aim_y, self.mode, is_piercing
        )
        game.player_bullets.append(bullet)
        
        # Отдача
        if self.mode == 'RED':
            self.vx -= aim_x * RED_MAX_SPEED * RED_RECOIL
            self.vy -= aim_y * RED_MAX_SPEED * RED_RECOIL
        elif self.mode == 'BLUE':
            self.vx -= aim_x * BLUE_MAX_SPEED * BLUE_RECOIL
            self.vy -= aim_y * BLUE_MAX_SPEED * BLUE_RECOIL
            self.squash_timer = PLAYER_SQUASH_DURATION * 0.7
            
            # AoE урон для Синего режима
            self.blue_aoe_attack(game)
        
        # Частицы выстрела
        game.particles.emit_directional(
            self.x + aim_x * self.radius * 1.3,
            self.y + aim_y * self.radius * 1.3,
            SHOOT_PARTICLES, (aim_x, aim_y), 0.4,
            MODE_COLORS[self.mode], 350.0, 0.3, 2.0
        )
        
        # Звук
        sound_map = {'RED': 'shoot_red', 'BLUE': 'shoot_blue', 'GREEN': 'shoot_green'}
        game.sound_manager.play(sound_map[self.mode], 0.5)
        
        return True
    
    def blue_aoe_attack(self, game: Any) -> None:
        """AoE атака для Синего режима."""
        game.particles.emit_burst(self.x, self.y, 15, COLOR_BLUE, 200.0, 0.5, 3.0)
        
        for enemy in game.enemies:
            if not enemy.alive:
                continue
            dist = vec_distance(self.x, self.y, enemy.x, enemy.y)
            if dist < BLUE_AOE_RADIUS + enemy.radius:
                if isinstance(enemy, DissonanceEnemy):
                    enemy.take_damage(BULLET_DAMAGE, game, 'BLUE', is_aoe=True)
                else:
                    enemy.take_damage(BULLET_DAMAGE * 0.5, game, 'BLUE', is_aoe=True)
    
    def take_damage(self, damage: int, game: Any, source_x: float, source_y: float) -> None:
        """Получение урона с эффектами."""
        if self.invuln_timer > 0 or self.dash_invuln or game.god_mode:
            return
        
        self.hp -= damage
        self.invuln_timer = PLAYER_INVULN_TIME
        
        dir_x = self.x - source_x
        dir_y = self.y - source_y
        game.screen_shake.trigger(12.0, SHAKE_DURATION, (dir_x, dir_y))
        
        game.particles.emit_burst(self.x, self.y, 12, COLOR_DANGER, 280.0, 0.6, 3.0)
        
        game.floating_texts.append(FloatingText(
            self.x, self.y - 20, f"-{damage}", COLOR_DANGER, 0.8, 20
        ))
        
        game.sound_manager.play('hit', 0.6)
        
        game.combo = 0
        
        if hasattr(game, 'music_system'):
            game.music_system.conductor_damage()
        
        if self.hp <= 0:
            self.hp = 0
            game.player_died()
    
    def draw(self, surface: pygame.Surface, time: float) -> None:
        if self.invuln_timer > 0:
            fade_t = self.invuln_timer / PLAYER_INVULN_TIME
            alpha = int(128 + 127 * math.sin(fade_t * math.pi * 8))
        else:
            alpha = 255
        
        color = MODE_COLORS[self.mode]
        for x, y, trail_alpha in self.trail:
            size = int(self.radius * trail_alpha * 0.8)
            if size > 0:
                trail_surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(trail_surf, (*color, int(80 * trail_alpha)),
                                   (size + 1, size + 1), size)
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        scale = self.squash_scale
        rx = int(self.radius * scale)
        ry = int(self.radius * (2 - scale))
        
        glow_surf = pygame.Surface((rx * 4, ry * 4), pygame.SRCALPHA)
        glow_pulse = 0.5 + 0.3 * math.sin(time * 4)
        pygame.draw.ellipse(glow_surf, (*color, int(60 * glow_pulse * alpha / 255)),
                            (0, 0, rx * 4, ry * 4))
        surface.blit(glow_surf, (int(self.x - rx * 2), int(self.y - ry * 2)))
        
        body_surf = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(body_surf, (*color, alpha),
                            (0, 0, rx * 2, ry * 2))
        surface.blit(body_surf, (int(self.x - rx), int(self.y - ry)))
        
        pygame.draw.ellipse(surface, COLOR_PRIMARY,
                            (int(self.x - rx), int(self.y - ry), rx * 2, ry * 2), 2)
        
        core_size = int(rx * 0.4)
        core_surf = pygame.Surface((core_size * 2, core_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(core_surf, (*COLOR_PRIMARY, alpha),
                           (core_size, core_size), core_size)
        surface.blit(core_surf, (int(self.x - core_size), int(self.y - core_size)))
        
        # v4.0: Chromatic Impulse индикатор
        if self.impulse_active:
            impulse_surf = pygame.Surface((self.radius * 6, self.radius * 6), pygame.SRCALPHA)
            pulse = 0.5 + 0.5 * math.sin(time * 10)
            pygame.draw.circle(impulse_surf, (*color, int(100 * pulse)),
                               (self.radius * 3, self.radius * 3), int(self.radius * 2.5), 2)
            surface.blit(impulse_surf, (int(self.x - self.radius * 3), int(self.y - self.radius * 3)))

# === ПУЛЯ ИГРОКА (v4.0: piercing) ===
class PlayerBullet:
    """Пуля игрока с цветом текущего режима."""
    
    def __init__(self, x: float, y: float, dx: float, dy: float, mode: str, is_piercing: bool = False):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.mode = mode
        self.radius = BULLET_RADIUS
        self.lifetime = BULLET_LIFETIME
        self.damage = BULLET_DAMAGE
        self.speed = BULLET_SPEED
        self.trail: List[Tuple[float, float, float]] = []
        self.is_refracted = False
        self.is_piercing = is_piercing  # v4.0: Chromatic Impulse
        self.hit_enemies: List[int] = []  # Для piercing: список ID врагов, которых уже ударили
    
    def update(self, dt: float) -> bool:
        self.x += self.dx * self.speed * dt
        self.y += self.dy * self.speed * dt
        self.lifetime -= dt
        
        self.trail.append((self.x, self.y, 1.0))
        if len(self.trail) > 4:
            self.trail.pop(0)
        for i in range(len(self.trail)):
            x, y, alpha = self.trail[i]
            self.trail[i] = (x, y, alpha * 0.6)
        
        return (self.lifetime > 0 and
                0 <= self.x <= SCREEN_WIDTH and
                0 <= self.y <= SCREEN_HEIGHT)
    
    def draw(self, surface: pygame.Surface) -> None:
        color = MODE_COLORS[self.mode]
        for x, y, alpha in self.trail:
            size = int(self.radius * alpha * 0.8)
            if size > 0:
                trail_surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(trail_surf, (*color, int(120 * alpha)),
                                   (size + 1, size + 1), size)
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        # v4.0: piercing пуля имеет больший размер
        draw_radius = self.radius * 1.5 if self.is_piercing else self.radius
        
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(draw_radius))
        pygame.draw.circle(surface, COLOR_PRIMARY,
                           (int(self.x), int(self.y)), int(draw_radius) - 1)

# === ПУЛЯ ВРАГА ===
class EnemyBullet:
    """Пуля врага."""
    
    def __init__(self, x: float, y: float, dx: float, dy: float,
                 speed: float = SHOOTER_BULLET_SPEED, damage: int = SHOOTER_BULLET_DAMAGE):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.speed = speed
        self.damage = damage
        self.radius = SHOOTER_BULLET_RADIUS
        self.lifetime = 4.0
        self.trail: List[Tuple[float, float, float]] = []
        self.slowed = False  # v4.0: Echo Chamber
    
    def update(self, dt: float, game: Any) -> bool:
        # v4.0: Echo Chamber - замедление пуль
        speed_mult = ECHO_SLOWDOWN_MULT if (hasattr(game, 'echo_chamber_active') and game.echo_chamber_active) else 1.0
        
        self.x += self.dx * self.speed * speed_mult * dt
        self.y += self.dy * self.speed * speed_mult * dt
        self.lifetime -= dt
        
        self.trail.append((self.x, self.y, 1.0))
        if len(self.trail) > 3:
            self.trail.pop(0)
        for i in range(len(self.trail)):
            x, y, alpha = self.trail[i]
            self.trail[i] = (x, y, alpha * 0.7)
        
        return (self.lifetime > 0 and
                -20 <= self.x <= SCREEN_WIDTH + 20 and
                -20 <= self.y <= SCREEN_HEIGHT + 20)
    
    def draw(self, surface: pygame.Surface) -> None:
        for x, y, alpha in self.trail:
            size = int(self.radius * alpha * 0.7)
            if size > 0:
                trail_surf = pygame.Surface((size * 2 + 2, size * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(trail_surf, (*COLOR_DANGER, int(150 * alpha)),
                                   (size + 1, size + 1), size)
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        pygame.draw.circle(surface, COLOR_DANGER, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, COLOR_ACCENT,
                           (int(self.x), int(self.y)), self.radius - 1)

# === БАЗОВЫЙ ВРАГ ===
class Enemy:
    """Базовый класс врага."""
    
    def __init__(self, x: float, y: float, hp: int, radius: float):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.hp = hp
        self.max_hp = hp
        self.radius = radius
        self.alive = True
        self.hit_flash = 0.0
        self.id = id(self)  # Уникальный ID для piercing
    
    def take_damage(self, damage: int, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        """Нанесение урона. Возвращает True если враг убит."""
        self.hp -= damage
        self.hit_flash = 0.1
        
        game.particles.emit_burst(self.x, self.y, HIT_PARTICLES,
                                  MODE_COLORS[bullet_mode], 200.0, 0.4, 2.0)
        
        if self.hp <= 0:
            self.alive = False
            self.on_death(game, bullet_mode)
            return True
        return False
    
    def on_death(self, game: Any, killer_mode: str) -> None:
        """Действия при смерти."""
        game.particles.emit_burst(self.x, self.y, ENEMY_DEATH_PARTICLES,
                                  COLOR_DANGER, 300.0, 0.9, 3.5)
        
        points = 100
        game.score += points * (1 + game.combo * 0.1)
        game.combo += 1
        game.max_combo = max(game.max_combo, game.combo)
        
        game.floating_texts.append(FloatingText(
            self.x, self.y, f"+{int(points)}", COLOR_ACCENT, 1.0, 16
        ))
        
        game.rhythm_tracker.on_kill(killer_mode, game)
        
        game.sound_manager.play('enemy_death', 0.4)
        
        if hasattr(game, 'music_system'):
            game.music_system.on_kill(killer_mode)
        
        # v4.0: Kill-based Dash regen
        game.player.dash_cooldown = max(0, game.player.dash_cooldown - DASH_KILL_REDUCTION)
        
        if random.random() < POWERUP_SPAWN_CHANCE:
            types = ['heal', 'invuln']
            game.powerups.append(PowerUp(self.x, self.y, random.choice(types)))
        
        dir_x = game.player.x - self.x
        dir_y = game.player.y - self.y
        game.screen_shake.trigger(4.0, 0.15, (dir_x, dir_y))
        
        game.check_resonance_spawn(self.x, self.y, killer_mode)
        
        # v4.0: Chromatic Impulse - проверка на 5+ убийств
        game.check_impulse_activation(killer_mode)
    
    def update(self, dt: float, player: Any) -> None:
        if self.hit_flash > 0:
            self.hit_flash -= dt
    
    def draw(self, surface: pygame.Surface) -> None:
        pass

# === ВРАГ-ПРЕСЛЕДОВАТЕЛЬ (v4.0: flanking) ===
class ChaserEnemy(Enemy):
    """Враг, преследующий игрока с возможностью обхода."""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, CHASER_HP, CHASER_RADIUS)
        self.speed = CHASER_SPEED
        self.wobble_phase = random.uniform(0, math.pi * 2)
        self.flank_direction = random.choice([-1, 1])  # -1 = слева, 1 = справа
    
    def update(self, dt: float, player: Any) -> None:
        super().update(dt, player)
        self.wobble_phase += dt * 3
        
        dx = player.x - self.x
        dy = player.y - self.y
        dist = vec_length(dx, dy)
        
        if dist > 1:
            nx = dx / dist
            ny = dy / dist
            
            # v4.0: Flanking поведение - обход сбоку
            perp_x = -ny * self.flank_direction
            perp_y = nx * self.flank_direction
            
            # 30% шанс flanking, 70% прямое преследование
            flank_weight = 0.3 if dist > 100 else 0.0
            
            nx = nx * (1 - flank_weight) + perp_x * flank_weight
            ny = ny * (1 - flank_weight) + perp_y * flank_weight
            nx, ny = vec_normalize(nx, ny)
            
            wobble = math.sin(self.wobble_phase) * 0.3
            nx += perp_x * wobble * 0.5
            ny += perp_y * wobble * 0.5
            nx, ny = vec_normalize(nx, ny)
            
            self.vx = lerp(self.vx, nx * self.speed, dt * 3)
            self.vy = lerp(self.vy, ny * self.speed, dt * 3)
        
        self.x += self.vx * dt
        self.y += self.vy * dt
    
    def draw(self, surface: pygame.Surface) -> None:
        color = COLOR_DANGER if self.hit_flash <= 0 else COLOR_PRIMARY
        
        angle = math.atan2(self.vy, self.vx)
        points = []
        for i in range(3):
            a = angle + i * (math.pi * 2 / 3)
            px = self.x + math.cos(a) * self.radius
            py = self.y + math.sin(a) * self.radius
            points.append((px, py))
        
        pygame.draw.polygon(surface, color, points)
        pygame.draw.polygon(surface, COLOR_PRIMARY, points, 2)
        
        pygame.draw.circle(surface, COLOR_ACCENT,
                           (int(self.x), int(self.y)), int(self.radius * 0.4))

# === ВРАГ-СТРЕЛОК (v4.0: panic mode) ===
class ShooterEnemy(Enemy):
    """Враг, стреляющий издалека с panic mode."""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, SHOOTER_HP, SHOOTER_RADIUS)
        self.speed = SHOOTER_SPEED
        self.fire_timer = random.uniform(0.5, SHOOTER_FIRE_INTERVAL)
        self.preferred_distance = 350.0
        self.orbit_angle = random.uniform(0, math.pi * 2)
        self.panic_mode = False
    
    def update(self, dt: float, player: Any) -> Optional[Any]:
        super().update(dt, player)
        self.fire_timer -= dt
        
        dx = player.x - self.x
        dy = player.y - self.y
        dist = vec_length(dx, dy)
        
        # v4.0: Panic mode при близости
        if dist < SHOOTER_PANIC_DISTANCE:
            self.panic_mode = True
            # Ускоренное отступление
            nx = -dx / dist
            ny = -dy / dist
            self.vx = lerp(self.vx, nx * self.speed * 1.5, dt * 3)
            self.vy = lerp(self.vy, ny * self.speed * 1.5, dt * 3)
            # Ускоренная стрельба
            if self.fire_timer <= 0:
                self.fire_timer = SHOOTER_FIRE_INTERVAL * 0.5
        else:
            self.panic_mode = False
            
            if dist > 1:
                nx = dx / dist
                ny = dy / dist
                
                self.orbit_angle += dt * 0.8
                perp_x = -ny
                perp_y = nx
                
                if dist > self.preferred_distance + 30:
                    self.vx = lerp(self.vx, nx * self.speed, dt * 2)
                    self.vy = lerp(self.vy, ny * self.speed, dt * 2)
                elif dist < self.preferred_distance - 30:
                    self.vx = lerp(self.vx, -nx * self.speed, dt * 2)
                    self.vy = lerp(self.vy, -ny * self.speed, dt * 2)
                else:
                    self.vx = lerp(self.vx, perp_x * self.speed, dt * 2)
                    self.vy = lerp(self.vy, perp_y * self.speed, dt * 2)
        
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        self.x = clamp(self.x, self.radius + 20, SCREEN_WIDTH - self.radius - 20)
        self.y = clamp(self.y, self.radius + 20, SCREEN_HEIGHT - self.radius - 20)
        
        if self.fire_timer <= 0 and dist < 500:
            self.fire_timer = SHOOTER_FIRE_INTERVAL
            bullet_dx, bullet_dy = vec_normalize(dx, dy)
            bullet = EnemyBullet(self.x, self.y, bullet_dx, bullet_dy)
            return bullet
        return None
    
    def draw(self, surface: pygame.Surface) -> None:
        color = COLOR_DANGER if self.hit_flash <= 0 else COLOR_PRIMARY
        
        half = self.radius
        rect = pygame.Rect(int(self.x - half), int(self.y - half),
                           int(half * 2), int(half * 2))
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, COLOR_PRIMARY, rect, 2)
        
        charge_t = 1 - (self.fire_timer / SHOOTER_FIRE_INTERVAL)
        if charge_t > 0.7:
            pygame.draw.circle(surface, COLOR_ACCENT,
                               (int(self.x), int(self.y)),
                               int(self.radius * 0.5 * (charge_t - 0.7) / 0.3))
        
        # v4.0: Panic mode индикатор
        if self.panic_mode:
            panic_surf = pygame.Surface((self.radius * 4, self.radius * 4), pygame.SRCALPHA)
            pygame.draw.circle(panic_surf, (*COLOR_DANGER, 100),
                               (self.radius * 2, self.radius * 2), self.radius * 2, 2)
            surface.blit(panic_surf, (int(self.x - self.radius * 2), int(self.y - self.radius * 2)))

# === ВРАГ-КАМИКАДЗЕ ===
class KamikazeEnemy(Enemy):
    """Враг, который бросается на игрока и взрывается с warning phase."""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, KAMIKAZE_HP, KAMIKAZE_RADIUS)
        self.speed = KAMIKAZE_SPEED
        self.warn_timer = 0.0
        self.exploded = False
        self.pulse_phase = 0.0
        self.warning_active = False
    
    def update(self, dt: float, player: Any) -> Optional[Any]:
        super().update(dt, player)
        self.pulse_phase += dt * 10
        
        dx = player.x - self.x
        dy = player.y - self.y
        dist = vec_length(dx, dy)
        
        if dist < KAMIKAZE_WARN_RADIUS + player.radius + 20 and not self.warning_active:
            self.warning_active = True
            self.warn_timer = KAMIKAZE_WARN_TIME
        
        if self.warning_active:
            self.warn_timer -= dt
            if self.warn_timer <= 0:
                self.warning_active = False
        
        if dist > 1:
            nx = dx / dist
            ny = dy / dist
            self.vx = lerp(self.vx, nx * self.speed, dt * 5)
            self.vy = lerp(self.vy, ny * self.speed, dt * 5)
        
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        if dist < self.radius + player.radius + 10 and not self.exploded:
            self.exploded = True
            return 'explode'
        
        return None
    
    def explode(self, game: Any) -> None:
        """Взрыв с уроном и эффектами."""
        self.alive = False
        game.particles.emit_burst(self.x, self.y, 30, COLOR_DANGER, 350.0, 1.0, 4.0)
        game.particles.emit_spiral(self.x, self.y, 20, COLOR_ACCENT, 200.0)
        game.screen_shake.trigger(10.0, 0.3, (0, 0))
        game.sound_manager.play('hit', 0.7)
        
        dist = vec_distance(self.x, self.y, game.player.x, game.player.y)
        if dist < KAMIKAZE_EXPLOSION_RADIUS:
            game.player.take_damage(KAMIKAZE_EXPLOSION_DAMAGE, game, self.x, self.y)
    
    def draw(self, surface: pygame.Surface) -> None:
        color = COLOR_DANGER if self.hit_flash <= 0 else COLOR_PRIMARY
        
        pulse = 0.8 + 0.2 * math.sin(self.pulse_phase)
        radius = int(self.radius * pulse)
        
        if self.warning_active:
            warn_t = self.warn_timer / KAMIKAZE_WARN_TIME
            warn_alpha = int(150 * (1 - warn_t))
            warn_radius = int(KAMIKAZE_WARN_RADIUS * (1 - warn_t * 0.3))
            
            warn_surf = pygame.Surface((warn_radius * 2, warn_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(warn_surf, (*COLOR_DANGER, warn_alpha),
                               (warn_radius, warn_radius), warn_radius, 3)
            surface.blit(warn_surf, (int(self.x - warn_radius), int(self.y - warn_radius)))
        
        glow_surf = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*COLOR_DANGER, 100),
                           (radius * 2, radius * 2), radius * 2)
        surface.blit(glow_surf, (int(self.x - radius * 2), int(self.y - radius * 2)))
        
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), radius)
        pygame.draw.circle(surface, COLOR_ACCENT,
                           (int(self.x), int(self.y)), radius, 2)
        
        speed = vec_length(self.vx, self.vy)
        if speed > 100:
            nx, ny = vec_normalize(self.vx, self.vy)
            end_x = self.x + nx * self.radius * 2
            end_y = self.y + ny * self.radius * 2
            pygame.draw.line(surface, COLOR_ACCENT,
                             (int(self.x), int(self.y)),
                             (int(end_x), int(end_y)), 2)

# === ДИССОНАНС-ВРАГ (v4.0: homing для отражённых пуль) ===
class DissonanceEnemy(ChaserEnemy):
    """Элитный враг со статическим шумом. Уязвим к Perfect Refraction + Синий AoE."""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = DISSONANCE_HP
        self.max_hp = DISSONANCE_HP
        self.glitch_offset = 0.0
        self.glitch_phase = 0.0
        self.speed = DISSONANCE_SPEED
    
    def take_damage(self, damage: int, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        if is_aoe and bullet_mode == 'BLUE':
            actual_damage = damage
        else:
            actual_damage = int(damage * DISSONANCE_NORMAL_DAMAGE_MULT)
        
        self.hp -= actual_damage
        self.hit_flash = 0.1
        
        self.glitch_offset = random.uniform(-5, 5)
        
        game.particles.emit_burst(self.x, self.y, 4,
                                  MODE_COLORS[bullet_mode], 150.0, 0.3, 2.0)
        
        if self.hp <= 0:
            self.alive = False
            self.on_death(game, bullet_mode)
            return True
        return False
    
    def on_perfect_refraction_hit(self, game: Any) -> None:
        """Мгновенная смерть от Perfect Refraction."""
        self.alive = False
        game.particles.emit_burst(self.x, self.y, 30, COLOR_ACCENT, 400.0, 1.0, 4.0)
        game.particles.emit_spiral(self.x, self.y, 25, COLOR_PRIMARY, 300.0)
        
        points = 500
        game.score += points * (1 + game.combo * 0.2)
        game.combo += 3
        game.max_combo = max(game.max_combo, game.combo)
        
        game.floating_texts.append(FloatingText(
            self.x, self.y, f"+{int(points)} DISSONANCE!", COLOR_ACCENT, 1.5, 24
        ))
        
        game.sound_manager.play('refraction_perfect', 0.8)
        game.screen_shake.trigger(12.0, 0.3, (0, 0))
        
        game.check_resonance_spawn(self.x, self.y, game.player.mode)
    
    def update(self, dt: float, player: Any) -> None:
        super().update(dt, player)
        self.glitch_phase += dt * 15
        if random.random() < 0.1:
            self.glitch_offset = random.uniform(-3, 3)
        else:
            self.glitch_offset *= 0.9
    
    def draw(self, surface: pygame.Surface) -> None:
        color = COLOR_DANGER if self.hit_flash <= 0 else COLOR_PRIMARY
        
        for offset in [-2, 0, 2]:
            x = int(self.x + self.glitch_offset + offset)
            y = int(self.y + offset)
            
            angle = math.atan2(self.vy, self.vx)
            points = []
            for i in range(3):
                a = angle + i * (math.pi * 2 / 3)
                px = x + math.cos(a) * self.radius
                py = y + math.sin(a) * self.radius
                points.append((px, py))
            
            alpha = 180 if offset == 0 else 80
            glitch_surf = pygame.Surface((int(self.radius * 4), int(self.radius * 4)), pygame.SRCALPHA)
            center_x = int(self.radius * 2)
            center_y = int(self.radius * 2)
            
            adjusted_points = [(int(px - x + center_x), int(py - y + center_y)) for px, py in points]
            pygame.draw.polygon(glitch_surf, (*color, alpha), adjusted_points)
            
            surface.blit(glitch_surf, (int(x - center_x), int(y - center_y)))
        
        if int(self.glitch_phase) % 3 == 0:
            for _ in range(5):
                noise_x = int(self.x + random.uniform(-self.radius, self.radius))
                noise_y = int(self.y + random.uniform(-self.radius, self.radius))
                pygame.draw.circle(surface, COLOR_PRIMARY, (noise_x, noise_y), 1)

# === POWER-UP ===
class PowerUp:
    """Подбираемый бонус."""
    
    def __init__(self, x: float, y: float, power_type: str):
        self.x = x
        self.y = y
        self.radius = POWERUP_RADIUS
        self.type = power_type
        self.lifetime = POWERUP_LIFETIME
        self.bob_phase = random.uniform(0, math.pi * 2)
        self.rotation = 0.0
    
    def update(self, dt: float) -> bool:
        self.lifetime -= dt
        self.bob_phase += dt * 3
        self.rotation += dt * 2
        return self.lifetime > 0
    
    def apply(self, game: Any) -> None:
        if self.type == 'heal':
            game.player.hp = min(game.player.max_hp,
                                 game.player.hp + POWERUP_HEAL_AMOUNT)
            game.floating_texts.append(FloatingText(
                game.player.x, game.player.y - 30,
                f"+{POWERUP_HEAL_AMOUNT} HP", COLOR_SUCCESS, 1.0, 20
            ))
        elif self.type == 'invuln':
            game.player.invuln_timer = max(game.player.invuln_timer,
                                           POWERUP_INVULN_DURATION)
            game.floating_texts.append(FloatingText(
                game.player.x, game.player.y - 30,
                "INVULN!", COLOR_ACCENT, 1.2, 22
            ))
        
        game.particles.emit_burst(self.x, self.y, 20, COLOR_SUCCESS, 250.0, 0.8, 3.0)
        game.sound_manager.play('pickup', 0.6)
    
    def draw(self, surface: pygame.Surface) -> None:
        bob = math.sin(self.bob_phase) * 4
        y_offset = bob
        color = COLOR_SUCCESS if self.type == 'heal' else COLOR_ACCENT
        
        if self.lifetime < 2.0 and int(self.lifetime * 4) % 2 == 0:
            return
        
        glow_surf = pygame.Surface((self.radius * 4, self.radius * 4), pygame.SRCALPHA)
        pulse = 0.6 + 0.4 * math.sin(self.bob_phase * 2)
        pygame.draw.circle(glow_surf, (*color, int(80 * pulse)),
                           (self.radius * 2, self.radius * 2), self.radius * 2)
        surface.blit(glow_surf, (int(self.x - self.radius * 2),
                                 int(self.y + y_offset - self.radius * 2)))
        
        size = self.radius
        angle = self.rotation
        points = []
        for i in range(4):
            a = angle + i * (math.pi / 2)
            px = self.x + math.cos(a) * size
            py = self.y + y_offset + math.sin(a) * size
            points.append((px, py))
        
        pygame.draw.polygon(surface, color, points)
        pygame.draw.polygon(surface, COLOR_PRIMARY, points, 2)
        
        if self.type == 'heal':
            pygame.draw.line(surface, COLOR_PRIMARY,
                             (int(self.x - size * 0.4), int(self.y + y_offset)),
                             (int(self.x + size * 0.4), int(self.y + y_offset)), 2)
            pygame.draw.line(surface, COLOR_PRIMARY,
                             (int(self.x), int(self.y + y_offset - size * 0.4)),
                             (int(self.x), int(self.y + y_offset + size * 0.4)), 2)
        else:
            pygame.draw.circle(surface, COLOR_PRIMARY,
                               (int(self.x), int(self.y + y_offset)),
                               int(size * 0.3))

# === CHROMATIC BUFFER ===
class ChromaticBuffer:
    """Буферизация ввода смены цвета для Идеального Преломления."""
    
    def __init__(self):
        self.last_change_time: float = -10.0
        self.last_mode: str = 'RED'
    
    def record_change(self, time: float, mode: str) -> None:
        self.last_change_time = time
        self.last_mode = mode
    
    def is_in_window(self, current_time: float) -> bool:
        return (current_time - self.last_change_time) <= PERFECT_REFRACTION_WINDOW

# === RHYTHM TRACKER ===
class RhythmTracker:
    """Отслеживает ритмический цикл (R→B→G→R)."""
    
    def __init__(self):
        self.current_step = 0
        self.cycle_complete_count = 0
        self.active = False
        self.pitch_boost = 0.0
    
    def on_kill(self, mode: str, game: Any) -> None:
        expected = RHYTHM_CYCLE[self.current_step]
        
        if mode == expected:
            self.current_step += 1
            self.pitch_boost = min(self.pitch_boost + RHYTHM_PITCH_BOOST, 0.5)
            
            if self.current_step >= len(RHYTHM_CYCLE):
                self.current_step = 0
                self.cycle_complete_count += 1
                self.on_cycle_complete(game)
            
            self.active = True
        else:
            self.current_step = 0
            self.pitch_boost = 0.0
            self.active = False
    
    def on_cycle_complete(self, game: Any) -> None:
        game.flash_alpha = 0.5
        game.flash_color = COLOR_PRIMARY
        
        game.particles.emit_spiral(game.player.x, game.player.y, 40,
                                   COLOR_ACCENT, 300.0)
        
        game.crystal.trigger_wave()
        
        game.sound_manager.play('combo', 0.7)
        
        game.floating_texts.append(FloatingText(
            game.player.x, game.player.y - 40,
            "RHYTHM!", COLOR_ACCENT, 1.2, 24
        ))
    
    def update(self, dt: float) -> None:
        if self.pitch_boost > 0 and not self.active:
            self.pitch_boost = max(0, self.pitch_boost - dt * 0.1)

# === MUSIC SYSTEM (v4.0: полноценная система) ===
class MusicSystem:
    """Процедурная музыка с синхронизацией по убийствам и таймерам."""
    
    def __init__(self, sound_manager: SoundManager):
        self.enabled = sound_manager.enabled
        self.sound_manager = sound_manager
        self.active = False
        self.kill_count = 0
        self.last_kill_mode = 'RED'
        self.note_sequence = ['melody_c', 'melody_e', 'melody_g']
        self.current_note_index = 0
        
        # v4.0: Таймеры для баса и перкуссии
        self.bass_timer = 0.0
        self.bass_interval = 0.5
        self.percussion_timer = 0.0
        self.percussion_interval = 0.25
    
    def start(self) -> None:
        if not self.enabled:
            return
        self.active = True
    
    def stop(self) -> None:
        self.active = False
    
    def on_kill(self, mode: str) -> None:
        """Воспроизведение мелодии при убийстве."""
        if not self.active or not self.enabled:
            return
        
        self.kill_count += 1
        self.last_kill_mode = mode
        
        note = self.note_sequence[self.current_note_index]
        self.sound_manager.play(note, 0.4)
        
        self.current_note_index = (self.current_note_index + 1) % len(self.note_sequence)
    
    def update(self, dt: float) -> None:
        """Обновление таймеров для баса и перкуссии."""
        if not self.active or not self.enabled:
            return
        
        # Бас каждые 0.5 сек
        self.bass_timer += dt
        if self.bass_timer >= self.bass_interval:
            self.bass_timer = 0.0
            self.sound_manager.play('bass_note', 0.3)
        
        # Перкуссия каждые 0.25 сек
        self.percussion_timer += dt
        if self.percussion_timer >= self.percussion_interval:
            self.percussion_timer = 0.0
            self.sound_manager.play('percussion_hit', 0.2)
    
    def conductor_damage(self) -> None:
        """При уроне - тишина на 2 секунды."""
        self.active = False
        pygame.time.set_timer(pygame.USEREVENT + 1, 2000)
    
    def conductor_restore(self) -> None:
        """Восстановление музыки."""
        self.active = True

# === HUD ===
class HUD:
    """Минималистичный HUD с HP-баром и Dash индикатором."""
    
    def __init__(self):
        self.font = pygame.font.SysFont("consolas", 20, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 14)
    
    def draw(self, surface: pygame.Surface, player: Any, game: Any) -> None:
        bar_x = HP_BAR_MARGIN
        bar_y = HP_BAR_MARGIN
        
        bg_rect = pygame.Rect(bar_x - 2, bar_y - 2,
                              HP_BAR_WIDTH + 4, HP_BAR_HEIGHT + 4)
        bg_surf = pygame.Surface((HP_BAR_WIDTH + 4, HP_BAR_HEIGHT + 4), pygame.SRCALPHA)
        bg_surf.fill((0, 0, 0, 128))
        surface.blit(bg_surf, (bar_x - 2, bar_y - 2))
        
        pygame.draw.rect(surface, (40, 45, 60),
                         (bar_x, bar_y, HP_BAR_WIDTH, HP_BAR_HEIGHT))
        
        hp_t = player.hp / player.max_hp
        fill_width = int(HP_BAR_WIDTH * hp_t)
        
        if hp_t > 0.6:
            hp_color = COLOR_SUCCESS
        elif hp_t > 0.3:
            hp_color = COLOR_ACCENT
        else:
            hp_color = COLOR_DANGER
        
        if fill_width > 0:
            pygame.draw.rect(surface, hp_color,
                             (bar_x, bar_y, fill_width, HP_BAR_HEIGHT))
        
        pygame.draw.rect(surface, COLOR_PRIMARY,
                         (bar_x, bar_y, HP_BAR_WIDTH, HP_BAR_HEIGHT), 2)
        
        label = self.font.render("HP", True, COLOR_TEXT)
        surface.blit(label, (bar_x + HP_BAR_WIDTH + 10, bar_y))
        
        # Dash индикатор (v4.0: Space/ПКМ)
        if player.dash_cooldown > 0:
            cd_t = 1 - (player.dash_cooldown / DASH_COOLDOWN)
            cd_width = int(100 * cd_t)
            cd_rect = pygame.Rect(HP_BAR_MARGIN, HP_BAR_MARGIN + 35, 100, 8)
            pygame.draw.rect(surface, (40, 45, 60), cd_rect)
            if cd_width > 0:
                pygame.draw.rect(surface, COLOR_ACCENT,
                                 (HP_BAR_MARGIN, HP_BAR_MARGIN + 35, cd_width, 8))
            pygame.draw.rect(surface, COLOR_PRIMARY, cd_rect, 1)
            label = self.small_font.render("DASH [SPACE/RMB]", True, COLOR_TEXT)
            surface.blit(label, (HP_BAR_MARGIN + 110, HP_BAR_MARGIN + 30))
        else:
            label = self.small_font.render("DASH READY [SPACE/RMB]", True, COLOR_SUCCESS)
            surface.blit(label, (HP_BAR_MARGIN, HP_BAR_MARGIN + 30))
        
        # v4.0: Chromatic Impulse индикатор
        if player.impulse_active:
            impulse_label = self.small_font.render("IMPULSE ACTIVE", True, MODE_COLORS[player.mode])
            surface.blit(impulse_label, (HP_BAR_MARGIN, HP_BAR_MARGIN + 55))
        
        # v4.0: Echo Chamber индикатор
        if hasattr(game, 'echo_chamber_active') and game.echo_chamber_active:
            echo_label = self.small_font.render("ECHO CHAMBER", True, COLOR_ACCENT)
            surface.blit(echo_label, (HP_BAR_MARGIN, HP_BAR_MARGIN + 75))
        
        mode_color = MODE_COLORS[player.mode]
        mode_name = player.mode
        mode_label = self.font.render(f"MODE: {mode_name}", True, mode_color)
        mode_rect = mode_label.get_rect()
        mode_rect.topright = (SCREEN_WIDTH - HP_BAR_MARGIN, HP_BAR_MARGIN)
        surface.blit(mode_label, mode_rect)
        
        wave_label = self.font.render(f"WAVE {game.wave}", True, COLOR_TEXT)
        wave_rect = wave_label.get_rect()
        wave_rect.topright = (SCREEN_WIDTH - HP_BAR_MARGIN,
                              HP_BAR_MARGIN + 30)
        surface.blit(wave_label, wave_rect)
        
        if game.show_fps:
            fps = int(game.clock.get_fps())
            fps_label = self.small_font.render(f"FPS: {fps}", True, COLOR_TEXT)
            surface.blit(fps_label, (SCREEN_WIDTH - 80, SCREEN_HEIGHT - 25))
        
        if game.god_mode:
            god_label = self.font.render("GOD MODE", True, COLOR_ACCENT)
            god_rect = god_label.get_rect()
            god_rect.center = (SCREEN_WIDTH // 2, 25)
            surface.blit(god_label, god_rect)

# === МЕНЮ ===
class Menu:
    """Меню (главное, пауза, game over)."""
    
    def __init__(self):
        self.big_font = pygame.font.SysFont("consolas", 72, bold=True)
        self.medium_font = pygame.font.SysFont("consolas", 32, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 20)
        self.pulse_phase = 0.0
    
    def update(self, dt: float) -> None:
        self.pulse_phase += dt * 2
    
    def draw_main(self, surface: pygame.Surface) -> None:
        surface.fill(COLOR_BG)
        
        grid_size = 60
        offset = int(self.pulse_phase * 20) % grid_size
        for x in range(-grid_size + offset, SCREEN_WIDTH + grid_size, grid_size):
            pygame.draw.line(surface, COLOR_BG2, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(-grid_size + offset, SCREEN_HEIGHT + grid_size, grid_size):
            pygame.draw.line(surface, COLOR_BG2, (0, y), (SCREEN_WIDTH, y), 1)
        
        pulse = 0.7 + 0.3 * math.sin(self.pulse_phase)
        title_color = color_lerp(COLOR_PRIMARY, COLOR_ACCENT, pulse)
        title = self.big_font.render("CHROMASHIFT", True, title_color)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 200))
        surface.blit(title, title_rect)
        
        subtitle = self.small_font.render(
            "Ритмичный шутер. Каждый цвет — агрегатное состояние.",
            True, COLOR_TEXT
        )
        sub_rect = subtitle.get_rect(center=(SCREEN_WIDTH // 2, 270))
        surface.blit(subtitle, sub_rect)
        
        play_pulse = int(200 + 55 * math.sin(self.pulse_phase * 2))
        play_color = (
            min(255, play_pulse),
            min(255, play_pulse),
            min(255, int(play_pulse * 1.1))
        )
        play = self.medium_font.render("[ ENTER ] НАЧАТЬ", True, play_color)
        play_rect = play.get_rect(center=(SCREEN_WIDTH // 2, 400))
        surface.blit(play, play_rect)
        
        controls = [
            "WASD - Движение",
            "ЛКМ - Стрельба",
            "SPACE/ПКМ - Dash (рывок с i-frames)",
            "1/Q - Красный (Импульс)  |  2/E - Синий (Якорь)  |  3/R - Зелёный (Текучесть)",
            "ESC - Пауза  |  F11 - Fullscreen",
        ]
        y = 480
        for text in controls:
            label = self.small_font.render(text, True, COLOR_TEXT)
            label_rect = label.get_rect(center=(SCREEN_WIDTH // 2, y))
            surface.blit(label, label_rect)
            y += 28
    
    def draw_pause(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))
        
        title = self.big_font.render("ПАУЗА", True, COLOR_ACCENT)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50))
        surface.blit(title, title_rect)
        
        hint = self.medium_font.render("ESC - продолжить", True, COLOR_TEXT)
        hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))
        surface.blit(hint, hint_rect)
    
    def draw_game_over(self, surface: pygame.Surface, score: int,
                       max_combo: int, wave: int) -> None:
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))
        
        title = self.big_font.render("GAME OVER", True, COLOR_DANGER)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 200))
        surface.blit(title, title_rect)
        
        stats = [
            (f"СЧЁТ: {int(score)}", COLOR_ACCENT),
            (f"МАКС. КОМБО: {max_combo}", COLOR_ACCENT),
            (f"ВОЛНА: {wave}", COLOR_ACCENT),
        ]
        y = 320
        for text, color in stats:
            label = self.medium_font.render(text, True, color)
            label_rect = label.get_rect(center=(SCREEN_WIDTH // 2, y))
            surface.blit(label, label_rect)
            y += 45
        
        pulse = int(200 + 55 * math.sin(self.pulse_phase * 2))
        restart_color = (
            min(255, pulse),
            min(255, pulse),
            min(255, int(pulse * 1.1))
        )
        restart = self.medium_font.render("[ R ] РЕСТАРТ", True, restart_color)
        restart_rect = restart.get_rect(center=(SCREEN_WIDTH // 2, 520))
        surface.blit(restart, restart_rect)
        
        menu = self.small_font.render("[ ESC ] В МЕНЮ", True, COLOR_TEXT)
        menu_rect = menu.get_rect(center=(SCREEN_WIDTH // 2, 560))
        surface.blit(menu, menu_rect)

# === ГЛАВНЫЙ КЛАСС ИГРЫ ===
class Game:
    """Главный класс игры. Состояния: MENU, PLAYING, PAUSED, GAME_OVER."""
    
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE
        )
        pygame.display.set_caption("CHROMASHIFT v4.0")
        self.clock = pygame.time.Clock()
        
        self.fullscreen = False
        self.god_mode = False
        self.show_fps = False
        self.running = True
        
        self.sound_manager = SoundManager()
        self.particles = ParticleManager()
        self.screen_shake = ScreenShake()
        self.chromatic_buffer = ChromaticBuffer()
        self.rhythm_tracker = RhythmTracker()
        self.crystal = PrismaticCrystal()
        self.music_system = MusicSystem(self.sound_manager)
        self.hud = HUD()
        self.menu = Menu()
        
        self.state = 'MENU'
        self.reset_game()
        
        self.render_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        
        self.bg_grid_offset = 0.0
        self.game_time = 0.0
        
        self.flash_alpha = 0.0
        self.flash_color = COLOR_PRIMARY
        
        self.resonances: List[ChromaticResonance] = []
        self.kill_streak: Dict[str, int] = {'RED': 0, 'BLUE': 0, 'GREEN': 0}
        
        # v4.0: Echo Chamber (Category 3 - Уникальность)
        self.echo_chamber_active = False
        self.echo_chamber_timer = 0.0
        self.refraction_streak = 0  # Серия Perfect Refraction
    
    def reset_game(self) -> None:
        """Полный сброс состояния для рестарта."""
        self.player = Player(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)
        self.enemies: List[Enemy] = []
        self.player_bullets: List[PlayerBullet] = []
        self.enemy_bullets: List[EnemyBullet] = []
        self.powerups: List[PowerUp] = []
        self.floating_texts: List[FloatingText] = []
        self.resonances: List[ChromaticResonance] = []
        
        self.particles.clear()
        
        self.screen_shake = ScreenShake()
        self.chromatic_buffer = ChromaticBuffer()
        self.rhythm_tracker = RhythmTracker()
        self.crystal = PrismaticCrystal()
        self.music_system = MusicSystem(self.sound_manager)
        
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.wave = 1
        self.wave_timer = 0.0
        self.wave_enemies_remaining = 0
        self.wave_spawn_timer = 0.0
        self.hitstop_timer = 0.0
        self.game_time = 0.0
        self.flash_alpha = 0.0
        self.kill_streak = {'RED': 0, 'BLUE': 0, 'GREEN': 0}
        
        # v4.0: Сброс Echo Chamber
        self.echo_chamber_active = False
        self.echo_chamber_timer = 0.0
        self.refraction_streak = 0
        
        self.start_new_wave()
    
    def start_new_wave(self) -> None:
        """Запуск новой волны."""
        is_breather = (self.wave % BREATHER_WAVE_INTERVAL == 0)
        
        if is_breather:
            enemy_count = int(BASE_ENEMIES_PER_WAVE * BREATHER_ENEMY_MULT)
        else:
            enemy_count = int(BASE_ENEMIES_PER_WAVE * (WAVE_MULTIPLIER ** (self.wave - 1)))
        
        self.wave_enemies_remaining = enemy_count
        self.wave_spawn_timer = 0.0
        
        wave_text = f"ВОЛНА {self.wave}"
        if is_breather:
            wave_text += " [BREATHER]"
        self.floating_texts.append(FloatingText(
            SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 50,
            wave_text, COLOR_ACCENT, 2.5, 48
        ))
        
        self.sound_manager.play('wave', 0.5)
        
        if is_breather:
            types = ['heal', 'invuln']
            x = random.uniform(200, SCREEN_WIDTH - 200)
            y = random.uniform(200, SCREEN_HEIGHT - 200)
            self.powerups.append(PowerUp(x, y, random.choice(types)))
    
    def spawn_enemy(self) -> None:
        """Спавн врага в случайной позиции на границе."""
        side = random.randint(0, 3)
        margin = 30
        if side == 0:
            x = random.uniform(margin, SCREEN_WIDTH - margin)
            y = -margin
        elif side == 1:
            x = SCREEN_WIDTH + margin
            y = random.uniform(margin, SCREEN_HEIGHT - margin)
        elif side == 2:
            x = random.uniform(margin, SCREEN_WIDTH - margin)
            y = SCREEN_HEIGHT + margin
        else:
            x = -margin
            y = random.uniform(margin, SCREEN_HEIGHT - margin)
        
        if self.wave < 3:
            enemy_type = random.choice(['chaser', 'kamikaze'])
        elif self.wave < 6:
            weights = [0.5, 0.3, 0.2]
            enemy_type = random.choices(
                ['chaser', 'shooter', 'kamikaze'],
                weights=weights
            )[0]
        else:
            weights = [0.4, 0.25, 0.2, 0.15]
            enemy_type = random.choices(
                ['chaser', 'shooter', 'kamikaze', 'dissonance'],
                weights=weights
            )[0]
        
        if enemy_type == 'chaser':
            self.enemies.append(ChaserEnemy(x, y))
        elif enemy_type == 'shooter':
            self.enemies.append(ShooterEnemy(x, y))
        elif enemy_type == 'kamikaze':
            self.enemies.append(KamikazeEnemy(x, y))
        elif enemy_type == 'dissonance':
            self.enemies.append(DissonanceEnemy(x, y))
    
    def check_resonance_spawn(self, x: float, y: float, mode: str) -> None:
        """Проверка и создание Хроматического Резонанса."""
        self.kill_streak[mode] += 1
        
        for m in MODE_COLORS.keys():
            if m != mode:
                self.kill_streak[m] = 0
        
        if self.kill_streak[mode] >= RESONANCE_KILL_THRESHOLD:
            self.resonances.append(ChromaticResonance(x, y, mode))
            self.kill_streak[mode] = 0
    
    def check_impulse_activation(self, mode: str) -> None:
        """v4.0: Проверка активации Chromatic Impulse (5+ убийств одного цвета)."""
        if self.kill_streak[mode] >= IMPULSE_KILL_THRESHOLD:
            self.player.impulse_active = True
            self.player.impulse_timer = 3.0  # 3 секунды piercing
            
            self.floating_texts.append(FloatingText(
                self.player.x, self.player.y - 50,
                "IMPULSE!", MODE_COLORS[mode], 1.5, 28
            ))
            
            self.kill_streak[mode] = 0
    
    def activate_echo_chamber(self) -> None:
        """v4.0: Активация Echo Chamber (3 Refraction подряд)."""
        self.echo_chamber_active = True
        self.echo_chamber_timer = ECHO_DURATION
        self.refraction_streak = 0
        
        self.floating_texts.append(FloatingText(
            SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2,
            "ECHO CHAMBER!", COLOR_ACCENT, 2.0, 36
        ))
        
        self.particles.emit_spiral(self.player.x, self.player.y, 50, COLOR_ACCENT, 400.0)
        self.sound_manager.play('combo', 0.8)
    
    def is_in_resonance(self, x: float, y: float, mode: str) -> bool:
        """Проверка находится ли точка в резонансе своего цвета."""
        for resonance in self.resonances:
            if resonance.color_mode == mode:
                dist = vec_distance(x, y, resonance.x, resonance.y)
                if dist < resonance.radius:
                    return True
        return False
    
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        
        elif event.type == pygame.USEREVENT + 1:
            self.music_system.conductor_restore()
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                self.fullscreen = not self.fullscreen
                flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
                self.screen = pygame.display.set_mode(
                    (SCREEN_WIDTH, SCREEN_HEIGHT), flags
                )
            elif event.key == pygame.K_F1:
                self.show_fps = not self.show_fps
            elif event.key == pygame.K_g:
                self.god_mode = not self.god_mode
            
            if self.state == 'MENU':
                if event.key == pygame.K_RETURN:
                    self.state = 'PLAYING'
                    self.reset_game()
            
            elif self.state == 'PLAYING':
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_p:
                    self.state = 'PAUSED'
                elif event.key in (pygame.K_1, pygame.K_q):
                    self.player.set_mode('RED', self)
                    self.chromatic_buffer.record_change(self.game_time, 'RED')
                elif event.key in (pygame.K_2, pygame.K_e):
                    self.player.set_mode('BLUE', self)
                    self.chromatic_buffer.record_change(self.game_time, 'BLUE')
                    if self.combo >= CRYSTAL_STAGE_2:
                        self.crystal.trigger_wave()
                elif event.key in (pygame.K_3, pygame.K_r):
                    self.player.set_mode('GREEN', self)
                    self.chromatic_buffer.record_change(self.game_time, 'GREEN')
            
            elif self.state == 'PAUSED':
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_p:
                    self.state = 'PLAYING'
            
            elif self.state == 'GAME_OVER':
                if event.key == pygame.K_r:
                    self.state = 'PLAYING'
                    self.reset_game()
                elif event.key == pygame.K_ESCAPE:
                    self.state = 'MENU'
        
        # v4.0: Dash через ПКМ
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:  # ПКМ
                if self.state == 'PLAYING':
                    self.player.start_dash(self)
    
    def update_playing(self, dt: float) -> None:
        self.game_time += dt
        self.bg_grid_offset += dt * 20
        
        keys = pygame.key.get_pressed()
        self.player.update(dt, keys, self.sound_manager, self.game_time, self)
        
        # v4.0: Стрельба через ЛКМ
        if pygame.mouse.get_pressed()[0]:
            if self.is_in_resonance(self.player.x, self.player.y, self.player.mode):
                if self.player.fire_cooldown > FIRE_COOLDOWN * 0.7:
                    self.player.fire_cooldown = FIRE_COOLDOWN * 0.7
            self.player.shoot(self)
        
        self.crystal.update(dt, self.player.x, self.player.y,
                            self.player.mode, self.combo)
        
        self.rhythm_tracker.update(dt)
        
        # v4.0: MusicSystem update
        self.music_system.update(dt)
        
        # v4.0: Echo Chamber таймер
        if self.echo_chamber_active:
            self.echo_chamber_timer -= dt
            if self.echo_chamber_timer <= 0:
                self.echo_chamber_active = False
        
        self.wave_timer += dt
        if self.wave_enemies_remaining > 0:
            self.wave_spawn_timer += dt
            if self.wave_spawn_timer >= WAVE_SPAWN_INTERVAL:
                self.wave_spawn_timer = 0
                self.spawn_enemy()
                self.wave_enemies_remaining -= 1
        elif len(self.enemies) == 0:
            self.wave += 1
            self.start_new_wave()
        
        for enemy in self.enemies:
            result = enemy.update(dt, self.player)
            if isinstance(result, EnemyBullet):
                self.enemy_bullets.append(result)
            elif result == 'explode' and isinstance(enemy, KamikazeEnemy):
                enemy.explode(self)
        
        self.player_bullets = [b for b in self.player_bullets if b.update(dt)]
        
        # v4.0: Обновление пуль врагов с передачей game для Echo Chamber
        self.enemy_bullets = [b for b in self.enemy_bullets if b.update(dt, self)]
        
        self.powerups = [p for p in self.powerups if p.update(dt)]
        
        self.resonances = [r for r in self.resonances if r.update(dt)]
        
        self.particles.update(dt)
        
        self.floating_texts = [t for t in self.floating_texts if t.update(dt)]
        
        self.screen_shake.update(dt)
        
        if self.flash_alpha > 0:
            self.flash_alpha = max(0, self.flash_alpha - dt * 5)
        
        # КОЛЛИЗИИ
        
        # 1. Пули игрока vs враги
        bullets_to_remove = []
        for i, bullet in enumerate(self.player_bullets):
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                
                # v4.0: Piercing - пропускаем уже ударенных врагов
                if bullet.is_piercing and enemy.id in bullet.hit_enemies:
                    continue
                
                if circle_collision(bullet.x, bullet.y, bullet.radius,
                                    enemy.x, enemy.y, enemy.radius):
                    if isinstance(enemy, DissonanceEnemy) and bullet.is_refracted:
                        enemy.on_perfect_refraction_hit(self)
                    else:
                        damage_mult = 1.0
                        if self.is_in_resonance(self.player.x, self.player.y, self.player.mode):
                            damage_mult = 1.0 + RESONANCE_DAMAGE_BOOST
                        
                        enemy.take_damage(int(bullet.damage * damage_mult), 
                                         self, bullet.mode)
                    
                    # v4.0: Piercing - добавляем врага в список ударенных
                    if bullet.is_piercing:
                        bullet.hit_enemies.append(enemy.id)
                    else:
                        bullets_to_remove.append(i)
                    break
        
        for i in sorted(bullets_to_remove, reverse=True):
            if i < len(self.player_bullets):
                self.player_bullets.pop(i)
        
        # 2. Пули врагов vs игрок
        bullets_to_remove = []
        for i, bullet in enumerate(self.enemy_bullets):
            if circle_collision(bullet.x, bullet.y, bullet.radius,
                                self.player.x, self.player.y, self.player.radius):
                
                if self.chromatic_buffer.is_in_window(self.game_time):
                    self.perfect_refraction(bullet)
                    bullets_to_remove.append(i)
                else:
                    self.player.take_damage(bullet.damage, self,
                                            bullet.x, bullet.y)
                    bullets_to_remove.append(i)
        
        for i in sorted(bullets_to_remove, reverse=True):
            if i < len(self.enemy_bullets):
                self.enemy_bullets.pop(i)
        
        # 3. Враги vs игрок (контакт)
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            if circle_collision(enemy.x, enemy.y, enemy.radius,
                                self.player.x, self.player.y, self.player.radius):
                if isinstance(enemy, ChaserEnemy):
                    self.player.take_damage(CHASER_DAMAGE, self, enemy.x, enemy.y)
                elif isinstance(enemy, KamikazeEnemy) and not enemy.exploded:
                    enemy.explode(self)
        
        # 4. Powerups vs игрок
        powerups_to_remove = []
        for i, powerup in enumerate(self.powerups):
            if circle_collision(powerup.x, powerup.y, powerup.radius,
                                self.player.x, self.player.y, self.player.radius):
                powerup.apply(self)
                powerups_to_remove.append(i)
        
        for i in sorted(powerups_to_remove, reverse=True):
            if i < len(self.powerups):
                self.powerups.pop(i)
        
        self.enemies = [e for e in self.enemies if e.alive]
    
    def perfect_refraction(self, bullet: EnemyBullet) -> None:
        """Идеальное преломление — парирование пули сменой цвета."""
        self.hitstop_timer = HITSTOP_DURATION
        
        source_dir_x = -bullet.dx
        source_dir_y = -bullet.dy
        
        self.screen_shake.trigger(8.0, 0.2, (source_dir_x, source_dir_y))
        
        # v4.0: Homing для Dissonance
        homing_target = None
        for enemy in self.enemies:
            if isinstance(enemy, DissonanceEnemy) and enemy.alive:
                dist = vec_distance(bullet.x, bullet.y, enemy.x, enemy.y)
                if dist < 200:
                    homing_target = enemy
                    break
        
        if homing_target:
            dx = homing_target.x - bullet.x
            dy = homing_target.y - bullet.y
            source_dir_x, source_dir_y = vec_normalize(dx, dy)
        
        reflected = PlayerBullet(
            bullet.x, bullet.y,
            source_dir_x, source_dir_y,
            self.player.mode
        )
        reflected.speed = bullet.speed * 2
        reflected.damage = bullet.damage * 3
        reflected.is_refracted = True
        self.player_bullets.append(reflected)
        
        self.particles.emit_burst(bullet.x, bullet.y, REFRACTION_PARTICLES,
                                  MODE_COLORS[self.player.mode], 400.0, 0.8, 4.0)
        self.sound_manager.play('refraction_perfect', 0.7)
        
        self.floating_texts.append(FloatingText(
            bullet.x, bullet.y - 20, "REFRACT!", COLOR_ACCENT, 1.0, 22
        ))
        
        self.combo += 2
        self.max_combo = max(self.max_combo, self.combo)
        self.score += 500
        
        # v4.0: Echo Chamber - серия Refraction
        self.refraction_streak += 1
        if self.refraction_streak >= ECHO_REFRACTION_THRESHOLD:
            self.activate_echo_chamber()
        
        self.music_system.conductor_restore()
    
    def player_died(self) -> None:
        """Смерть игрока."""
        self.state = 'GAME_OVER'
        self.particles.emit_burst(self.player.x, self.player.y,
                                  PLAYER_DEATH_PARTICLES, COLOR_PRIMARY,
                                  400.0, 1.5, 5.0)
        self.screen_shake.trigger(15.0, 0.5, (0, 0))
        self.flash_alpha = 0.8
        self.flash_color = COLOR_DANGER
        self.sound_manager.play('death', 0.8)
        self.music_system.stop()
    
    def update(self, dt: float) -> None:
        self.menu.update(dt)
        
        if self.state == 'PLAYING':
            self.update_playing(dt)
    
    def draw_background(self, surface: pygame.Surface) -> None:
        surface.fill(COLOR_BG)
        
        grid_size = 60
        offset = int(self.bg_grid_offset) % grid_size
        for x in range(-grid_size + offset, SCREEN_WIDTH + grid_size, grid_size):
            pygame.draw.line(surface, COLOR_BG2, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(-grid_size + offset, SCREEN_HEIGHT + grid_size, grid_size):
            pygame.draw.line(surface, COLOR_BG2, (0, y), (SCREEN_WIDTH, y), 1)
    
    def draw(self) -> None:
        self.render_surface.fill(COLOR_BG)
        self.draw_background(self.render_surface)
        
        if self.state == 'MENU':
            self.menu.draw_main(self.render_surface)
        elif self.state in ('PLAYING', 'PAUSED', 'GAME_OVER'):
            for resonance in self.resonances:
                resonance.draw(self.render_surface)
            
            for powerup in self.powerups:
                powerup.draw(self.render_surface)
            
            for bullet in self.enemy_bullets:
                bullet.draw(self.render_surface)
            
            for bullet in self.player_bullets:
                bullet.draw(self.render_surface)
            
            for enemy in self.enemies:
                enemy.draw(self.render_surface)
            
            if self.state != 'GAME_OVER':
                self.player.draw(self.render_surface, self.game_time)
            
            if self.state != 'GAME_OVER':
                self.crystal.draw(self.render_surface,
                                  self.player.x, self.player.y,
                                  self.player.mode, self.combo,
                                  self.game_time)
            
            self.particles.draw(self.render_surface)
            
            for text in self.floating_texts:
                text.draw(self.render_surface)
            
            if self.state != 'GAME_OVER':
                self.hud.draw(self.render_surface, self.player, self)
            
            if self.state == 'PAUSED':
                self.menu.draw_pause(self.render_surface)
            elif self.state == 'GAME_OVER':
                self.menu.draw_game_over(self.render_surface, self.score,
                                         self.max_combo, self.wave)
        
        if self.flash_alpha > 0:
            flash_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            flash_surf.fill((*self.flash_color, int(255 * self.flash_alpha)))
            self.render_surface.blit(flash_surf, (0, 0))
        
        self.screen.fill(COLOR_BG)
        self.screen_shake.apply(self.screen, self.render_surface)
        
        pygame.display.flip()
    
    def run(self) -> None:
        """Главный игровой цикл."""
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            dt = min(dt, 0.05)
            
            for event in pygame.event.get():
                self.handle_event(event)
            
            if self.hitstop_timer > 0:
                self.hitstop_timer -= dt
                self.screen_shake.update(dt)
            else:
                self.update(dt)
            
            self.draw()
        
        pygame.quit()
        sys.exit()

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    game = Game()
    game.run()
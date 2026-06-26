# === ИМПОРТЫ ===
import pygame
import sys
import math
import random
import json
import os
import logging
from typing import List, Tuple, Optional, Dict, Any, Set

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# Настройка логирования
logging.basicConfig(level=logging.WARNING, format='[%(levelname)s] %(message)s')
logger = logging.getLogger('ChromaShift')

# === GAME CONFIG (SINGLETON + HOT-RELOAD) ===
class GameConfig:
    """Singleton-конфигурация с hot-reload из config.json."""
    _instance: Optional['GameConfig'] = None
    _file_mtime: float = 0.0
    _config_path: str = "chromashift_config.json"
    
    def __new__(cls) -> 'GameConfig':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._defaults = self._get_defaults()
        self._values: Dict[str, Any] = dict(self._defaults)
        self._load()
    
    def _get_defaults(self) -> Dict[str, Any]:
        """Все магические числа игры."""
        return {
            # Экран
            'SCREEN_WIDTH': 1280,
            'SCREEN_HEIGHT': 720,
            'TARGET_FPS': 60,
            
            # Цвета (как кортежи)
            'COLOR_BG': (10, 12, 20),
            'COLOR_BG2': (22, 28, 45),
            'COLOR_PRIMARY': (230, 240, 255),
            'COLOR_ACCENT': (255, 215, 100),
            'COLOR_DANGER': (255, 60, 80),
            'COLOR_SUCCESS': (100, 255, 150),
            'COLOR_TEXT': (240, 245, 255),
            'COLOR_RED': (255, 50, 80),
            'COLOR_BLUE': (60, 140, 255),
            'COLOR_GREEN': (80, 255, 140),
            
            # Физика режимов
            'RED_ACCEL': 2400.0, 'RED_DECEL': 3.5, 'RED_MAX_SPEED': 520.0, 'RED_RECOIL': 0.05,
            'BLUE_ACCEL': 900.0, 'BLUE_DECEL': 32.0, 'BLUE_MAX_SPEED': 280.0,
            'BLUE_RECOIL': 0.15, 'BLUE_AOE_RADIUS': 80.0,
            'GREEN_ACCEL': 1400.0, 'GREEN_DECEL': 5.5, 'GREEN_MAX_SPEED': 420.0,
            'GREEN_RECOIL': 0.0, 'GREEN_LATERAL_DRIFT': 0.12,
            
            # Игрок
            'PLAYER_RADIUS': 14, 'PLAYER_MAX_HP': 100,
            'PLAYER_INVULN_TIME': 1.2, 'PLAYER_SQUASH_DURATION': 0.15,
            
            # Dash
            'DASH_SPEED': 900.0, 'DASH_DURATION': 0.15, 'DASH_COOLDOWN': 1.5,
            'DASH_KILL_REDUCTION': 0.3, 'DASH_INVULN_FRAMES': 0.2,
            
            # Стрельба
            'FIRE_COOLDOWN': 0.14, 'BULLET_SPEED': 820.0,
            'BULLET_LIFETIME': 1.6, 'BULLET_RADIUS': 4, 'BULLET_DAMAGE': 25,
            
            # Chromatic Impulse
            'IMPULSE_KILL_THRESHOLD': 5,
            
            # Echo Chamber
            'ECHO_REFRACTION_THRESHOLD': 3, 'ECHO_DURATION': 5.0,
            'ECHO_SLOWDOWN_MULT': 0.7,
            
            # Perfect Refraction
            'PERFECT_REFRACTION_WINDOW': 0.25,
            'PARRY_INDICATOR_RADIUS': 90.0,
            'PARRY_WARNING_RADIUS': 200.0,
            
            # Враги
            'CHASER_SPEED': 155.0, 'CHASER_HP': 50, 'CHASER_RADIUS': 13, 'CHASER_DAMAGE': 15,
            'SHOOTER_SPEED': 95.0, 'SHOOTER_HP': 40, 'SHOOTER_RADIUS': 14,
            'SHOOTER_FIRE_INTERVAL': 1.6, 'SHOOTER_BULLET_SPEED': 310.0,
            'SHOOTER_BULLET_DAMAGE': 10, 'SHOOTER_BULLET_RADIUS': 5,
            'SHOOTER_PANIC_DISTANCE': 150.0,
            'KAMIKAZE_SPEED': 290.0, 'KAMIKAZE_HP': 30, 'KAMIKAZE_RADIUS': 12,
            'KAMIKAZE_EXPLOSION_RADIUS': 65, 'KAMIKAZE_EXPLOSION_DAMAGE': 30,
            'KAMIKAZE_WARN_TIME': 1.0, 'KAMIKAZE_WARN_RADIUS': 80.0,
            'DISSONANCE_HP': 250, 'DISSONANCE_RADIUS': 15, 'DISSONANCE_SPEED': 120.0,
            'DISSONANCE_NORMAL_DAMAGE_MULT': 0.2, 'DISSONANCE_HOMING_STRENGTH': 0.3,
            
            # Волны
            'BASE_ENEMIES_PER_WAVE': 4, 'WAVE_MULTIPLIER': 1.18,
            'WAVE_SPAWN_INTERVAL': 0.6, 'BREATHER_WAVE_INTERVAL': 5,
            'BREATHER_ENEMY_MULT': 0.5,
            
            # Частицы
            'MAX_PARTICLES': 300, 'PARTICLE_POOL_SIZE': 500,
            'PARTICLE_LIFETIME': 0.8, 'ENEMY_DEATH_PARTICLES': 18,
            'SHOOT_PARTICLES': 10, 'PLAYER_DEATH_PARTICLES': 35,
            'HIT_PARTICLES': 6, 'REFRACTION_PARTICLES': 25,
            
            # Screen shake
            'SHAKE_DURATION': 0.25, 'SHAKE_DECAY': 8.0,
            
            # Flash
            'FLASH_DURATION': 0.12,
            
            # Hit-stop
            'HITSTOP_DURATION': 0.07,
            
            # Chromatic buffer
            'BUFFER_WINDOW': 0.12,
            
            # Ритм
            'BEAT_INTERVAL': 0.5, 'BEAT_WINDOW': 0.18,
            
            # Power-ups
            'POWERUP_SPEED': 50.0, 'POWERUP_RADIUS': 11,
            'POWERUP_LIFETIME': 12.0, 'POWERUP_HEAL_AMOUNT': 30,
            'POWERUP_INVULN_DURATION': 5.0, 'POWERUP_SPAWN_CHANCE': 0.12,
            
            # UI
            'HP_BAR_WIDTH': 280, 'HP_BAR_HEIGHT': 18, 'HP_BAR_MARGIN': 20,
            
            # Кристалл
            'CRYSTAL_STAGE_1': 3, 'CRYSTAL_STAGE_2': 7,
            
            # Резонанс
            'RESONANCE_RADIUS': 100.0, 'RESONANCE_LIFETIME': 8.0,
            'RESONANCE_KILL_THRESHOLD': 3, 'RESONANCE_SPEED_BOOST': 0.25,
            'RESONANCE_DAMAGE_BOOST': 0.50, 'RESONANCE_DRIFT_SPEED': 20.0,
            
            # Meta
            'META_SAVE_FILE': "chromashift_save.json",
            'META_POINTS_PER_1000_SCORE': 1,
            
            # SpatialHash
            'SPATIAL_CELL_SIZE': 100,
        }
    
    def _load(self) -> None:
        """Загрузка из config.json (если есть)."""
        try:
            if os.path.exists(self._config_path):
                GameConfig._file_mtime = os.path.getmtime(self._config_path)
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if key in self._defaults:
                            self._values[key] = value
        except Exception as e:
            logger.warning(f"Config load error: {e}")
    
    def check_for_changes(self) -> bool:
        """Hot-reload: проверяет mtime файла."""
        try:
            if os.path.exists(self._config_path):
                mtime = os.path.getmtime(self._config_path)
                if mtime > GameConfig._file_mtime:
                    GameConfig._file_mtime = mtime
                    self._load()
                    logger.info("Config reloaded (hot-reload)")
                    return True
        except Exception:
            pass
        return False
    
    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._values:
            return self._values[name]
        raise AttributeError(f"Config has no attribute '{name}'")
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

# Глобальный конфиг
CFG = GameConfig()

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

# === SURFACE CACHE ===
class SurfaceCache:
    """Кэширование Surface для предотвращения аллокаций в draw()."""
    _cache: Dict[Tuple, pygame.Surface] = {}
    
    @classmethod
    def get_glow(cls, radius: int, color: Tuple[int, int, int], alpha: int = 255) -> pygame.Surface:
        key = ('glow', radius, color, alpha)
        if key not in cls._cache:
            size = radius * 4
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, alpha), (size // 2, size // 2), radius)
            cls._cache[key] = surf
        return cls._cache[key]
    
    @classmethod
    def get_circle(cls, radius: int, color: Tuple[int, int, int], alpha: int = 255) -> pygame.Surface:
        key = ('circle', radius, color, alpha)
        if key not in cls._cache:
            size = radius * 2 + 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, alpha), (radius + 1, radius + 1), radius)
            cls._cache[key] = surf
        return cls._cache[key]
    
    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()

# === SPATIAL HASH (ОПТИМИЗАЦИЯ КОЛЛИЗИЙ) ===
class SpatialHash:
    """Spatial hash для O(1) запросов коллизий."""
    
    def __init__(self, cell_size: int = None):
        self.cell_size = cell_size if cell_size is not None else CFG.SPATIAL_CELL_SIZE
        self.cells: Dict[Tuple[int, int], List[Any]] = {}
    
    def _key(self, x: float, y: float) -> Tuple[int, int]:
        return (int(x // self.cell_size), int(y // self.cell_size))
    
    def clear(self) -> None:
        self.cells.clear()
    
    def insert(self, obj: Any) -> None:
        """Вставка объекта (должен иметь x, y, radius)."""
        r = getattr(obj, 'radius', 0)
        x, y = obj.x, obj.y
        min_cx = int((x - r) // self.cell_size)
        max_cx = int((x + r) // self.cell_size)
        min_cy = int((y - r) // self.cell_size)
        max_cy = int((y + r) // self.cell_size)
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                key = (cx, cy)
                if key not in self.cells:
                    self.cells[key] = []
                self.cells[key].append(obj)
    
    def query(self, x: float, y: float, radius: float) -> List[Any]:
        """Запрос объектов в радиусе."""
        result: List[Any] = []
        seen: Set[int] = set()
        min_cx = int((x - radius) // self.cell_size)
        max_cx = int((x + radius) // self.cell_size)
        min_cy = int((y - radius) // self.cell_size)
        max_cy = int((y + radius) // self.cell_size)
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                key = (cx, cy)
                if key in self.cells:
                    for obj in self.cells[key]:
                        obj_id = id(obj)
                        if obj_id not in seen:
                            seen.add(obj_id)
                            result.append(obj)
        return result

# === ЗВУКОВОЙ МЕНЕДЖЕР ===
class SoundManager:
    """Менеджер звуков с процедурным синтезом и защитой от крашей."""
    
    def __init__(self):
        self.enabled = False
        self.sounds: Dict[str, Any] = {}
        self._failed_sounds: Set[str] = set()
        
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.enabled = True
            self._generate_sounds()
        except Exception as e:
            logger.warning(f"Sound init failed: {e}")
            self.enabled = False
    
    def _generate_sounds(self) -> None:
        if not self.enabled:
            return
        
        self.sounds['shoot_red'] = self._synth(1200, 400, 60, 'sine', 0.25)
        self.sounds['shoot_blue'] = self._synth(200, 80, 150, 'sine', 0.2)
        self.sounds['shoot_green'] = self._synth(800, 1200, 100, 'sine', 0.2)
        
        self.sounds['refraction'] = self._synth(2000, 500, 80, 'sine', 0.35)
        self.sounds['hit'] = self._synth(150, 50, 200, 'sine', 0.3)
        self.sounds['death'] = self._synth(300, 50, 400, 'saw', 0.4)
        self.sounds['enemy_death'] = self._synth(500, 100, 120, 'sine', 0.2)
        self.sounds['pickup'] = self._synth_arpeggio([262, 330, 392], 60, 0.2)
        self.sounds['wave'] = self._synth(100, 400, 300, 'sine', 0.25)
        self.sounds['refraction_perfect'] = self._synth(2500, 800, 100, 'sine', 0.4)
        self.sounds['combo'] = self._synth(600, 1200, 100, 'sine', 0.25)
        self.sounds['dash'] = self._synth(400, 800, 80, 'sine', 0.3)
        
        self.sounds['mode_red'] = self._synth(600, 800, 50, 'sine', 0.2)
        self.sounds['mode_blue'] = self._synth(300, 200, 80, 'sine', 0.2)
        self.sounds['mode_green'] = self._synth(500, 700, 60, 'sine', 0.2)
        
        self.sounds['beat_kill'] = self._synth(800, 1200, 80, 'sine', 0.3)
        self.sounds['error'] = self._synth(150, 80, 150, 'square', 0.3)
        
        self.sounds['bass_note'] = self._synth(80, 80, 200, 'sine', 0.3)
        self.sounds['percussion_hit'] = self._synth(2000, 1000, 50, 'noise', 0.2)
        self.sounds['melody_c'] = self._synth(262, 262, 150, 'sine', 0.25)
        self.sounds['melody_e'] = self._synth(330, 330, 150, 'sine', 0.25)
        self.sounds['melody_g'] = self._synth(392, 392, 150, 'sine', 0.25)
    
    def _synth(self, freq_start: float, freq_end: float, duration_ms: int,
               wave_type: str, volume: float) -> Optional[Any]:
        if not self.enabled:
            return None
        
        sample_rate = 44100
        n_samples = int(sample_rate * duration_ms / 1000)
        
        try:
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
                
                return pygame.sndarray.make_sound(stereo.copy())
            else:
                samples = []
                attack_samples = int(n_samples * 0.04)
                release_start = int(n_samples * 0.75)
                
                for i in range(n_samples):
                    t = i / sample_rate
                    progress = i / n_samples
                    freq = freq_start + (freq_end - freq_start) * progress
                    value = math.sin(2 * math.pi * freq * t)
                    
                    if i < attack_samples:
                        env = i / attack_samples
                    elif i > release_start:
                        env = (n_samples - i) / (n_samples - release_start)
                    else:
                        env = 1.0
                    
                    value *= env * volume
                    val_int = int(value * 16384)
                    samples.extend([val_int, val_int])
                
                return pygame.mixer.Sound(buffer=bytes(samples))
        except Exception as e:
            logger.warning(f"Sound synth failed: {e}")
            return None
    
    def _synth_arpeggio(self, freqs: List[float], note_ms: int, volume: float) -> Optional[Any]:
        if not self.enabled:
            return None
        
        sample_rate = 44100
        total_samples = int(sample_rate * note_ms / 1000 * len(freqs))
        
        try:
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
                    release = int(length * 0.4)
                    env = np.ones(length)
                    env[-release:] = np.linspace(1, 0, release)
                    wave[start:end] = note * env * volume
                
                wave_16 = np.int16(wave * 32767)
                stereo = np.column_stack((wave_16, wave_16))
                return pygame.sndarray.make_sound(stereo.copy())
        except Exception as e:
            logger.warning(f"Arpeggio synth failed: {e}")
        return None
    
    def play(self, name: str, volume: float = 1.0) -> None:
        if not self.enabled or name not in self.sounds or name in self._failed_sounds:
            return
        sound = self.sounds[name]
        if sound is None:
            return
        try:
            sound.set_volume(volume)
            sound.play()
        except Exception as e:
            logger.warning(f"Sound play failed '{name}': {e}")
            self._failed_sounds.add(name)
            if len(self._failed_sounds) > 10:
                logger.warning("Too many sound failures, disabling sound")
                self.enabled = False

# === PARTICLE + POOL ===
class Particle:
    """Частица с reset() для переиспользования."""
    
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.color: Tuple[int, int, int] = (255, 255, 255)
        self.lifetime = 0.0
        self.max_lifetime = 0.0
        self.size = 3.0
        self.gravity = 0.0
        self.active = False
    
    def reset(self, x: float, y: float, vx: float, vy: float,
              color: Tuple[int, int, int], lifetime: float,
              size: float = 3.0, gravity: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.size = size
        self.gravity = gravity
        self.active = True
    
    def update(self, dt: float) -> bool:
        if not self.active:
            return False
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.96
        self.vy *= 0.96
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.active = False
            return False
        return True
    
    def draw(self, surface: pygame.Surface) -> None:
        if not self.active:
            return
        t = self.lifetime / self.max_lifetime
        size = int(self.size * (0.3 + 0.7 * t))
        if size < 1:
            size = 1
        color = color_lerp(CFG.COLOR_BG, self.color, t)
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), size)


class ParticlePool:
    """Object pool для частиц."""
    
    def __init__(self, size: int = None):
        pool_size = size if size is not None else CFG.PARTICLE_POOL_SIZE
        self._pool: List[Particle] = [Particle() for _ in range(pool_size)]
        self._index = 0
        self._size = pool_size
    
    def get(self) -> Particle:
        """Получить частицу из пула (round-robin)."""
        p = self._pool[self._index]
        self._index = (self._index + 1) % self._size
        return p


class ParticleManager:
    """Управляет всеми частицами с пулом для стабильного FPS."""
    
    def __init__(self):
        self.pool = ParticlePool()
        self.active: List[Particle] = []
    
    def emit_burst(self, x: float, y: float, count: int,
                   color: Tuple[int, int, int], speed: float = 250.0,
                   lifetime: float = 0.8, size: float = 3.5,
                   gravity: float = 50.0) -> None:
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            s = speed * random.uniform(0.3, 1.0)
            vx = math.cos(angle) * s
            vy = math.sin(angle) * s
            p = self.pool.get()
            p.reset(x, y, vx, vy, color, lifetime, size, gravity)
            self.active.append(p)
        
        max_p = CFG.MAX_PARTICLES
        if len(self.active) > max_p:
            self.active = self.active[-max_p:]
    
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
            p = self.pool.get()
            p.reset(x, y, vx, vy, color, lifetime, size, 0)
            self.active.append(p)
        
        max_p = CFG.MAX_PARTICLES
        if len(self.active) > max_p:
            self.active = self.active[-max_p:]
    
    def emit_spiral(self, x: float, y: float, count: int,
                    color: Tuple[int, int, int], speed: float = 200.0) -> None:
        for i in range(count):
            angle = (i / count) * math.pi * 2
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            p = self.pool.get()
            p.reset(x, y, vx, vy, color, 1.2, 4.0, 0)
            self.active.append(p)
        
        max_p = CFG.MAX_PARTICLES
        if len(self.active) > max_p:
            self.active = self.active[-max_p:]
    
    def update(self, dt: float) -> None:
        self.active = [p for p in self.active if p.update(dt)]
    
    def draw(self, surface: pygame.Surface) -> None:
        for p in self.active:
            p.draw(surface)
    
    def clear(self) -> None:
        self.active.clear()

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
    
    def trigger(self, intensity: float, duration: float = None,
                direction: Optional[Tuple[float, float]] = None) -> None:
        if duration is None:
            duration = CFG.SHAKE_DURATION
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
            self.offset_x = random.uniform(-self.intensity, self.intensity)
            self.offset_y = random.uniform(-self.intensity, self.intensity)
        else:
            self.offset_x = self.dir_x * self.intensity * math.sin(self.duration * 40)
            self.offset_y = self.dir_y * self.intensity * math.sin(self.duration * 40)
        
        self.intensity *= math.exp(-CFG.SHAKE_DECAY * dt)
    
    def apply(self, surface: pygame.Surface, temp_surface: pygame.Surface) -> None:
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
        color = color_lerp(CFG.COLOR_BG, self.color, t)
        text_surf = self.font.render(self.text, True, color)
        text_surf.set_alpha(alpha)
        rect = text_surf.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(text_surf, rect)

# === PARRY INDICATOR (С WARNING ZONE) ===
class ParryIndicator:
    """Визуальный индикатор окна для Perfect Refraction с warning zone."""
    
    def __init__(self):
        self.active = False
        self.warning_active = False
        self.timer = 0.0
        self.warning_timer = 0.0
        self.max_timer = CFG.PERFECT_REFRACTION_WINDOW
        self.warning_max = 0.5
        self.pulse_phase = 0.0
    
    def trigger(self) -> None:
        """Активировать активный индикатор (жёлтое кольцо)."""
        self.active = True
        self.timer = self.max_timer
    
    def start_warning(self) -> None:
        """Активировать warning zone (мигание)."""
        if not self.warning_active:
            self.warning_active = True
            self.warning_timer = self.warning_max
    
    def update(self, dt: float) -> None:
        self.pulse_phase += dt * 8
        if self.active:
            self.timer -= dt
            if self.timer <= 0:
                self.active = False
        if self.warning_active:
            self.warning_timer -= dt
            if self.warning_timer <= 0:
                self.warning_active = False
    
    def draw(self, surface: pygame.Surface, px: float, py: float) -> None:
        # Warning zone — мигающее внешнее кольцо
        if self.warning_active:
            pulse = 0.5 + 0.5 * math.sin(self.pulse_phase)
            warn_r = CFG.PARRY_WARNING_RADIUS
            alpha = int(80 * pulse * (self.warning_timer / self.warning_max))
            if alpha > 5:
                warn_surf = pygame.Surface((int(warn_r * 2 + 4), int(warn_r * 2 + 4)), pygame.SRCALPHA)
                center = int(warn_r + 2)
                pygame.draw.circle(warn_surf, (*CFG.COLOR_ACCENT, alpha), (center, center), int(warn_r), 2)
                surface.blit(warn_surf, (int(px - center), int(py - center)))
        
        # Active parry ring
        if self.active:
            t = self.timer / self.max_timer
            r = CFG.PLAYER_RADIUS + (CFG.PARRY_INDICATOR_RADIUS - CFG.PLAYER_RADIUS) * t
            alpha = int(255 * t)
            ring_surf = pygame.Surface((int(r * 2 + 4), int(r * 2 + 4)), pygame.SRCALPHA)
            center = int(r + 2)
            pygame.draw.circle(ring_surf, (*CFG.COLOR_ACCENT, alpha), (center, center), int(r), 3)
            surface.blit(ring_surf, (int(px - center), int(py - center)))

# === BEAT SYNC TRACKER ===
class BeatSyncTracker:
    """Отслеживает убийства в такт музыкальному басу."""
    
    def __init__(self):
        self.beat_window = CFG.BEAT_WINDOW
        self.last_beat_time = 0.0
        self.beat_kill_count = 0
    
    def on_beat(self, game_time: float) -> None:
        self.last_beat_time = game_time
    
    def on_kill(self, game: Any) -> None:
        time_since = game.game_time - self.last_beat_time
        beat_interval = CFG.BEAT_INTERVAL
        
        if time_since < self.beat_window or time_since > (beat_interval - self.beat_window):
            self.beat_kill_count += 1
            game.score += 150
            game.particles.emit_burst(game.player.x, game.player.y, 10, CFG.COLOR_ACCENT, 200.0, 0.5)
            game.floating_texts.append(FloatingText(
                game.player.x, game.player.y - 30, "BEAT!", CFG.COLOR_ACCENT, 0.8, 20
            ))
            game.sound_manager.play('beat_kill', 0.3)
            
            if self.beat_kill_count >= 10:
                self.beat_kill_count = 0
                game.crystal.trigger_wave()

# === TELEMETRY ===
class Telemetry:
    """Сбор статистики для анализа геймплея."""
    
    def __init__(self):
        self.deaths_at_wave: Dict[int, int] = {}
        self.refraction_attempts = 0
        self.refraction_successes = 0
        self.session_start_time = 0.0
        self.total_playtime = 0.0
        self.max_wave_reached = 0
    
    def on_death(self, wave: int, game_time: float) -> None:
        self.deaths_at_wave[wave] = self.deaths_at_wave.get(wave, 0) + 1
        self.max_wave_reached = max(self.max_wave_reached, wave)
        self.total_playtime += game_time - self.session_start_time
    
    def on_refraction_attempt(self, success: bool) -> None:
        self.refraction_attempts += 1
        if success:
            self.refraction_successes += 1
    
    def get_refraction_success_rate(self) -> float:
        if self.refraction_attempts == 0:
            return 0.0
        return (self.refraction_successes / self.refraction_attempts) * 100
    
    def dump(self) -> str:
        return (
            f"Telemetry Report:\n"
            f"  Max Wave: {self.max_wave_reached}\n"
            f"  Total Playtime: {self.total_playtime:.1f}s\n"
            f"  Refraction Success Rate: {self.get_refraction_success_rate():.1f}%\n"
            f"  Deaths by Wave: {dict(sorted(self.deaths_at_wave.items()))}"
        )

# === META PROGRESSION (С UPGRADE TREE) ===
class MetaProgression:
    """Система персистентных улучшений между сессиями."""
    
    def __init__(self):
        self.chromatic_points = 0
        self.upgrade_tree: Dict[str, Dict[str, Any]] = self._default_tree()
        self.load()
    
    def _default_tree(self) -> Dict[str, Dict[str, Any]]:
        return {
            'max_hp': {
                'name': 'Chromatic Vitality',
                'desc': '+10 Max HP per level',
                'max_lvl': 3,
                'costs': [100, 250, 500],
                'current_lvl': 0,
            },
            'dash_cd': {
                'name': 'Phase Shift',
                'desc': '-10% Dash Cooldown',
                'max_lvl': 3,
                'costs': [150, 300, 600],
                'current_lvl': 0,
            },
            'refract_win': {
                'name': 'Temporal Lens',
                'desc': '+0.03s Refraction Window',
                'max_lvl': 2,
                'costs': [200, 400],
                'current_lvl': 0,
            },
        }
    
    def load(self) -> None:
        save_file = CFG.META_SAVE_FILE
        try:
            if os.path.exists(save_file):
                with open(save_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.chromatic_points = data.get('chromatic_points', 0)
                    
                    # Миграция: если нет upgrade_tree или он старый
                    saved_tree = data.get('upgrade_tree', data.get('upgrades', None))
                    if saved_tree is None:
                        # Старый формат — сброс
                        self.upgrade_tree = self._default_tree()
                    else:
                        # Миграция: проверяем каждый ключ
                        default = self._default_tree()
                        for key in default:
                            if key in saved_tree:
                                saved = saved_tree[key]
                                # Поддержка старого формата (просто число)
                                if isinstance(saved, (int, float)):
                                    default[key]['current_lvl'] = min(
                                        int(saved), default[key]['max_lvl']
                                    )
                                elif isinstance(saved, dict) and 'current_lvl' in saved:
                                    default[key]['current_lvl'] = min(
                                        int(saved['current_lvl']), default[key]['max_lvl']
                                    )
                        self.upgrade_tree = default
        except Exception as e:
            logger.warning(f"Meta load error: {e}")
            self.upgrade_tree = self._default_tree()
    
    def save(self) -> None:
        save_file = CFG.META_SAVE_FILE
        try:
            data = {
                'chromatic_points': self.chromatic_points,
                'upgrade_tree': self.upgrade_tree,
            }
            with open(save_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Meta save error: {e}")
    
    def add_points(self, score: int) -> None:
        points = score // 1000 * CFG.META_POINTS_PER_1000_SCORE
        self.chromatic_points += points
        self.save()
    
    def can_purchase(self, key: str) -> bool:
        if key not in self.upgrade_tree:
            return False
        upg = self.upgrade_tree[key]
        lvl = upg['current_lvl']
        if lvl >= upg['max_lvl']:
            return False
        cost = upg['costs'][lvl]
        return self.chromatic_points >= cost
    
    def purchase(self, key: str) -> bool:
        if not self.can_purchase(key):
            return False
        upg = self.upgrade_tree[key]
        cost = upg['costs'][upg['current_lvl']]
        self.chromatic_points -= cost
        upg['current_lvl'] += 1
        self.save()
        return True
    
    def get_max_hp_bonus(self) -> int:
        return self.upgrade_tree['max_hp']['current_lvl'] * 10
    
    def get_dash_cooldown_mult(self) -> float:
        lvl = self.upgrade_tree['dash_cd']['current_lvl']
        return 1.0 - (lvl * 0.10)
    
    def get_refraction_window_bonus(self) -> float:
        lvl = self.upgrade_tree['refract_win']['current_lvl']
        return lvl * 0.03

# === JUICE SYSTEM ===
class JuiceSystem:
    """Динамический game feel — управляет shake, частицами, flash."""
    
    def __init__(self):
        self.accumulated_impact = 0.0
        self.decay_rate = 5.0
    
    def trigger_impact(self, impact_force: float, color: Tuple[int, int, int],
                       game: Any) -> None:
        """
        impact_force: 1.0 — мелкий враг, 2.0 — камикадзе, 3.0 — диссонанс
        """
        self.accumulated_impact = min(self.accumulated_impact + impact_force, 10.0)
        
        # Screen shake
        shake_intensity = 4.0 * impact_force
        shake_duration = 0.15 * impact_force
        dir_x = game.player.x - game._last_impact_x
        dir_y = game.player.y - game._last_impact_y
        game.screen_shake.trigger(shake_intensity, shake_duration, (dir_x, dir_y))
        
        # Частицы — больше при высоком комбо
        base_particles = int(CFG.ENEMY_DEATH_PARTICLES * impact_force)
        particle_count = int(base_particles * (1 + game.combo * 0.05))
        particle_count = min(particle_count, 50)
        game.particles.emit_burst(
            game._last_impact_x, game._last_impact_y,
            particle_count, color, 300.0 * impact_force, 0.9, 3.5
        )
        
        # Flash при больших импактах
        if impact_force >= 2.5:
            game.flash_alpha = max(game.flash_alpha, 0.3)
            game.flash_color = color
    
    def update(self, dt: float) -> None:
        self.accumulated_impact *= math.exp(-self.decay_rate * dt)

# === ПРИЗМАТИЧЕСКИЙ КРИСТАЛЛ ===
class PrismaticCrystal:
    """Диегетический UI для комбо."""
    
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
        
        if combo >= CFG.CRYSTAL_STAGE_1:
            offset_x = math.cos(self.rotation) * 15
            offset_y = math.sin(self.rotation) * 15
            crystal_x = player_x + offset_x
            crystal_y = player_y + offset_y
            mode_colors = {
                'RED': CFG.COLOR_RED,
                'BLUE': CFG.COLOR_BLUE,
                'GREEN': CFG.COLOR_GREEN,
            }
            color = mode_colors[player_mode]
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
        mode_colors = {
            'RED': CFG.COLOR_RED,
            'BLUE': CFG.COLOR_BLUE,
            'GREEN': CFG.COLOR_GREEN,
        }
        color = mode_colors[player_mode]
        
        for x, y, alpha, trail_color in self.trail:
            if alpha > 0.05:
                size = int(5 * alpha)
                trail_surf = SurfaceCache.get_circle(size, trail_color, int(100 * alpha))
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        if combo < CFG.CRYSTAL_STAGE_1:
            offset_x = -10
            offset_y = 0
            crystal_x = player_x + offset_x
            crystal_y = player_y + offset_y
            
            size = 6
            dim_color = color_lerp(CFG.COLOR_BG, color, 0.4)
            points = [
                (crystal_x, crystal_y - size),
                (crystal_x + size, crystal_y),
                (crystal_x, crystal_y + size),
                (crystal_x - size, crystal_y),
            ]
            pygame.draw.polygon(surface, dim_color, points)
            pygame.draw.polygon(surface, color_lerp(CFG.COLOR_BG, color, 0.7), points, 1)
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
            
            if combo >= CFG.CRYSTAL_STAGE_2:
                pulse = 0.5 + 0.5 * math.sin(self.pulse_phase)
                glow_size = int(size + 4 * pulse)
                glow_surf = SurfaceCache.get_glow(glow_size, color, int(80 * pulse))
                surface.blit(glow_surf, (int(crystal_x - glow_size * 2),
                                         int(crystal_y - glow_size * 2)))
            
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, CFG.COLOR_PRIMARY, points, 1)
        
        if self.wave_active and combo >= CFG.CRYSTAL_STAGE_2:
            t = 1 - (self.wave_radius / 80)
            alpha = int(200 * t)
            if alpha > 0:
                wave_surf = pygame.Surface((200, 200), pygame.SRCALPHA)
                pygame.draw.circle(wave_surf, (*color, alpha),
                                   (100, 100), int(self.wave_radius), 3)
                surface.blit(wave_surf, (int(player_x - 100), int(player_y - 100)))

# === ХРОМАТИЧЕСКИЙ РЕЗОНАНС ===
class ChromaticResonance:
    """Цветные пятна на полу от убийств одного цвета."""
    
    def __init__(self, x: float, y: float, color_mode: str):
        self.x = x
        self.y = y
        self.color_mode = color_mode
        mode_colors = {
            'RED': CFG.COLOR_RED,
            'BLUE': CFG.COLOR_BLUE,
            'GREEN': CFG.COLOR_GREEN,
        }
        self.color = mode_colors[color_mode]
        self.radius = CFG.RESONANCE_RADIUS
        self.lifetime = CFG.RESONANCE_LIFETIME
        self.max_lifetime = CFG.RESONANCE_LIFETIME
        self.pulse_phase = 0.0
        
        self.drift_x = random.uniform(-1, 1)
        self.drift_y = random.uniform(-1, 1)
        self.drift_x, self.drift_y = vec_normalize(self.drift_x, self.drift_y)
    
    def update(self, dt: float) -> bool:
        self.lifetime -= dt
        self.pulse_phase += dt * 2
        
        self.x += self.drift_x * CFG.RESONANCE_DRIFT_SPEED * dt
        self.y += self.drift_y * CFG.RESONANCE_DRIFT_SPEED * dt
        
        sw = CFG.SCREEN_WIDTH
        sh = CFG.SCREEN_HEIGHT
        self.x = clamp(self.x, self.radius, sw - self.radius)
        self.y = clamp(self.y, self.radius, sh - self.radius)
        
        return self.lifetime > 0
    
    def draw(self, surface: pygame.Surface) -> None:
        t = self.lifetime / self.max_lifetime
        alpha = int(120 * t)
        
        pulse = 0.8 + 0.2 * math.sin(self.pulse_phase)
        draw_radius = int(self.radius * pulse)
        
        glow_surf = SurfaceCache.get_glow(draw_radius, self.color, int(alpha * 0.3))
        surface.blit(glow_surf, (int(self.x - draw_radius * 2), int(self.y - draw_radius * 2)))
        
        resonance_surf = SurfaceCache.get_circle(draw_radius, self.color, alpha)
        surface.blit(resonance_surf, (int(self.x - draw_radius), int(self.y - draw_radius)))
        
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), draw_radius, 2)

# === ИГРОК ===
class Player:
    """Игрок с тремя физическими режимами и Dash."""
    
    def __init__(self, x: float, y: float, meta: MetaProgression):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.radius = CFG.PLAYER_RADIUS
        self.max_hp = CFG.PLAYER_MAX_HP + meta.get_max_hp_bonus()
        self.hp = self.max_hp
        self.mode = 'RED'
        self.invuln_timer = 0.0
        self.fire_cooldown = 0.0
        self.facing_x = 0.0
        self.facing_y = -1.0
        self.trail: List[Tuple[float, float, float]] = []
        self.squash_timer = 0.0
        self.squash_scale = 1.0
        self.invuln_flash = 0.0
        
        self.dash_cooldown = 0.0
        self.dash_cooldown_max = CFG.DASH_COOLDOWN * meta.get_dash_cooldown_mult()
        self.is_dashing = False
        self.dash_timer = 0.0
        self.dash_invuln = False
        
        self.impulse_active = False
        self.impulse_timer = 0.0
    
    def set_mode(self, mode: str, game: Any) -> None:
        if mode != self.mode:
            self.mode = mode
            if mode == 'BLUE':
                self.squash_timer = CFG.PLAYER_SQUASH_DURATION
            
            sound_map = {'RED': 'mode_red', 'BLUE': 'mode_blue', 'GREEN': 'mode_green'}
            game.sound_manager.play(sound_map[mode], 0.4)
    
    def start_dash(self, game: Any) -> None:
        if self.dash_cooldown > 0 or self.is_dashing:
            return
        
        if vec_length(self.facing_x, self.facing_y) < 0.1:
            return
        
        self.is_dashing = True
        self.dash_timer = CFG.DASH_DURATION
        self.dash_invuln = True
        self.dash_cooldown = self.dash_cooldown_max
        
        self.squash_timer = 0.2
        self.squash_scale = 1.3
        
        game.sound_manager.play('dash', 0.5)
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        game.particles.emit_burst(self.x, self.y, 15, mode_colors[self.mode], 300.0, 0.5, 3.0)
    
    def update(self, dt: float, keys: Any, mouse_pos: Tuple[int, int], game: Any) -> None:
        if self.invuln_timer > 0:
            self.invuln_timer -= dt
            self.invuln_flash += dt * 8
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt
        if self.dash_cooldown > 0:
            self.dash_cooldown -= dt
        if self.squash_timer > 0:
            self.squash_timer -= dt
            t = self.squash_timer / CFG.PLAYER_SQUASH_DURATION
            if t > 0.5:
                self.squash_scale = lerp(0.8, 1.1, (1 - t) * 2)
            else:
                self.squash_scale = lerp(1.1, 1.0, (0.5 - t) * 2)
        else:
            self.squash_scale = 1.0
        
        if self.impulse_active:
            self.impulse_timer -= dt
            if self.impulse_timer <= 0:
                self.impulse_active = False
        
        mx, my = mouse_pos
        dx_m, dy_m = mx - self.x, my - self.y
        if vec_length(dx_m, dy_m) > 10:
            self.facing_x, self.facing_y = vec_normalize(dx_m, dy_m)
        
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
        
        if keys[pygame.K_SPACE]:
            self.start_dash(game)
        
        if dx != 0 or dy != 0:
            dx, dy = vec_normalize(dx, dy)
        
        if self.is_dashing:
            self.dash_timer -= dt
            self.dash_invuln = True
            
            self.vx = self.facing_x * CFG.DASH_SPEED
            self.vy = self.facing_y * CFG.DASH_SPEED
            
            if len(self.trail) < 8:
                self.trail.append((self.x, self.y, 1.5))
            
            if self.dash_timer <= 0:
                self.is_dashing = False
                self.dash_invuln = False
                self.vx *= 0.5
                self.vy *= 0.5
        else:
            if self.mode == 'RED':
                if dx != 0 or dy != 0:
                    self.vx += dx * CFG.RED_ACCEL * dt
                    self.vy += dy * CFG.RED_ACCEL * dt
                else:
                    decay = math.exp(-CFG.RED_DECEL * dt)
                    self.vx *= decay
                    self.vy *= decay
                speed = vec_length(self.vx, self.vy)
                if speed > CFG.RED_MAX_SPEED:
                    self.vx = (self.vx / speed) * CFG.RED_MAX_SPEED
                    self.vy = (self.vy / speed) * CFG.RED_MAX_SPEED
                    
            elif self.mode == 'BLUE':
                if dx != 0 or dy != 0:
                    self.vx += dx * CFG.BLUE_ACCEL * dt
                    self.vy += dy * CFG.BLUE_ACCEL * dt
                else:
                    decay = math.exp(-CFG.BLUE_DECEL * dt)
                    self.vx *= decay
                    self.vy *= decay
                speed = vec_length(self.vx, self.vy)
                if speed > CFG.BLUE_MAX_SPEED:
                    self.vx = (self.vx / speed) * CFG.BLUE_MAX_SPEED
                    self.vy = (self.vy / speed) * CFG.BLUE_MAX_SPEED
                    
            elif self.mode == 'GREEN':
                if dx != 0 or dy != 0:
                    self.vx += dx * CFG.GREEN_ACCEL * dt
                    self.vy += dy * CFG.GREEN_ACCEL * dt
                else:
                    decay = math.exp(-CFG.GREEN_DECEL * dt)
                    self.vx *= decay
                    self.vy *= decay
                speed = vec_length(self.vx, self.vy)
                if speed > 10 and speed > CFG.GREEN_MAX_SPEED:
                    self.vx = (self.vx / speed) * CFG.GREEN_MAX_SPEED
                    self.vy = (self.vy / speed) * CFG.GREEN_MAX_SPEED
                elif speed > 10:
                    perp_x = -self.vy
                    perp_y = self.vx
                    drift_strength = CFG.GREEN_LATERAL_DRIFT * math.sin(game.game_time * 5)
                    self.vx += perp_x * drift_strength * dt * 60
                    self.vy += perp_y * drift_strength * dt * 60
        
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        sw = CFG.SCREEN_WIDTH
        sh = CFG.SCREEN_HEIGHT
        self.x = clamp(self.x, self.radius, sw - self.radius)
        self.y = clamp(self.y, self.radius, sh - self.radius)
        
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
        if self.fire_cooldown > 0:
            return False
        
        self.fire_cooldown = CFG.FIRE_COOLDOWN
        
        aim_x, aim_y = self.facing_x, self.facing_y
        
        is_piercing = self.impulse_active
        
        bullet = PlayerBullet(
            self.x + aim_x * self.radius * 1.3,
            self.y + aim_y * self.radius * 1.3,
            aim_x, aim_y, self.mode, is_piercing
        )
        game.player_bullets.append(bullet)
        
        if self.mode == 'RED':
            self.vx -= aim_x * CFG.RED_MAX_SPEED * CFG.RED_RECOIL
            self.vy -= aim_y * CFG.RED_MAX_SPEED * CFG.RED_RECOIL
        elif self.mode == 'BLUE':
            self.vx -= aim_x * CFG.BLUE_MAX_SPEED * CFG.BLUE_RECOIL
            self.vy -= aim_y * CFG.BLUE_MAX_SPEED * CFG.BLUE_RECOIL
            self.squash_timer = CFG.PLAYER_SQUASH_DURATION * 0.7
            self.blue_aoe_attack(game)
        
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        game.particles.emit_directional(
            self.x + aim_x * self.radius * 1.3,
            self.y + aim_y * self.radius * 1.3,
            CFG.SHOOT_PARTICLES, (aim_x, aim_y), 0.4,
            mode_colors[self.mode], 350.0, 0.3, 2.0
        )
        
        sound_map = {'RED': 'shoot_red', 'BLUE': 'shoot_blue', 'GREEN': 'shoot_green'}
        game.sound_manager.play(sound_map[self.mode], 0.5)
        
        return True
    
    def blue_aoe_attack(self, game: Any) -> None:
        game.particles.emit_burst(self.x, self.y, 15, CFG.COLOR_BLUE, 200.0, 0.5, 3.0)
        
        # Используем SpatialHash для AOE
        nearby = game.spatial_hash.query(self.x, self.y, CFG.BLUE_AOE_RADIUS + 50)
        for enemy in nearby:
            if not hasattr(enemy, 'alive') or not enemy.alive:
                continue
            dist = vec_distance(self.x, self.y, enemy.x, enemy.y)
            if dist < CFG.BLUE_AOE_RADIUS + enemy.radius:
                if isinstance(enemy, DissonanceEnemy):
                    enemy.take_damage(CFG.BULLET_DAMAGE, game, 'BLUE', is_aoe=True)
                else:
                    enemy.take_damage(int(CFG.BULLET_DAMAGE * 0.5), game, 'BLUE', is_aoe=True)
    
    def take_damage(self, damage: int, game: Any, source_x: float, source_y: float) -> None:
        if self.invuln_timer > 0 or self.dash_invuln or game.god_mode:
            return
        
        self.hp -= damage
        self.invuln_timer = CFG.PLAYER_INVULN_TIME
        
        dir_x = self.x - source_x
        dir_y = self.y - source_y
        game.screen_shake.trigger(12.0, CFG.SHAKE_DURATION, (dir_x, dir_y))
        
        game.particles.emit_burst(self.x, self.y, 12, CFG.COLOR_DANGER, 280.0, 0.6, 3.0)
        
        game.floating_texts.append(FloatingText(
            self.x, self.y - 20, f"-{damage}", CFG.COLOR_DANGER, 0.8, 20
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
            fade_t = self.invuln_timer / CFG.PLAYER_INVULN_TIME
            alpha = int(128 + 127 * math.sin(fade_t * math.pi * 8))
        else:
            alpha = 255
        
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        color = mode_colors[self.mode]
        for x, y, trail_alpha in self.trail:
            size = int(self.radius * trail_alpha * 0.8)
            if size > 0:
                trail_surf = SurfaceCache.get_circle(size, color, int(80 * trail_alpha))
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        scale = self.squash_scale
        rx = int(self.radius * scale)
        ry = int(self.radius * (2 - scale))
        
        glow_surf = SurfaceCache.get_glow(rx, color, int(60 * (0.5 + 0.3 * math.sin(time * 4)) * alpha / 255))
        surface.blit(glow_surf, (int(self.x - rx * 2), int(self.y - ry * 2)))
        
        body_surf = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(body_surf, (*color, alpha), (0, 0, rx * 2, ry * 2))
        surface.blit(body_surf, (int(self.x - rx), int(self.y - ry)))
        
        pygame.draw.ellipse(surface, CFG.COLOR_PRIMARY,
                            (int(self.x - rx), int(self.y - ry), rx * 2, ry * 2), 2)
        
        core_size = int(rx * 0.4)
        core_surf = SurfaceCache.get_circle(core_size, CFG.COLOR_PRIMARY, alpha)
        surface.blit(core_surf, (int(self.x - core_size), int(self.y - core_size)))
        
        aim_x = self.x + self.facing_x * (self.radius + 15)
        aim_y = self.y + self.facing_y * (self.radius + 15)
        pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(aim_x), int(aim_y)), 3)
        
        if self.impulse_active:
            impulse_surf = pygame.Surface((self.radius * 6, self.radius * 6), pygame.SRCALPHA)
            pulse = 0.5 + 0.5 * math.sin(time * 10)
            pygame.draw.circle(impulse_surf, (*color, int(100 * pulse)),
                               (self.radius * 3, self.radius * 3), int(self.radius * 2.5), 2)
            surface.blit(impulse_surf, (int(self.x - self.radius * 3), int(self.y - self.radius * 3)))

# === ПУЛЯ ИГРОКА ===
class PlayerBullet:
    def __init__(self, x: float, y: float, dx: float, dy: float, mode: str, is_piercing: bool = False):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.mode = mode
        self.radius = CFG.BULLET_RADIUS
        self.lifetime = CFG.BULLET_LIFETIME
        self.damage = CFG.BULLET_DAMAGE
        self.speed = CFG.BULLET_SPEED
        self.trail: List[Tuple[float, float, float]] = []
        self.is_refracted = False
        self.is_piercing = is_piercing
        self.hit_enemies: List[int] = []
    
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
        
        sw = CFG.SCREEN_WIDTH
        sh = CFG.SCREEN_HEIGHT
        return (self.lifetime > 0 and
                0 <= self.x <= sw and
                0 <= self.y <= sh)
    
    def draw(self, surface: pygame.Surface) -> None:
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        color = mode_colors[self.mode]
        for x, y, alpha in self.trail:
            size = int(self.radius * alpha * 0.8)
            if size > 0:
                trail_surf = SurfaceCache.get_circle(size, color, int(120 * alpha))
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        draw_radius = self.radius * 1.5 if self.is_piercing else self.radius
        
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(draw_radius))
        pygame.draw.circle(surface, CFG.COLOR_PRIMARY,
                           (int(self.x), int(self.y)), int(draw_radius) - 1)

# === ПУЛЯ ВРАГА ===
class EnemyBullet:
    def __init__(self, x: float, y: float, dx: float, dy: float,
                 speed: float = None, damage: int = None):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.speed = speed if speed is not None else CFG.SHOOTER_BULLET_SPEED
        self.damage = damage if damage is not None else CFG.SHOOTER_BULLET_DAMAGE
        self.radius = CFG.SHOOTER_BULLET_RADIUS
        self.lifetime = 4.0
        self.trail: List[Tuple[float, float, float]] = []
        self.slowed = False
    
    def update(self, dt: float, game: Any) -> bool:
        speed_mult = CFG.ECHO_SLOWDOWN_MULT if game.echo_chamber_active else 1.0
        
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
                -20 <= self.x <= CFG.SCREEN_WIDTH + 20 and
                -20 <= self.y <= CFG.SCREEN_HEIGHT + 20)
    
    def draw(self, surface: pygame.Surface) -> None:
        for x, y, alpha in self.trail:
            size = int(self.radius * alpha * 0.7)
            if size > 0:
                trail_surf = SurfaceCache.get_circle(size, CFG.COLOR_DANGER, int(150 * alpha))
                surface.blit(trail_surf, (int(x - size - 1), int(y - size - 1)))
        
        pygame.draw.circle(surface, CFG.COLOR_DANGER, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, CFG.COLOR_ACCENT,
                           (int(self.x), int(self.y)), self.radius - 1)

# === БАЗОВЫЙ ВРАГ ===
class Enemy:
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
        self.id = id(self)
    
    def take_damage(self, damage: int, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        self.hp -= damage
        self.hit_flash = 0.1
        
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        game.particles.emit_burst(self.x, self.y, CFG.HIT_PARTICLES,
                                  mode_colors[bullet_mode], 200.0, 0.4, 2.0)
        
        if self.hp <= 0:
            self.alive = False
            self.on_death(game, bullet_mode)
            return True
        return False
    
    def on_death(self, game: Any, killer_mode: str) -> None:
        # JuiceSystem — динамический game feel
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        color = mode_colors[killer_mode]
        
        impact_force = 1.0
        if isinstance(self, KamikazeEnemy):
            impact_force = 2.0
        elif isinstance(self, DissonanceEnemy):
            impact_force = 3.0
        
        game._last_impact_x = self.x
        game._last_impact_y = self.y
        game.juice_system.trigger_impact(impact_force, color, game)
        
        points = 100
        game.score += points * (1 + game.combo * 0.1)
        game.combo += 1
        game.max_combo = max(game.max_combo, game.combo)
        
        game.floating_texts.append(FloatingText(
            self.x, self.y, f"+{int(points)}", CFG.COLOR_ACCENT, 1.0, 16
        ))
        
        game.beat_tracker.on_kill(game)
        
        game.sound_manager.play('enemy_death', 0.4)
        
        if hasattr(game, 'music_system'):
            game.music_system.on_kill(killer_mode)
        
        game.player.dash_cooldown = max(0, game.player.dash_cooldown - CFG.DASH_KILL_REDUCTION)
        
        if random.random() < CFG.POWERUP_SPAWN_CHANCE:
            types = ['heal', 'invuln']
            game.powerups.append(PowerUp(self.x, self.y, random.choice(types)))
        
        game.check_resonance_spawn(self.x, self.y, killer_mode)
        game.check_impulse_activation(killer_mode)
    
    def update(self, dt: float, player: Any) -> None:
        if self.hit_flash > 0:
            self.hit_flash -= dt
    
    def draw(self, surface: pygame.Surface) -> None:
        pass

# === ВРАГ-ПРЕСЛЕДОВАТЕЛЬ ===
class ChaserEnemy(Enemy):
    def __init__(self, x: float, y: float):
        super().__init__(x, y, CFG.CHASER_HP, CFG.CHASER_RADIUS)
        self.speed = CFG.CHASER_SPEED
        self.wobble_phase = random.uniform(0, math.pi * 2)
        self.flank_direction = random.choice([-1, 1])
    
    def update(self, dt: float, player: Any) -> None:
        super().update(dt, player)
        self.wobble_phase += dt * 3
        
        dx = player.x - self.x
        dy = player.y - self.y
        dist = vec_length(dx, dy)
        
        if dist > 0.001:
            nx = dx / dist
            ny = dy / dist
            
            perp_x = -ny * self.flank_direction
            perp_y = nx * self.flank_direction
            
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
        else:
            # Защита от деления на ноль — случайное направление
            angle = random.uniform(0, math.pi * 2)
            self.vx = math.cos(angle) * self.speed * 0.5
            self.vy = math.sin(angle) * self.speed * 0.5
        
        self.x += self.vx * dt
        self.y += self.vy * dt
    
    def draw(self, surface: pygame.Surface) -> None:
        color = CFG.COLOR_DANGER if self.hit_flash <= 0 else CFG.COLOR_PRIMARY
        
        angle = math.atan2(self.vy, self.vx)
        points = []
        for i in range(3):
            a = angle + i * (math.pi * 2 / 3)
            px = self.x + math.cos(a) * self.radius
            py = self.y + math.sin(a) * self.radius
            points.append((px, py))
        
        pygame.draw.polygon(surface, color, points)
        pygame.draw.polygon(surface, CFG.COLOR_PRIMARY, points, 2)
        
        pygame.draw.circle(surface, CFG.COLOR_ACCENT,
                           (int(self.x), int(self.y)), int(self.radius * 0.4))

# === ВРАГ-СТРЕЛОК ===
class ShooterEnemy(Enemy):
    def __init__(self, x: float, y: float):
        super().__init__(x, y, CFG.SHOOTER_HP, CFG.SHOOTER_RADIUS)
        self.speed = CFG.SHOOTER_SPEED
        self.fire_timer = random.uniform(0.5, CFG.SHOOTER_FIRE_INTERVAL)
        self.preferred_distance = 350.0
        self.orbit_angle = random.uniform(0, math.pi * 2)
        self.panic_mode = False
    
    def update(self, dt: float, player: Any) -> Optional[Any]:
        super().update(dt, player)
        self.fire_timer -= dt
        
        dx = player.x - self.x
        dy = player.y - self.y
        dist = vec_length(dx, dy)
        
        if dist > 0.001:
            if dist < CFG.SHOOTER_PANIC_DISTANCE:
                self.panic_mode = True
                nx = -dx / dist
                ny = -dy / dist
                self.vx = lerp(self.vx, nx * self.speed * 1.5, dt * 3)
                self.vy = lerp(self.vy, ny * self.speed * 1.5, dt * 3)
                if self.fire_timer <= 0:
                    self.fire_timer = CFG.SHOOTER_FIRE_INTERVAL * 0.5
            else:
                self.panic_mode = False
                
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
        else:
            self.panic_mode = False
        
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        sw = CFG.SCREEN_WIDTH
        sh = CFG.SCREEN_HEIGHT
        self.x = clamp(self.x, self.radius + 20, sw - self.radius - 20)
        self.y = clamp(self.y, self.radius + 20, sh - self.radius - 20)
        
        if self.fire_timer <= 0 and dist < 500:
            self.fire_timer = CFG.SHOOTER_FIRE_INTERVAL
            if dist > 0.001:
                bullet_dx, bullet_dy = vec_normalize(dx, dy)
                bullet = EnemyBullet(self.x, self.y, bullet_dx, bullet_dy)
                return bullet
        return None
    
    def draw(self, surface: pygame.Surface) -> None:
        color = CFG.COLOR_DANGER if self.hit_flash <= 0 else CFG.COLOR_PRIMARY
        
        half = self.radius
        rect = pygame.Rect(int(self.x - half), int(self.y - half),
                           int(half * 2), int(half * 2))
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, CFG.COLOR_PRIMARY, rect, 2)
        
        charge_t = 1 - (self.fire_timer / CFG.SHOOTER_FIRE_INTERVAL)
        if charge_t > 0.7:
            pygame.draw.circle(surface, CFG.COLOR_ACCENT,
                               (int(self.x), int(self.y)),
                               int(self.radius * 0.5 * (charge_t - 0.7) / 0.3))
        
        if self.panic_mode:
            panic_surf = SurfaceCache.get_circle(int(self.radius * 2), CFG.COLOR_DANGER, 100)
            surface.blit(panic_surf, (int(self.x - self.radius * 2), int(self.y - self.radius * 2)))

# === ВРАГ-КАМИКАДЗЕ ===
class KamikazeEnemy(Enemy):
    def __init__(self, x: float, y: float):
        super().__init__(x, y, CFG.KAMIKAZE_HP, CFG.KAMIKAZE_RADIUS)
        self.speed = CFG.KAMIKAZE_SPEED
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
        
        if dist < CFG.KAMIKAZE_WARN_RADIUS + player.radius + 20 and not self.warning_active:
            self.warning_active = True
            self.warn_timer = CFG.KAMIKAZE_WARN_TIME
        
        if self.warning_active:
            self.warn_timer -= dt
            if self.warn_timer <= 0:
                self.warning_active = False
        
        if dist > 0.001:
            nx = dx / dist
            ny = dy / dist
            self.vx = lerp(self.vx, nx * self.speed, dt * 5)
            self.vy = lerp(self.vy, ny * self.speed, dt * 5)
        else:
            angle = random.uniform(0, math.pi * 2)
            self.vx = math.cos(angle) * self.speed * 0.5
            self.vy = math.sin(angle) * self.speed * 0.5
        
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        if dist < self.radius + player.radius + 10 and not self.exploded:
            self.exploded = True
            return 'explode'
        
        return None
    
    def explode(self, game: Any) -> None:
        self.alive = False
        game.particles.emit_burst(self.x, self.y, 30, CFG.COLOR_DANGER, 350.0, 1.0, 4.0)
        game.particles.emit_spiral(self.x, self.y, 20, CFG.COLOR_ACCENT, 200.0)
        game.screen_shake.trigger(10.0, 0.3, (0, 0))
        game.sound_manager.play('hit', 0.7)
        
        dist = vec_distance(self.x, self.y, game.player.x, game.player.y)
        if dist < CFG.KAMIKAZE_EXPLOSION_RADIUS:
            game.player.take_damage(CFG.KAMIKAZE_EXPLOSION_DAMAGE, game, self.x, self.y)
    
    def draw(self, surface: pygame.Surface) -> None:
        color = CFG.COLOR_DANGER if self.hit_flash <= 0 else CFG.COLOR_PRIMARY
        
        pulse = 0.8 + 0.2 * math.sin(self.pulse_phase)
        radius = int(self.radius * pulse)
        
        if self.warning_active:
            warn_t = self.warn_timer / CFG.KAMIKAZE_WARN_TIME
            warn_alpha = int(150 * (1 - warn_t))
            warn_radius = int(CFG.KAMIKAZE_WARN_RADIUS * (1 - warn_t * 0.3))
            
            warn_surf = pygame.Surface((warn_radius * 2, warn_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(warn_surf, (*CFG.COLOR_DANGER, warn_alpha),
                               (warn_radius, warn_radius), warn_radius, 3)
            surface.blit(warn_surf, (int(self.x - warn_radius), int(self.y - warn_radius)))
        
        glow_surf = SurfaceCache.get_glow(radius * 2, CFG.COLOR_DANGER, 100)
        surface.blit(glow_surf, (int(self.x - radius * 2), int(self.y - radius * 2)))
        
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), radius)
        pygame.draw.circle(surface, CFG.COLOR_ACCENT,
                           (int(self.x), int(self.y)), radius, 2)
        
        speed = vec_length(self.vx, self.vy)
        if speed > 100:
            nx, ny = vec_normalize(self.vx, self.vy)
            end_x = self.x + nx * self.radius * 2
            end_y = self.y + ny * self.radius * 2
            pygame.draw.line(surface, CFG.COLOR_ACCENT,
                             (int(self.x), int(self.y)),
                             (int(end_x), int(end_y)), 2)

# === ДИССОНАНС-ВРАГ ===
class DissonanceEnemy(ChaserEnemy):
    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = CFG.DISSONANCE_HP
        self.max_hp = CFG.DISSONANCE_HP
        self.glitch_offset = 0.0
        self.glitch_phase = 0.0
        self.speed = CFG.DISSONANCE_SPEED
    
    def take_damage(self, damage: int, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        if is_aoe and bullet_mode == 'BLUE':
            actual_damage = damage
        else:
            actual_damage = int(damage * CFG.DISSONANCE_NORMAL_DAMAGE_MULT)
        
        self.hp -= actual_damage
        self.hit_flash = 0.1
        
        self.glitch_offset = random.uniform(-5, 5)
        
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        game.particles.emit_burst(self.x, self.y, 4,
                                  mode_colors[bullet_mode], 150.0, 0.3, 2.0)
        
        if self.hp <= 0:
            self.alive = False
            self.on_death(game, bullet_mode)
            return True
        return False
    
    def on_perfect_refraction_hit(self, game: Any) -> None:
        self.alive = False
        game.particles.emit_burst(self.x, self.y, 30, CFG.COLOR_ACCENT, 400.0, 1.0, 4.0)
        game.particles.emit_spiral(self.x, self.y, 25, CFG.COLOR_PRIMARY, 300.0)
        
        points = 500
        game.score += points * (1 + game.combo * 0.2)
        game.combo += 3
        game.max_combo = max(game.max_combo, game.combo)
        
        game.floating_texts.append(FloatingText(
            self.x, self.y, f"+{int(points)} DISSONANCE!", CFG.COLOR_ACCENT, 1.5, 24
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
        color = CFG.COLOR_DANGER if self.hit_flash <= 0 else CFG.COLOR_PRIMARY
        
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
                pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (noise_x, noise_y), 1)

# === POWER-UP ===
class PowerUp:
    def __init__(self, x: float, y: float, power_type: str):
        self.x = x
        self.y = y
        self.radius = CFG.POWERUP_RADIUS
        self.type = power_type
        self.lifetime = CFG.POWERUP_LIFETIME
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
                                 game.player.hp + CFG.POWERUP_HEAL_AMOUNT)
            game.floating_texts.append(FloatingText(
                game.player.x, game.player.y - 30,
                f"+{CFG.POWERUP_HEAL_AMOUNT} HP", CFG.COLOR_SUCCESS, 1.0, 20
            ))
        elif self.type == 'invuln':
            game.player.invuln_timer = max(game.player.invuln_timer,
                                           CFG.POWERUP_INVULN_DURATION)
            game.floating_texts.append(FloatingText(
                game.player.x, game.player.y - 30,
                "INVULN!", CFG.COLOR_ACCENT, 1.2, 22
            ))
        
        game.particles.emit_burst(self.x, self.y, 20, CFG.COLOR_SUCCESS, 250.0, 0.8, 3.0)
        game.sound_manager.play('pickup', 0.6)
    
    def draw(self, surface: pygame.Surface) -> None:
        bob = math.sin(self.bob_phase) * 4
        y_offset = bob
        color = CFG.COLOR_SUCCESS if self.type == 'heal' else CFG.COLOR_ACCENT
        
        if self.lifetime < 2.0 and int(self.lifetime * 4) % 2 == 0:
            return
        
        glow_surf = SurfaceCache.get_glow(self.radius * 2, color, int(80 * (0.6 + 0.4 * math.sin(self.bob_phase * 2))))
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
        pygame.draw.polygon(surface, CFG.COLOR_PRIMARY, points, 2)
        
        if self.type == 'heal':
            pygame.draw.line(surface, CFG.COLOR_PRIMARY,
                             (int(self.x - size * 0.4), int(self.y + y_offset)),
                             (int(self.x + size * 0.4), int(self.y + y_offset)), 2)
            pygame.draw.line(surface, CFG.COLOR_PRIMARY,
                             (int(self.x), int(self.y + y_offset - size * 0.4)),
                             (int(self.x), int(self.y + y_offset + size * 0.4)), 2)
        else:
            pygame.draw.circle(surface, CFG.COLOR_PRIMARY,
                               (int(self.x), int(self.y + y_offset)),
                               int(size * 0.3))

# === CHROMATIC BUFFER ===
class ChromaticBuffer:
    def __init__(self):
        self.last_change_time: float = -10.0
        self.last_mode: str = 'RED'
    
    def record_change(self, time: float, mode: str) -> None:
        self.last_change_time = time
        self.last_mode = mode
    
    def is_in_window(self, current_time: float) -> bool:
        return (current_time - self.last_change_time) <= CFG.PERFECT_REFRACTION_WINDOW

# === MUSIC SYSTEM ===
class MusicSystem:
    def __init__(self, sound_manager: SoundManager):
        self.enabled = sound_manager.enabled
        self.sound_manager = sound_manager
        self.active = False
        self.kill_count = 0
        self.last_kill_mode = 'RED'
        self.note_sequence = ['melody_c', 'melody_e', 'melody_g']
        self.current_note_index = 0
        
        self.bass_timer = 0.0
        self.bass_interval = CFG.BEAT_INTERVAL
        self.percussion_timer = 0.0
        self.percussion_interval = 0.25
    
    def start(self) -> None:
        if not self.enabled:
            return
        self.active = True
    
    def stop(self) -> None:
        self.active = False
    
    def on_kill(self, mode: str) -> None:
        if not self.active or not self.enabled:
            return
        
        self.kill_count += 1
        self.last_kill_mode = mode
        
        note = self.note_sequence[self.current_note_index]
        self.sound_manager.play(note, 0.4)
        
        self.current_note_index = (self.current_note_index + 1) % len(self.note_sequence)
    
    def update(self, dt: float, game_time: float, beat_tracker: BeatSyncTracker) -> None:
        if not self.active or not self.enabled:
            return
        
        self.bass_timer += dt
        if self.bass_timer >= self.bass_interval:
            self.bass_timer = 0.0
            self.sound_manager.play('bass_note', 0.3)
            beat_tracker.on_beat(game_time)
        
        self.percussion_timer += dt
        if self.percussion_timer >= self.percussion_interval:
            self.percussion_timer = 0.0
            self.sound_manager.play('percussion_hit', 0.2)
    
    def conductor_damage(self) -> None:
        self.active = False
        pygame.time.set_timer(pygame.USEREVENT + 1, 2000)
    
    def conductor_restore(self) -> None:
        self.active = True

# === HUD ===
class HUD:
    def __init__(self):
        self.font = pygame.font.SysFont("consolas", 20, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 14)
    
    def draw(self, surface: pygame.Surface, player: Any, game: Any) -> None:
        margin = CFG.HP_BAR_MARGIN
        bar_w = CFG.HP_BAR_WIDTH
        bar_h = CFG.HP_BAR_HEIGHT
        
        bg_rect = pygame.Rect(margin - 2, margin - 2, bar_w + 4, bar_h + 4)
        bg_surf = pygame.Surface((bar_w + 4, bar_h + 4), pygame.SRCALPHA)
        bg_surf.fill((0, 0, 0, 128))
        surface.blit(bg_surf, (margin - 2, margin - 2))
        
        pygame.draw.rect(surface, (40, 45, 60), (margin, margin, bar_w, bar_h))
        
        hp_t = player.hp / player.max_hp
        fill_width = int(bar_w * hp_t)
        
        if hp_t > 0.6:
            hp_color = CFG.COLOR_SUCCESS
        elif hp_t > 0.3:
            hp_color = CFG.COLOR_ACCENT
        else:
            hp_color = CFG.COLOR_DANGER
        
        if fill_width > 0:
            pygame.draw.rect(surface, hp_color, (margin, margin, fill_width, bar_h))
        
        pygame.draw.rect(surface, CFG.COLOR_PRIMARY, (margin, margin, bar_w, bar_h), 2)
        
        label = self.font.render("HP", True, CFG.COLOR_TEXT)
        surface.blit(label, (margin + bar_w + 10, margin))
        
        if player.dash_cooldown > 0:
            cd_t = 1 - (player.dash_cooldown / player.dash_cooldown_max)
            cd_width = int(100 * cd_t)
            cd_rect = pygame.Rect(margin, margin + 35, 100, 8)
            pygame.draw.rect(surface, (40, 45, 60), cd_rect)
            if cd_width > 0:
                pygame.draw.rect(surface, CFG.COLOR_ACCENT,
                                 (margin, margin + 35, cd_width, 8))
            pygame.draw.rect(surface, CFG.COLOR_PRIMARY, cd_rect, 1)
            label = self.small_font.render("DASH [SPACE/RMB]", True, CFG.COLOR_TEXT)
            surface.blit(label, (margin + 110, margin + 30))
        else:
            label = self.small_font.render("DASH READY [SPACE/RMB]", True, CFG.COLOR_SUCCESS)
            surface.blit(label, (margin, margin + 30))
        
        if player.impulse_active:
            mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
            impulse_label = self.small_font.render("IMPULSE ACTIVE", True, mode_colors[player.mode])
            surface.blit(impulse_label, (margin, margin + 55))
        
        if game.echo_chamber_active:
            echo_label = self.small_font.render("ECHO CHAMBER", True, CFG.COLOR_ACCENT)
            surface.blit(echo_label, (margin, margin + 75))
        
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        mode_color = mode_colors[player.mode]
        mode_name = player.mode
        mode_label = self.font.render(f"MODE: {mode_name}", True, mode_color)
        mode_rect = mode_label.get_rect()
        mode_rect.topright = (CFG.SCREEN_WIDTH - margin, margin)
        surface.blit(mode_label, mode_rect)
        
        wave_label = self.font.render(f"WAVE {game.wave}", True, CFG.COLOR_TEXT)
        wave_rect = wave_label.get_rect()
        wave_rect.topright = (CFG.SCREEN_WIDTH - margin, margin + 30)
        surface.blit(wave_label, wave_rect)
        
        # [NEW] Chromatic Points indicator
        if game.meta.chromatic_points > 0:
            cp_label = self.small_font.render(
                f"CHROMA: {game.meta.chromatic_points}", True, CFG.COLOR_ACCENT
            )
            surface.blit(cp_label, (CFG.SCREEN_WIDTH - margin - 120, margin + 55))
        
        if game.show_fps:
            fps = int(game.clock.get_fps())
            fps_label = self.small_font.render(f"FPS: {fps}", True, CFG.COLOR_TEXT)
            surface.blit(fps_label, (CFG.SCREEN_WIDTH - 80, CFG.SCREEN_HEIGHT - 25))
        
        if game.god_mode:
            god_label = self.font.render("GOD MODE", True, CFG.COLOR_ACCENT)
            god_rect = god_label.get_rect()
            god_rect.center = (CFG.SCREEN_WIDTH // 2, 25)
            surface.blit(god_label, god_rect)

# === MENU ===
class Menu:
    def __init__(self):
        self.big_font = pygame.font.SysFont("consolas", 72, bold=True)
        self.medium_font = pygame.font.SysFont("consolas", 32, bold=True)
        self.small_font = pygame.font.SysFont("consolas", 20)
        self.pulse_phase = 0.0
    
    def update(self, dt: float) -> None:
        self.pulse_phase += dt * 2
    
    def draw_main(self, surface: pygame.Surface, meta: MetaProgression) -> None:
        surface.fill(CFG.COLOR_BG)
        
        grid_size = 60
        offset = int(self.pulse_phase * 20) % grid_size
        for x in range(-grid_size + offset, CFG.SCREEN_WIDTH + grid_size, grid_size):
            pygame.draw.line(surface, CFG.COLOR_BG2, (x, 0), (x, CFG.SCREEN_HEIGHT), 1)
        for y in range(-grid_size + offset, CFG.SCREEN_HEIGHT + grid_size, grid_size):
            pygame.draw.line(surface, CFG.COLOR_BG2, (0, y), (CFG.SCREEN_WIDTH, y), 1)
        
        pulse = 0.7 + 0.3 * math.sin(self.pulse_phase)
        title_color = color_lerp(CFG.COLOR_PRIMARY, CFG.COLOR_ACCENT, pulse)
        title = self.big_font.render("CHROMASHIFT", True, title_color)
        title_rect = title.get_rect(center=(CFG.SCREEN_WIDTH // 2, 180))
        surface.blit(title, title_rect)
        
        subtitle = self.small_font.render(
            "Ритмичный шутер. Каждый цвет — агрегатное состояние.",
            True, CFG.COLOR_TEXT
        )
        sub_rect = subtitle.get_rect(center=(CFG.SCREEN_WIDTH // 2, 250))
        surface.blit(subtitle, sub_rect)
        
        play_pulse = int(200 + 55 * math.sin(self.pulse_phase * 2))
        play_color = (
            min(255, play_pulse),
            min(255, play_pulse),
            min(255, int(play_pulse * 1.1))
        )
        play = self.medium_font.render("[ ENTER ] НАЧАТЬ", True, play_color)
        play_rect = play.get_rect(center=(CFG.SCREEN_WIDTH // 2, 340))
        surface.blit(play, play_rect)
        
        # [NEW] Кнопка дерева прокачки
        upgrade_color = CFG.COLOR_ACCENT if meta.chromatic_points > 0 else CFG.COLOR_TEXT
        upgrade_text = f"[ U ] ДЕРЕВО ПРОКАЧКИ  (Chroma: {meta.chromatic_points})"
        upgrade = self.medium_font.render(upgrade_text, True, upgrade_color)
        upgrade_rect = upgrade.get_rect(center=(CFG.SCREEN_WIDTH // 2, 400))
        surface.blit(upgrade, upgrade_rect)
        
        controls = [
            "WASD - Движение",
            "МЫШЬ - Прицел",
            "ЛКМ - Стрельба",
            "SPACE/ПКМ - Dash (рывок с i-frames)",
            "1/Q - Красный (Импульс)  |  2/E - Синий (Якорь)  |  3/R - Зелёный (Текучесть)",
            "ESC - Пауза  |  F11 - Fullscreen  |  F1 - FPS",
        ]
        y = 480
        for text in controls:
            label = self.small_font.render(text, True, CFG.COLOR_TEXT)
            label_rect = label.get_rect(center=(CFG.SCREEN_WIDTH // 2, y))
            surface.blit(label, label_rect)
            y += 28
    
    def draw_pause(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))
        
        title = self.big_font.render("ПАУЗА", True, CFG.COLOR_ACCENT)
        title_rect = title.get_rect(center=(CFG.SCREEN_WIDTH // 2, CFG.SCREEN_HEIGHT // 2 - 50))
        surface.blit(title, title_rect)
        
        hint = self.medium_font.render("ESC - продолжить", True, CFG.COLOR_TEXT)
        hint_rect = hint.get_rect(center=(CFG.SCREEN_WIDTH // 2, CFG.SCREEN_HEIGHT // 2 + 30))
        surface.blit(hint, hint_rect)
    
    def draw_game_over(self, surface: pygame.Surface, score: int,
                       max_combo: int, wave: int, meta: MetaProgression) -> None:
        overlay = pygame.Surface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))
        
        title = self.big_font.render("GAME OVER", True, CFG.COLOR_DANGER)
        title_rect = title.get_rect(center=(CFG.SCREEN_WIDTH // 2, 180))
        surface.blit(title, title_rect)
        
        stats = [
            (f"СЧЁТ: {int(score)}", CFG.COLOR_ACCENT),
            (f"МАКС. КОМБО: {max_combo}", CFG.COLOR_ACCENT),
            (f"ВОЛНА: {wave}", CFG.COLOR_ACCENT),
            (f"CHROMA POINTS: +{score // 1000}", CFG.COLOR_ACCENT),
        ]
        y = 300
        for text, color in stats:
            label = self.medium_font.render(text, True, color)
            label_rect = label.get_rect(center=(CFG.SCREEN_WIDTH // 2, y))
            surface.blit(label, label_rect)
            y += 45
        
        pulse = int(200 + 55 * math.sin(self.pulse_phase * 2))
        restart_color = (
            min(255, pulse),
            min(255, pulse),
            min(255, int(pulse * 1.1))
        )
        restart = self.medium_font.render("[ R ] РЕСТАРТ", True, restart_color)
        restart_rect = restart.get_rect(center=(CFG.SCREEN_WIDTH // 2, 500))
        surface.blit(restart, restart_rect)
        
        menu = self.small_font.render("[ ESC ] В МЕНЮ", True, CFG.COLOR_TEXT)
        menu_rect = menu.get_rect(center=(CFG.SCREEN_WIDTH // 2, 540))
        surface.blit(menu, menu_rect)
        
        upgrade = self.small_font.render(
            f"[ U ] ДЕРЕВО ПРОКАЧКИ (Chroma: {meta.chromatic_points})",
            True, CFG.COLOR_ACCENT
        )
        upgrade_rect = upgrade.get_rect(center=(CFG.SCREEN_WIDTH // 2, 575))
        surface.blit(upgrade, upgrade_rect)

# === UPGRADE MENU ===
class UpgradeMenu:
    """Меню дерева прокачки мета-прогрессии."""
    
    def __init__(self):
        self.big_font = pygame.font.SysFont("consolas", 48, bold=True)
        self.title_font = pygame.font.SysFont("consolas", 28, bold=True)
        self.name_font = pygame.font.SysFont("consolas", 22, bold=True)
        self.desc_font = pygame.font.SysFont("consolas", 16)
        self.small_font = pygame.font.SysFont("consolas", 18)
        self.selected_index = 0
        self.pulse_phase = 0.0
        self.keys_order = ['max_hp', 'dash_cd', 'refract_win']
    
    def update(self, dt: float) -> None:
        self.pulse_phase += dt * 3
    
    def handle_input(self, event: pygame.event.Event, meta: MetaProgression,
                     sound_manager: SoundManager) -> Optional[str]:
        """Возвращает 'back' если нужно выйти."""
        if event.type != pygame.KEYDOWN:
            return None
        
        if event.key in (pygame.K_ESCAPE, pygame.K_q, pygame.K_u):
            return 'back'
        
        if event.key in (pygame.K_w, pygame.K_UP):
            self.selected_index = (self.selected_index - 1) % len(self.keys_order)
            return None
        
        if event.key in (pygame.K_s, pygame.K_DOWN):
            self.selected_index = (self.selected_index + 1) % len(self.keys_order)
            return None
        
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            key = self.keys_order[self.selected_index]
            if meta.can_purchase(key):
                if meta.purchase(key):
                    sound_manager.play('pickup', 0.7)
                else:
                    sound_manager.play('error', 0.5)
            else:
                sound_manager.play('error', 0.5)
            return None
        
        return None
    
    def draw(self, surface: pygame.Surface, meta: MetaProgression) -> None:
        surface.fill(CFG.COLOR_BG)
        
        # Фоновая сетка
        grid_size = 60
        pulse = 0.5 + 0.5 * math.sin(self.pulse_phase)
        grid_color = color_lerp(CFG.COLOR_BG2, CFG.COLOR_ACCENT, pulse * 0.2)
        for x in range(0, CFG.SCREEN_WIDTH, grid_size):
            pygame.draw.line(surface, grid_color, (x, 0), (x, CFG.SCREEN_HEIGHT), 1)
        for y in range(0, CFG.SCREEN_HEIGHT, grid_size):
            pygame.draw.line(surface, grid_color, (0, y), (CFG.SCREEN_WIDTH, y), 1)
        
        # Заголовок
        title = self.big_font.render("UPGRADE TREE", True, CFG.COLOR_ACCENT)
        title_rect = title.get_rect(center=(CFG.SCREEN_WIDTH // 2, 70))
        surface.blit(title, title_rect)
        
        # Chromatic Points
        points_text = f"CHROMATIC POINTS: {meta.chromatic_points}"
        points_label = self.title_font.render(points_text, True, CFG.COLOR_PRIMARY)
        points_rect = points_label.get_rect(center=(CFG.SCREEN_WIDTH // 2, 130))
        surface.blit(points_label, points_rect)
        
        # Список улучшений
        start_y = 200
        item_height = 140
        panel_width = 700
        panel_x = (CFG.SCREEN_WIDTH - panel_width) // 2
        
        for i, key in enumerate(self.keys_order):
            upg = meta.upgrade_tree[key]
            y = start_y + i * item_height
            is_selected = (i == self.selected_index)
            is_maxed = upg['current_lvl'] >= upg['max_lvl']
            can_afford = meta.can_purchase(key)
            
            # Фон панели
            panel_rect = pygame.Rect(panel_x, y, panel_width, item_height - 20)
            if is_selected:
                bg_alpha = 80 + int(40 * math.sin(self.pulse_phase * 2))
                bg_color = (*CFG.COLOR_ACCENT, bg_alpha)
                border_color = CFG.COLOR_ACCENT
            else:
                bg_color = (30, 35, 50, 120)
                border_color = (80, 90, 110)
            
            panel_surf = pygame.Surface((panel_width, item_height - 20), pygame.SRCALPHA)
            panel_surf.fill(bg_color)
            surface.blit(panel_surf, (panel_x, y))
            pygame.draw.rect(surface, border_color, panel_rect, 2 if is_selected else 1)
            
            # Название
            name_color = CFG.COLOR_PRIMARY if (can_afford or is_maxed) else (150, 150, 160)
            name_label = self.name_font.render(upg['name'], True, name_color)
            surface.blit(name_label, (panel_x + 20, y + 12))
            
            # Описание
            desc_label = self.desc_font.render(upg['desc'], True, CFG.COLOR_TEXT)
            surface.blit(desc_label, (panel_x + 20, y + 45))
            
            # Уровень (прогресс-бар)
            lvl_x = panel_x + 20
            lvl_y = y + 75
            lvl_text = f"Lv. {upg['current_lvl']}/{upg['max_lvl']}"
            lvl_label = self.small_font.render(lvl_text, True, CFG.COLOR_TEXT)
            surface.blit(lvl_label, (lvl_x, lvl_y))
            
            # Пипки уровня
            pip_size = 16
            pip_gap = 4
            pips_x = lvl_x + 80
            for lvl_idx in range(upg['max_lvl']):
                pip_rect = pygame.Rect(pips_x + lvl_idx * (pip_size + pip_gap), lvl_y + 2,
                                       pip_size, pip_size)
                if lvl_idx < upg['current_lvl']:
                    pygame.draw.rect(surface, CFG.COLOR_SUCCESS, pip_rect)
                    pygame.draw.rect(surface, CFG.COLOR_PRIMARY, pip_rect, 1)
                else:
                    pygame.draw.rect(surface, (60, 65, 80), pip_rect)
                    pygame.draw.rect(surface, (100, 105, 120), pip_rect, 1)
            
            # Цена
            price_x = panel_x + panel_width - 180
            if is_maxed:
                price_text = "MAXED"
                price_color = (120, 130, 150)
            else:
                cost = upg['costs'][upg['current_lvl']]
                price_text = f"Cost: {cost}"
                price_color = CFG.COLOR_SUCCESS if can_afford else CFG.COLOR_DANGER
            
            price_label = self.name_font.render(price_text, True, price_color)
            price_rect = price_label.get_rect()
            price_rect.midright = (panel_x + panel_width - 20, y + 35)
            surface.blit(price_label, price_rect)
            
            # Кнопка покупки
            if not is_maxed:
                btn_rect = pygame.Rect(panel_x + panel_width - 180, y + 65, 160, 32)
                if can_afford:
                    btn_color = CFG.COLOR_ACCENT
                    btn_text = "[ ENTER ] BUY"
                else:
                    btn_color = (100, 100, 110)
                    btn_text = "NOT ENOUGH"
                
                pygame.draw.rect(surface, btn_color, btn_rect, 2)
                btn_label = self.small_font.render(btn_text, True, btn_color)
                btn_label_rect = btn_label.get_rect(center=btn_rect.center)
                surface.blit(btn_label, btn_label_rect)
        
        # Подсказки внизу
        hint_y = CFG.SCREEN_HEIGHT - 60
        hints = [
            "[W/S] — Навигация",
            "[ENTER/SPACE] — Купить",
            "[U/ESC/Q] — Назад в меню",
        ]
        hint_x = CFG.SCREEN_WIDTH // 2 - 300
        for hint in hints:
            label = self.small_font.render(hint, True, CFG.COLOR_TEXT)
            surface.blit(label, (hint_x, hint_y))
            hint_x += 220

# === ГЛАВНЫЙ КЛАСС ИГРЫ ===
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(
            (CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.RESIZABLE
        )
        pygame.display.set_caption("CHROMASHIFT v6.0")
        self.clock = pygame.time.Clock()
        
        self.fullscreen = False
        self.god_mode = False
        self.show_fps = False
        self.running = True
        
        self.sound_manager = SoundManager()
        self.particles = ParticleManager()
        self.screen_shake = ScreenShake()
        self.chromatic_buffer = ChromaticBuffer()
        self.beat_tracker = BeatSyncTracker()
        self.crystal = PrismaticCrystal()
        self.music_system = MusicSystem(self.sound_manager)
        self.hud = HUD()
        self.menu = Menu()
        
        self.parry_indicator = ParryIndicator()
        self.telemetry = Telemetry()
        self.meta = MetaProgression()
        
        # [NEW] v6 системы
        self.spatial_hash = SpatialHash()
        self.juice_system = JuiceSystem()
        self.upgrade_menu = UpgradeMenu()
        self._last_impact_x = 0.0
        self._last_impact_y = 0.0
        
        self.state = 'MENU'
        self.reset_game()
        
        self.render_surface = pygame.Surface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT))
        
        self.bg_grid_offset = 0.0
        self.game_time = 0.0
        
        self.flash_alpha = 0.0
        self.flash_color = CFG.COLOR_PRIMARY
        
        self.resonances: List[ChromaticResonance] = []
        self.kill_streak: Dict[str, int] = {'RED': 0, 'BLUE': 0, 'GREEN': 0}
        
        self.echo_chamber_active = False
        self.echo_chamber_timer = 0.0
        self.refraction_streak = 0
        
        self._config_check_timer = 0.0
    
    def reset_game(self) -> None:
        self.player = Player(CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2, self.meta)
        self.enemies: List[Enemy] = []
        self.player_bullets: List[PlayerBullet] = []
        self.enemy_bullets: List[EnemyBullet] = []
        self.powerups: List[PowerUp] = []
        self.floating_texts: List[FloatingText] = []
        self.resonances: List[ChromaticResonance] = []
        
        self.particles.clear()
        
        self.screen_shake = ScreenShake()
        self.chromatic_buffer = ChromaticBuffer()
        self.beat_tracker = BeatSyncTracker()
        self.crystal = PrismaticCrystal()
        self.music_system = MusicSystem(self.sound_manager)
        self.parry_indicator = ParryIndicator()
        self.spatial_hash = SpatialHash()
        self.juice_system = JuiceSystem()
        
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
        
        self.echo_chamber_active = False
        self.echo_chamber_timer = 0.0
        self.refraction_streak = 0
        
        self.telemetry.session_start_time = pygame.time.get_ticks() / 1000.0
        
        self.start_new_wave()
    
    def start_new_wave(self) -> None:
        is_breather = (self.wave % CFG.BREATHER_WAVE_INTERVAL == 0)
        
        if is_breather:
            enemy_count = int(CFG.BASE_ENEMIES_PER_WAVE * CFG.BREATHER_ENEMY_MULT)
        else:
            enemy_count = int(CFG.BASE_ENEMIES_PER_WAVE * (CFG.WAVE_MULTIPLIER ** (self.wave - 1)))
        
        self.wave_enemies_remaining = enemy_count
        self.wave_spawn_timer = 0.0
        
        wave_text = f"ВОЛНА {self.wave}"
        if is_breather:
            wave_text += " [ПЕРЕДЫШКА]"
        self.floating_texts.append(FloatingText(
            CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2 - 50,
            wave_text, CFG.COLOR_ACCENT, 2.5, 48
        ))
        
        self.sound_manager.play('wave', 0.5)
        
        if is_breather:
            types = ['heal', 'invuln']
            x = random.uniform(200, CFG.SCREEN_WIDTH - 200)
            y = random.uniform(200, CFG.SCREEN_HEIGHT - 200)
            self.powerups.append(PowerUp(x, y, random.choice(types)))
    
    def spawn_enemy(self) -> None:
        side = random.randint(0, 3)
        margin = 30
        sw = CFG.SCREEN_WIDTH
        sh = CFG.SCREEN_HEIGHT
        if side == 0:
            x = random.uniform(margin, sw - margin)
            y = -margin
        elif side == 1:
            x = sw + margin
            y = random.uniform(margin, sh - margin)
        elif side == 2:
            x = random.uniform(margin, sw - margin)
            y = sh + margin
        else:
            x = -margin
            y = random.uniform(margin, sh - margin)
        
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
        self.kill_streak[mode] += 1
        
        for m in MODE_COLORS if False else ['RED', 'BLUE', 'GREEN']:
            if m != mode:
                self.kill_streak[m] = 0
        
        if self.kill_streak[mode] >= CFG.RESONANCE_KILL_THRESHOLD:
            self.resonances.append(ChromaticResonance(x, y, mode))
            self.kill_streak[mode] = 0
    
    def check_impulse_activation(self, mode: str) -> None:
        if self.kill_streak[mode] >= CFG.IMPULSE_KILL_THRESHOLD:
            self.player.impulse_active = True
            self.player.impulse_timer = 3.0
            
            mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
            self.floating_texts.append(FloatingText(
                self.player.x, self.player.y - 50,
                "IMPULSE!", mode_colors[mode], 1.5, 28
            ))
            
            self.kill_streak[mode] = 0
    
    def activate_echo_chamber(self) -> None:
        self.echo_chamber_active = True
        self.echo_chamber_timer = CFG.ECHO_DURATION
        self.refraction_streak = 0
        
        self.floating_texts.append(FloatingText(
            CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2,
            "ECHO CHAMBER!", CFG.COLOR_ACCENT, 2.0, 36
        ))
        
        self.particles.emit_spiral(self.player.x, self.player.y, 50, CFG.COLOR_ACCENT, 400.0)
        self.sound_manager.play('combo', 0.8)
    
    def is_in_resonance(self, x: float, y: float, mode: str) -> bool:
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
                    (CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), flags
                )
            elif event.key == pygame.K_F1:
                self.show_fps = not self.show_fps
            elif event.key == pygame.K_g:
                self.god_mode = not self.god_mode
            
            if self.state == 'MENU':
                if event.key == pygame.K_RETURN:
                    self.state = 'PLAYING'
                    self.reset_game()
                elif event.key == pygame.K_u:
                    self.state = 'UPGRADE_MENU'
            
            elif self.state == 'UPGRADE_MENU':
                result = self.upgrade_menu.handle_input(event, self.meta, self.sound_manager)
                if result == 'back':
                    self.state = 'MENU'
            
            elif self.state == 'PLAYING':
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_p:
                    self.state = 'PAUSED'
                elif event.key in (pygame.K_1, pygame.K_q):
                    self.player.set_mode('RED', self)
                    self.chromatic_buffer.record_change(self.game_time, 'RED')
                elif event.key in (pygame.K_2, pygame.K_e):
                    self.player.set_mode('BLUE', self)
                    self.chromatic_buffer.record_change(self.game_time, 'BLUE')
                    if self.combo >= CFG.CRYSTAL_STAGE_2:
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
                elif event.key == pygame.K_u:
                    self.state = 'UPGRADE_MENU'
                elif event.key == pygame.K_ESCAPE:
                    self.state = 'MENU'
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:
                if self.state == 'PLAYING':
                    self.player.start_dash(self)
    
    def update_playing(self, dt: float) -> None:
        self.game_time += dt
        self.bg_grid_offset += dt * 20
        
        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        
        self.player.update(dt, keys, mouse_pos, self)
        
        if pygame.mouse.get_pressed()[0]:
            if self.is_in_resonance(self.player.x, self.player.y, self.player.mode):
                if self.player.fire_cooldown > CFG.FIRE_COOLDOWN * 0.7:
                    self.player.fire_cooldown = CFG.FIRE_COOLDOWN * 0.7
            self.player.shoot(self)
        
        self.crystal.update(dt, self.player.x, self.player.y,
                            self.player.mode, self.combo)
        
        self.music_system.update(dt, self.game_time, self.beat_tracker)
        
        if self.echo_chamber_active:
            self.echo_chamber_timer -= dt
            if self.echo_chamber_timer <= 0:
                self.echo_chamber_active = False
        
        self.wave_timer += dt
        if self.wave_enemies_remaining > 0:
            self.wave_spawn_timer += dt
            if self.wave_spawn_timer >= CFG.WAVE_SPAWN_INTERVAL:
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
        self.enemy_bullets = [b for b in self.enemy_bullets if b.update(dt, self)]
        self.powerups = [p for p in self.powerups if p.update(dt)]
        self.resonances = [r for r in self.resonances if r.update(dt)]
        self.particles.update(dt)
        self.floating_texts = [t for t in self.floating_texts if t.update(dt)]
        self.screen_shake.update(dt)
        self.parry_indicator.update(dt)
        self.juice_system.update(dt)
        
        if self.flash_alpha > 0:
            self.flash_alpha = max(0, self.flash_alpha - dt * 5)
        
        # === SPATIAL HASH: rebuild each frame ===
        self.spatial_hash.clear()
        for enemy in self.enemies:
            if enemy.alive:
                self.spatial_hash.insert(enemy)
        for bullet in self.enemy_bullets:
            self.spatial_hash.insert(bullet)
        for powerup in self.powerups:
            self.spatial_hash.insert(powerup)
        
        # 1. Пули игрока vs враги (через SpatialHash)
        bullets_to_remove = []
        for i, bullet in enumerate(self.player_bullets):
            query_radius = bullet.radius + 50
            nearby = self.spatial_hash.query(bullet.x, bullet.y, query_radius)
            for enemy in nearby:
                if not hasattr(enemy, 'alive') or not enemy.alive:
                    continue
                if not hasattr(enemy, 'radius'):
                    continue
                
                if bullet.is_piercing and enemy.id in bullet.hit_enemies:
                    continue
                
                if circle_collision(bullet.x, bullet.y, bullet.radius,
                                    enemy.x, enemy.y, enemy.radius):
                    if isinstance(enemy, DissonanceEnemy) and bullet.is_refracted:
                        enemy.on_perfect_refraction_hit(self)
                    else:
                        damage_mult = 1.0
                        if self.is_in_resonance(self.player.x, self.player.y, self.player.mode):
                            damage_mult = 1.0 + CFG.RESONANCE_DAMAGE_BOOST
                        
                        enemy.take_damage(int(bullet.damage * damage_mult), 
                                         self, bullet.mode)
                    
                    if bullet.is_piercing:
                        bullet.hit_enemies.append(enemy.id)
                    else:
                        bullets_to_remove.append(i)
                    break
        
        for i in sorted(bullets_to_remove, reverse=True):
            if i < len(self.player_bullets):
                self.player_bullets.pop(i)
        
        # 2. Пули врагов vs игрок (через SpatialHash)
        bullets_to_remove = []
        for i, bullet in enumerate(self.enemy_bullets):
            dist_to_player = vec_distance(bullet.x, bullet.y, self.player.x, self.player.y)
            
            # Warning zone
            if dist_to_player < CFG.PARRY_WARNING_RADIUS:
                self.parry_indicator.start_warning()
            
            # Active parry zone
            if dist_to_player < CFG.PARRY_INDICATOR_RADIUS and not self.parry_indicator.active:
                self.parry_indicator.trigger()
            
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
        
        # 3. Враги vs игрок (контакт) — через SpatialHash
        nearby_player = self.spatial_hash.query(
            self.player.x, self.player.y, self.player.radius + 50
        )
        for enemy in nearby_player:
            if not hasattr(enemy, 'alive') or not enemy.alive:
                continue
            if not hasattr(enemy, 'radius'):
                continue
            if circle_collision(enemy.x, enemy.y, enemy.radius,
                                self.player.x, self.player.y, self.player.radius):
                if isinstance(enemy, ChaserEnemy):
                    self.player.take_damage(CFG.CHASER_DAMAGE, self, enemy.x, enemy.y)
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
        self.hitstop_timer = CFG.HITSTOP_DURATION
        
        source_dir_x = -bullet.dx
        source_dir_y = -bullet.dy
        
        self.screen_shake.trigger(8.0, 0.2, (source_dir_x, source_dir_y))
        
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
        
        mode_colors = {'RED': CFG.COLOR_RED, 'BLUE': CFG.COLOR_BLUE, 'GREEN': CFG.COLOR_GREEN}
        self.particles.emit_burst(bullet.x, bullet.y, CFG.REFRACTION_PARTICLES,
                                  mode_colors[self.player.mode], 400.0, 0.8, 4.0)
        self.sound_manager.play('refraction_perfect', 0.7)
        
        self.floating_texts.append(FloatingText(
            bullet.x, bullet.y - 20, "REFRACT!", CFG.COLOR_ACCENT, 1.0, 22
        ))
        
        self.combo += 2
        self.max_combo = max(self.max_combo, self.combo)
        self.score += 500
        
        self.refraction_streak += 1
        if self.refraction_streak >= CFG.ECHO_REFRACTION_THRESHOLD:
            self.activate_echo_chamber()
        
        self.telemetry.on_refraction_attempt(True)
        
        self.music_system.conductor_restore()
    
    def player_died(self) -> None:
        self.state = 'GAME_OVER'
        
        self.telemetry.on_death(self.wave, self.game_time)
        
        self.meta.add_points(int(self.score))
        
        self.particles.emit_burst(self.player.x, self.player.y,
                                  CFG.PLAYER_DEATH_PARTICLES, CFG.COLOR_PRIMARY,
                                  400.0, 1.5, 5.0)
        self.screen_shake.trigger(15.0, 0.5, (0, 0))
        self.flash_alpha = 0.8
        self.flash_color = CFG.COLOR_DANGER
        self.sound_manager.play('death', 0.8)
        self.music_system.stop()
    
    def update(self, dt: float) -> None:
        # Hot-reload config
        self._config_check_timer += dt
        if self._config_check_timer > 1.0:
            self._config_check_timer = 0.0
            CFG.check_for_changes()
        
        self.menu.update(dt)
        self.upgrade_menu.update(dt)
        
        if self.state == 'PLAYING':
            self.update_playing(dt)
    
    def draw_background(self, surface: pygame.Surface) -> None:
        surface.fill(CFG.COLOR_BG)
        
        if self.wave < 6:
            grid_color = CFG.COLOR_BG2
        elif self.wave < 11:
            grid_color = (40, 20, 30)
        else:
            pulse = 0.5 + 0.5 * math.sin(self.game_time * 2)
            grid_color = color_lerp(CFG.COLOR_BG2, CFG.COLOR_ACCENT, pulse * 0.3)
        
        grid_size = 60
        offset = int(self.bg_grid_offset) % grid_size
        for x in range(-grid_size + offset, CFG.SCREEN_WIDTH + grid_size, grid_size):
            pygame.draw.line(surface, grid_color, (x, 0), (x, CFG.SCREEN_HEIGHT), 1)
        for y in range(-grid_size + offset, CFG.SCREEN_HEIGHT + grid_size, grid_size):
            pygame.draw.line(surface, grid_color, (0, y), (CFG.SCREEN_WIDTH, y), 1)
    
    def draw(self) -> None:
        self.render_surface.fill(CFG.COLOR_BG)
        
        if self.state == 'MENU':
            self.menu.draw_main(self.render_surface, self.meta)
        elif self.state == 'UPGRADE_MENU':
            self.upgrade_menu.draw(self.render_surface, self.meta)
        elif self.state in ('PLAYING', 'PAUSED', 'GAME_OVER'):
            self.draw_background(self.render_surface)
            
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
                self.parry_indicator.draw(self.render_surface, self.player.x, self.player.y)
            
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
                                         self.max_combo, self.wave, self.meta)
        
        if self.flash_alpha > 0:
            flash_surf = pygame.Surface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.SRCALPHA)
            flash_surf.fill((*self.flash_color, int(255 * self.flash_alpha)))
            self.render_surface.blit(flash_surf, (0, 0))
        
        self.screen.fill(CFG.COLOR_BG)
        self.screen_shake.apply(self.screen, self.render_surface)
        
        pygame.display.flip()
    
    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(CFG.TARGET_FPS) / 1000.0
            dt = min(dt, 0.05)
            
            for event in pygame.event.get():
                self.handle_event(event)
            
            if self.hitstop_timer > 0:
                self.hitstop_timer -= dt
                self.screen_shake.update(dt)
            else:
                self.update(dt)
            
            self.draw()
        
        print("\n" + "=" * 60)
        print(self.telemetry.dump())
        print("=" * 60)
        
        pygame.quit()
        sys.exit()

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    game = Game()
    game.run()
"""Утилиты: математика, цвета/палитры, кэши поверхностей и шрифтов, SpatialHash."""
import math
import random
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set, Tuple

import pygame

from .config import CFG

# === ПАЛИТРЫ (доступность) ===
# Цвета режимов для разных типов цветового зрения + высокая контрастность.
PALETTES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    'default': {'RED': (255, 50, 80), 'BLUE': (60, 140, 255), 'GREEN': (80, 255, 140)},
    'deuteranopia': {'RED': (230, 120, 0), 'BLUE': (40, 120, 255), 'GREEN': (240, 230, 80)},
    'protanopia': {'RED': (200, 160, 0), 'BLUE': (30, 110, 255), 'GREEN': (120, 230, 255)},
    'tritanopia': {'RED': (255, 40, 90), 'BLUE': (0, 170, 170), 'GREEN': (255, 170, 200)},
    'high_contrast': {'RED': (255, 0, 0), 'BLUE': (0, 120, 255), 'GREEN': (0, 255, 0)},
}
PALETTE_NAMES = {
    'default': 'Стандартная', 'deuteranopia': 'Дейтеранопия', 'protanopia': 'Протанопия',
    'tritanopia': 'Тританопия', 'high_contrast': 'Высокий контраст',
}
_active_palette = dict(PALETTES['default'])
_visual = {'glow': 1.0, 'shake': 1.0, 'flash': 1.0, 'ui_scale': 1.0, 'shapes': False}


def set_palette(name: str) -> None:
    _active_palette.clear()
    _active_palette.update(PALETTES.get(name, PALETTES['default']))


def set_visual(**kwargs: Any) -> None:
    for k, v in kwargs.items():
        if k in _visual:
            _visual[k] = v


def visual(key: str) -> Any:
    return _visual[key]


def mode_color(mode: str) -> Tuple[int, int, int]:
    return _active_palette.get(mode, (255, 255, 255))


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
    """Кэширование Surface для предотвращения аллокаций в draw().

    Альфа квантуется, а размер кэша ограничен (LRU): иначе пульсирующие
    эффекты (резонанс, свечение) порождают тысячи уникальных ключей и
    неограниченный рост памяти.
    """
    _cache: 'OrderedDict[Tuple, pygame.Surface]' = OrderedDict()
    MAX_ENTRIES = 512
    ALPHA_STEP = 8

    @classmethod
    def _quantize_alpha(cls, alpha: int) -> int:
        alpha = int(clamp(alpha, 0, 255))
        if alpha >= 255:
            return 255
        return (alpha // cls.ALPHA_STEP) * cls.ALPHA_STEP

    @classmethod
    def _lookup(cls, key: Tuple) -> Optional[pygame.Surface]:
        surf = cls._cache.get(key)
        if surf is not None:
            cls._cache.move_to_end(key)
        return surf

    @classmethod
    def _store(cls, key: Tuple, surf: pygame.Surface) -> pygame.Surface:
        cls._cache[key] = surf
        if len(cls._cache) > cls.MAX_ENTRIES:
            cls._cache.popitem(last=False)
        return surf
    
    @classmethod
    def get_glow(cls, radius: int, color: Tuple[int, int, int], alpha: int = 255) -> pygame.Surface:
        radius = max(1, int(radius))
        alpha = cls._quantize_alpha(alpha)
        key = ('glow', radius, tuple(color), alpha)
        surf = cls._lookup(key)
        if surf is None:
            size = radius * 4
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, alpha), (size // 2, size // 2), radius)
            cls._store(key, surf)
        return surf
    
    @classmethod
    def get_circle(cls, radius: int, color: Tuple[int, int, int], alpha: int = 255) -> pygame.Surface:
        radius = max(1, int(radius))
        alpha = cls._quantize_alpha(alpha)
        key = ('circle', radius, tuple(color), alpha)
        surf = cls._lookup(key)
        if surf is None:
            size = radius * 2 + 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, alpha), (radius + 1, radius + 1), radius)
            cls._store(key, surf)
        return surf
    
    @classmethod
    def clear(cls) -> None:
        cls._cache.clear()


# === FONT CACHE ===
_FONT_CACHE: Dict[Tuple[str, int, bool], pygame.font.Font] = {}


def get_font(name: str, size: int, bold: bool = False, scaled: bool = False) -> pygame.font.Font:
    """SysFont ищет шрифт в системе — дорого вызывать на каждый FloatingText."""
    size = max(8, int(size * _visual['ui_scale'])) if scaled else size
    key = (name, size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont(name, size, bold=bold)
        _FONT_CACHE[key] = font
    return font

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


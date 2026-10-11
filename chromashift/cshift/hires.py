"""Чёткий рендер (0.7.0).

Раньше кадр всегда рисовался в 1280×720 и затем растягивался до размера
монитора со сглаживанием — на полном экране всё «плыло». Теперь кадр
рисуется сразу в физическом разрешении окна, а весь игровой код по-прежнему
работает в логических координатах 1280×720:

* HiSurface — поверхность в физических пикселях, которая снаружи выглядит
  как логическая (get_width/get_rect/blit/fill пересчитывают координаты);
* функции pygame.draw.* для HiSurface масштабируют координаты, радиусы и
  толщину линий;
* шрифты растеризуются в нужном физическом размере (текст не растягивается).

Внешний вид и пропорции не меняются: при масштабе 1.0 картинка идентична
прежней, при большем — те же фигуры, только с родной чёткостью.
"""
import math
import weakref
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

import pygame

_state: Dict[str, Any] = {'scale': 1.0}
_ORIG: Dict[str, Any] = {}


def get_scale() -> float:
    return _state['scale']


def set_scale(s: float) -> bool:
    """Меняет масштаб рендера. Возвращает True, если масштаб изменился."""
    s = max(0.5, min(4.0, float(s)))
    if abs(s - _state['scale']) < 1e-4:
        return False
    _state['scale'] = s
    _TEXT_CACHE.clear()
    _HI_FONTS.clear()
    return True


def _pt(p: Any, s: float) -> Tuple[float, float]:
    return (p[0] * s, p[1] * s)


def _rect(r: Any, s: float) -> pygame.Rect:
    if not isinstance(r, pygame.Rect):
        r = pygame.Rect(r) if len(r) == 4 else pygame.Rect(r[0], r[1])
    x0, y0 = int(round(r.x * s)), int(round(r.y * s))
    x1, y1 = int(round((r.x + r.w) * s)), int(round((r.y + r.h) * s))
    return pygame.Rect(x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def _w(width: Any, s: float) -> int:
    width = int(width)
    return 0 if width <= 0 else max(1, int(round(width * s)))


class HiSurface(pygame.Surface):
    """Поверхность в физических пикселях с логическим интерфейсом."""

    def __init__(self, size: Any, flags: int = 0, s: Optional[float] = None):
        s = _state['scale'] if s is None else float(s)
        lw, lh = max(1, int(math.ceil(size[0]))), max(1, int(math.ceil(size[1])))
        super().__init__((max(1, int(math.ceil(lw * s))), max(1, int(math.ceil(lh * s)))), flags)
        self.lw, self.lh, self.s = lw, lh, s

    # --- логические размеры ---
    def get_width(self) -> int:
        return self.lw

    def get_height(self) -> int:
        return self.lh

    def get_size(self) -> Tuple[int, int]:
        return (self.lw, self.lh)

    def get_rect(self, **kw: Any) -> pygame.Rect:
        r = pygame.Rect(0, 0, self.lw, self.lh)
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    def physical(self) -> pygame.Surface:
        return self

    # --- операции ---
    def fill(self, color: Any, rect: Any = None, special_flags: int = 0) -> pygame.Rect:
        if rect is None:
            return pygame.Surface.fill(self, color, None, special_flags)
        return pygame.Surface.fill(self, color, _rect(rect, self.s), special_flags)

    def blit(self, source: pygame.Surface, dest: Any = (0, 0), area: Any = None, special_flags: int = 0) -> pygame.Rect:
        s = self.s
        dx, dy = dest[0], dest[1]
        pos = (int(round(dx * s)), int(round(dy * s)))
        if isinstance(source, HiSurface) and abs(source.s - s) < 1e-4:
            a = None if area is None else _rect(area, s)
            return pygame.Surface.blit(self, source, pos, a, special_flags)
        if abs(s - 1.0) < 1e-4 and not isinstance(source, HiSurface):
            return pygame.Surface.blit(self, source, (int(dx), int(dy)), area, special_flags)
        src = upscaled(source, s)
        a = None if area is None else _rect(area, s)
        return pygame.Surface.blit(self, src, pos, a, special_flags)


_UPSCALED: 'weakref.WeakKeyDictionary[pygame.Surface, Tuple[float, pygame.Surface]]' = weakref.WeakKeyDictionary()


def upscaled(source: pygame.Surface, s: float) -> pygame.Surface:
    """Обычную (логическую) поверхность масштабирует до физической."""
    src_s = source.s if isinstance(source, HiSurface) else 1.0
    k = s / src_s
    hit = _UPSCALED.get(source)
    if hit is not None and abs(hit[0] - s) < 1e-4:
        return hit[1]
    w = pygame.Surface.get_width(source)
    h = pygame.Surface.get_height(source)
    tw, th = max(1, int(round(w * k))), max(1, int(round(h * k)))
    try:
        if w * h < 250_000 and source.get_bitsize() in (24, 32):
            out = pygame.transform.smoothscale(source, (tw, th))
        else:
            out = pygame.transform.scale(source, (tw, th))
    except (pygame.error, ValueError):
        out = pygame.transform.scale(source, (tw, th))
    try:
        _UPSCALED[source] = (s, out)
    except TypeError:
        pass
    return out


def layer(size: Any, flags: int = pygame.SRCALPHA) -> pygame.Surface:
    """Временный слой для эффектов в текущем масштабе рендера."""
    return HiSurface(size, flags)


# =====================================================================
# pygame.draw для HiSurface
# =====================================================================
def _install_draw_patch() -> None:
    if _ORIG:
        return
    d = pygame.draw
    for name in ('circle', 'rect', 'line', 'lines', 'polygon', 'ellipse', 'arc', 'aaline', 'aalines'):
        _ORIG[name] = getattr(d, name)

    def circle(surface: Any, color: Any, center: Any, radius: float, width: int = 0, *a: Any, **k: Any) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['circle'](surface, color, _pt(center, s), radius * s, _w(width, s), *a, **k)
        return _ORIG['circle'](surface, color, center, radius, width, *a, **k)

    def rect(surface: Any, color: Any, r: Any, width: int = 0, *a: Any, **k: Any) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            k = {kk: (int(round(v * s)) if kk.startswith('border') and v > 0 else v) for kk, v in k.items()}
            a = tuple(int(round(v * s)) if isinstance(v, (int, float)) and v > 0 else v for v in a)
            return _ORIG['rect'](surface, color, _rect(r, s), _w(width, s), *a, **k)
        return _ORIG['rect'](surface, color, r, width, *a, **k)

    def line(surface: Any, color: Any, start: Any, end: Any, width: int = 1) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['line'](surface, color, _pt(start, s), _pt(end, s), max(1, _w(width, s)))
        return _ORIG['line'](surface, color, start, end, width)

    def lines(surface: Any, color: Any, closed: bool, points: Any, width: int = 1) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['lines'](surface, color, closed, [_pt(p, s) for p in points], max(1, _w(width, s)))
        return _ORIG['lines'](surface, color, closed, points, width)

    def polygon(surface: Any, color: Any, points: Any, width: int = 0) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['polygon'](surface, color, [_pt(p, s) for p in points], _w(width, s))
        return _ORIG['polygon'](surface, color, points, width)

    def ellipse(surface: Any, color: Any, r: Any, width: int = 0) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['ellipse'](surface, color, _rect(r, s), _w(width, s))
        return _ORIG['ellipse'](surface, color, r, width)

    def arc(surface: Any, color: Any, r: Any, start: float, stop: float, width: int = 1) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['arc'](surface, color, _rect(r, s), start, stop, max(1, _w(width, s)))
        return _ORIG['arc'](surface, color, r, start, stop, width)

    def aaline(surface: Any, color: Any, start: Any, end: Any, *a: Any) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['aaline'](surface, color, _pt(start, s), _pt(end, s), *a)
        return _ORIG['aaline'](surface, color, start, end, *a)

    def aalines(surface: Any, color: Any, closed: bool, points: Any, *a: Any) -> Any:
        if isinstance(surface, HiSurface):
            s = surface.s
            return _ORIG['aalines'](surface, color, closed, [_pt(p, s) for p in points], *a)
        return _ORIG['aalines'](surface, color, closed, points, *a)

    for name, fn in (('circle', circle), ('rect', rect), ('line', line), ('lines', lines), ('polygon', polygon),
                     ('ellipse', ellipse), ('arc', arc), ('aaline', aaline), ('aalines', aalines)):
        setattr(d, name, fn)


_install_draw_patch()


# =====================================================================
# Шрифты
# =====================================================================
_HI_FONTS: Dict[Tuple[str, int, bool], pygame.font.Font] = {}
_TEXT_CACHE: 'OrderedDict[Tuple, pygame.Surface]' = OrderedDict()
_TEXT_CACHE_MAX = 1500


class HiFont:
    """Шрифт: метрики в логических пикселях, растеризация — в физических."""

    def __init__(self, name: str, size: int, bold: bool = False):
        self.name, self.size_pt, self.bold = name, size, bold
        self.logical = pygame.font.SysFont(name, size, bold=bold)

    def _phys(self, s: float) -> pygame.font.Font:
        ps = max(6, int(round(self.size_pt * s)))
        key = (self.name, ps, self.bold)
        f = _HI_FONTS.get(key)
        if f is None:
            f = pygame.font.SysFont(self.name, ps, bold=self.bold)
            _HI_FONTS[key] = f
        return f

    def size(self, txt: str) -> Tuple[int, int]:
        return self.logical.size(txt)

    def get_height(self) -> int:
        return self.logical.get_height()

    def get_linesize(self) -> int:
        return self.logical.get_linesize()

    def render(self, txt: str, antialias: bool, color: Any, background: Any = None) -> pygame.Surface:
        s = _state['scale']
        key = (self.name, self.size_pt, self.bold, txt, bool(antialias), tuple(color), tuple(background) if background else None, s)
        hit = _TEXT_CACHE.get(key)
        if hit is not None:
            _TEXT_CACHE.move_to_end(key)
            al = hit.get_alpha()
            if al is not None and al != 255:  # всплывающий текст мог поменять прозрачность
                hit.set_alpha(255)  # (set_alpha(None) у SRCALPHA-поверхности ломает попиксельную альфу)
            return hit
        if abs(s - 1.0) < 1e-4:
            out = self.logical.render(txt, antialias, color, background) if background else \
                self.logical.render(txt, antialias, color)
        else:
            img = self._phys(s).render(txt, antialias, color, background) if background else \
                self._phys(s).render(txt, antialias, color)
            lw, lh = self.logical.size(txt)
            # физический шрифт может быть чуть шире логического — не обрезаем последний символ
            iw, ih = img.get_size()
            lw, lh = max(lw, int(math.ceil(iw / s))), max(lh, int(math.ceil(ih / s)))
            out = HiSurface((max(1, lw), max(1, lh)), pygame.SRCALPHA, s)
            pygame.Surface.blit(out, img, (0, 0))
        _TEXT_CACHE[key] = out
        if len(_TEXT_CACHE) > _TEXT_CACHE_MAX:
            _TEXT_CACHE.popitem(last=False)
        return out

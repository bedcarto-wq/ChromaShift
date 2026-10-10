"""Визуальные эффекты: частицы с пулом, тряска, текст, индикатор парирования,
JuiceSystem, призматический кристалл, зоны хроматического резонанса."""
import math
import random
from typing import Any, List, Optional, Tuple

import pygame

from .config import CFG
from .utils import (SurfaceCache, clamp, color_lerp, get_font, mode_color,
                    vec_normalize, visual)


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
        intensity *= visual('shake')
        if intensity <= 0.01:
            return
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
        self.font = get_font("consolas", font_size, bold=True)
    
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
    
    def __init__(self, window: Optional[float] = None):
        self.active = False
        self.warning_active = False
        self.timer = 0.0
        self.warning_timer = 0.0
        self.max_timer = window if window is not None else CFG.PERFECT_REFRACTION_WINDOW
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
            color = mode_color(player_mode)
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
        color = mode_color(player_mode)
        
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
    
    def __init__(self, x: float, y: float, color_mode: str, radius_mult: float = 1.0,
                 lifetime_add: float = 0.0, static: bool = False):
        self.x = x
        self.y = y
        self.color_mode = color_mode
        self.color = mode_color(color_mode)
        self.radius = CFG.RESONANCE_RADIUS * radius_mult
        self.lifetime = CFG.RESONANCE_LIFETIME + lifetime_add
        self.max_lifetime = self.lifetime
        self.pulse_phase = 0.0
        self.static = static  # постоянные зоны арены «Призма»
        
        self.drift_x = random.uniform(-1, 1)
        self.drift_y = random.uniform(-1, 1)
        self.drift_x, self.drift_y = vec_normalize(self.drift_x, self.drift_y)
    
    def update(self, dt: float) -> bool:
        self.pulse_phase += dt * 2
        if self.static:
            return True
        self.lifetime -= dt
        
        self.x += self.drift_x * CFG.RESONANCE_DRIFT_SPEED * dt
        self.y += self.drift_y * CFG.RESONANCE_DRIFT_SPEED * dt
        
        sw = CFG.SCREEN_WIDTH
        sh = CFG.SCREEN_HEIGHT
        self.x = clamp(self.x, self.radius, sw - self.radius)
        self.y = clamp(self.y, self.radius, sh - self.radius)
        
        return self.lifetime > 0
    
    def draw(self, surface: pygame.Surface) -> None:
        self.color = mode_color(self.color_mode)
        t = 0.6 if self.static else self.lifetime / self.max_lifetime
        alpha = int(120 * t)
        
        pulse = 0.8 + 0.2 * math.sin(self.pulse_phase)
        draw_radius = int(self.radius * pulse)
        
        glow_surf = SurfaceCache.get_glow(draw_radius, self.color, int(alpha * 0.3))
        surface.blit(glow_surf, (int(self.x - draw_radius * 2), int(self.y - draw_radius * 2)))
        
        resonance_surf = SurfaceCache.get_circle(draw_radius, self.color, alpha)
        surface.blit(resonance_surf, (int(self.x - draw_radius), int(self.y - draw_radius)))
        
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), draw_radius, 2)


"""Новые враги 0.7.0, мини-боссы, ещё два босса и объекты поля (мины, лучи, краска, порталы).

Все враги работают через общий протокол Enemy: update(dt, player) может вернуть пулю,
список пуль или «действия»-кортежи, которые обрабатывает Game.handle_enemy_result:
  ('spawn', kind, x, y, counted)      — призыв
  ('mine', x, y, color)               — мина
  ('beam', x, y, angle, color, dmg)   — луч лазерщика / босса
  ('jam', x, y, radius)               — глушение смены цвета
  ('inversion', seconds)              — инверсия физики цветов
"""
import math
import random
from typing import Any, List, Optional, Tuple

import pygame

from .config import CFG, MODES
from .entities import (BossEnemy, ChaserEnemy, Enemy, EnemyBullet, MODE_SHAPES, draw_shape)
from .utils import SurfaceCache, clamp, color_lerp, lerp, mode_color, vec_distance, vec_length, vec_normalize, visual


def _keep_distance(e: Enemy, player: Any, dt: float, want: float, strafe: float = 0.7) -> None:
    dx, dy = player.x - e.x, player.y - e.y
    dist = max(1.0, vec_length(dx, dy))
    nx, ny = dx / dist, dy / dist
    if dist > want + 40:
        tx, ty = nx, ny
    elif dist < want - 40:
        tx, ty = -nx, -ny
    else:
        tx, ty = -ny * strafe, nx * strafe
    e.vx = lerp(e.vx, tx * e.speed, min(1.0, dt * 2.5))
    e.vy = lerp(e.vy, ty * e.speed, min(1.0, dt * 2.5))
    e.x = clamp(e.x + e.vx * dt, e.radius + 15, CFG.SCREEN_WIDTH - e.radius - 15)
    e.y = clamp(e.y + e.vy * dt, e.radius + 15, CFG.SCREEN_HEIGHT - e.radius - 15)


def _body_color(e: Enemy, base: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return CFG.COLOR_PRIMARY if e.hit_flash > 0 else base


def colored_bullet(x: float, y: float, ang: float, speed: float, dmg: float, color: str, src: str) -> EnemyBullet:
    return EnemyBullet(x, y, math.cos(ang), math.sin(ang), speed, dmg, src, color=color)


# =====================================================================
# РЯДОВЫЕ ВРАГИ
# =====================================================================
class SwarmEnemy(ChaserEnemy):
    """Рой: очень слабые, быстрые, приходят десятками. Умирают с одного попадания."""
    kind = 'swarm'

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 12.0
        self.radius = 7
        self.speed = 215.0
        self.contact_damage = 6.0
        self.flank_direction = random.choice([-1, 1])

    def draw(self, surface: pygame.Surface) -> None:
        a = math.atan2(self.vy, self.vx)
        draw_shape(surface, 'diamond', _body_color(self, (255, 120, 150)), self.x, self.y, self.radius + 1, a)


class ShardEnemy(ChaserEnemy):
    """Осколок Призмы: уязвим только к своему цвету."""
    kind = 'shard'

    def __init__(self, x: float, y: float, color: Optional[str] = None):
        super().__init__(x, y)
        self.hp = self.max_hp = 18.0
        self.radius = 8
        self.speed = 175.0
        self.contact_damage = 7.0
        c = color or random.choice(MODES)
        self.vulnerable_mode = c
        self.color_tag = c

    def draw(self, surface: pygame.Surface) -> None:
        a = math.atan2(self.vy, self.vx)
        draw_shape(surface, 'triangle', _body_color(self, mode_color(self.color_tag)), self.x, self.y, self.radius + 2, a)


class PrismEnemy(Enemy):
    """Призма: стреляет цветными пулями и раскалывается на три осколка разных цветов."""
    kind = 'prism'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 60, 16)
        self.speed = 90.0
        self.fire_timer = random.uniform(1.0, 2.2)
        self.color_i = random.randrange(3)
        self.rot = 0.0

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.rot += dt * 1.5
        _keep_distance(self, player, dt, 260)
        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = 2.2
            self.color_i = (self.color_i + 1) % 3
            ang = math.atan2(player.y - self.y, player.x - self.x)
            return colored_bullet(self.x, self.y, ang, 230, CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult,
                                  MODES[self.color_i], f"пуля: {self.name}")
        return None

    def death_spawns(self) -> List[Tuple[str, float, float, dict]]:
        return [('shard', self.x + math.cos(i * 2.094) * 18, self.y + math.sin(i * 2.094) * 18, {'color': m})
                for i, m in enumerate(MODES)]

    def draw(self, surface: pygame.Surface) -> None:
        for i, m in enumerate(MODES):
            a = self.rot + i * 2.094
            pts = [(self.x, self.y), (self.x + math.cos(a) * self.radius, self.y + math.sin(a) * self.radius),
                   (self.x + math.cos(a + 2.094) * self.radius, self.y + math.sin(a + 2.094) * self.radius)]
            pygame.draw.polygon(surface, _body_color(self, mode_color(m)), pts)
        draw_shape(surface, 'triangle', CFG.COLOR_PRIMARY, self.x, self.y, self.radius, self.rot, 2)


class MirrorEnemy(Enemy):
    """Зеркало: пули ТВОЕГО текущего цвета отражает обратно. Бей другим цветом."""
    kind = 'mirror'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 70, 15)
        self.speed = 95.0
        self.color_tag = random.choice(MODES)
        self.color_timer = 4.0
        self.t = 0.0

    def reflects(self, bullet_mode: str) -> bool:
        return bullet_mode == self.color_tag

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.t += dt
        _keep_distance(self, player, dt, 300, 1.0)
        self.color_timer -= dt
        if self.color_timer <= 0:
            self.color_timer = 4.0
            self.color_tag = random.choice([m for m in MODES if m != self.color_tag])
        return None

    def draw(self, surface: pygame.Surface) -> None:
        col = _body_color(self, mode_color(self.color_tag))
        warn = self.color_timer < 0.6 and int(self.t * 10) % 2 == 0
        draw_shape(surface, 'square', (25, 28, 40), self.x, self.y, self.radius, self.t * 0.5)
        draw_shape(surface, 'square', CFG.COLOR_PRIMARY if warn else col, self.x, self.y, self.radius, self.t * 0.5, 3)
        pygame.draw.line(surface, CFG.COLOR_PRIMARY, (self.x - 6, self.y + 6), (self.x + 6, self.y - 6), 2)


class ChameleonEnemy(ChaserEnemy):
    """Хамелеон: копирует твой цвет с задержкой ~1 с и почти неуязвим к нему."""
    kind = 'chameleon'

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 55.0
        self.radius = 14
        self.speed = 150.0
        self.contact_damage = 12.0
        self.history: List[Tuple[float, str]] = []
        self.t = 0.0
        self.color_tag = 'RED'

    def damage_factor(self, bullet_mode: str) -> float:
        f = super().damage_factor(bullet_mode)
        return f * (0.15 if bullet_mode == self.color_tag else 1.0)

    def weakness(self) -> Optional[str]:
        return None

    def update(self, dt: float, player: Any) -> Any:
        self.t += dt
        mode = getattr(player, 'mode', None)
        if mode in MODES:
            if not self.history or self.history[-1][1] != mode:
                self.history.append((self.t, mode))
            while len(self.history) > 1 and self.history[1][0] <= self.t - 1.0:
                self.history.pop(0)
            if self.history and self.history[0][0] <= self.t - 1.0:
                self.color_tag = self.history[0][1]
        return super().update(dt, player)

    def draw(self, surface: pygame.Surface) -> None:
        col = _body_color(self, mode_color(self.color_tag))
        pygame.draw.ellipse(surface, col, (int(self.x - self.radius), int(self.y - self.radius * 0.8),
                                           int(self.radius * 2), int(self.radius * 1.6)))
        pygame.draw.ellipse(surface, CFG.COLOR_PRIMARY, (int(self.x - self.radius), int(self.y - self.radius * 0.8),
                                                         int(self.radius * 2), int(self.radius * 1.6)), 2)
        a = math.atan2(self.vy, self.vx)
        pygame.draw.circle(surface, CFG.COLOR_BG, (int(self.x + math.cos(a) * 6), int(self.y + math.sin(a) * 6)), 3)


class ShieldbearerEnemy(ChaserEnemy):
    """Щитоносец: союзники рядом получают вдвое меньше урона. Убивай первым."""
    kind = 'shieldbearer'
    AURA = 120.0

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 90.0
        self.radius = 17
        self.speed = 75.0
        self.contact_damage = 10.0
        self.t = 0.0

    def update(self, dt: float, player: Any) -> Any:
        self.t += dt
        return super().update(dt, player)

    def draw(self, surface: pygame.Surface) -> None:
        a = 0.5 + 0.5 * math.sin(self.t * 3)
        pygame.draw.circle(surface, color_lerp(CFG.COLOR_BG, (120, 170, 255), 0.25 + 0.2 * a),
                           (int(self.x), int(self.y)), int(self.AURA), 1)
        draw_shape(surface, 'hex', _body_color(self, (90, 130, 230)), self.x, self.y, self.radius, self.t * 0.3)
        draw_shape(surface, 'hex', CFG.COLOR_PRIMARY, self.x, self.y, self.radius, self.t * 0.3, 2)


class MinerEnemy(Enemy):
    """Минёр: оставляет цветные мины. Мина безопасна, если ты в её цвете."""
    kind = 'miner'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 45, 14)
        self.speed = 110.0
        self.mine_timer = random.uniform(1.5, 3.2)
        self.t = 0.0

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.t += dt
        _keep_distance(self, player, dt, 280, 1.0)
        self.mine_timer -= dt
        if self.mine_timer <= 0:
            self.mine_timer = 3.2
            return ('mine', self.x, self.y, random.choice(MODES))
        return None

    def draw(self, surface: pygame.Surface) -> None:
        col = _body_color(self, (230, 160, 60))
        pygame.draw.circle(surface, col, (int(self.x), int(self.y)), self.radius)
        for i in range(4):
            a = self.t + i * math.pi / 2
            pygame.draw.line(surface, CFG.COLOR_PRIMARY, (self.x, self.y),
                             (self.x + math.cos(a) * (self.radius + 4), self.y + math.sin(a) * (self.radius + 4)), 2)


class LaserEnemy(Enemy):
    """Лазерщик: предупреждает тонкой линией, затем бьёт цветным лучом. Свой цвет луч поглощает."""
    kind = 'laser'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 50, 15)
        self.speed = 70.0
        self.state = 'move'
        self.timer = random.uniform(1.5, 2.8)
        self.angle = 0.0
        self.color = random.choice(MODES)
        self.color_tag = self.color

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        target = math.atan2(player.y - self.y, player.x - self.x)
        self.timer -= dt
        if self.state == 'move':
            _keep_distance(self, player, dt, 330, 0.8)
            self.angle = target
            if self.timer <= 0:
                self.state, self.timer = 'aim', 1.1
                self.color = random.choice(MODES)
                self.color_tag = self.color
        elif self.state == 'aim':
            diff = (target - self.angle + math.pi) % (2 * math.pi) - math.pi
            self.angle += clamp(diff, -1.4 * dt, 1.4 * dt)  # медленно доводит — можно уйти
            if self.timer <= 0:
                self.state, self.timer = 'lock', 0.45
        elif self.state == 'lock':
            if self.timer <= 0:
                self.state, self.timer = 'cool', 0.6
                return ('beam', self.x, self.y, self.angle, self.color, 22 * self.damage_mult)
        elif self.state == 'cool':
            if self.timer <= 0:
                self.state, self.timer = 'move', random.uniform(1.8, 2.6)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        col = mode_color(self.color)
        if self.state in ('aim', 'lock'):
            ex, ey = self.x + math.cos(self.angle) * 1500, self.y + math.sin(self.angle) * 1500
            w = 1 if self.state == 'aim' else (3 if int(self.timer * 20) % 2 == 0 else 1)
            pygame.draw.line(surface, col, (self.x, self.y), (ex, ey), w)
        draw_shape(surface, 'diamond', _body_color(self, (200, 200, 215)), self.x, self.y, self.radius, self.angle)
        pygame.draw.circle(surface, col, (int(self.x), int(self.y)), 5)


class DevourerEnemy(ChaserEnemy):
    """Пожиратель: поглощает пули и растёт. Наберёт 22 попадания — лопнет кольцом пуль."""
    kind = 'devourer'
    LIMIT = 22

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 85.0
        self.radius = 15
        self.base_radius = 15
        self.speed = 85.0
        self.contact_damage = 14.0
        self.t = 0.0
        self.burst = False

    def take_damage(self, damage: float, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        if not is_aoe and self.alive:
            self.absorbed += 1
            self.radius = self.base_radius + min(14, self.absorbed * 0.6)
        return super().take_damage(damage, game, bullet_mode, is_aoe)

    def update(self, dt: float, player: Any) -> Any:
        self.t += dt
        super().update(dt, player)
        if self.absorbed >= self.LIMIT and self.alive:
            self.alive = False
            self.burst = True
            return [EnemyBullet(self.x, self.y, math.cos(i * math.pi / 7), math.sin(i * math.pi / 7), 210,
                                CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult, f"взрыв: {self.name}") for i in range(14)]
        return None

    def draw(self, surface: pygame.Surface) -> None:
        k = self.absorbed / self.LIMIT
        col = _body_color(self, color_lerp((120, 60, 160), CFG.COLOR_DANGER, k))
        pygame.draw.circle(surface, col, (int(self.x), int(self.y)), int(self.radius))
        a = math.atan2(self.vy, self.vx)
        mouth = 0.4 + 0.3 * math.sin(self.t * 8)
        pts = [(self.x, self.y), (self.x + math.cos(a - mouth) * self.radius, self.y + math.sin(a - mouth) * self.radius),
               (self.x + math.cos(a + mouth) * self.radius, self.y + math.sin(a + mouth) * self.radius)]
        pygame.draw.polygon(surface, CFG.COLOR_BG, pts)
        pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), int(self.radius), 2)


class SummonerEnemy(Enemy):
    """Призыватель: держится вдали и вызывает рои, пока жив."""
    kind = 'summoner'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 70, 16)
        self.speed = 60.0
        self.timer = 2.0
        self.summoned = 0
        self.t = 0.0

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.t += dt
        _keep_distance(self, player, dt, 340, 0.5)
        self.timer -= dt
        if self.timer <= 0 and self.summoned < 12:
            self.timer = 4.5
            self.summoned += 3
            return [('spawn', 'swarm', self.x + math.cos(i * 2.1) * 30, self.y + math.sin(i * 2.1) * 30, False)
                    for i in range(3)]
        return None

    def draw(self, surface: pygame.Surface) -> None:
        col = _body_color(self, (170, 90, 220))
        draw_shape(surface, 'hex', col, self.x, self.y, self.radius, -self.t)
        k = 1 - clamp(self.timer / 4.5, 0, 1)
        pygame.draw.arc(surface, CFG.COLOR_ACCENT, (self.x - 22, self.y - 22, 44, 44), 0, k * 2 * math.pi, 2)


class TeleporterEnemy(ChaserEnemy):
    """Телепортер: прыгает тебе за спину (место прыжка видно заранее)."""
    kind = 'teleporter'

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 40.0
        self.radius = 13
        self.speed = 120.0
        self.contact_damage = 14.0
        self.tp_timer = random.uniform(2.0, 3.5)
        self.tp_warn = 0.0
        self.tp_target = (x, y)

    def update(self, dt: float, player: Any) -> Any:
        if self.tp_warn > 0:
            self.tp_warn -= dt
            if self.tp_warn <= 0:
                self.x, self.y = self.tp_target
                self.vx = self.vy = 0.0
            return None
        self.tp_timer -= dt
        if self.tp_timer <= 0:
            self.tp_timer = 3.5
            fx, fy = getattr(player, 'facing_x', 0.0), getattr(player, 'facing_y', -1.0)
            tx = clamp(player.x - fx * 170, 30, CFG.SCREEN_WIDTH - 30)
            ty = clamp(player.y - fy * 170, 30, CFG.SCREEN_HEIGHT - 30)
            self.tp_target = (tx, ty)
            self.tp_warn = 0.6
            return None
        return super().update(dt, player)

    def draw(self, surface: pygame.Surface) -> None:
        col = _body_color(self, (90, 230, 230))
        draw_shape(surface, 'triangle', col, self.x, self.y, self.radius, math.atan2(self.vy, self.vx))
        if self.tp_warn > 0:
            tx, ty = self.tp_target
            r = int(8 + 14 * (self.tp_warn / 0.6))
            pygame.draw.circle(surface, (90, 230, 230), (int(tx), int(ty)), r, 2)
            pygame.draw.line(surface, (60, 140, 140), (self.x, self.y), (tx, ty), 1)


class ResonatorEnemy(Enemy):
    """Резонатор: ускоряет всех врагов рядом."""
    kind = 'resonator'
    AURA = 150.0

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 60, 15)
        self.speed = 80.0
        self.t = 0.0

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.t += dt
        _keep_distance(self, player, dt, 240, 0.6)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        for k in range(2):
            r = (self.t * 80 + k * 75) % self.AURA
            pygame.draw.circle(surface, color_lerp(CFG.COLOR_BG, (255, 220, 120), 1 - r / self.AURA),
                               (int(self.x), int(self.y)), int(r), 1)
        pygame.draw.circle(surface, _body_color(self, (240, 200, 90)), (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), self.radius, 2)


class LeaderEnemy(ChaserEnemy):
    """Вожак: убей его — и отряд растеряется (медленнее, получает +25% урона)."""
    kind = 'leader'

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 130.0
        self.radius = 17
        self.speed = 120.0
        self.contact_damage = 18.0
        self.is_leader = True

    def draw(self, surface: pygame.Surface) -> None:
        a = math.atan2(self.vy, self.vx)
        draw_shape(surface, 'triangle', _body_color(self, (255, 90, 60)), self.x, self.y, self.radius, a)
        draw_shape(surface, 'triangle', CFG.COLOR_ACCENT, self.x, self.y, self.radius, a, 2)


# =====================================================================
# МИНИ-БОСС
# =====================================================================
class WardenEnemy(Enemy):
    """Страж-Призма (волны 5, 15, 25): меняет уязвимый цвет, стреляет цветными очередями, зовёт рой."""
    kind = 'warden'
    boss_like = True

    def __init__(self, x: float, y: float, tier: int = 1):
        super().__init__(x, y, CFG.MINIBOSS_HP * (1 + 0.6 * (tier - 1)), 26)
        self.tier = tier
        self.speed = 65.0
        self.vulnerable_mode = random.choice(MODES)
        self.color_timer = 5.0
        self.burst_timer = 2.0
        self.summon_timer = 6.0
        self.ring_timer = 3.0
        self.t = 0.0

    @property
    def phase(self) -> int:
        return 1 if self.hp > self.max_hp * 0.5 else 2

    def damage_factor(self, bullet_mode: str) -> float:
        if bullet_mode != self.vulnerable_mode:
            return 0.5 if bullet_mode == 'VIOLET' else CFG.BOSS_OFF_COLOR_DAMAGE_MULT
        return 1.0

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.t += dt
        _keep_distance(self, player, dt, 260, 0.9)
        out: List[Any] = []
        self.color_timer -= dt
        if self.color_timer <= 0:
            self.color_timer = 5.0
            self.vulnerable_mode = random.choice([m for m in MODES if m != self.vulnerable_mode])
        self.burst_timer -= dt
        if self.burst_timer <= 0:
            self.burst_timer = 2.4 if self.phase == 1 else 1.7
            ang = math.atan2(player.y - self.y, player.x - self.x)
            c = random.choice(MODES)
            for k in (-0.22, 0.0, 0.22):
                out.append(colored_bullet(self.x, self.y, ang + k, 240, CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult, c,
                                          f"очередь: {self.name}"))
        self.summon_timer -= dt
        if self.summon_timer <= 0:
            self.summon_timer = 7.0
            out += [('spawn', 'swarm', self.x + math.cos(i * 1.57) * 40, self.y + math.sin(i * 1.57) * 40, False)
                    for i in range(4)]
        if self.phase == 2:
            self.ring_timer -= dt
            if self.ring_timer <= 0:
                self.ring_timer = 3.0
                off = random.uniform(0, math.pi)
                for i in range(10):
                    out.append(EnemyBullet(self.x, self.y, math.cos(off + i * 0.628), math.sin(off + i * 0.628), 190,
                                           CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult, f"кольцо: {self.name}"))
        return out

    def draw(self, surface: pygame.Surface) -> None:
        col = _body_color(self, mode_color(self.vulnerable_mode))
        glow = SurfaceCache.get_glow(int(self.radius), col, int(55 * visual('glow')))
        surface.blit(glow, (int(self.x - self.radius * 2), int(self.y - self.radius * 2)))
        draw_shape(surface, 'diamond', (30, 25, 45), self.x, self.y, self.radius, self.t * 0.6)
        draw_shape(surface, 'diamond', col, self.x, self.y, self.radius, self.t * 0.6, 4)
        draw_shape(surface, 'triangle', CFG.COLOR_PRIMARY, self.x, self.y, self.radius * 0.45, -self.t, 2)


# =====================================================================
# БОСС 2: ХРОМАТИЧЕСКАЯ ГИДРА (волна 20, 50…)
# =====================================================================
class HydraHead(Enemy):
    """Голова Гидры: уязвима только к своему цвету, стреляет пулями своего цвета."""
    kind = 'hydra_head'

    def __init__(self, x: float, y: float, color: str = 'RED', body: Any = None, index: int = 0, hp: float = 260):
        super().__init__(x, y, hp, 15)
        self.body = body
        self.index = index
        self.vulnerable_mode = color
        self.color_tag = color
        self.counted = False
        self.fire_timer = 1.5 + index * 0.6

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        b = self.body
        if b is None or not b.alive:
            self.alive = False
            return None
        a = b.t * 0.8 + self.index * 2.094
        self.x, self.y = b.x + math.cos(a) * 70, b.y + math.sin(a) * 70
        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = 1.9
            ang = math.atan2(player.y - self.y, player.x - self.x)
            return [colored_bullet(self.x, self.y, ang + k, 220, CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult,
                                   self.color_tag, f"голова Гидры") for k in (-0.12, 0.12)]
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if self.body is not None:
            pygame.draw.line(surface, (70, 60, 90), (self.body.x, self.body.y), (self.x, self.y), 3)
        col = _body_color(self, mode_color(self.color_tag))
        pygame.draw.circle(surface, col, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), self.radius, 2)


class HydraBoss(BossEnemy):
    """Три головы разных цветов прикрывают тело (пока они живы, тело почти неуязвимо).
    Без голов — таран и спираль. На 35% головы отрастают один раз."""
    title = 'Хроматическая Гидра'

    def __init__(self, x: float, y: float, tier: int = 1):
        super().__init__(x, y, tier)
        self.hp = self.max_hp = CFG.BOSS_HP * 1.15 * (1 + 0.5 * (tier - 1))
        self.heads: List[HydraHead] = []
        self.spawned = False
        self.regrown = False
        self.t = 0.0
        self.vulnerable_mode = None

    @property
    def name(self) -> str:
        return self.title

    @property
    def phase(self) -> int:
        if any(h.alive for h in self.heads):
            return 1 if not self.regrown else 3
        return 2

    def damage_factor(self, bullet_mode: str) -> float:
        return 0.08 if any(h.alive for h in self.heads) else 1.0

    def update(self, dt: float, player: Any) -> Any:
        self.t += dt
        out: List[Any] = []
        if not self.spawned:
            self.spawned = True
            out.append(('hydra_heads', 1.0))
        if not self.regrown and self.hp < self.max_hp * 0.35:
            self.regrown = True
            out.append(('hydra_heads', 0.6))
        heads_alive = any(h.alive for h in self.heads)
        dx, dy = player.x - self.x, player.y - self.y
        nx, ny = vec_normalize(dx, dy)
        if heads_alive:
            self.vx = lerp(self.vx, nx * 45, dt)
            self.vy = lerp(self.vy, ny * 45, dt)
        else:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.attack_timer = 2.2
                out += self._radial(16, 210, random.uniform(0, math.pi))
            self.charge_timer -= dt
            if self.charge_state == 'none' and self.charge_timer <= 0:
                self.charge_timer, self.charge_state, self.charge_t, self.charge_dir = 4.5, 'warn', 0.8, (nx, ny)
            if self.charge_state == 'warn':
                self.charge_t -= dt
                self.vx *= 0.9
                self.vy *= 0.9
                if self.charge_t <= 0:
                    self.charge_state, self.charge_t = 'go', 0.6
            elif self.charge_state == 'go':
                self.charge_t -= dt
                self.vx, self.vy = self.charge_dir[0] * 520, self.charge_dir[1] * 520
                if self.charge_t <= 0:
                    self.charge_state = 'none'
                    self.vx *= 0.2
                    self.vy *= 0.2
            else:
                self.vx = lerp(self.vx, nx * 80, dt * 2)
                self.vy = lerp(self.vy, ny * 80, dt * 2)
        if self.hit_flash > 0:
            self.hit_flash -= dt
        self.x = clamp(self.x + self.vx * dt, self.radius, CFG.SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y + self.vy * dt, self.radius, CFG.SCREEN_HEIGHT - self.radius)
        return out

    def draw(self, surface: pygame.Surface) -> None:
        heads_alive = any(h.alive for h in self.heads)
        col = CFG.COLOR_PRIMARY if self.hit_flash > 0 else ((90, 80, 120) if heads_alive else CFG.COLOR_DANGER)
        if self.charge_state == 'warn':
            pygame.draw.line(surface, CFG.COLOR_DANGER, (self.x, self.y),
                             (self.x + self.charge_dir[0] * 600, self.y + self.charge_dir[1] * 600), 3)
        draw_shape(surface, 'hex', (30, 22, 40), self.x, self.y, self.radius, self.t * 0.4)
        draw_shape(surface, 'hex', col, self.x, self.y, self.radius, self.t * 0.4, 4)
        if heads_alive:
            pygame.draw.circle(surface, (150, 150, 200), (int(self.x), int(self.y)), self.radius + 8, 1)


# =====================================================================
# БОСС 3 (ФИНАЛЬНЫЙ): АБСОЛЮТНЫЙ СПЕКТР (волна 30, 60…)
# =====================================================================
class SpectrumBoss(BossEnemy):
    """Фаза 1 «Призма»: цветные стены пуль — пройти можно только в их цвете.
    Фаза 2 «Инверсия»: физика цветов перемешивается, цветные кольца с просветом.
    Фаза 3 «Распад»: призывает Зеркала и рой, спираль цветных пуль."""
    title = 'Абсолютный Спектр'

    def __init__(self, x: float, y: float, tier: int = 1):
        super().__init__(x, y, tier)
        self.hp = self.max_hp = CFG.BOSS_HP * 1.4 * (1 + 0.5 * (tier - 1))
        self.radius = 38
        self.t = 0.0
        self.wall_timer = 2.0
        self.ring_timer = 2.5
        self.summon_timer = 5.0
        self.last_phase = 1
        self.wall_color_i = 0

    @property
    def name(self) -> str:
        return self.title

    def update(self, dt: float, player: Any) -> Any:
        self.t += dt
        if self.hit_flash > 0:
            self.hit_flash -= dt
        out: List[Any] = []
        ph = self.phase
        if ph != self.last_phase:
            self.last_phase = ph
            if ph == 2:
                out.append(('inversion', 14.0))
        self.color_timer -= dt
        if self.color_timer <= 0:
            self.color_timer = 5.0 if ph < 3 else 3.5
            self.vulnerable_mode = random.choice([m for m in MODES if m != self.vulnerable_mode])
        nx, ny = vec_normalize(player.x - self.x, player.y - self.y)
        dist = vec_distance(self.x, self.y, player.x, player.y)
        sign = 1 if dist > 260 else -1
        self.vx = lerp(self.vx, nx * 60 * sign, dt * 2)
        self.vy = lerp(self.vy, ny * 60 * sign, dt * 2)
        dmg = CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult
        if ph == 1:
            self.wall_timer -= dt
            if self.wall_timer <= 0:
                self.wall_timer = 2.4
                self.wall_color_i = (self.wall_color_i + 1) % 3
                c = MODES[self.wall_color_i]
                base = math.atan2(ny, nx)
                for k in range(15):
                    out.append(colored_bullet(self.x, self.y, base + (k - 7) * 0.09, 200, dmg, c, f"стена: {self.title}"))
        elif ph == 2:
            self.ring_timer -= dt
            if self.ring_timer <= 0:
                self.ring_timer = 2.2
                gap = random.uniform(0, 2 * math.pi)
                c = random.choice(MODES)
                for i in range(22):
                    a = i * 2 * math.pi / 22
                    if abs((a - gap + math.pi) % (2 * math.pi) - math.pi) < 0.45:
                        continue
                    out.append(colored_bullet(self.x, self.y, a, 190, dmg, c, f"кольцо: {self.title}"))
        else:
            self.spiral_timer -= dt
            if self.spiral_timer <= 0:
                self.spiral_timer = 0.16
                self.spiral_angle += 0.5
                for k in range(2):
                    a = self.spiral_angle + k * math.pi
                    out.append(colored_bullet(self.x, self.y, a, 220, dmg, MODES[int(self.t * 2) % 3], f"спираль: {self.title}"))
            self.summon_timer -= dt
            if self.summon_timer <= 0:
                self.summon_timer = 8.0
                out.append(('spawn', 'mirror', self.x - 80, self.y, False))
                out += [('spawn', 'swarm', self.x + math.cos(i) * 60, self.y + math.sin(i) * 60, False) for i in range(5)]
        self.x = clamp(self.x + self.vx * dt, self.radius, CFG.SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y + self.vy * dt, self.radius, CFG.SCREEN_HEIGHT - self.radius)
        return out

    def draw(self, surface: pygame.Surface) -> None:
        col = CFG.COLOR_PRIMARY if self.hit_flash > 0 else mode_color(self.vulnerable_mode)
        glow = SurfaceCache.get_glow(int(self.radius), col, int(80 * visual('glow')))
        surface.blit(glow, (int(self.x - self.radius * 2), int(self.y - self.radius * 2)))
        for i, m in enumerate(MODES):
            draw_shape(surface, 'triangle', mode_color(m), self.x, self.y, self.radius * (1 - i * 0.22),
                       self.t * (0.6 + i * 0.3) * (1 if i % 2 == 0 else -1), 3)
        draw_shape(surface, 'hex', col, self.x, self.y, self.radius, -self.t * 0.2, 4)


# =====================================================================
# ОБЪЕКТЫ ПОЛЯ
# =====================================================================
class Mine:
    """Цветная мина: безопасна, если игрок в её цвете (обезвреживается), иначе взрывается."""

    def __init__(self, x: float, y: float, color: str):
        self.x, self.y, self.color = x, y, color
        self.arm = 0.8
        self.fuse = -1.0
        self.life = 20.0
        self.radius = 9
        self.alive = True

    def update(self, dt: float, game: Any) -> bool:
        self.life -= dt
        if self.arm > 0:
            self.arm -= dt
            return self.life > 0
        p = game.player
        d = vec_distance(self.x, self.y, p.x, p.y)
        if self.fuse < 0 and d < 34 + p.radius:
            if p.mode == self.color:
                game.particles.emit_burst(self.x, self.y, 10, mode_color(self.color), 160.0, 0.4, 2.0)
                game.score += 50
                game.color_mech.add_overload(1)
                return False
            self.fuse = 0.45
        if self.fuse >= 0:
            self.fuse -= dt
            if self.fuse <= 0:
                game.particles.emit_burst(self.x, self.y, 24, mode_color(self.color), 320.0, 0.6, 3.0)
                game.screen_shake.trigger(6.0, 0.2)
                if vec_distance(self.x, self.y, p.x, p.y) < 70 + p.radius:
                    p.take_damage(18, game, self.x, self.y, 'мина Минёра')
                return False
        return self.life > 0

    def draw(self, surface: pygame.Surface, t: float) -> None:
        col = mode_color(self.color)
        r = self.radius + (3 if self.fuse >= 0 and int(t * 20) % 2 == 0 else 0)
        draw_shape(surface, MODE_SHAPES[self.color] if visual('shapes') else 'circle', col, self.x, self.y, r, 0, 0)
        pygame.draw.circle(surface, CFG.COLOR_DANGER if self.arm <= 0 else (90, 90, 100), (int(self.x), int(self.y)), 3)
        if self.fuse >= 0:
            pygame.draw.circle(surface, CFG.COLOR_DANGER, (int(self.x), int(self.y)), 70, 1)


class Beam:
    """Цветной луч: наносит урон один раз; игрок в цвете луча поглощает его."""

    def __init__(self, x: float, y: float, angle: float, color: str, damage: float, duration: float = 0.3,
                 source: str = 'луч Лазерщика'):
        self.x, self.y, self.angle, self.color, self.damage = x, y, angle, color, damage
        self.t = duration
        self.duration = duration
        self.hit = False
        self.source = source

    def update(self, dt: float, game: Any) -> bool:
        self.t -= dt
        p = game.player
        if not self.hit:
            ex, ey = math.cos(self.angle), math.sin(self.angle)
            px, py = p.x - self.x, p.y - self.y
            proj = px * ex + py * ey
            if proj > 0:
                perp = abs(px * ey - py * ex)
                if perp < 7 + p.radius:
                    self.hit = True
                    if p.mode == self.color:
                        game.particles.emit_burst(p.x, p.y, 12, mode_color(self.color), 200.0, 0.4, 2.0)
                        game.color_mech.add_overload(2)
                        game.floating_texts_add(p.x, p.y - 30, 'ПОГЛОЩЕНО', mode_color(self.color))
                    else:
                        p.take_damage(self.damage, game, self.x, self.y, self.source)
        return self.t > 0

    def draw(self, surface: pygame.Surface) -> None:
        k = clamp(self.t / self.duration, 0, 1)
        ex, ey = self.x + math.cos(self.angle) * 1500, self.y + math.sin(self.angle) * 1500
        col = mode_color(self.color)
        pygame.draw.line(surface, col, (self.x, self.y), (ex, ey), max(2, int(14 * k)))
        pygame.draw.line(surface, CFG.COLOR_PRIMARY, (self.x, self.y), (ex, ey), max(1, int(4 * k)))


class PaintZone:
    """Краска: остаётся после некоторых убийств. В своём цвете — быстрее; пули своего цвета — сильнее."""

    def __init__(self, x: float, y: float, color: str, radius: float = 55.0, life: float = 7.0):
        self.x, self.y, self.color, self.radius, self.life, self.max_life = x, y, color, radius, life, life

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0

    def contains(self, x: float, y: float) -> bool:
        return (x - self.x) ** 2 + (y - self.y) ** 2 < self.radius ** 2

    def draw(self, surface: pygame.Surface) -> None:
        a = int(55 * clamp(self.life / 1.5, 0, 1))
        r = int(self.radius)
        s = SurfaceCache.get_circle(r, mode_color(self.color), a)
        surface.blit(s, (int(self.x - r - 1), int(self.y - r - 1)))


class Portal:
    """Цветной портал: игрок проходит, только если он в цвете портала; пули своего цвета — тоже."""

    def __init__(self, x: float, y: float, color: str):
        self.x, self.y, self.color = x, y, color
        self.radius = 26
        self.pair: Optional['Portal'] = None

    def draw(self, surface: pygame.Surface, t: float) -> None:
        col = mode_color(self.color)
        for k in range(3):
            r = int(self.radius - k * 7 + 2 * math.sin(t * 4 + k))
            pygame.draw.circle(surface, color_lerp(CFG.COLOR_BG, col, 1 - k * 0.25), (int(self.x), int(self.y)), max(3, r), 2)
        if visual('shapes'):
            draw_shape(surface, MODE_SHAPES[self.color], col, self.x, self.y, 6)


class PrismWall:
    """Способность «Призменная стена»: сегмент, гасящий вражеские пули."""

    def __init__(self, x: float, y: float, angle: float, life: float = 4.0, length: float = 150.0):
        self.x, self.y, self.angle, self.life, self.length = x, y, angle, life, length

    def update(self, dt: float) -> bool:
        self.life -= dt
        return self.life > 0

    def blocks(self, bx: float, by: float, r: float) -> bool:
        ex, ey = math.cos(self.angle), math.sin(self.angle)
        px, py = bx - self.x, by - self.y
        proj = px * ex + py * ey
        if abs(proj) > self.length / 2:
            return False
        return abs(px * ey - py * ex) < 8 + r

    def draw(self, surface: pygame.Surface) -> None:
        ex, ey = math.cos(self.angle) * self.length / 2, math.sin(self.angle) * self.length / 2
        k = clamp(self.life / 1.0, 0.3, 1)
        pygame.draw.line(surface, color_lerp(CFG.COLOR_BG, CFG.COLOR_PRIMARY, k), (self.x - ex, self.y - ey),
                         (self.x + ex, self.y + ey), 6)
        pygame.draw.line(surface, CFG.COLOR_ACCENT, (self.x - ex, self.y - ey), (self.x + ex, self.y + ey), 2)


EXT_ENEMIES = {
    'swarm': SwarmEnemy, 'shard': ShardEnemy, 'prism': PrismEnemy, 'mirror': MirrorEnemy,
    'chameleon': ChameleonEnemy, 'shieldbearer': ShieldbearerEnemy, 'miner': MinerEnemy, 'laser': LaserEnemy,
    'devourer': DevourerEnemy, 'summoner': SummonerEnemy, 'teleporter': TeleporterEnemy,
    'resonator': ResonatorEnemy, 'leader': LeaderEnemy,
}
EXT_NAMES = {
    'swarm': 'Рой', 'shard': 'Осколок', 'prism': 'Призма', 'mirror': 'Зеркало', 'chameleon': 'Хамелеон',
    'shieldbearer': 'Щитоносец', 'miner': 'Минёр', 'laser': 'Лазерщик', 'devourer': 'Пожиратель',
    'summoner': 'Призыватель', 'teleporter': 'Телепортер', 'resonator': 'Резонатор', 'leader': 'Вожак',
    'warden': 'Страж-Призма', 'hydra_head': 'Голова Гидры',
}
EXT_HINTS = {
    'swarm': 'Слабые и быстрые, приходят десятками. BLUE-волна косит их пачками.',
    'shard': 'Осколок Призмы: полный урон только от своего цвета.',
    'prism': 'Стреляет цветными пулями (в их цвете они поглощаются) и раскалывается на 3 осколка.',
    'mirror': 'Отражает пули ТВОЕГО текущего цвета. Смени цвет и бей.',
    'chameleon': 'Копирует твой цвет с задержкой ~1 с и почти неуязвим к нему — меняй цвет чаще.',
    'shieldbearer': 'Союзники в его круге получают вдвое меньше урона. Убивай первым.',
    'miner': 'Ставит цветные мины. В цвете мины её можно спокойно обезвредить.',
    'laser': 'Тонкая линия — прицеливание, мигание — выстрел. В цвете луча он поглощается.',
    'devourer': 'Каждое попадание его раздувает: на 22-м лопнет кольцом пуль. Бей быстро или взрывом BLUE.',
    'summoner': 'Держится вдали и вызывает рои. Пробейся к нему.',
    'teleporter': 'Прыгает тебе за спину — место прыжка подсвечено заранее.',
    'resonator': 'Ускоряет всех врагов рядом с собой.',
    'leader': 'Вожак отряда. Без него отряд растерян: медленнее и получает +25% урона.',
    'warden': 'Мини-босс. Уязвим к цвету оболочки, зовёт рой, во 2-й фазе стреляет кольцами.',
    'hydra_head': 'Голова Гидры: бей её цветом. Пока головы живы, тело почти неуязвимо.',
}

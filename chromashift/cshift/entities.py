"""Игровые сущности: игрок, пули, враги (включая элит и босса), бонусы, препятствия."""
import math
import random
from typing import Any, List, Optional, Tuple

import pygame

from .config import ALL_MODES, CFG, MODES
from .hires import get_scale, layer
from .utils import (SurfaceCache, circle_collision, clamp, color_lerp, lerp,
                    mode_color, vec_distance, vec_length, vec_normalize, visual)
from .fx import FloatingText

MODE_SHAPES = {'RED': 'triangle', 'BLUE': 'square', 'GREEN': 'circle', 'VIOLET': 'diamond'}


def draw_shape(surface: pygame.Surface, shape: str, color: Tuple[int, int, int],
               x: float, y: float, r: float, angle: float = 0.0, width: int = 0) -> None:
    """Рисует фигуру: используется для режима «формы вместо цвета» и косметики корабля."""
    if shape == 'circle' or r < 2:
        pygame.draw.circle(surface, color, (int(x), int(y)), max(1, int(r)), width)
        return
    sides = {'triangle': 3, 'square': 4, 'diamond': 4, 'hex': 6}.get(shape, 0)
    if not sides:
        pygame.draw.circle(surface, color, (int(x), int(y)), max(1, int(r)), width)
        return
    offset = angle + (math.pi / 4 if shape == 'square' else 0.0)
    pts = [(x + math.cos(offset + i * 2 * math.pi / sides) * r,
            y + math.sin(offset + i * 2 * math.pi / sides) * r) for i in range(sides)]
    pygame.draw.polygon(surface, color, pts, width)


# === ИГРОК ===
class Player:
    """Игрок с тремя физическими режимами, Dash и модификаторами забега (RunMods)."""

    def __init__(self, x: float, y: float, mods: Any = None, settings: Any = None,
                 start_mode: str = 'RED'):
        from .progression import RunMods  # локальный импорт: избегаем цикла
        self.mods = mods if mods is not None else RunMods()
        self.settings = settings
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.radius = CFG.PLAYER_RADIUS
        self.max_hp = max(10, int((CFG.PLAYER_MAX_HP + self.mods.max_hp_add) * self.mods.max_hp_mult))
        self.hp = self.max_hp
        self.mode = start_mode if start_mode in MODES else 'RED'
        self.invuln_timer = 0.0
        self.fire_cooldown = 0.0
        self.facing_x = 0.0
        self.facing_y = -1.0
        self.move_x = 0.0
        self.move_y = 0.0
        self.trail: List[Tuple[float, float, float]] = []
        self.squash_timer = 0.0
        self.squash_scale = 1.0
        self.invuln_flash = 0.0

        self.dash_cooldown = 0.0
        self.dash_cooldown_max = CFG.DASH_COOLDOWN * self.mods.dash_cd_mult
        self.is_dashing = False
        self.dash_timer = 0.0
        self.dash_invuln_timer = 0.0
        self.dash_invuln = False
        self.dash_dir = (0.0, -1.0)

        self.impulse_active = False
        self.impulse_timer = 0.0
        self.shield_charges = self.mods.shield_charges
        self.revives = self.mods.revives
        self.shockwave_cooldown = 0.0
        self.twin_toggle = False
        self.in_resonance = False
        self.last_damage_source = ''
        self.ship_shape = 'circle'
        self.trail_style = 'mode'
        self.color_lock_t = 0.0        # Диссонанс/волна «Один цвет»: смена цвета заблокирована
        self.physics_map: dict = {}     # волна «Инверсия»: режим → чья физика используется
        self.phase_t = 0.0              # VIOLET-навык «Фаза»: неосязаемость
        self.speed_bonus = 1.0          # краска своего цвета и прочие временные бонусы
        self.last_switch_time = -10.0

    # --- Режимы ---
    def set_mode(self, mode: str, game: Any) -> None:
        if mode == self.mode or mode not in ALL_MODES:
            return
        if mode == 'VIOLET' and not getattr(self.mods, 'violet_unlocked', False):
            return
        self.mode = mode
        if mode == 'BLUE':
            self.squash_timer = CFG.PLAYER_SQUASH_DURATION
            if self.mods.blue_shockwave and self.shockwave_cooldown <= 0:
                self.shockwave_cooldown = 3.0
                game.blue_shockwave(self.x, self.y)
        game.sound_manager.play({'RED': 'mode_red', 'BLUE': 'mode_blue', 'GREEN': 'mode_green',
                                 'VIOLET': 'mode_violet'}[mode], 0.4)

    def mode_param(self, name: str) -> float:
        phys = self.physics_map.get(self.mode, self.mode)  # «Инверсия» подменяет физику цвета
        base = CFG.get(f'{phys}_{name}')
        mult = getattr(self.mods, f'{name.lower()}_mult').get(self.mode, 1.0)
        return base * mult

    # --- Dash ---
    def start_dash(self, game: Any) -> bool:
        if self.dash_cooldown > 0 or self.is_dashing:
            return False
        direction = (self.facing_x, self.facing_y)
        if self.settings is not None and self.settings.get('dash_direction') == 'move':
            if abs(self.move_x) + abs(self.move_y) > 0.1:
                direction = vec_normalize(self.move_x, self.move_y)
        if vec_length(*direction) < 0.1:
            return False
        self.dash_dir = direction
        self.is_dashing = True
        self.dash_timer = CFG.DASH_DURATION
        # Неуязвимость: не короче самого рывка (DASH_INVULN_FRAMES = небольшой «хвост»)
        self.dash_invuln_timer = max(CFG.DASH_DURATION, CFG.DASH_INVULN_FRAMES + self.mods.dash_invuln_add)
        self.dash_invuln = True
        self.dash_cooldown = self.dash_cooldown_max
        self.squash_timer = 0.2
        self.squash_scale = 1.3
        game.sound_manager.play('dash', 0.5)
        game.particles.emit_burst(self.x, self.y, 15, mode_color(self.mode), 300.0, 0.5, 3.0)
        game.on_player_dash(self)
        return True

    # --- Обновление ---
    def update(self, dt: float, move: Tuple[float, float], aim: Tuple[float, float], game: Any) -> None:
        if self.invuln_timer > 0:
            self.invuln_timer -= dt
            self.invuln_flash += dt * 8
        if self.fire_cooldown > 0:
            self.fire_cooldown -= dt
        if self.dash_cooldown > 0:
            self.dash_cooldown -= dt
        if self.shockwave_cooldown > 0:
            self.shockwave_cooldown -= dt
        if self.color_lock_t > 0:
            self.color_lock_t -= dt
        if self.phase_t > 0:
            self.phase_t -= dt
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
        if self.dash_invuln_timer > 0:
            self.dash_invuln_timer -= dt
        self.dash_invuln = self.is_dashing or self.dash_invuln_timer > 0

        ax, ay = aim[0] - self.x, aim[1] - self.y
        if vec_length(ax, ay) > 10:
            self.facing_x, self.facing_y = vec_normalize(ax, ay)

        dx, dy = move
        if abs(dx) + abs(dy) > 1e-6:
            length = vec_length(dx, dy)
            if length > 1.0:
                dx, dy = dx / length, dy / length
        self.move_x, self.move_y = dx, dy

        if self.is_dashing:
            self.dash_timer -= dt
            speed = CFG.DASH_SPEED * self.mods.dash_speed_mult
            self.vx = self.dash_dir[0] * speed
            self.vy = self.dash_dir[1] * speed
            if len(self.trail) < 8:
                self.trail.append((self.x, self.y, 1.5))
            if self.dash_timer <= 0:
                self.is_dashing = False
                self.vx *= 0.5
                self.vy *= 0.5
        else:
            accel = self.mode_param('ACCEL')
            decel = self.mode_param('DECEL')
            max_speed = self.mode_param('MAX_SPEED')
            if self.in_resonance:
                max_speed *= 1.0 + CFG.RESONANCE_SPEED_BOOST
            max_speed *= self.speed_bonus
            if dx != 0 or dy != 0:
                self.vx += dx * accel * dt
                self.vy += dy * accel * dt
            else:
                decay = math.exp(-decel * dt)
                self.vx *= decay
                self.vy *= decay
            speed = vec_length(self.vx, self.vy)
            if speed > max_speed:
                self.vx = (self.vx / speed) * max_speed
                self.vy = (self.vy / speed) * max_speed
            elif self.physics_map.get(self.mode, self.mode) == 'GREEN' and speed > 10:
                drift = CFG.GREEN_LATERAL_DRIFT * self.mods.drift_mult * math.sin(game.game_time * 5)
                perp_x, perp_y = -self.vy, self.vx
                self.vx += perp_x * drift * dt * 60
                self.vy += perp_y * drift * dt * 60

        self.x += self.vx * dt
        self.y += self.vy * dt
        self.x = clamp(self.x, self.radius, CFG.SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y, self.radius, CFG.SCREEN_HEIGHT - self.radius)

        if vec_length(self.vx, self.vy) > 50:
            self.trail.append((self.x, self.y, 1.0))
        if len(self.trail) > 5:
            self.trail.pop(0)
        self.trail = [(x, y, a * 0.75) for x, y, a in self.trail if a * 0.75 > 0.05]

    # --- Стрельба ---
    def shoot(self, game: Any) -> bool:
        if self.fire_cooldown > 0 or self.phase_t > 0:
            return False
        self.fire_cooldown = CFG.FIRE_COOLDOWN / max(0.2, self.mods.fire_rate_mult)
        aim_x, aim_y = self.facing_x, self.facing_y
        base_angle = math.atan2(aim_y, aim_x)
        angles = [0.0]
        dmg_mult = self.mods.damage_mult * self.mods.mode_damage_mult.get(self.mode, 1.0)
        cm = getattr(game, 'color_mech', None)
        if cm is not None:
            dmg_mult *= cm.damage_bonus()
        if self.mode == 'VIOLET':
            dmg_mult *= 0.85
        if self.mode == 'BLUE' and self.mods.blue_split:
            angles = [-0.18, 0.0, 0.18]
            dmg_mult *= 0.6
        offsets = [0.0]
        if self.mods.twin_barrel:
            offsets = [-5.0, 5.0]
            dmg_mult *= 0.6
        for ang in angles:
            for off in offsets:
                bx, by = math.cos(base_angle + ang), math.sin(base_angle + ang)
                ox, oy = -by * off, bx * off
                b = PlayerBullet(self.x + bx * self.radius * 1.3 + ox,
                                 self.y + by * self.radius * 1.3 + oy,
                                 bx, by, self.mode, self.impulse_active)
                b.damage = CFG.BULLET_DAMAGE * dmg_mult
                b.speed = CFG.BULLET_SPEED * self.mods.bullet_speed_mult
                b.pierce_left = getattr(self.mods, 'bullet_pierce', 0) + (1 if self.mode == 'VIOLET' else 0)
                b.bounces = getattr(self.mods, 'bullet_bounce', 0)
                if getattr(self.mods, 'bullet_homing', False):
                    b.homing = True
                    b.homing_strength = 2.0
                game.player_bullets.append(b)
                if cm is not None:
                    cm.decorate_bullet(b)
        game.on_player_shot(len(angles) * len(offsets))

        recoil = CFG.get(f'{self.mode}_RECOIL')
        max_speed = CFG.get(f'{self.mode}_MAX_SPEED')
        game.screen_shake.trigger({'RED': 1.2, 'BLUE': 2.6, 'GREEN': 0.6, 'VIOLET': 0.9}[self.mode] * 0.6, 0.06)
        self.vx -= aim_x * max_speed * recoil
        self.vy -= aim_y * max_speed * recoil
        if self.mode == 'BLUE':
            self.squash_timer = CFG.PLAYER_SQUASH_DURATION * 0.7
            self.blue_aoe_attack(game)
        game.particles.emit_directional(
            self.x + aim_x * self.radius * 1.3, self.y + aim_y * self.radius * 1.3,
            CFG.SHOOT_PARTICLES, (aim_x, aim_y), 0.4, mode_color(self.mode), 350.0, 0.3, 2.0)
        game.sound_manager.play({'RED': 'shoot_red', 'BLUE': 'shoot_blue', 'GREEN': 'shoot_green',
                                 'VIOLET': 'shoot_violet'}[self.mode], 0.5)
        return True

    def blue_aoe_attack(self, game: Any) -> None:
        radius = CFG.BLUE_AOE_RADIUS * self.mods.blue_aoe_mult
        game.particles.emit_burst(self.x, self.y, 15, mode_color('BLUE'), 200.0, 0.5, 3.0)
        dmg_mult = self.mods.damage_mult * self.mods.mode_damage_mult['BLUE']
        pull = getattr(self.mods, 'blue_gravity', False)
        hits = 0
        for enemy in game.spatial_hash.query(self.x, self.y, radius + 50):
            if not getattr(enemy, 'alive', False) or not isinstance(enemy, Enemy):
                continue
            if vec_distance(self.x, self.y, enemy.x, enemy.y) < radius + enemy.radius:
                base = CFG.BULLET_DAMAGE if isinstance(enemy, DissonanceEnemy) else CFG.BULLET_DAMAGE * 0.5
                if pull and not isinstance(enemy, BossEnemy):  # узел «Гравитационный якорь»: BLUE притягивает
                    nx, ny = vec_normalize(self.x - enemy.x, self.y - enemy.y)
                    enemy.vx += nx * 160
                    enemy.vy += ny * 160
                enemy.take_damage(base * dmg_mult, game, 'BLUE', is_aoe=True)
                hits += 1
        cm = getattr(game, 'color_mech', None)
        if cm is not None and hits >= 3:
            cm.trial_event('blue_multi')

    # --- Урон ---
    def can_be_damaged(self, game: Any) -> bool:
        return not (self.invuln_timer > 0 or self.dash_invuln or self.phase_t > 0 or game.god_mode or game.is_training)

    def take_damage(self, damage: float, game: Any, source_x: float, source_y: float,
                    source: str = 'неизвестно') -> bool:
        if not self.can_be_damaged(game):
            return False
        damage = max(1, int(round(damage * game.enemy_damage_mult)))
        if getattr(self.mods, 'glass_mode', False):
            damage = max(damage, 25)  # риск «Стекло»
        if self.shield_charges > 0:
            self.shield_charges -= 1
            self.invuln_timer = 0.6
            game.particles.emit_burst(self.x, self.y, 20, CFG.COLOR_PRIMARY, 260.0, 0.5, 3.0)
            game.floating_texts.append(FloatingText(self.x, self.y - 24, "ЩИТ", CFG.COLOR_PRIMARY, 0.8, 18))
            game.sound_manager.play('shield', 0.5)
            return False
        self.hp -= damage
        self.last_damage_source = source
        self.invuln_timer = CFG.PLAYER_INVULN_TIME * self.mods.invuln_time_mult
        game.screen_shake.trigger(12.0, CFG.SHAKE_DURATION, (self.x - source_x, self.y - source_y))
        game.particles.emit_burst(self.x, self.y, 12, CFG.COLOR_DANGER, 280.0, 0.6, 3.0)
        game.floating_texts.append(FloatingText(self.x, self.y - 20, f"-{damage}", CFG.COLOR_DANGER, 0.8, 20))
        game.sound_manager.play('hit', 0.6)
        game.on_player_damaged(damage, source)
        if self.hp <= 0:
            if self.revives > 0:
                self.revives -= 1
                self.hp = max(1, int(self.max_hp * 0.3))
                self.invuln_timer = 2.0
                game.floating_texts.append(FloatingText(self.x, self.y - 40, "ВТОРОЙ ШАНС!", CFG.COLOR_ACCENT, 1.5, 26))
                game.flash(CFG.COLOR_ACCENT, 0.5)
                game.sound_manager.play('revive', 0.7)
            else:
                self.hp = 0
                game.player_died()
        return True

    # --- Отрисовка ---
    def draw(self, surface: pygame.Surface, time: float) -> None:
        alpha = 255
        if self.invuln_timer > 0:
            fade_t = self.invuln_timer / max(0.01, CFG.PLAYER_INVULN_TIME)
            alpha = int(128 + 127 * math.sin(fade_t * math.pi * 8))
        color = mode_color(self.mode)
        trail_color = color
        if self.trail_style == 'white':
            trail_color = CFG.COLOR_PRIMARY
        elif self.trail_style == 'gold':
            trail_color = CFG.COLOR_ACCENT
        elif self.trail_style == 'rainbow':
            trail_color = mode_color(MODES[int(time * 6) % 3])
        if self.phase_t > 0:
            alpha = 90
        for x, y, ta in self.trail:
            size = int(self.radius * ta * 0.8)
            if size > 0:
                ts = SurfaceCache.get_circle(size, trail_color, int(80 * ta))
                surface.blit(ts, (int(x - size - 1), int(y - size - 1)))

        rx = int(self.radius * self.squash_scale)
        ry = int(self.radius * (2 - self.squash_scale))
        glow_a = int(60 * (0.5 + 0.3 * math.sin(time * 4)) * alpha / 255 * visual('glow'))
        glow = SurfaceCache.get_glow(rx, color, glow_a)
        surface.blit(glow, (int(self.x - rx * 2), int(self.y - rx * 2)))

        shape = MODE_SHAPES[self.mode] if visual('shapes') else self.ship_shape
        if shape == 'circle':
            body = layer((rx * 2, ry * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(body, (*color, alpha), (0, 0, rx * 2, ry * 2))
            surface.blit(body, (int(self.x - rx), int(self.y - ry)))
            pygame.draw.ellipse(surface, CFG.COLOR_PRIMARY, (int(self.x - rx), int(self.y - ry), rx * 2, ry * 2), 2)
        else:
            angle = math.atan2(self.facing_y, self.facing_x)
            draw_shape(surface, shape, color, self.x, self.y, rx * 1.15, angle)
            draw_shape(surface, shape, CFG.COLOR_PRIMARY, self.x, self.y, rx * 1.15, angle, 2)

        core = int(rx * 0.4)
        if core > 0:
            cs = SurfaceCache.get_circle(core, CFG.COLOR_PRIMARY, alpha)
            surface.blit(cs, (int(self.x - core), int(self.y - core)))
        pygame.draw.circle(surface, CFG.COLOR_PRIMARY,
                           (int(self.x + self.facing_x * (self.radius + 15)),
                            int(self.y + self.facing_y * (self.radius + 15))), 3)
        if self.shield_charges > 0:
            pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), self.radius + 7, 1)
        if self.color_lock_t > 0:
            pygame.draw.circle(surface, (150, 150, 160), (int(self.x), int(self.y)), self.radius + 11, 1)
            draw_shape(surface, 'square', (150, 150, 160), self.x, self.y - self.radius - 16, 4, time * 4, 1)
        if self.impulse_active:
            pulse = 0.5 + 0.5 * math.sin(time * 10)
            pygame.draw.circle(surface, color_lerp(CFG.COLOR_BG, color, pulse),
                               (int(self.x), int(self.y)), int(self.radius * 2.5), 2)


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
        self.damage = float(CFG.BULLET_DAMAGE)
        self.speed = CFG.BULLET_SPEED
        self.trail: List[Tuple[float, float, float]] = []
        self.is_refracted = False
        self.is_piercing = is_piercing
        self.hit_enemies: List[int] = []
        self.ricochets = 0
        self.homing = False
        self.homing_strength = 6.0
        self.pierce_left = 0      # пробивание обычных пуль (узлы дерева, VIOLET)
        self.bounces = 0          # отскоки от краёв арены (узел, волна «Зеркало»)
        self.mix: Optional[str] = None  # смешанный выстрел двух цветов
        self.crit = False
        self.painted = False
        self.slow_hit = False

    def update(self, dt: float, game: Any = None) -> bool:
        if self.homing and game is not None:
            target = game.nearest_enemy(self.x, self.y, 320, exclude=self.hit_enemies)
            if target is not None:
                tx, ty = vec_normalize(target.x - self.x, target.y - self.y)
                k = min(1.0, dt * self.homing_strength)
                self.dx, self.dy = vec_normalize(lerp(self.dx, tx, k), lerp(self.dy, ty, k))
        self.x += self.dx * self.speed * dt
        self.y += self.dy * self.speed * dt
        mirror = game is not None and getattr(getattr(game, 'director', None), 'special', None) == 'mirror'
        if self.bounces > 0 or (mirror and not getattr(self, 'mirror_used', False)):
            W, H = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
            bounced = False
            if self.x < 0 or self.x > W:
                self.dx, self.x, bounced = -self.dx, clamp(self.x, 0, W), True
            if self.y < 0 or self.y > H:
                self.dy, self.y, bounced = -self.dy, clamp(self.y, 0, H), True
            if bounced:
                if self.bounces > 0:
                    self.bounces -= 1
                else:
                    self.mirror_used = True
        self.lifetime -= dt
        self.trail.append((self.x, self.y, 1.0))
        if len(self.trail) > 4:
            self.trail.pop(0)
        self.trail = [(x, y, a * 0.6) for x, y, a in self.trail]
        return self.lifetime > 0 and 0 <= self.x <= CFG.SCREEN_WIDTH and 0 <= self.y <= CFG.SCREEN_HEIGHT

    def ricochet(self, game: Any, from_enemy: Any) -> bool:
        """Отражённая пуля перескакивает к следующему врагу."""
        if self.ricochets <= 0:
            return False
        target = game.nearest_enemy(self.x, self.y, 400, exclude=self.hit_enemies + [from_enemy.id])
        if target is None:
            return False
        self.ricochets -= 1
        self.dx, self.dy = vec_normalize(target.x - self.x, target.y - self.y)
        self.hit_enemies.append(from_enemy.id)
        self.lifetime = max(self.lifetime, 0.8)
        return True

    def draw(self, surface: pygame.Surface) -> None:
        color = mode_color(self.mode)
        for x, y, a in self.trail:
            size = int(self.radius * a * 0.8)
            if size > 0:
                ts = SurfaceCache.get_circle(size, color, int(120 * a))
                surface.blit(ts, (int(x - size - 1), int(y - size - 1)))
        r = self.radius * 1.5 if (self.is_piercing or self.is_refracted or self.mix) else self.radius
        if self.mix:
            pygame.draw.circle(surface, CFG.COLOR_ACCENT, (int(self.x), int(self.y)), int(r + 3), 1)
        if self.crit:
            pygame.draw.circle(surface, (255, 240, 150), (int(self.x), int(self.y)), int(r + 2), 1)
        if visual('shapes'):
            draw_shape(surface, MODE_SHAPES[self.mode], color, self.x, self.y, r + 1,
                       math.atan2(self.dy, self.dx))
        else:
            pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(r))
            pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), max(1, int(r) - 1))


# === ПУЛЯ ВРАГА ===
class EnemyBullet:
    def __init__(self, x: float, y: float, dx: float, dy: float,
                 speed: Optional[float] = None, damage: Optional[float] = None,
                 source: str = 'пуля стрелка', radius: Optional[int] = None, color: Optional[str] = None):
        self.color = color  # цветная пуля: поглощается, если игрок в том же цвете
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.speed = speed if speed is not None else CFG.SHOOTER_BULLET_SPEED
        self.damage = damage if damage is not None else CFG.SHOOTER_BULLET_DAMAGE
        self.radius = radius if radius is not None else CFG.SHOOTER_BULLET_RADIUS
        self.lifetime = 4.0
        self.trail: List[Tuple[float, float, float]] = []
        self.source = source
        self.alive = True

    def update(self, dt: float, game: Any) -> bool:
        mult = (CFG.ECHO_SLOWDOWN_MULT if game.echo_chamber_active else 1.0) * game.enemy_bullet_speed_mult
        self.x += self.dx * self.speed * mult * dt
        self.y += self.dy * self.speed * mult * dt
        self.lifetime -= dt
        self.trail.append((self.x, self.y, 1.0))
        if len(self.trail) > 3:
            self.trail.pop(0)
        self.trail = [(x, y, a * 0.7) for x, y, a in self.trail]
        return (self.alive and self.lifetime > 0 and
                -20 <= self.x <= CFG.SCREEN_WIDTH + 20 and -20 <= self.y <= CFG.SCREEN_HEIGHT + 20)

    def draw(self, surface: pygame.Surface) -> None:
        for x, y, a in self.trail:
            size = int(self.radius * a * 0.7)
            if size > 0:
                ts = SurfaceCache.get_circle(size, CFG.COLOR_DANGER, int(150 * a))
                surface.blit(ts, (int(x - size - 1), int(y - size - 1)))
        if self.color:
            col = mode_color(self.color)
            if visual('shapes'):
                draw_shape(surface, MODE_SHAPES[self.color], col, self.x, self.y, self.radius + 2)
            else:
                pygame.draw.circle(surface, col, (int(self.x), int(self.y)), self.radius + 1)
            pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), max(1, self.radius - 2))
            return
        pygame.draw.circle(surface, CFG.COLOR_DANGER, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, CFG.COLOR_ACCENT, (int(self.x), int(self.y)), max(1, self.radius - 1))


# === ЭЛИТНЫЕ МОДИФИКАТОРЫ ===
ELITE_MODS = {
    'fast': ('Быстрый', (255, 230, 120)),
    'armored': ('Бронированный', (180, 190, 210)),
    'splitting': ('Расщепляющийся', (255, 140, 220)),
    'shielded': ('Цветной щит', (255, 255, 255)),
    'vampire': ('Вампир', (200, 40, 60)),
    'accelerator': ('Ускоритель', (120, 255, 255)),
    'reflective': ('Отражающая аура', (220, 220, 255)),
}
ENEMY_NAMES = {
    'chaser': 'Преследователь', 'shooter': 'Стрелок', 'kamikaze': 'Камикадзе',
    'dissonance': 'Диссонанс', 'boss': 'Диссонанс-Прайм', 'dummy': 'Манекен', 'turret': 'Турель',
}
ENEMY_HINTS = {
    'chaser': 'Бежит на вас и бьёт касанием. После удара отступает и перегруппировывается.',
    'shooter': 'Держит дистанцию и стреляет. Смените цвет перед попаданием — Преломление.',
    'kamikaze': 'Красный круг — зона взрыва. Рывок даёт неуязвимость.',
    'dissonance': 'Броня цвета корпуса: бейте ДРУГИМ цветом. Его импульс глушит смену цвета. Отражённая пуля убивает сразу.',
}


# === БАЗОВЫЙ ВРАГ ===
class Enemy:
    kind = 'enemy'

    def __init__(self, x: float, y: float, hp: float, radius: float):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.hp = float(hp)
        self.max_hp = float(hp)
        self.radius = radius
        self.alive = True
        self.hit_flash = 0.0
        self.id = id(self)
        self.speed = 0.0
        self.damage_mult = 1.0
        self.elite: List[str] = []
        self.vulnerable_mode: Optional[str] = None  # цветной щит: полный урон только от этого режима
        self.counted = True  # учитывается в прогрессе волны
        self.color_tag: Optional[str] = None  # цвет врага (броня/слабость) — для цепных реакций и «точных» убийств
        self.spawn_t = 0.35       # анимация появления
        self.contact_damage = 0.0  # урон касанием (0 — по правилам класса)
        self.aura_shield = False   # под щитом Щитоносца
        self.aura_speed = 1.0      # аура Резонатора/Ускорителя
        self.scatter_t = 0.0       # отряд потерял вожака
        self.slow_t = 0.0          # морозный выстрел
        self.stun_t = 0.0          # парирование касанием
        self.retreat_t = 0.0       # отступление после удара
        self.squad_id: Optional[int] = None
        self.is_leader = False
        self.absorbed = 0

    @property
    def name(self) -> str:
        base = ENEMY_NAMES.get(self.kind, self.kind)
        return f"{base} (элита)" if self.elite else base

    def apply_scaling(self, hp_mult: float, speed_mult: float, dmg_mult: float) -> None:
        self.hp *= hp_mult
        self.max_hp *= hp_mult
        self.speed *= speed_mult
        self.damage_mult *= dmg_mult

    def make_elite(self, mods: List[str], shield_mode: Optional[str] = None) -> None:
        self.elite = list(mods)
        if 'fast' in mods:
            self.speed *= 1.4
        if 'armored' in mods:
            # 0.7.0: меньше «губки» (было ×2.2 HP и −25% урона), зато бьёт больнее
            self.hp *= 1.5
            self.max_hp *= 1.5
            self.damage_mult *= 1.25
        if 'shielded' in mods:
            self.vulnerable_mode = shield_mode or random.choice(MODES)
        self.radius *= 1.15

    def damage_factor(self, bullet_mode: str) -> float:
        factor = 1.0
        if self.vulnerable_mode is not None and bullet_mode != self.vulnerable_mode:
            factor *= 0.5 if bullet_mode == 'VIOLET' else 0.15  # VIOLET — «фазовые» пули
        if 'armored' in self.elite:
            factor *= 0.85
        if self.aura_shield:
            factor *= 0.5
        if self.scatter_t > 0:
            factor *= 1.25
        return factor

    def weakness(self) -> Optional[str]:
        """Цвет, которым этого врага «правильно» убивать (для бонуса «ТОЧНО»)."""
        return self.vulnerable_mode

    def time_factor(self) -> float:
        """Множитель хода времени врага: заморозка, оглушение, растерянность, ауры."""
        if self.stun_t > 0:
            return 0.0
        k = self.aura_speed
        if self.slow_t > 0:
            k *= 0.5
        if self.scatter_t > 0:
            k *= 0.6
        return k

    def tick_status(self, dt: float) -> None:
        for attr in ('spawn_t', 'scatter_t', 'slow_t', 'stun_t', 'retreat_t'):
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, max(0.0, v - dt))
        self.aura_shield = False
        self.aura_speed = 1.0

    def take_damage(self, damage: float, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        if not self.alive:
            return False
        self.hp -= damage * self.damage_factor(bullet_mode)
        self.hit_flash = 0.1
        game.particles.emit_burst(self.x, self.y, CFG.HIT_PARTICLES, mode_color(bullet_mode), 200.0, 0.4, 2.0)
        if self.hp <= 0:
            self.alive = False
            self.on_death(game, bullet_mode)
            return True
        return False

    def on_death(self, game: Any, killer_mode: str) -> None:
        game.on_enemy_killed(self, killer_mode)

    def update(self, dt: float, player: Any) -> Any:
        if self.hit_flash > 0:
            self.hit_flash -= dt
        return None

    def draw(self, surface: pygame.Surface) -> None:
        pass

    def draw_overlay(self, surface: pygame.Surface, time: float) -> None:
        """Индикация элит и цветного щита (рисуется поверх тела врага)."""
        if self.vulnerable_mode is not None:
            pulse = 0.6 + 0.4 * math.sin(time * 6)
            col = color_lerp(CFG.COLOR_BG, mode_color(self.vulnerable_mode), pulse)
            pygame.draw.circle(surface, col, (int(self.x), int(self.y)), int(self.radius + 6), 3)
            if visual('shapes'):
                draw_shape(surface, MODE_SHAPES[self.vulnerable_mode], col,
                           self.x, self.y - self.radius - 12, 5)
        if self.elite:
            for i, m in enumerate(self.elite):
                if m == 'shielded':
                    continue
                c = ELITE_MODS[m][1]
                a = time * 2 + i * 2.1
                pygame.draw.circle(surface, c, (int(self.x + math.cos(a) * (self.radius + 10)),
                                                int(self.y + math.sin(a) * (self.radius + 10))), 3)
        if self.is_leader:
            pts = [(self.x - 8, self.y - self.radius - 6), (self.x - 8, self.y - self.radius - 14),
                   (self.x - 3, self.y - self.radius - 9), (self.x, self.y - self.radius - 16),
                   (self.x + 3, self.y - self.radius - 9), (self.x + 8, self.y - self.radius - 14),
                   (self.x + 8, self.y - self.radius - 6)]
            pygame.draw.polygon(surface, CFG.COLOR_ACCENT, pts)
        if self.aura_shield:
            pygame.draw.circle(surface, (150, 200, 255), (int(self.x), int(self.y)), int(self.radius + 4), 1)
        if self.slow_t > 0:
            pygame.draw.circle(surface, (170, 230, 255), (int(self.x), int(self.y)), int(self.radius + 2), 2)
        if self.stun_t > 0:
            for k in range(3):
                a = time * 6 + k * 2.1
                pygame.draw.circle(surface, CFG.COLOR_ACCENT, (int(self.x + math.cos(a) * 10),
                                                               int(self.y - self.radius - 8 + math.sin(a) * 3)), 2)
        if self.color_tag and self.color_tag != self.vulnerable_mode:
            # Иконка цвета врага (для доступности — форма вместо цвета)
            col = mode_color(self.color_tag)
            draw_shape(surface, MODE_SHAPES.get(self.color_tag, 'circle'), col, self.x + self.radius + 6,
                       self.y - self.radius - 4, 4, 0, 0 if visual('shapes') else 1)
        if self.spawn_t > 0:
            k = self.spawn_t / 0.35
            pygame.draw.circle(surface, CFG.COLOR_PRIMARY, (int(self.x), int(self.y)), int(self.radius + 30 * k), 1)
        if self.max_hp > 120 and self.hp < self.max_hp:
            w = int(self.radius * 2)
            t = clamp(self.hp / self.max_hp, 0, 1)
            pygame.draw.rect(surface, (40, 45, 60), (int(self.x - w / 2), int(self.y - self.radius - 10), w, 4))
            pygame.draw.rect(surface, CFG.COLOR_DANGER, (int(self.x - w / 2), int(self.y - self.radius - 10), int(w * t), 4))


class ChaserEnemy(Enemy):
    kind = 'chaser'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, CFG.CHASER_HP, CFG.CHASER_RADIUS)
        self.speed = CFG.CHASER_SPEED
        self.wobble_phase = random.uniform(0, math.pi * 2)
        self.flank_direction = random.choice([-1, 1])
        self.contact_damage = float(CFG.CHASER_DAMAGE)

    def update(self, dt: float, player: Any) -> None:
        super().update(dt, player)
        self.wobble_phase += dt * 3

        dx = player.x - self.x
        dy = player.y - self.y
        dist = vec_length(dx, dy)
        if self.scatter_t > 0:  # отряд без вожака мечется
            dx, dy = math.cos(self.wobble_phase * 1.7) * 100, math.sin(self.wobble_phase * 1.3) * 100
            dist = 100.0
        elif self.retreat_t > 0:  # после удара — отступает и перегруппировывается
            dx, dy, dist = -dx, -dy, max(1.0, dist)
        
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
    kind = 'shooter'

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
                return EnemyBullet(self.x, self.y, bullet_dx, bullet_dy,
                                   damage=CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult,
                                   source=f"пуля: {self.name}")
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
    kind = 'kamikaze'

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
            game.player.take_damage(CFG.KAMIKAZE_EXPLOSION_DAMAGE * self.damage_mult, game,
                                    self.x, self.y, f"взрыв: {self.name}")
        game.on_kamikaze_exploded(self)
    
    def draw(self, surface: pygame.Surface) -> None:
        color = CFG.COLOR_DANGER if self.hit_flash <= 0 else CFG.COLOR_PRIMARY
        
        pulse = 0.8 + 0.2 * math.sin(self.pulse_phase)
        radius = int(self.radius * pulse)
        
        if self.warning_active:
            warn_t = self.warn_timer / CFG.KAMIKAZE_WARN_TIME
            warn_alpha = int(150 * (1 - warn_t))
            warn_radius = int(CFG.KAMIKAZE_WARN_RADIUS * (1 - warn_t * 0.3))
            
            warn_surf = layer((warn_radius * 2, warn_radius * 2), pygame.SRCALPHA)
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
    """Диссонанс 0.7.0: цветная броня вместо огромного запаса HP.

    * Корпус окрашен в один из цветов и почти не получает урона пулями ЭТОГО цвета,
      остальные цвета бьют в полную силу. Цвет брони меняется (мерцание перед сменой).
    * Взрыв BLUE и отражённые пули по-прежнему работают (отражённая убивает сразу).
    * Угроза: импульс «глушения» — внутри круга игрок не может сменить цвет.
    """
    kind = 'dissonance'

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = float(CFG.DISSONANCE_HP)
        self.max_hp = float(CFG.DISSONANCE_HP)
        self.radius = CFG.DISSONANCE_RADIUS
        self.glitch_offset = 0.0
        self.glitch_phase = 0.0
        self.speed = CFG.DISSONANCE_SPEED
        self.contact_damage = float(CFG.DISSONANCE_DAMAGE)
        self.color_tag = random.choice(MODES)
        self.color_timer = CFG.DISSONANCE_COLOR_TIME * random.uniform(0.6, 1.0)
        self.jam_timer = CFG.DISSONANCE_JAM_INTERVAL * random.uniform(0.5, 1.0)
        self.jam_warn = 0.0
        self.jam_flash = 0.0

    def damage_factor(self, bullet_mode: str) -> float:
        f = super().damage_factor(bullet_mode)
        if bullet_mode == self.color_tag:
            f *= CFG.DISSONANCE_ARMOR_MULT
        elif bullet_mode == 'VIOLET':
            f *= 0.6
        return f

    def weakness(self) -> Optional[str]:
        return None  # любой цвет, кроме цвета брони

    def take_damage(self, damage: float, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        if not self.alive:
            return False
        mult = 1.0
        if is_aoe and bullet_mode == 'BLUE':
            mult = 1.0 / max(0.01, self.damage_factor('BLUE'))  # взрыв BLUE игнорирует броню
        self.hp -= damage * mult * self.damage_factor(bullet_mode)
        self.hit_flash = 0.1
        self.glitch_offset = random.uniform(-5, 5)
        armored = bullet_mode == self.color_tag and not is_aoe
        game.particles.emit_burst(self.x, self.y, 2 if armored else 5, mode_color(bullet_mode), 150.0, 0.3, 2.0)
        if armored and random.random() < 0.15:
            game.floating_texts.append(FloatingText(self.x, self.y - 24, 'БРОНЯ', (170, 170, 180), 0.5, 13))
        if self.hp <= 0:
            self.alive = False
            self.on_death(game, bullet_mode)
            return True
        return False

    def on_perfect_refraction_hit(self, game: Any) -> None:
        """Отражённая пуля мгновенно уничтожает Диссонанс."""
        if not self.alive:
            return
        self.alive = False
        game.particles.emit_burst(self.x, self.y, 30, CFG.COLOR_ACCENT, 400.0, 1.0, 4.0)
        game.particles.emit_spiral(self.x, self.y, 25, CFG.COLOR_PRIMARY, 300.0)
        game.floating_texts.append(FloatingText(self.x, self.y, "ГАРМОНИЯ!", CFG.COLOR_ACCENT, 1.5, 24))
        game.sound_manager.play('refraction_perfect', 0.8)
        game.screen_shake.trigger(12.0, 0.3, (0, 0))
        game.on_enemy_killed(self, game.player.mode, refraction_kill=True)

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.glitch_phase += dt * 15
        if random.random() < 0.1:
            self.glitch_offset = random.uniform(-3, 3)
        else:
            self.glitch_offset *= 0.9
        self.color_timer -= dt
        if self.color_timer <= 0:
            self.color_tag = random.choice([m for m in MODES if m != self.color_tag])
            self.color_timer = CFG.DISSONANCE_COLOR_TIME
        if self.jam_flash > 0:
            self.jam_flash -= dt
        if self.jam_warn > 0:
            self.jam_warn -= dt
            if self.jam_warn <= 0:
                self.jam_flash = 0.35
                return ('jam', self.x, self.y, CFG.DISSONANCE_JAM_RADIUS)
            return None
        self.jam_timer -= dt
        if self.jam_timer <= 0 and vec_distance(self.x, self.y, player.x, player.y) < CFG.DISSONANCE_JAM_RADIUS * 2.2:
            self.jam_timer = CFG.DISSONANCE_JAM_INTERVAL
            self.jam_warn = 0.7
        return None

    def draw(self, surface: pygame.Surface) -> None:
        changing = self.color_timer < 0.6 and int(self.glitch_phase) % 2 == 0
        base = mode_color(self.color_tag)
        color = CFG.COLOR_PRIMARY if self.hit_flash > 0 else (color_lerp(base, CFG.COLOR_PRIMARY, 0.6) if changing else base)
        angle = math.atan2(self.vy, self.vx)
        for offset in (-2, 0, 2):
            x = self.x + self.glitch_offset + offset
            y = self.y + offset
            pts = [(x + math.cos(angle + i * 2.0944) * self.radius, y + math.sin(angle + i * 2.0944) * self.radius)
                   for i in range(3)]
            if offset == 0:
                pygame.draw.polygon(surface, color, pts)
                pygame.draw.polygon(surface, CFG.COLOR_PRIMARY, pts, 2)
            else:
                pygame.draw.polygon(surface, color_lerp(CFG.COLOR_BG, color, 0.45), pts, 1)
        pygame.draw.circle(surface, CFG.COLOR_DANGER, (int(self.x), int(self.y)), max(2, int(self.radius * 0.3)))
        if visual('shapes'):
            draw_shape(surface, MODE_SHAPES[self.color_tag], CFG.COLOR_PRIMARY, self.x, self.y - self.radius - 10, 4, 0, 1)
        if self.jam_warn > 0:
            k = 1 - self.jam_warn / 0.7
            pygame.draw.circle(surface, (170, 170, 190), (int(self.x), int(self.y)),
                               int(CFG.DISSONANCE_JAM_RADIUS * k), 2)
            pygame.draw.circle(surface, (90, 90, 110), (int(self.x), int(self.y)), int(CFG.DISSONANCE_JAM_RADIUS), 1)
        if self.jam_flash > 0:
            pygame.draw.circle(surface, (210, 210, 230), (int(self.x), int(self.y)), int(CFG.DISSONANCE_JAM_RADIUS), 3)


# === БОСС: ДИССОНАНС-ПРАЙМ (каждые 10 волн) ===
class BossEnemy(Enemy):
    """Три фазы: радиальные залпы → таран с предупреждением → спираль и призыв.

    Цветной щит меняет уязвимый цвет; урон другим цветом ослаблен (BOSS_OFF_COLOR_DAMAGE_MULT).
    """
    kind = 'boss'

    def __init__(self, x: float, y: float, tier: int = 1):
        super().__init__(x, y, CFG.BOSS_HP * (1 + 0.5 * (tier - 1)), CFG.BOSS_RADIUS)
        self.speed = CFG.BOSS_SPEED
        self.tier = tier
        self.vulnerable_mode = random.choice(MODES)
        self.color_timer = 6.0
        self.attack_timer = 2.0
        self.charge_timer = 5.0
        self.summon_timer = 8.0
        self.spiral_timer = 0.0
        self.spiral_angle = 0.0
        self.charge_state = 'none'
        self.charge_dir = (0.0, 0.0)
        self.charge_t = 0.0
        self.phase_speed = 1.0
        self.glitch = 0.0

    @property
    def phase(self) -> int:
        frac = self.hp / self.max_hp
        return 1 if frac > 0.66 else (2 if frac > 0.33 else 3)

    def damage_factor(self, bullet_mode: str) -> float:
        if self.vulnerable_mode is not None and bullet_mode != self.vulnerable_mode:
            return CFG.BOSS_OFF_COLOR_DAMAGE_MULT
        return 1.0

    def _radial(self, count: int, speed: float, offset: float = 0.0) -> List[EnemyBullet]:
        out = []
        for i in range(count):
            a = offset + i * 2 * math.pi / count
            out.append(EnemyBullet(self.x, self.y, math.cos(a), math.sin(a), speed,
                                   CFG.SHOOTER_BULLET_DAMAGE * self.damage_mult, f"залп: {self.name}"))
        return out

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        dt_p = dt * self.phase_speed
        self.glitch = self.glitch * 0.9 + (random.uniform(-3, 3) if random.random() < 0.1 else 0)
        self.color_timer -= dt_p
        if self.color_timer <= 0:
            self.color_timer = 6.0 if self.phase < 3 else 4.0
            self.vulnerable_mode = random.choice([m for m in MODES if m != self.vulnerable_mode])
        actions: List[Any] = []
        dx, dy = player.x - self.x, player.y - self.y
        dist = vec_length(dx, dy)
        nx, ny = vec_normalize(dx, dy)

        if self.charge_state == 'warn':
            self.charge_t -= dt
            if self.charge_t <= 0:
                self.charge_state = 'go'
                self.charge_t = 0.6
        elif self.charge_state == 'go':
            self.charge_t -= dt
            self.vx, self.vy = self.charge_dir[0] * 520, self.charge_dir[1] * 520
            if self.charge_t <= 0:
                self.charge_state = 'none'
                self.vx *= 0.2
                self.vy *= 0.2
        else:
            target = 220.0
            sign = 1 if dist > target else -1
            self.vx = lerp(self.vx, nx * self.speed * sign, dt * 2)
            self.vy = lerp(self.vy, ny * self.speed * sign, dt * 2)

        self.attack_timer -= dt_p
        if self.attack_timer <= 0:
            self.attack_timer = 2.6 if self.phase == 1 else 2.0
            actions += self._radial(12 if self.phase == 1 else 16, 210, random.uniform(0, math.pi))
        if self.phase >= 2 and self.charge_state == 'none':
            self.charge_timer -= dt_p
            if self.charge_timer <= 0:
                self.charge_timer = 5.0
                self.charge_state = 'warn'
                self.charge_t = 0.8
                self.charge_dir = (nx, ny)
        if self.phase >= 3:
            self.spiral_timer -= dt_p
            if self.spiral_timer <= 0:
                self.spiral_timer = 0.14
                self.spiral_angle += 0.45
                actions += self._radial(2, 230, self.spiral_angle)
            self.summon_timer -= dt_p
            if self.summon_timer <= 0:
                self.summon_timer = 8.0
                actions.append(('summon', 3))

        self.x = clamp(self.x + self.vx * dt, self.radius, CFG.SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y + self.vy * dt, self.radius, CFG.SCREEN_HEIGHT - self.radius)
        return actions

    def draw(self, surface: pygame.Surface) -> None:
        col = CFG.COLOR_PRIMARY if self.hit_flash > 0 else mode_color(self.vulnerable_mode)
        if self.charge_state == 'warn':
            ex = self.x + self.charge_dir[0] * 600
            ey = self.y + self.charge_dir[1] * 600
            pygame.draw.line(surface, CFG.COLOR_DANGER, (int(self.x), int(self.y)), (int(ex), int(ey)), 3)
        glow = SurfaceCache.get_glow(int(self.radius), col, int(70 * visual('glow')))
        surface.blit(glow, (int(self.x - self.radius * 2), int(self.y - self.radius * 2)))
        rot = pygame.time.get_ticks() / 900.0
        draw_shape(surface, 'hex', (35, 20, 45), self.x + self.glitch, self.y, self.radius, rot)
        draw_shape(surface, 'hex', col, self.x + self.glitch, self.y, self.radius, rot, 4)
        draw_shape(surface, 'hex', CFG.COLOR_DANGER, self.x - self.glitch, self.y, self.radius * 0.55, -rot, 2)


# === ТРЕНИРОВОЧНЫЕ ЦЕЛИ ===
class DummyEnemy(Enemy):
    """Манекен: не умирает, показывает урон — для отработки режимов."""
    kind = 'dummy'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 10_000, 18)
        self.counted = False
        self.recent_damage = 0.0

    def take_damage(self, damage: float, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        self.hit_flash = 0.1
        self.recent_damage += damage
        game.particles.emit_burst(self.x, self.y, 4, mode_color(bullet_mode), 150.0, 0.3, 2.0)
        return False

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.recent_damage *= math.exp(-dt)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        col = CFG.COLOR_PRIMARY if self.hit_flash > 0 else (120, 130, 150)
        draw_shape(surface, 'diamond', col, self.x, self.y, self.radius, 0, 3)


class TurretEnemy(Enemy):
    """Турель для тренировки парирования: медленные пули, неуязвима."""
    kind = 'turret'

    def __init__(self, x: float, y: float):
        super().__init__(x, y, 10_000, 16)
        self.counted = False
        self.fire_timer = 1.4

    def take_damage(self, damage: float, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        self.hit_flash = 0.1
        return False

    def update(self, dt: float, player: Any) -> Any:
        super().update(dt, player)
        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = 1.4
            dx, dy = vec_normalize(player.x - self.x, player.y - self.y)
            return EnemyBullet(self.x, self.y, dx, dy, 200, 0, "тренировочная турель")
        return None

    def draw(self, surface: pygame.Surface) -> None:
        draw_shape(surface, 'square', CFG.COLOR_ACCENT, self.x, self.y, self.radius, 0, 3)


# === АРЕНА И ЭФФЕКТЫ ПОЛЯ ===
class Pillar:
    """Препятствие арены «Колонны»: выталкивает объекты, гасит пули."""

    def __init__(self, x: float, y: float, radius: float):
        self.x = x
        self.y = y
        self.radius = radius

    def push_out(self, obj: Any) -> None:
        dx, dy = obj.x - self.x, obj.y - self.y
        dist = vec_length(dx, dy)
        min_d = self.radius + getattr(obj, 'radius', 0)
        if dist < min_d:
            nx, ny = (dx / dist, dy / dist) if dist > 1e-4 else (1.0, 0.0)
            obj.x = self.x + nx * min_d
            obj.y = self.y + ny * min_d
            if hasattr(obj, 'vx'):
                dot = obj.vx * nx + obj.vy * ny
                if dot < 0:
                    obj.vx -= dot * nx
                    obj.vy -= dot * ny

    def blocks(self, x: float, y: float, r: float) -> bool:
        return circle_collision(self.x, self.y, self.radius, x, y, r)

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(surface, CFG.COLOR_BG2, (int(self.x), int(self.y)), int(self.radius))
        pygame.draw.circle(surface, (90, 100, 130), (int(self.x), int(self.y)), int(self.radius), 2)


class Decoy:
    """Остаточный образ (модуль GREEN): отвлекает преследователей."""

    def __init__(self, x: float, y: float, lifetime: float = 1.5):
        self.x = x
        self.y = y
        self.radius = 14
        self.lifetime = lifetime

    def update(self, dt: float) -> bool:
        self.lifetime -= dt
        return self.lifetime > 0

    def draw(self, surface: pygame.Surface) -> None:
        a = int(clamp(self.lifetime / 1.5, 0, 1) * 140)
        s = SurfaceCache.get_circle(self.radius, mode_color('GREEN'), a)
        surface.blit(s, (int(self.x - self.radius - 1), int(self.y - self.radius - 1)))


class Hazard:
    """Огненный след рывка (RED): периодически наносит урон врагам."""

    def __init__(self, x: float, y: float, dps: float = 60.0, lifetime: float = 1.2):
        self.x = x
        self.y = y
        self.radius = 18
        self.dps = dps
        self.lifetime = lifetime
        self.tick = 0.0

    def update(self, dt: float) -> bool:
        self.lifetime -= dt
        self.tick -= dt
        return self.lifetime > 0

    def draw(self, surface: pygame.Surface) -> None:
        a = int(clamp(self.lifetime / 1.2, 0, 1) * 110)
        s = SurfaceCache.get_circle(self.radius, mode_color('RED'), a)
        surface.blit(s, (int(self.x - self.radius - 1), int(self.y - self.radius - 1)))


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
        self.group: Optional[int] = None  # бонусы «на выбор»: взял один — остальные исчезают
    
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
        
        elif self.type == 'shield':
            game.player.shield_charges += 1
            game.floating_texts.append(FloatingText(
                game.player.x, game.player.y - 30, "+ЩИТ", CFG.COLOR_PRIMARY, 1.2, 22))
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
    def __init__(self, window: Optional[float] = None):
        self.last_change_time: float = -10.0
        self.last_mode: str = 'RED'
        # Окно Perfect Refraction с учётом улучшения Temporal Lens
        self.window = window if window is not None else CFG.PERFECT_REFRACTION_WINDOW
    
    def record_change(self, time: float, mode: str) -> None:
        self.last_change_time = time
        self.last_mode = mode
    
    def is_in_window(self, current_time: float) -> bool:
        return (current_time - self.last_change_time) <= self.window


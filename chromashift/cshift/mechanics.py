"""Цветовые механики 0.7.0 — всё, что строится на главной идее «цвет меняет физику».

ColorMechanics живёт внутри забега (game.color_mech) и отвечает за:
  * поглощение цветных пуль/лучей/мин в своём цвете и шкалу ПЕРЕГРУЗКИ;
  * смешанные выстрелы (смена цвета сразу после выстрела), Хроматический вихрь (3 цвета подряд);
  * парирование касанием (смена цвета за миг до контакта), «ТОЧНО», цепные реакции, краску, криты;
  * цветовые навыки (R) и способности (F), гравитационные колодцы, порталы;
  * осколки и магазин забега с временными узлами, замедление на последнем убийстве, повтор 10 с;
  * испытания тренировки по цветам.
"""
import collections
import math
import random
from typing import Any, Deque, Dict, List, Optional, Tuple

from .config import ALL_MODES, CFG, MODES
from .utils import clamp, mode_color, vec_distance, vec_normalize

ABILITIES: Dict[str, Dict[str, Any]] = {
    'nova': {'name': 'Нова', 'desc': 'Взрыв вокруг корабля: урон, отталкивание, стирает пули рядом', 'cd': 14.0},
    'timeslow': {'name': 'Стоп-кадр', 'desc': 'На 3 с враги и их пули замедляются в 2.5 раза', 'cd': 18.0},
    'prism_wall': {'name': 'Призменная стена', 'desc': 'Стена перед кораблём гасит вражеские пули 4 с', 'cd': 13.0},
    'shift': {'name': 'Сдвиг', 'desc': 'Мгновенный прыжок на 220 px по направлению движения', 'cd': 9.0},
}
COLOR_SKILLS: Dict[str, Tuple[str, str]] = {
    'RED': ('Вспышка', 'Кольцо из 16 пуль RED'),
    'BLUE': ('Колодец', 'Гравитационный колодец в точке прицела: стягивает врагов и взрывается'),
    'GREEN': ('Шквал', 'Мгновенно перезаряжает рывок и даёт +25% скорости на 3 с'),
    'VIOLET': ('Фаза', 'Неосязаемость ~1 с (без стрельбы)'),
}
SHOP_ITEMS: Dict[str, Dict[str, Any]] = {
    'heal': {'name': 'Ремкомплект', 'desc': '+30 HP', 'cost': 15},
    'shield': {'name': 'Заряд щита', 'desc': '+1 щит', 'cost': 25},
    'dmg': {'name': 'Заточка', 'desc': '+6% урона до конца забега', 'cost': 30},
    'rate': {'name': 'Разгон', 'desc': '+6% скорострельности до конца забега', 'cost': 30},
    'reroll': {'name': 'Жетон переброса', 'desc': '+1 переброс артефактов', 'cost': 20},
}
# Временные узлы: действуют только в текущем забеге
TEMP_NODES: Dict[str, Dict[str, Any]] = {
    'temp_pierce': {'name': 'Временный узел: Сверло', 'desc': 'Пули пробивают +1 врага', 'cost': 45,
                    'apply': lambda m: setattr(m, 'bullet_pierce', m.bullet_pierce + 1)},
    'temp_crit': {'name': 'Временный узел: Разлом', 'desc': '+8% шанс крита', 'cost': 40,
                  'apply': lambda m: setattr(m, 'crit_add', m.crit_add + 0.08)},
    'temp_overload': {'name': 'Временный узел: Накал', 'desc': 'Перегрузка копится в 1.5 раза быстрее', 'cost': 35,
                      'apply': lambda m: setattr(m, 'overload_gain_mult', m.overload_gain_mult * 1.5)},
    'temp_paint': {'name': 'Временный узел: Палитра', 'desc': '+15% шанс краски', 'cost': 30,
                   'apply': lambda m: setattr(m, 'paint_chance_add', m.paint_chance_add + 0.15)},
    'temp_violet': {'name': 'Временный узел: Аметист', 'desc': 'Открывает VIOLET на этот забег', 'cost': 50,
                    'apply': lambda m: setattr(m, 'violet_unlocked', True)},
    'temp_speed': {'name': 'Временный узел: Форсаж', 'desc': '+8% скорости всеми цветами', 'cost': 30,
                   'apply': lambda m: m.all_speed(1.08)},
    'temp_chain': {'name': 'Временный узел: Цепь', 'desc': 'Цепные реакции ×1.5', 'cost': 35,
                   'apply': lambda m: setattr(m, 'chain_damage_mult', m.chain_damage_mult * 1.5)},
    'temp_bounce': {'name': 'Временный узел: Отскок', 'desc': 'Пули отскакивают от стен 1 раз', 'cost': 40,
                    'apply': lambda m: setattr(m, 'bullet_bounce', m.bullet_bounce + 1)},
}
TRIALS: Dict[str, Dict[str, Any]] = {
    'trial_red': {'name': 'Испытание RED', 'desc': 'Уничтожьте 12 манекенов за 25 с', 'goal': 12, 'time': 25.0,
                  'mode': 'RED', 'reward': 20},
    'trial_blue': {'name': 'Испытание BLUE', 'desc': 'Заденьте волной BLUE 3+ манекенов одним выстрелом 5 раз',
                   'goal': 5, 'time': 40.0, 'mode': 'BLUE', 'reward': 20},
    'trial_green': {'name': 'Испытание GREEN', 'desc': 'Продержитесь 30 с под огнём турелей, пропустив не больше 2 пуль',
                    'goal': 30, 'time': 30.5, 'mode': 'GREEN', 'reward': 20},
    'trial_violet': {'name': 'Испытание VIOLET', 'desc': 'Пробейте одной пулей двух манекенов 6 раз',
                     'goal': 6, 'time': 40.0, 'mode': 'VIOLET', 'reward': 25},
    'trial_parry': {'name': 'Испытание Преломления', 'desc': 'Совершите 6 Преломлений за 45 с',
                    'goal': 6, 'time': 45.0, 'mode': 'RED', 'reward': 25},
}


class GravityWell:
    def __init__(self, x: float, y: float, life: float, radius: float, strength: float,
                 affects: str = 'enemies', burst: float = 0.0):
        self.x, self.y, self.life, self.max_life = x, y, life, life
        self.radius, self.strength, self.affects, self.burst = radius, strength, affects, burst


class ColorMechanics:
    def __init__(self, game: Any):
        self.game = game
        self.overload = 0.0
        self.overload_t = 0.0
        self.mix_prev: Optional[str] = None
        self.mix_until = -10.0
        self.mix_cd = 0.0
        self.last_shot_time = -10.0
        self.switches: List[Tuple[float, str]] = []
        self.vortex_cd = 0.0
        self.skill_cd = 0.0
        self.ability_cd = 0.0
        self.ability = 'nova'
        self.timeslow_t = 0.0
        self.green_rush_t = 0.0
        self.unstable_t = 20.0
        self.wells: List[GravityWell] = []
        self.chain_queue: List[Tuple[float, float, str, float]] = []
        self.shards = 0
        self.rerolls = 0
        self.temp_nodes: List[str] = []
        self.slowmo_t = 0.0
        self.replay: Deque[Any] = collections.deque(maxlen=int(CFG.REPLAY_SECONDS / 0.05))
        self._rec_t = 0.0
        self.portal_cd = 0.0
        self.kills_for_heal = 0
        self.trial: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------ общие
    @property
    def mods(self) -> Any:
        return self.game.mods

    @property
    def player(self) -> Any:
        return self.game.player

    def stat(self, key: str, n: int = 1) -> None:
        self.game.stats[key] = self.game.stats.get(key, 0) + n

    def in_own_paint(self) -> bool:
        p = self.player
        return any(z.color == p.mode and z.contains(p.x, p.y) for z in self.game.paints)

    def enemy_time_scale(self) -> float:
        return 0.4 if self.timeslow_t > 0 else 1.0

    # ------------------------------------------------------------ стрельба
    def damage_bonus(self) -> float:
        k = 1.0
        if self.overload_t > 0:
            k *= 1.5
        if self.in_own_paint():
            k *= 1.3 if self.game.profile.loadout.get('hull') == 'painter' else 1.2
        return k

    def decorate_bullet(self, b: Any) -> None:
        g = self.game
        self.last_shot_time = g.game_time
        if random.random() < CFG.CRIT_CHANCE + self.mods.crit_add:
            b.crit = True
            b.damage *= CFG.CRIT_MULT + self.mods.crit_mult_add
        if self.overload_t > 0:
            b.pierce_left += 1
        if self.in_own_paint():
            b.painted = True
        if self.mix_prev and g.game_time <= self.mix_until and self.mix_prev != b.mode:
            b.mix = self.mix_prev

    def consume_mix(self) -> None:
        if self.mix_prev:
            self.mix_prev = None
            self.mix_cd = CFG.MIX_COOLDOWN * self.mods.mix_cd_mult

    def bullet_mode_vs(self, b: Any, e: Any) -> str:
        """Смешанный выстрел бьёт тем из двух цветов, к которому враг уязвимее."""
        if not b.mix:
            return b.mode
        return max((b.mode, b.mix), key=lambda m: e.damage_factor(m))

    # ------------------------------------------------------------ смена цвета
    def on_switch(self, old: str, new: str) -> None:
        g = self.game
        t = g.game_time
        self.player.last_switch_time = t
        if self.mix_cd <= 0 and t - self.last_shot_time <= CFG.MIX_WINDOW:
            self.mix_prev = old
            self.mix_until = t + CFG.MIX_WINDOW
            g.tip('mix', 'Смешанный выстрел: смените цвет сразу после выстрела — пуля бьёт двумя цветами')
        self.switches = [(st, m) for st, m in self.switches if t - st <= 1.2] + [(t, new)]
        if self.vortex_cd <= 0 and len({m for _, m in self.switches}) >= 3:
            self.vortex()

    def vortex(self) -> None:
        g, p = self.game, self.player
        from .entities import PlayerBullet
        self.vortex_cd = 4.0
        self.switches = []
        self.stat('vortexes')
        cols = [m for m in ALL_MODES if m != 'VIOLET' or self.mods.violet_unlocked]
        for i in range(12):
            a = i * math.pi / 6
            b = PlayerBullet(p.x, p.y, math.cos(a), math.sin(a), cols[i % len(cols)])
            b.damage = CFG.BULLET_DAMAGE * 1.2 * self.mods.damage_mult
            b.speed = CFG.BULLET_SPEED * 0.9
            g.player_bullets.append(b)
        g.particles.emit_spiral(p.x, p.y, 30, CFG.COLOR_ACCENT, 320.0)
        g.floating_texts_add(p.x, p.y - 40, 'ВИХРЬ!', CFG.COLOR_ACCENT, 1.0, 24)
        g.sound_manager.play('combo', 0.5)
        g.tip('vortex', 'Хроматический вихрь: три разных цвета за секунду выпускают кольцо пуль')

    # ------------------------------------------------------------ поглощение и перегрузка
    def try_absorb(self, bullet: Any) -> bool:
        p = self.player
        if not getattr(bullet, 'color', None) or bullet.color != p.mode:
            return False
        g = self.game
        self.add_overload(1)
        self.stat('absorbed')
        g.particles.emit_burst(bullet.x, bullet.y, 6, mode_color(bullet.color), 140.0, 0.3, 2.0)
        g.sound_manager.play('absorb', 0.3)
        g.tip('absorb', 'Цветные пули своего цвета поглощаются и заряжают ПЕРЕГРУЗКУ')
        return True

    def add_overload(self, n: float) -> None:
        if self.overload_t > 0:
            return
        self.overload += n * self.mods.overload_gain_mult
        if self.overload >= CFG.OVERLOAD_MAX:
            self.overload = 0.0
            self.overload_t = 5.0 + self.mods.overload_duration_add
            g = self.game
            g.floating_texts_add(self.player.x, self.player.y - 50, 'ПЕРЕГРУЗКА!', CFG.COLOR_ACCENT, 1.5, 28)
            g.flash(mode_color(self.player.mode), 0.3)
            g.sound_manager.play('overload', 0.6)

    # ------------------------------------------------------------ контакт
    def touch_parry(self, enemy: Any) -> bool:
        """Смена цвета за миг до касания — враг оглушён и отброшен, урона нет."""
        g, p = self.game, self.player
        window = CFG.PARRY_SWITCH_WINDOW + self.mods.parry_touch_window_add
        if g.game_time - p.last_switch_time > window or getattr(enemy, 'boss_like', False) or enemy.kind == 'boss':
            return False
        enemy.stun_t = 1.2
        nx, ny = vec_normalize(enemy.x - p.x, enemy.y - p.y)
        enemy.vx, enemy.vy = nx * 420, ny * 420
        enemy.x += nx * 20
        enemy.y += ny * 20
        p.last_switch_time = -10.0
        p.invuln_timer = max(p.invuln_timer, 0.25)
        self.stat('touch_parries')
        g.floating_texts_add(enemy.x, enemy.y - 26, 'ПАРИРОВАНИЕ', CFG.COLOR_ACCENT, 0.8, 18)
        g.particles.emit_burst(p.x, p.y, 14, mode_color(p.mode), 260.0, 0.4, 2.5)
        g.sound_manager.play('parry_touch', 0.5)
        g.hitstop_timer = max(g.hitstop_timer, 0.04)
        return True

    # ------------------------------------------------------------ убийства
    def on_kill(self, enemy: Any, mode: str, last_of_wave: bool = False) -> float:
        """Возвращает множитель очков (ТОЧНО)."""
        g = self.game
        mult = 1.0
        weak = enemy.weakness()
        if weak is not None and weak == mode:
            mult = self.mods.precise_mult
            self.stat('precise_kills')
            g.floating_texts_add(enemy.x, enemy.y - 44, 'ТОЧНО', mode_color(mode), 0.6, 15)
        # Цепная реакция: враг ЦВЕТА выстрела детонирует и ранит соседей
        if enemy.color_tag is not None and enemy.color_tag == mode and enemy.kind != 'dissonance':
            if len(self.chain_queue) < 12:
                self.chain_queue.append((enemy.x, enemy.y, mode, 22.0 * self.mods.chain_damage_mult))
        if random.random() < CFG.PAINT_CHANCE + self.mods.paint_chance_add and len(g.paints) < 14:
            from .enemies_ext import PaintZone
            g.paints.append(PaintZone(enemy.x, enemy.y, mode, 55.0 * self.mods.paint_radius_mult))
        big = 3 if enemy.max_hp > 300 else 1
        self.shards += max(1, int(round(CFG.SHARDS_PER_KILL * self.mods.shards_mult * big)))
        if self.mods.heal_on_kills and not self.mods.no_heal:
            self.kills_for_heal += 1
            if self.kills_for_heal >= self.mods.heal_on_kills:
                self.kills_for_heal = 0
                p = self.player
                p.hp = min(p.max_hp, p.hp + 1)
        if last_of_wave and g.settings.get('slowmo', True):
            self.slowmo_t = 0.55
        if self.trial and self.trial['id'] == 'trial_red':
            self.trial['progress'] += 1
        return mult

    def process_chains(self) -> None:
        g = self.game
        queue, self.chain_queue = self.chain_queue, []
        for x, y, mode, dmg in queue:
            g.particles.emit_burst(x, y, 16, mode_color(mode), 260.0, 0.4, 3.0)
            hit = False
            for e in list(g.enemies):
                if e.alive and e.kind not in ('dummy', 'turret') and vec_distance(x, y, e.x, e.y) < 90 + e.radius:
                    hit = True
                    e.take_damage(dmg * self.mods.damage_mult, g, mode, is_aoe=True)
            if hit:
                self.stat('chains')
                g.floating_texts_add(x, y - 20, 'ЦЕПЬ', mode_color(mode), 0.5, 14)
        # новые звенья цепи (если кто-то погиб) обработаются в следующем кадре

    # ------------------------------------------------------------ навыки и способности
    def color_skill(self) -> bool:
        g, p = self.game, self.player
        if self.skill_cd > 0 or g.dying_timer >= 0:
            return False
        from .entities import PlayerBullet
        mode = p.mode
        self.skill_cd = CFG.COLOR_SKILL_COOLDOWN * self.mods.skill_cd_mult
        if mode == 'RED':
            for i in range(16):
                a = i * math.pi / 8
                b = PlayerBullet(p.x, p.y, math.cos(a), math.sin(a), 'RED')
                b.damage = CFG.BULLET_DAMAGE * 1.3 * self.mods.damage_mult * self.mods.mode_damage_mult['RED']
                g.player_bullets.append(b)
        elif mode == 'BLUE':
            ax, ay = g.input.aim_point(p, [e for e in g.enemies if e.alive])
            self.wells.append(GravityWell(ax, ay, 2.5, 200, 380, 'enemies', burst=45.0 * self.mods.damage_mult))
        elif mode == 'GREEN':
            p.dash_cooldown = 0.0
            self.green_rush_t = 3.0
        elif mode == 'VIOLET':
            p.phase_t = 1.0 + self.mods.phase_duration_add
        g.floating_texts_add(p.x, p.y - 44, COLOR_SKILLS[mode][0].upper(), mode_color(mode), 0.9, 20)
        g.sound_manager.play('skill', 0.5)
        return True

    def use_ability(self) -> bool:
        g, p = self.game, self.player
        if self.ability_cd > 0 or g.dying_timer >= 0:
            return False
        ab = ABILITIES.get(self.ability, ABILITIES['nova'])
        self.ability_cd = ab['cd'] * self.mods.ability_cd_mult
        if self.ability == 'timeslow':
            self.timeslow_t = 3.0
            g.flash((150, 200, 255), 0.25)
        elif self.ability == 'prism_wall':
            from .enemies_ext import PrismWall
            a = math.atan2(p.facing_y, p.facing_x)
            g.walls.append(PrismWall(p.x + math.cos(a) * 60, p.y + math.sin(a) * 60, a + math.pi / 2))
        elif self.ability == 'shift':
            dx, dy = (p.move_x, p.move_y) if abs(p.move_x) + abs(p.move_y) > 0.1 else (p.facing_x, p.facing_y)
            dx, dy = vec_normalize(dx, dy)
            g.particles.emit_burst(p.x, p.y, 16, mode_color(p.mode), 200.0, 0.4, 2.5)
            p.x = clamp(p.x + dx * 220, p.radius, CFG.SCREEN_WIDTH - p.radius)
            p.y = clamp(p.y + dy * 220, p.radius, CFG.SCREEN_HEIGHT - p.radius)
            p.invuln_timer = max(p.invuln_timer, 0.3)
            g.particles.emit_burst(p.x, p.y, 16, mode_color(p.mode), 200.0, 0.4, 2.5)
        else:  # nova
            g.particles.emit_burst(p.x, p.y, 40, CFG.COLOR_PRIMARY, 520.0, 0.6, 4.0)
            g.screen_shake.trigger(9.0, 0.25)
            for e in list(g.enemies):
                if e.alive and vec_distance(p.x, p.y, e.x, e.y) < 190 + e.radius:
                    nx, ny = vec_normalize(e.x - p.x, e.y - p.y)
                    if not getattr(e, 'boss_like', False) and e.kind != 'boss':
                        e.vx += nx * 600
                        e.vy += ny * 600
                    e.take_damage(55 * self.mods.damage_mult, g, p.mode, is_aoe=True)
            g.enemy_bullets = [b for b in g.enemy_bullets if vec_distance(p.x, p.y, b.x, b.y) > 190]
        g.sound_manager.play('ability', 0.55)
        return True

    # ------------------------------------------------------------ магазин
    def buy(self, item: str) -> Tuple[bool, str]:
        g, p = self.game, self.player
        if item in SHOP_ITEMS:
            cost = SHOP_ITEMS[item]['cost']
        elif item in TEMP_NODES:
            cost = TEMP_NODES[item]['cost']
            if item in self.temp_nodes:
                return False, 'Уже взят'
        else:
            return False, 'Нет такого товара'
        if self.shards < cost:
            return False, f'Нужно {cost} осколков'
        if item == 'heal':
            if self.mods.no_heal:
                return False, 'Лечение отключено'
            if p.hp >= p.max_hp:
                return False, 'HP уже полное'
        self.shards -= cost
        if item == 'heal':
            p.hp = min(p.max_hp, p.hp + 30)
        elif item == 'shield':
            p.shield_charges += 1
        elif item == 'dmg':
            self.mods.damage_mult *= 1.06
        elif item == 'rate':
            self.mods.fire_rate_mult *= 1.06
        elif item == 'reroll':
            self.rerolls += 1
        else:
            TEMP_NODES[item]['apply'](self.mods)
            self.temp_nodes.append(item)
        from .progression import apply_caps
        apply_caps(self.mods)
        g.refresh_player_from_mods()
        self.stat('shop_buys')
        g.sound_manager.play('artifact', 0.5)
        name = SHOP_ITEMS[item]['name'] if item in SHOP_ITEMS else TEMP_NODES[item]['name']
        return True, f'Куплено: {name}'

    def shop_offer(self, rng: Any) -> List[str]:
        temps = [t for t in sorted(TEMP_NODES) if t not in self.temp_nodes
                 and not (t == 'temp_violet' and self.mods.violet_unlocked)]
        return list(SHOP_ITEMS) + rng.sample(temps, min(2, len(temps)))

    # ------------------------------------------------------------ испытания тренировки
    def start_trial(self, tid: str) -> None:
        self.trial = {'id': tid, 'progress': 0.0, 'time': TRIALS[tid]['time'], 'hits': 0, 'done': False}

    def trial_event(self, kind: str) -> None:
        tr = self.trial
        if not tr or tr['done']:
            return
        tid = tr['id']
        if (kind, tid) in (('blue_multi', 'trial_blue'), ('pierce2', 'trial_violet'), ('refraction', 'trial_parry')):
            tr['progress'] += 1
        elif kind == 'hit' and tid == 'trial_green':
            tr['hits'] += 1

    def update_trial(self, dt: float) -> None:
        tr = self.trial
        if not tr or tr['done']:
            return
        g = self.game
        info = TRIALS[tr['id']]
        tr['time'] -= dt
        if tr['id'] == 'trial_green':
            tr['progress'] = info['time'] - tr['time']
            if tr['hits'] > 2:
                tr['done'] = True
                g.announce('ИСПЫТАНИЕ ПРОВАЛЕНО', 'Больше 2 попаданий. F5 — заново, Esc — выход')
                return
        if tr['progress'] >= info['goal']:
            tr['done'] = True
            first = tr['id'] not in g.profile.data['trials_done']
            if first:
                g.profile.data['trials_done'].append(tr['id'])
                g.profile.add_cp(info['reward'])
                g.profile.save()
            g.announce('ИСПЫТАНИЕ ПРОЙДЕНО', f"+{info['reward']} CP" if first else 'Уже пройдено раньше')
            g.sound_manager.play('achievement', 0.6)
        elif tr['time'] <= 0:
            tr['done'] = True
            g.announce('ВРЕМЯ ВЫШЛО', 'F5 — попробовать снова, Esc — выход')

    # ------------------------------------------------------------ кадр
    def update(self, dt: float) -> None:
        g, p = self.game, self.player
        for attr in ('mix_cd', 'vortex_cd', 'skill_cd', 'ability_cd', 'timeslow_t', 'green_rush_t', 'overload_t',
                     'portal_cd'):
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, max(0.0, v - dt))
        if p.phase_t > 0:
            p.phase_t = max(0.0, p.phase_t - dt)
        if p.color_lock_t > 0:
            p.color_lock_t = max(0.0, p.color_lock_t - dt)
        p.speed_bonus = (1.15 if self.in_own_paint() else 1.0) * (1.25 if self.green_rush_t > 0 else 1.0)
        if self.mods.unstable_colors and not g.is_training:
            self.unstable_t -= dt
            if self.unstable_t <= 0:
                self.unstable_t = 20.0
                g.set_player_mode(random.choice([m for m in MODES if m != p.mode]), forced=True)
                g.floating_texts_add(p.x, p.y - 40, 'НЕСТАБИЛЬНОСТЬ', CFG.COLOR_DANGER, 0.9, 18)
        self._update_wells(dt)
        self._update_portals()
        if self.chain_queue:
            self.process_chains()
        self.update_trial(dt)
        self._rec_t -= dt
        if self._rec_t <= 0:  # повтор: снимок раз в 0.05 с
            self._rec_t = 0.05
            self.replay.append((
                (p.x, p.y, p.mode),
                [(e.x, e.y, e.radius, e.color_tag or e.vulnerable_mode) for e in g.enemies if e.alive][:80],
                [(b.x, b.y, b.color) for b in g.enemy_bullets][:120],
                [(b.x, b.y, b.mode) for b in g.player_bullets][:120],
            ))

    def _update_wells(self, dt: float) -> None:
        g, p = self.game, self.player
        keep = []
        for w in self.wells:
            w.life -= dt
            if w.affects in ('enemies', 'all'):
                for e in g.enemies:
                    if not e.alive or getattr(e, 'boss_like', False) or e.kind in ('boss', 'turret', 'dummy'):
                        continue
                    d = vec_distance(w.x, w.y, e.x, e.y)
                    if 8 < d < w.radius:
                        nx, ny = vec_normalize(w.x - e.x, w.y - e.y)
                        e.x += nx * w.strength * dt * (1 - d / w.radius)
                        e.y += ny * w.strength * dt * (1 - d / w.radius)
            if w.affects in ('player', 'all'):
                d = vec_distance(w.x, w.y, p.x, p.y)
                if 10 < d < w.radius:
                    nx, ny = vec_normalize(w.x - p.x, w.y - p.y)
                    p.vx += nx * w.strength * dt
                    p.vy += ny * w.strength * dt
                for b in g.enemy_bullets:
                    d = vec_distance(w.x, w.y, b.x, b.y)
                    if 10 < d < w.radius:
                        nx, ny = vec_normalize(w.x - b.x, w.y - b.y)
                        b.dx, b.dy = vec_normalize(b.dx + nx * dt * 1.5, b.dy + ny * dt * 1.5)
            if w.life <= 0:
                if w.burst > 0:
                    g.particles.emit_burst(w.x, w.y, 30, mode_color('BLUE'), 380.0, 0.5, 3.5)
                    for e in list(g.enemies):
                        if e.alive and vec_distance(w.x, w.y, e.x, e.y) < 110 + e.radius:
                            e.take_damage(w.burst, g, 'BLUE', is_aoe=True)
                continue
            keep.append(w)
        self.wells = keep

    def _update_portals(self) -> None:
        g, p = self.game, self.player
        if not g.portals:
            return
        if self.portal_cd <= 0:
            for pt in g.portals:
                if pt.pair and p.mode == pt.color and vec_distance(p.x, p.y, pt.x, pt.y) < pt.radius:
                    p.x, p.y = pt.pair.x, pt.pair.y
                    self.portal_cd = 0.9
                    g.particles.emit_burst(p.x, p.y, 16, mode_color(pt.color), 240.0, 0.4, 2.5)
                    g.sound_manager.play('portal', 0.4)
                    break
        for b in g.player_bullets:
            if getattr(b, 'portal_used', False):
                continue
            for pt in g.portals:
                if pt.pair and b.mode == pt.color and vec_distance(b.x, b.y, pt.x, pt.y) < pt.radius:
                    b.x, b.y = pt.pair.x + b.dx * (pt.radius + 4), pt.pair.y + b.dy * (pt.radius + 4)
                    b.portal_used = True
                    break
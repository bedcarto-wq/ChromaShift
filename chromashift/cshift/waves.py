"""Директор волн 0.6.5: бюджет угроз, отряды и формации, подволны на долях такта,
телеграф спавна, лимиты, элиты, боссы, особые волны, DDA и итоги волны."""
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .config import CFG, MODES
from .utils import clamp, vec_distance, vec_normalize

ENEMY_UNLOCK = {'chaser': 1, 'shooter': 2, 'kamikaze': 3, 'dissonance': 5}
TRAINING_TIPS = {
    'shooter': ('Новый враг: Стрелок', 'Смените цвет прямо перед попаданием пули — Преломление'),
    'kamikaze': ('Новый враг: Камикадзе', 'Красный круг — зона взрыва. Рывок даёт неуязвимость'),
    'dissonance': ('Новый враг: Диссонанс', 'Почти неуязвим к обычным пулям — убейте отражённой пулей'),
}
SPECIAL_WAVES = {
    'darkness': ('Волна «Тьма»', 'Видимость ограничена — следите за телеграфами'),
    'haste': ('Волна «Ускорение»', 'Враги на 30% быстрее, музыка на пределе'),
    'mono': ('Монохромная волна', 'Все враги уязвимы к одному цвету'),
}

# (id, состав, формация, с какой волны, базовый вес)
SQUADS: List[Tuple[str, List[Tuple[str, int]], str, int, float]] = [
    ('pack', [('chaser', 3)], 'arc', 1, 1.0),
    ('big_pack', [('chaser', 5)], 'arc', 4, 0.8),
    ('firing_line', [('shooter', 2)], 'line', 2, 0.9),
    ('battery', [('shooter', 3)], 'line', 6, 0.6),
    ('swarm', [('kamikaze', 3)], 'ring', 3, 0.8),
    ('mixed', [('chaser', 2), ('shooter', 1)], 'cluster', 3, 1.0),
    ('ambush', [('kamikaze', 2), ('chaser', 2)], 'pincer', 5, 0.8),
    ('hunter', [('dissonance', 1), ('chaser', 2)], 'cluster', 5, 0.6),
    ('siege', [('shooter', 2), ('kamikaze', 2)], 'pincer', 7, 0.7),
    ('choir', [('dissonance', 2)], 'pincer', 9, 0.4),
]


def enemy_cost(kind: str) -> float:
    return float(CFG.get(f'WAVE_COST_{kind.upper()}', 1.0))


def squad_cost(members: List[Tuple[str, int]]) -> float:
    return sum(enemy_cost(k) * n for k, n in members)


def smoothstep(x: float) -> float:
    x = clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def wave_budget(n: int) -> float:
    return CFG.WAVE_BUDGET_BASE + CFG.WAVE_BUDGET_GROWTH * max(0, n - 1) ** CFG.WAVE_BUDGET_EXPONENT


def wave_scaling(n: int) -> Tuple[float, float, float]:
    k = max(0, n - 1)
    return (min(CFG.ENEMY_HP_SCALE_MAX, 1 + CFG.ENEMY_HP_SCALE * k),
            min(CFG.ENEMY_SPEED_SCALE_MAX, 1 + CFG.ENEMY_SPEED_SCALE * k),
            min(CFG.ENEMY_DAMAGE_SCALE_MAX, 1 + CFG.ENEMY_DAMAGE_SCALE * k))


class WaveDirector:
    def __init__(self, game: Any, rng: Optional[random.Random] = None):
        self.game = game
        self.rng = rng or random.Random()
        self.wave = 0
        self.state = 'intermission'
        self.timer = 1.5
        self.subwaves: List[List[Dict[str, Any]]] = []
        self.current_sub = -1
        self.sub_size = 0
        self.sub_timer = 0.0
        self.release_pending = False
        self.release_wait = 0.0
        self.telegraphs: List[Dict[str, Any]] = []
        self.total = 0
        self.killed = 0
        self.wave_time = 0.0
        self.wave_damage = 0.0
        self.wave_kills = 0
        self.budget = 0.0
        self.par = 0.0
        self.dda = 1.0
        self.overheat = False
        self.next_overheat = False
        self.special: Optional[str] = None
        self.mono_mode: Optional[str] = None
        self.is_boss_wave = False
        self.is_breather = False
        self.boss: Any = None
        self.recent_squads: List[str] = []
        self.introduced: set = set()
        self.log: List[Dict[str, Any]] = []
        self.last_summary: Optional[Dict[str, Any]] = None
        self.peak_alive = 1

    # --- Параметры ---
    @property
    def mods(self) -> Any:
        return self.game.mods

    def elite_chance(self, n: int) -> float:
        if n < CFG.ELITE_START_WAVE:
            return 0.0
        return min(CFG.ELITE_MAX_CHANCE, CFG.ELITE_CHANCE_PER_WAVE * (n - CFG.ELITE_START_WAVE + 1)
                   + self.mods.elite_chance_add)

    def telegraph_time(self) -> float:
        return max(0.3, CFG.WAVE_TELEGRAPH_TIME + self.mods.telegraph_add)

    def progress(self) -> float:
        if self.state != 'active' or self.total <= 0:
            return 1.0 if self.state == 'intermission' else 0.0
        return clamp(self.killed / self.total, 0.0, 1.0)

    # --- Состав волны ---
    def squad_weight(self, sq: Tuple, n: int) -> float:
        sid, members, _, min_wave, base = sq
        if n < min_wave:
            return 0.0
        w = base * (0.25 + 0.75 * smoothstep((n - min_wave + 1) / 3.0))  # плавное введение
        if sid in self.recent_squads[-2:]:
            w *= 0.35  # анти-повтор
        return w

    def compose(self, n: int, budget: float) -> List[Dict[str, Any]]:
        squads: List[Dict[str, Any]] = []
        remaining = budget
        guard = 0
        while remaining >= 1.0 and guard < 60:
            guard += 1
            options = [(sq, self.squad_weight(sq, n)) for sq in SQUADS]
            options = [(sq, w) for sq, w in options if w > 0 and squad_cost(sq[1]) <= remaining + 0.6]
            if not options:
                squads.append({'id': 'filler', 'members': [('chaser', 1)], 'formation': 'cluster'})
                remaining -= enemy_cost('chaser')
                continue
            sq = self.rng.choices([o[0] for o in options], weights=[o[1] for o in options], k=1)[0]
            squads.append({'id': sq[0], 'members': list(sq[1]), 'formation': sq[2]})
            self.recent_squads.append(sq[0])
            remaining -= squad_cost(sq[1])
        self.recent_squads = self.recent_squads[-6:]
        return squads

    # --- Позиции ---
    def edge_point(self, far_from: Tuple[float, float]) -> Tuple[float, float]:
        w, h, m = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT, 50
        cands = []
        for _ in range(8):
            side = self.rng.randrange(4)
            if side == 0:
                p = (self.rng.uniform(m, w - m), m)
            elif side == 1:
                p = (self.rng.uniform(m, w - m), h - m)
            elif side == 2:
                p = (m, self.rng.uniform(m, h - m))
            else:
                p = (w - m, self.rng.uniform(m, h - m))
            cands.append(p)
        cands.sort(key=lambda p: -vec_distance(p[0], p[1], far_from[0], far_from[1]))
        if self.rng.random() < CFG.WAVE_FAR_EDGE_BIAS:
            return cands[0]
        safe = [p for p in cands if vec_distance(p[0], p[1], far_from[0], far_from[1]) >= CFG.WAVE_SAFE_RADIUS]
        return self.rng.choice(safe or cands[:1])

    def formation_points(self, formation: str, count: int, player: Tuple[float, float]) -> List[Tuple[float, float]]:
        ax, ay = self.edge_point(player)
        dx, dy = vec_normalize(player[0] - ax, player[1] - ay)
        px, py = -dy, dx
        pts: List[Tuple[float, float]] = []
        if formation == 'line':
            for i in range(count):
                o = (i - (count - 1) / 2) * 60
                pts.append((ax + px * o, ay + py * o))
        elif formation == 'arc':
            for i in range(count):
                a = (i - (count - 1) / 2) * 0.35
                r = 70
                pts.append((ax + px * math.sin(a) * r * 2 - dx * math.cos(a) * 20, ay + py * math.sin(a) * r * 2 - dy * math.cos(a) * 20))
        elif formation == 'ring':
            for i in range(count):
                a = i * 2 * math.pi / count
                pts.append((ax + math.cos(a) * 45, ay + math.sin(a) * 45))
        elif formation == 'pincer':
            bx, by = CFG.SCREEN_WIDTH - ax, CFG.SCREEN_HEIGHT - ay
            for i in range(count):
                cx, cy = (ax, ay) if i % 2 == 0 else (bx, by)
                pts.append((cx + self.rng.uniform(-30, 30), cy + self.rng.uniform(-30, 30)))
        else:
            for _ in range(count):
                pts.append((ax + self.rng.uniform(-50, 50), ay + self.rng.uniform(-50, 50)))
        out = []
        for x, y in pts:
            x = clamp(x, 30, CFG.SCREEN_WIDTH - 30)
            y = clamp(y, 30, CFG.SCREEN_HEIGHT - 30)
            # Безопасная зона вокруг игрока
            d = vec_distance(x, y, player[0], player[1])
            if d < CFG.WAVE_SAFE_RADIUS:
                nx, ny = vec_normalize(x - player[0], y - player[1]) if d > 1 else (1.0, 0.0)
                x = clamp(player[0] + nx * CFG.WAVE_SAFE_RADIUS, 30, CFG.SCREEN_WIDTH - 30)
                y = clamp(player[1] + ny * CFG.WAVE_SAFE_RADIUS, 30, CFG.SCREEN_HEIGHT - 30)
            out.append((x, y))
        return out

    # --- Жизненный цикл ---
    def begin_wave(self) -> None:
        self.wave += 1
        n = self.wave
        g = self.game
        self.is_boss_wave = n % CFG.BOSS_WAVE_INTERVAL == 0
        self.is_breather = (n % CFG.BREATHER_WAVE_INTERVAL == 0) and not self.is_boss_wave
        self.overheat = self.next_overheat
        self.next_overheat = False
        self.special = None
        self.mono_mode = None
        if (not self.is_boss_wave and not self.is_breather and n >= CFG.SPECIAL_WAVE_MIN
                and self.rng.random() < CFG.SPECIAL_WAVE_CHANCE):
            self.special = self.rng.choice(sorted(SPECIAL_WAVES))
            if self.special == 'mono':
                self.mono_mode = self.rng.choice(MODES)
        budget = wave_budget(n) * self.mods.budget_mult * self.dda
        if self.overheat:
            budget *= CFG.OVERHEAT_BUDGET_MULT
        if self.is_breather:
            budget *= CFG.BREATHER_BUDGET_MULT
        if self.is_boss_wave:
            budget *= 0.3
        self.budget = budget
        self.par = max(10.0, budget * CFG.WAVE_PAR_SECONDS_PER_BUDGET + (25.0 if self.is_boss_wave else 0.0))
        squads = self.compose(n, budget)
        player = (g.player.x, g.player.y)

        # Обучающая пачка: первый выход нового типа — отдельно и с подсказкой
        intro_kind = None
        for kind, w in ENEMY_UNLOCK.items():
            if w == n and kind not in self.introduced and kind in TRAINING_TIPS:
                intro_kind = kind
                self.introduced.add(kind)
        groups: List[List[Dict[str, Any]]] = []
        if intro_kind:
            pts = self.formation_points('line', 2, player)
            groups.append([self._entry(intro_kind, x, y, i, allow_elite=False) for i, (x, y) in enumerate(pts)])
            title, tip = TRAINING_TIPS[intro_kind]
            g.announce(title, tip)
        if self.is_boss_wave:
            tier = max(1, n // CFG.BOSS_WAVE_INTERVAL)
            boss_entry = {'kind': 'boss', 'x': CFG.SCREEN_WIDTH / 2, 'y': 110.0, 'elite': [], 'shield': None,
                          't': 1.6, 'delay': 0.0, 'tier': tier}
            groups.append([boss_entry])
        # Подволны: отряды делятся на группы
        n_groups = max(1, min(6, 1 + int(len(squads) / 2.5)))
        buckets: List[List[Dict[str, Any]]] = [[] for _ in range(n_groups)]
        for i, sq in enumerate(squads):
            count = sum(c for _, c in sq['members'])
            pts = self.formation_points(sq['formation'], count, player)
            kinds = [k for k, c in sq['members'] for _ in range(c)]
            bucket = buckets[i % n_groups]
            for j, (kind, (x, y)) in enumerate(zip(kinds, pts)):
                bucket.append(self._entry(kind, x, y, len(bucket) + j))
        groups += [b for b in buckets if b]
        self.subwaves = groups
        self.total = sum(1 for grp in groups for e in grp)
        self.killed = 0
        self.current_sub = -1
        self.release_pending = False
        self.wave_time = 0.0
        self.wave_damage = 0.0
        self.wave_kills = 0
        self.peak_alive = 1
        self.boss = None
        self.state = 'active'
        self._release_next()

        title = f"ВОЛНА {n}"
        subtitle = ''
        if self.is_boss_wave:
            title += ' — БОСС'
            subtitle = 'Диссонанс-Прайм: бейте цветом его щита'
        elif self.is_breather:
            title += ' — ПЕРЕДЫШКА'
            subtitle = 'Выберите один из двух бонусов'
            g.spawn_breather_choice()
        elif self.special:
            title += ' — ' + SPECIAL_WAVES[self.special][0]
            subtitle = SPECIAL_WAVES[self.special][1]
            if self.special == 'mono':
                subtitle = f"Все враги уязвимы только к {self.mono_mode}"
        if self.overheat:
            subtitle = (subtitle + ' · ' if subtitle else '') + 'ПЕРЕГРЕВ: больше врагов, ×1.5 очков'
        if not intro_kind:
            g.announce(title, subtitle)
        else:
            g.floating_title(title)
        g.sound_manager.play('wave', 0.5)
        if self.is_boss_wave:
            g.sound_manager.play('boss_phase', 0.6)

    def _entry(self, kind: str, x: float, y: float, index: int, allow_elite: bool = True) -> Dict[str, Any]:
        elite: List[str] = []
        shield = None
        if allow_elite and self.rng.random() < self.elite_chance(self.wave):
            elite = [self.rng.choice(['fast', 'armored', 'splitting', 'shielded'])]
            if 'shielded' in elite:
                shield = self.rng.choice(MODES)
        if self.mono_mode and kind != 'dissonance':
            if 'shielded' not in elite:
                elite = elite + ['shielded']
            shield = self.mono_mode
        return {'kind': kind, 'x': x, 'y': y, 'elite': elite, 'shield': shield,
                't': self.telegraph_time(), 'delay': index * CFG.WAVE_SPAWN_STAGGER}

    def _release_next(self) -> None:
        self.current_sub += 1
        self.release_pending = False
        if self.current_sub >= len(self.subwaves):
            return
        grp = self.subwaves[self.current_sub]
        self.sub_size = len(grp)
        self.sub_timer = 0.0
        self.telegraphs.extend(dict(e) for e in grp)
        if self.current_sub > 0:
            self.game.sound_manager.play('telegraph', 0.35)

    def counted_alive(self) -> int:
        return sum(1 for e in self.game.enemies if e.alive and e.counted)

    def on_counted_kill(self) -> None:
        self.killed += 1
        self.wave_kills += 1

    def on_player_damaged(self, dmg: float) -> None:
        self.wave_damage += dmg

    def update(self, dt: float, beat: bool) -> None:
        g = self.game
        if self.state == 'intermission':
            self.timer -= dt
            if self.timer <= 0 and not g.modal_open():
                self.begin_wave()
            return
        if self.state != 'active':
            return
        self.wave_time += dt
        self.sub_timer += dt
        alive = self.counted_alive()
        self.peak_alive = max(self.peak_alive, alive)
        # Телеграфы → враги (с учётом лимитов)
        shooters = sum(1 for e in g.enemies if e.alive and e.kind == 'shooter')
        kamikaze = sum(1 for e in g.enemies if e.alive and e.kind == 'kamikaze')
        active = sum(1 for e in g.enemies if e.alive)
        for tg in self.telegraphs:
            if tg['delay'] > 0:
                tg['delay'] -= dt
                continue
            tg['t'] -= dt
            if tg['t'] > 0:
                continue
            if active >= CFG.WAVE_MAX_ACTIVE_ENEMIES and tg['kind'] != 'boss':
                tg['t'] = 0.0
                continue
            if tg['kind'] == 'shooter' and shooters >= CFG.WAVE_MAX_SHOOTERS:
                continue
            if tg['kind'] == 'kamikaze' and kamikaze >= CFG.WAVE_MAX_KAMIKAZE:
                continue
            enemy = g.spawn_enemy(tg['kind'], tg['x'], tg['y'], tg['elite'], tg['shield'], tg.get('tier', 1))
            if tg['kind'] == 'boss':
                self.boss = enemy
            tg['done'] = True
            active += 1
            shooters += tg['kind'] == 'shooter'
            kamikaze += tg['kind'] == 'kamikaze'
        self.telegraphs = [t for t in self.telegraphs if not t.get('done')]
        # Следующая подволна: на доле такта, когда осталось мало врагов или вышло время
        if self.current_sub < len(self.subwaves) - 1:
            sub_alive = alive + len(self.telegraphs)
            if not self.release_pending and (sub_alive <= self.sub_size * CFG.WAVE_SUBWAVE_RELEASE_FRACTION
                                             or self.sub_timer >= CFG.WAVE_SUBWAVE_MAX_GAP):
                self.release_pending = True
                self.release_wait = 0.0
            if self.release_pending:
                self.release_wait += dt
                if beat or self.release_wait > CFG.BEAT_INTERVAL * 1.5:
                    self._release_next()
        # Интенсивность музыки следует за давлением волны
        pressure = clamp((alive + 0.5 * len(self.telegraphs)) / max(6.0, self.peak_alive), 0, 1)
        if self.special == 'haste' or self.is_boss_wave:
            pressure = max(pressure, 0.8)
        g.music_system.intensity = 0.25 + 0.75 * pressure
        # Конец волны
        if (self.current_sub >= len(self.subwaves) - 1 and not self.telegraphs and alive == 0
                and not any(e.alive and getattr(e, 'kind', '') == 'boss' for e in g.enemies)):
            self.finish_wave()

    def finish_wave(self) -> None:
        g = self.game
        n = self.wave
        no_damage = self.wave_damage <= 0
        score = CFG.WAVE_REWARD_SCORE * n
        if no_damage:
            score = int(score * (1 + CFG.WAVE_NO_DAMAGE_BONUS))
        par_bonus = int(max(0.0, self.par - self.wave_time) * 20)
        score += par_bonus
        if self.overheat:
            score = int(score * 1.5)
        cp = CFG.CP_PER_WAVE + (2 if self.is_boss_wave else 0)
        # DDA: плавная подстройка бюджета (не трогает урон и окна)
        dmg_ratio = self.wave_damage / max(1.0, g.player.max_hp)
        if g.settings.get('dda', True) and g.run_type not in ('daily', 'weekly', 'pure'):
            if dmg_ratio < 0.1 and self.wave_time < self.par:
                self.dda += 0.04
            elif dmg_ratio > 0.5:
                self.dda -= 0.06
            self.dda = clamp(self.dda, CFG.DDA_MIN, CFG.DDA_MAX)
        # Перегрев: слишком быстро и чисто — следующая волна плотнее и дороже
        if no_damage and self.wave_time < self.par * 0.5 and not self.is_boss_wave:
            self.next_overheat = True
        summary = {'wave': n, 'time': round(self.wave_time, 1), 'kills': self.wave_kills,
                   'damage': int(self.wave_damage), 'no_damage': no_damage, 'par': round(self.par, 1),
                   'score_bonus': score, 'par_bonus': par_bonus, 'cp': cp, 'special': self.special,
                   'boss': self.is_boss_wave, 'breather': self.is_breather, 'budget': round(self.budget, 1),
                   'dda': round(self.dda, 2), 'overheat': self.overheat, 'next_overheat': self.next_overheat}
        self.log.append(summary)
        self.last_summary = summary
        self.state = 'intermission'
        self.timer = CFG.WAVE_INTERMISSION
        self.telegraphs = []
        g.on_wave_cleared(summary)

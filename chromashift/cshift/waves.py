"""Директор волн 0.7.0: бюджет угроз, отряды и формации (в том числе рои по 8–14 и отряды
с вожаком), подволны на долях такта, телеграф спавна, лимиты по типам, элиты, подкрепления,
особые волны (тьма, ускорение, монохром, выживание, засада, один цвет, инверсия, гравитация,
зеркала), мини-босс, три босса по кругу (победа на 30-й волне), Орда, ставка на волну,
режимы Босс-раш / Блиц / Бесконечный / Свои волны, DDA и итоги волны."""
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .config import CFG, MODES
from .enemies_ext import EXT_HINTS, EXT_NAMES
from .utils import clamp, vec_distance, vec_normalize

ENEMY_UNLOCK = {'chaser': 1, 'swarm': 2, 'shooter': 2, 'kamikaze': 3, 'leader': 4, 'dissonance': 5,
                'prism': 6, 'miner': 7, 'mirror': 8, 'chameleon': 9, 'shieldbearer': 11, 'laser': 12,
                'devourer': 13, 'summoner': 14, 'teleporter': 16, 'resonator': 17}
TRAINING_TIPS = {
    'shooter': ('Новый враг: Стрелок', 'Смените цвет прямо перед попаданием пули — Преломление'),
    'kamikaze': ('Новый враг: Камикадзе', 'Красный круг — зона взрыва. Рывок даёт неуязвимость'),
    'dissonance': ('Новый враг: Диссонанс', 'Броня гасит обычные пули наполовину, рядом с ним '
                   'нельзя сменить цвет. Отражённая пуля и волна BLUE бьют в полную силу'),
}
for _k, _hint in EXT_HINTS.items():
    if _k in ENEMY_UNLOCK:
        TRAINING_TIPS[_k] = ('Новый враг: ' + EXT_NAMES[_k], _hint)

SPECIAL_WAVES = {
    'darkness': ('Волна «Тьма»', 'Видимость ограничена — следите за телеграфами'),
    'haste': ('Волна «Ускорение»', 'Враги на 30% быстрее, музыка на пределе'),
    'mono': ('Монохромная волна', 'Все враги уязвимы к одному цвету'),
    'survive': ('Волна «Выживание»', 'Продержитесь {t} с — враги идут без остановки'),
    'ambush': ('Волна «Засада»', 'Враги появляются рядом — телеграф дольше обычного'),
    'onecolor': ('Волна «Один цвет»', 'Цвет зафиксирован на всю волну'),
    'inversion': ('Волна «Инверсия»', 'Физика цветов перемешана — привыкайте заново'),
    'gravity': ('Волна «Гравитация»', 'Гравитационные колодцы тянут вас и пули'),
    'mirror': ('Волна «Зеркала»', 'Много Зеркал — меняйте цвет перед выстрелом'),
}
SPECIAL_MIN_WAVE = {'darkness': 7, 'haste': 7, 'mono': 7, 'survive': 8, 'ambush': 9, 'onecolor': 10,
                    'inversion': 12, 'gravity': 11, 'mirror': 12}
BOSS_CYCLE = ('boss', 'hydra', 'spectrum')
BOSS_SUBTITLES = {'boss': 'Диссонанс-Прайм: бейте цветом его щита',
                  'hydra': 'Хроматическая Гидра: сначала головы — каждая уязвима к своему цвету',
                  'spectrum': 'Абсолютный Спектр: проходите стены пуль в их цвете'}
VICTORY_WAVE = 30
# Лимиты одновременно живых врагов по типам (сверх общего WAVE_MAX_ACTIVE_ENEMIES)
TYPE_LIMITS = {'shooter': CFG.WAVE_MAX_SHOOTERS, 'kamikaze': CFG.WAVE_MAX_KAMIKAZE, 'laser': 3, 'summoner': 2,
               'miner': 3, 'mirror': 5, 'devourer': 3, 'shieldbearer': 3, 'resonator': 3, 'teleporter': 4,
               'dissonance': 4, 'swarm': 45, 'prism': 4, 'chameleon': 5, 'leader': 3}
ELITE_TYPES = ['fast', 'armored', 'splitting', 'shielded', 'vampire', 'accelerator', 'reflective']

# (id, состав, формация, с какой волны, базовый вес)
SQUADS: List[Tuple[str, List[Tuple[str, int]], str, int, float]] = [
    ('pack', [('chaser', 3)], 'arc', 1, 1.0),
    ('big_pack', [('chaser', 5)], 'arc', 4, 0.8),
    ('swarm_s', [('swarm', 8)], 'ring', 2, 0.9),
    ('swarm_l', [('swarm', 14)], 'ring', 6, 0.7),
    ('firing_line', [('shooter', 2)], 'line', 2, 0.9),
    ('battery', [('shooter', 3)], 'line', 6, 0.6),
    ('kamikaze_ring', [('kamikaze', 3)], 'ring', 3, 0.8),
    ('mixed', [('chaser', 2), ('shooter', 1)], 'cluster', 3, 1.0),
    ('warband', [('leader', 1), ('chaser', 4)], 'arc', 4, 0.7),
    ('ambush', [('kamikaze', 2), ('chaser', 2)], 'pincer', 5, 0.8),
    ('hunter', [('dissonance', 1), ('chaser', 2)], 'cluster', 5, 0.6),
    ('prism_pair', [('prism', 2)], 'line', 6, 0.6),
    ('minefield', [('miner', 1), ('swarm', 6)], 'cluster', 7, 0.6),
    ('siege', [('shooter', 2), ('kamikaze', 2)], 'pincer', 7, 0.7),
    ('mirror_pair', [('mirror', 2), ('chaser', 2)], 'pincer', 8, 0.6),
    ('chameleons', [('chameleon', 3)], 'arc', 9, 0.6),
    ('choir', [('dissonance', 2)], 'pincer', 9, 0.4),
    ('phalanx', [('shieldbearer', 1), ('chaser', 4)], 'arc', 11, 0.7),
    ('laser_net', [('laser', 2), ('swarm', 6)], 'line', 12, 0.5),
    ('devourers', [('devourer', 2)], 'pincer', 13, 0.5),
    ('summon_circle', [('summoner', 1), ('chaser', 2)], 'cluster', 14, 0.5),
    ('blinkers', [('teleporter', 3)], 'ring', 16, 0.5),
    ('resonance', [('resonator', 1), ('chaser', 3), ('swarm', 6)], 'cluster', 17, 0.6),
    ('war_host', [('leader', 1), ('shooter', 2), ('chaser', 3)], 'arc', 15, 0.5),
    ('rainbow', [('prism', 1), ('mirror', 1), ('chameleon', 1)], 'pincer', 18, 0.5),
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
        self.boss_kind: Optional[str] = None
        self.is_miniboss = False
        self.is_breather = False
        self.boss: Any = None
        self.recent_squads: List[str] = []
        self.introduced: set = set()
        self.log: List[Dict[str, Any]] = []
        self.last_summary: Optional[Dict[str, Any]] = None
        self.peak_alive = 1
        # 0.7.0
        self.squad_counter = 0
        self.reinforcements = 0
        self.reinforce_timer = 0.0
        self.survive_left = 0.0
        self.gamble_next = False
        self.gamble = False
        self.clean_streak = 0
        self.tempo = False
        self.victory_done = False

    # --- Параметры ---
    @property
    def mods(self) -> Any:
        return self.game.mods

    @property
    def run_type(self) -> str:
        return getattr(self.game, 'run_type', 'standard')

    def horde(self) -> bool:
        return 'horde' in (getattr(self.game, 'risks', None) or [])

    def elite_chance(self, n: int) -> float:
        if n < CFG.ELITE_START_WAVE:
            return 0.0
        return min(CFG.ELITE_MAX_CHANCE, CFG.ELITE_CHANCE_PER_WAVE * (n - CFG.ELITE_START_WAVE + 1)
                   + self.mods.elite_chance_add)

    def telegraph_time(self) -> float:
        t = max(0.3, CFG.WAVE_TELEGRAPH_TIME + self.mods.telegraph_add)
        return t * (1.6 if self.special == 'ambush' else 1.0)

    def progress(self) -> float:
        if self.state == 'active' and self.special == 'survive':
            return clamp(1 - self.survive_left / CFG.SURVIVE_DURATION, 0.0, 1.0)
        if self.state != 'active' or self.total <= 0:
            return 1.0 if self.state == 'intermission' else 0.0
        return clamp(self.killed / self.total, 0.0, 1.0)

    def boss_kind_for(self, n: int) -> Tuple[str, int]:
        """Боссы по кругу: 10 — Прайм, 20 — Гидра, 30 — Спектр, дальше по кругу с ростом уровня."""
        if self.run_type == 'bossrush':
            idx = n - 1
        else:
            idx = n // CFG.BOSS_WAVE_INTERVAL - 1
        return BOSS_CYCLE[idx % 3], 1 + idx // 3

    def toggle_gamble(self) -> str:
        """Ставка на следующую волну (клавиша B в паузе между волнами)."""
        if self.state != 'intermission':
            return 'Ставку можно сделать только между волнами'
        self.gamble_next = not self.gamble_next
        if self.gamble_next:
            return (f"Ставка принята: врагов ×{CFG.GAMBLE_BUDGET_MULT:g}. Пройдите волну, потеряв меньше 25% HP, "
                    f"— очки ×{CFG.GAMBLE_SCORE_MULT:g} и +{CFG.GAMBLE_CP} CP")
        return 'Ставка отменена'

    # --- Состав волны ---
    def squad_weight(self, sq: Tuple, n: int) -> float:
        sid, members, _, min_wave, base = sq
        if n < min_wave:
            return 0.0
        w = base * (0.25 + 0.75 * smoothstep((n - min_wave + 1) / 3.0))  # плавное введение
        if sid in self.recent_squads[-2:]:
            w *= 0.35  # анти-повтор
        if any(k == 'swarm' for k, _ in members):
            w *= self.mods.swarm_mult
        if self.special == 'mirror' and any(k == 'mirror' for k, _ in members):
            w *= 4.0
        return w

    def scaled_members(self, members: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        out = []
        for k, c in members:
            if k == 'swarm':
                c = max(1, int(round(c * min(3.0, self.mods.swarm_mult))))
            out.append((k, c))
        return out

    def compose(self, n: int, budget: float) -> List[Dict[str, Any]]:
        squads: List[Dict[str, Any]] = []
        remaining = budget
        guard = 0
        while remaining >= 1.0 and guard < 80:
            guard += 1
            options = [(sq, self.squad_weight(sq, n)) for sq in SQUADS]
            options = [(sq, w) for sq, w in options if w > 0 and squad_cost(sq[1]) <= remaining + 0.6]
            if not options:
                squads.append({'id': 'filler', 'members': [('chaser', 1)], 'formation': 'cluster'})
                remaining -= enemy_cost('chaser')
                continue
            sq = self.rng.choices([o[0] for o in options], weights=[o[1] for o in options], k=1)[0]
            squads.append({'id': sq[0], 'members': self.scaled_members(sq[1]), 'formation': sq[2]})
            self.recent_squads.append(sq[0])
            remaining -= squad_cost(sq[1])
        if self.special == 'mirror' and n >= ENEMY_UNLOCK['mirror']:
            squads.append({'id': 'mirror_pair', 'members': [('mirror', 2)], 'formation': 'pincer'})
        self.recent_squads = self.recent_squads[-6:]
        return squads

    def custom_wave(self, n: int) -> Optional[Dict[str, Any]]:
        waves = getattr(self.game, 'custom_waves', None) or []
        if self.run_type == 'custom' and 1 <= n <= len(waves):
            return waves[n - 1]
        return None

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
        safe_r = CFG.WAVE_SAFE_RADIUS * (0.7 if self.special == 'ambush' else 1.0)
        if self.special == 'ambush':
            a0 = self.rng.uniform(0, 2 * math.pi)
            ax, ay = player[0] + math.cos(a0) * safe_r * 1.1, player[1] + math.sin(a0) * safe_r * 1.1
        else:
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
                pts.append((ax + px * math.sin(a) * r * 2 - dx * math.cos(a) * 20,
                            ay + py * math.sin(a) * r * 2 - dy * math.cos(a) * 20))
        elif formation == 'ring':
            rr = 45 + 4 * max(0, count - 6)
            for i in range(count):
                a = i * 2 * math.pi / count
                pts.append((ax + math.cos(a) * rr, ay + math.sin(a) * rr))
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
            d = vec_distance(x, y, player[0], player[1])
            if d < safe_r:  # безопасная зона вокруг игрока
                nx, ny = vec_normalize(x - player[0], y - player[1]) if d > 1 else (1.0, 0.0)
                x = clamp(player[0] + nx * safe_r, 30, CFG.SCREEN_WIDTH - 30)
                y = clamp(player[1] + ny * safe_r, 30, CFG.SCREEN_HEIGHT - 30)
            out.append((x, y))
        return out

    def squads_to_entries(self, squads: List[Dict[str, Any]], player: Tuple[float, float],
                          n_groups: int) -> List[List[Dict[str, Any]]]:
        buckets: List[List[Dict[str, Any]]] = [[] for _ in range(max(1, n_groups))]
        for i, sq in enumerate(squads):
            count = sum(c for _, c in sq['members'])
            pts = self.formation_points(sq['formation'], count, player)
            kinds = [k for k, c in sq['members'] for _ in range(c)]
            self.squad_counter += 1
            sid = self.squad_counter if any(k == 'leader' for k in kinds) else None
            bucket = buckets[i % len(buckets)]
            for j, (kind, (x, y)) in enumerate(zip(kinds, pts)):
                e = self._entry(kind, x, y, len(bucket) + j)
                e['squad'] = sid
                bucket.append(e)
        return [b for b in buckets if b]

    # --- Жизненный цикл ---
    def begin_wave(self) -> None:
        self.wave += 1
        n = self.wave
        g = self.game
        rt = self.run_type
        custom = self.custom_wave(n)
        self.boss_kind = None
        if rt == 'bossrush':
            self.is_boss_wave = True
        elif custom is not None:
            self.is_boss_wave = bool(custom.get('boss'))
        else:
            self.is_boss_wave = n % CFG.BOSS_WAVE_INTERVAL == 0
        self.is_miniboss = (not self.is_boss_wave and custom is None and rt not in ('bossrush',)
                            and n % CFG.BOSS_WAVE_INTERVAL == CFG.BREATHER_WAVE_INTERVAL)
        self.is_breather = ((n % CFG.BREATHER_WAVE_INTERVAL == 0) and not self.is_boss_wave
                            and not self.is_miniboss and rt not in ('blitz', 'bossrush') and custom is None)
        self.overheat = self.next_overheat
        self.next_overheat = False
        self.gamble = self.gamble_next
        self.gamble_next = False
        self.special = None
        self.mono_mode = None
        self.reinforcements = 0
        self.reinforce_timer = 0.0
        if custom is not None:
            self.special = custom.get('special') if custom.get('special') in SPECIAL_WAVES else None
        elif (not self.is_boss_wave and not self.is_breather and not self.is_miniboss
              and n >= CFG.SPECIAL_WAVE_MIN
              and self.rng.random() < CFG.SPECIAL_WAVE_CHANCE * (1.5 if rt == 'endless' else 1.0)):
            pool = sorted(k for k, w in SPECIAL_MIN_WAVE.items() if n >= w)
            self.special = self.rng.choice(pool)
        if self.special == 'mono':
            self.mono_mode = self.rng.choice(MODES)
        self.survive_left = CFG.SURVIVE_DURATION if self.special == 'survive' else 0.0
        # wave_effects: узлы дерева «с волны N»
        prof = getattr(g, 'profile', None)
        if prof is not None and getattr(self.mods, 'wave_effects', None):
            on = prof.apply_wave_effects(self.mods, n)
            if on and hasattr(g, 'refresh_player_from_mods'):
                g.refresh_player_from_mods()
                if hasattr(g, 'floating_texts_add'):
                    g.floating_texts_add(g.player.x, g.player.y - 40, 'Включено: ' + ', '.join(on),
                                         (255, 220, 140), 2.0, 18)
        budget = wave_budget(n) * self.mods.budget_mult * self.dda
        if self.overheat:
            budget *= CFG.OVERHEAT_BUDGET_MULT
        if self.is_breather or self.is_miniboss:
            budget *= CFG.BREATHER_BUDGET_MULT
        if self.gamble:
            budget *= CFG.GAMBLE_BUDGET_MULT
        if self.tempo:
            budget *= 1.15
        if rt == 'blitz':
            budget *= 1.3
        if self.is_boss_wave:
            budget *= 0.3 if rt != 'bossrush' else 0.2
        if self.special == 'survive':
            budget *= 0.6  # стартовый состав; дальше — непрерывные подкрепления
        self.budget = budget
        self.par = max(10.0, budget * CFG.WAVE_PAR_SECONDS_PER_BUDGET + (25.0 if self.is_boss_wave else 0.0))
        if custom is not None:
            squads = [{'id': 'custom', 'members': [(k, int(c)) for k, c in custom.get('members', [])
                                                    if k in ENEMY_UNLOCK and int(c) > 0],
                       'formation': custom.get('formation', 'cluster')}]
            squads = [sq for sq in squads if sq['members']]
        else:
            squads = self.compose(n, budget)
        player = (g.player.x, g.player.y)

        # Обучающая пачка: первый выход нового типа — отдельно и с подсказкой
        intro_kind = None
        if custom is None and rt not in ('bossrush',):
            for kind, w in ENEMY_UNLOCK.items():
                if w == n and kind not in self.introduced and kind in TRAINING_TIPS:
                    intro_kind = kind
                    self.introduced.add(kind)
                    break
        groups: List[List[Dict[str, Any]]] = []
        if intro_kind:
            cnt = 6 if intro_kind == 'swarm' else 2
            pts = self.formation_points('ring' if intro_kind == 'swarm' else 'line', cnt, player)
            groups.append([self._entry(intro_kind, x, y, i, allow_elite=False) for i, (x, y) in enumerate(pts)])
            title, tip = TRAINING_TIPS[intro_kind]
            g.announce(title, tip)
        if self.is_boss_wave:
            kind, tier = self.boss_kind_for(n)
            if custom is not None and custom.get('boss') in BOSS_CYCLE:
                kind = custom['boss']
            self.boss_kind = kind
            groups.append([{'kind': kind, 'x': CFG.SCREEN_WIDTH / 2, 'y': 110.0, 'elite': [], 'shield': None,
                            't': 1.6, 'delay': 0.0, 'tier': tier, 'squad': None}])
        if self.is_miniboss:
            tier = 1 + n // (CFG.BOSS_WAVE_INTERVAL * 2)
            groups.append([{'kind': 'warden', 'x': CFG.SCREEN_WIDTH / 2, 'y': 120.0, 'elite': [], 'shield': None,
                            't': 1.4, 'delay': 0.0, 'tier': tier, 'squad': None}])
        n_groups = max(1, min(7, 1 + int(len(squads) / 2.5)))
        groups += self.squads_to_entries(squads, player, n_groups)
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
        if self.special and hasattr(g, 'on_special_wave'):
            g.on_special_wave(self.special)

        title = f"ВОЛНА {n}"
        subtitle = ''
        if self.is_boss_wave:
            title += ' — БОСС'
            subtitle = BOSS_SUBTITLES.get(self.boss_kind, '')
        elif self.is_miniboss:
            title += ' — СТРАЖ'
            subtitle = 'Мини-босс Страж-Призма: бейте цветом его оболочки'
        elif self.is_breather:
            title += ' — ПЕРЕДЫШКА'
            subtitle = 'Выберите один из двух бонусов'
            g.spawn_breather_choice()
        elif self.special:
            title += ' — ' + SPECIAL_WAVES[self.special][0]
            subtitle = SPECIAL_WAVES[self.special][1].format(t=int(CFG.SURVIVE_DURATION))
            if self.special == 'mono':
                subtitle = f"Все враги уязвимы только к {self.mono_mode}"
        extras = []
        if self.overheat:
            extras.append('ПЕРЕГРЕВ: больше врагов, ×1.5 очков')
        if self.gamble:
            extras.append('СТАВКА')
        if self.tempo:
            extras.append('ТЕМП: +15% врагов')
        if extras:
            subtitle = ' · '.join(([subtitle] if subtitle else []) + extras)
        if not intro_kind:
            g.announce(title, subtitle)
        else:
            g.floating_title(title)
        g.sound_manager.play('wave', 0.5)
        if self.is_boss_wave or self.is_miniboss:
            g.sound_manager.play('boss_phase', 0.6)

    def _entry(self, kind: str, x: float, y: float, index: int, allow_elite: bool = True) -> Dict[str, Any]:
        elite: List[str] = []
        shield = None
        if allow_elite and kind != 'swarm' and self.rng.random() < self.elite_chance(self.wave):
            elite = [self.rng.choice(ELITE_TYPES)]
            if 'shielded' in elite:
                shield = self.rng.choice(MODES)
        if self.mono_mode and kind not in ('dissonance', 'swarm'):
            if 'shielded' not in elite:
                elite = elite + ['shielded']
            shield = self.mono_mode
        stagger = CFG.WAVE_SPAWN_STAGGER * (0.35 if kind == 'swarm' else 1.0)
        return {'kind': kind, 'x': x, 'y': y, 'elite': elite, 'shield': shield,
                't': self.telegraph_time(), 'delay': index * stagger, 'squad': None}

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

    def reinforce(self) -> None:
        """Подкрепление: небольшой отряд, если волна затянулась (или непрерывно в «Выживании»)."""
        g = self.game
        n = max(1, self.wave)
        budget = max(3.0, wave_budget(n) * 0.25 * self.mods.budget_mult)
        squads = self.compose(n, budget)
        entries = [e for grp in self.squads_to_entries(squads, (g.player.x, g.player.y), 1) for e in grp]
        self.telegraphs.extend(entries)
        self.total += len(entries)
        self.game.sound_manager.play('telegraph', 0.35)

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
        # Телеграфы → враги (с учётом общих лимитов и лимитов по типам)
        counts: Dict[str, int] = {}
        active = 0
        for e in g.enemies:
            if e.alive:
                active += 1
                counts[e.kind] = counts.get(e.kind, 0) + 1
        for tg in self.telegraphs:
            if tg['delay'] > 0:
                tg['delay'] -= dt
                continue
            tg['t'] -= dt
            if tg['t'] > 0:
                continue
            big = tg['kind'] in BOSS_CYCLE or tg['kind'] == 'warden'
            if active >= CFG.WAVE_MAX_ACTIVE_ENEMIES and not big:
                tg['t'] = 0.0
                continue
            lim = TYPE_LIMITS.get(tg['kind'])
            if lim is not None and counts.get(tg['kind'], 0) >= lim:
                continue
            enemy = g.spawn_enemy(tg['kind'], tg['x'], tg['y'], tg['elite'], tg['shield'], tg.get('tier', 1))
            if tg.get('squad') is not None:
                enemy.squad_id = tg['squad']
                if tg['kind'] == 'leader':
                    enemy.is_leader = True
            if tg['kind'] in BOSS_CYCLE:
                self.boss = enemy
            tg['done'] = True
            active += 1
            counts[tg['kind']] = counts.get(tg['kind'], 0) + 1
        self.telegraphs = [t for t in self.telegraphs if not t.get('done')]
        # Следующая подволна: на доле такта, когда осталось мало врагов или вышло время
        last_sub = self.current_sub >= len(self.subwaves) - 1
        if not last_sub:
            sub_alive = alive + len(self.telegraphs)
            if not self.release_pending and (sub_alive <= self.sub_size * CFG.WAVE_SUBWAVE_RELEASE_FRACTION
                                             or self.sub_timer >= CFG.WAVE_SUBWAVE_MAX_GAP):
                self.release_pending = True
                self.release_wait = 0.0
            if self.release_pending:
                self.release_wait += dt
                if beat or self.release_wait > CFG.BEAT_INTERVAL * 1.5:
                    self._release_next()
        # Подкрепления
        if self.special == 'survive':
            self.survive_left -= dt
            self.reinforce_timer += dt
            if self.reinforce_timer >= 6.0 and self.survive_left > 4.0:
                self.reinforce_timer = 0.0
                self.reinforce()
        elif last_sub and not self.is_boss_wave and self.reinforcements < 2 and alive > 0:
            self.reinforce_timer += dt
            if self.reinforce_timer >= CFG.WAVE_REINFORCE_AFTER and alive <= 3:
                self.reinforce_timer = 0.0
                self.reinforcements += 1
                self.reinforce()
        # Интенсивность музыки следует за давлением волны
        pressure = clamp((alive + 0.5 * len(self.telegraphs)) / max(6.0, self.peak_alive), 0, 1)
        if self.special in ('haste', 'survive') or self.is_boss_wave:
            pressure = max(pressure, 0.8)
        g.music_system.intensity = 0.25 + 0.75 * pressure
        # Конец волны
        if self.special == 'survive':
            if self.survive_left <= 0:
                for e in g.enemies:
                    if e.alive and e.counted and not getattr(e, 'boss_like', False) and e.kind != 'boss':
                        e.alive = False
                        g.particles.emit_burst(e.x, e.y, 6, (200, 200, 255), 120.0, 0.3, 2.0)
                self.telegraphs = []
                self.finish_wave()
            return
        if (last_sub and not self.telegraphs and alive == 0
                and not any(e.alive and getattr(e, 'kind', '') == 'boss' for e in g.enemies)):
            self.finish_wave()

    def finish_wave(self) -> None:
        g = self.game
        n = self.wave
        rt = self.run_type
        no_damage = self.wave_damage <= 0
        score = CFG.WAVE_REWARD_SCORE * n
        if no_damage:
            score = int(score * (1 + CFG.WAVE_NO_DAMAGE_BONUS))
        par_bonus = int(max(0.0, self.par - self.wave_time) * 20)
        score += par_bonus
        if self.overheat:
            score = int(score * 1.5)
        cp = CFG.CP_PER_WAVE + (2 if self.is_boss_wave else 0) + (1 if self.is_miniboss else 0)
        gamble_won = None
        if self.gamble:
            gamble_won = self.wave_damage < 0.25 * max(1.0, g.player.max_hp)
            if gamble_won:
                score = int(score * CFG.GAMBLE_SCORE_MULT)
                cp += CFG.GAMBLE_CP
                g.stats['gambles_won'] = g.stats.get('gambles_won', 0) + 1
        # DDA: плавная подстройка бюджета (не трогает урон и окна)
        dmg_ratio = self.wave_damage / max(1.0, g.player.max_hp)
        if g.settings.get('dda', True) and rt not in ('daily', 'weekly', 'pure', 'custom', 'bossrush'):
            if dmg_ratio < 0.1 and self.wave_time < self.par:
                self.dda += 0.04
            elif dmg_ratio > 0.5:
                self.dda -= 0.06
            self.dda = clamp(self.dda, CFG.DDA_MIN, CFG.DDA_MAX)
        # Перегрев: слишком быстро и чисто — следующая волна плотнее и дороже
        if no_damage and self.wave_time < self.par * 0.5 and not self.is_boss_wave:
            self.next_overheat = True
        # Темп: после 3 чистых волн подряд — короче пауза и чуть больше врагов
        self.clean_streak = self.clean_streak + 1 if no_damage else 0
        self.tempo = self.clean_streak >= 3
        summary = {'wave': n, 'time': round(self.wave_time, 1), 'kills': self.wave_kills,
                   'damage': int(self.wave_damage), 'no_damage': no_damage, 'par': round(self.par, 1),
                   'score_bonus': score, 'par_bonus': par_bonus, 'cp': cp, 'special': self.special,
                   'boss': self.is_boss_wave, 'boss_kind': self.boss_kind, 'miniboss': self.is_miniboss,
                   'breather': self.is_breather, 'budget': round(self.budget, 1), 'dda': round(self.dda, 2),
                   'overheat': self.overheat, 'next_overheat': self.next_overheat, 'gamble': gamble_won,
                   'tempo': self.tempo, 'reinforcements': self.reinforcements}
        self.log.append(summary)
        self.last_summary = summary
        self.state = 'intermission'
        t = CFG.WAVE_INTERMISSION
        if self.horde():
            t *= CFG.HORDE_INTERMISSION_MULT
        if rt == 'blitz':
            t = 0.6
        if self.tempo:
            t *= 0.6
        self.timer = t
        self.telegraphs = []
        if self.special and hasattr(g, 'on_special_end'):
            g.on_special_end(self.special)
        g.on_wave_cleared(summary)
        if self.is_miniboss and rt != 'blitz':
            g.spawn_breather_choice()
        # Победа: 30-я волна стандартного забега, 3 босса в Босс-раше, конец своих волн
        victory = False
        if not self.victory_done:
            if rt in ('standard', 'daily', 'weekly', 'pure') and n >= VICTORY_WAVE and self.is_boss_wave:
                victory = True
            elif rt == 'bossrush' and n >= len(BOSS_CYCLE):
                victory = True
            elif rt == 'custom' and n >= len(getattr(g, 'custom_waves', None) or [None]):
                victory = True
        if victory:
            self.victory_done = True
            if hasattr(g, 'on_victory'):
                g.on_victory()
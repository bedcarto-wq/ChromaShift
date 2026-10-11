"""Метагейм ChromaShift 0.7.0: модификаторы забега, дерево улучшений, корпуса и модули,
артефакты, профили и сохранения, статистика, достижения, контракты, испытания."""
import copy
import datetime as _dt
import json
import logging
import os
import random
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import ALL_MODES, CFG, MODES, GAME_VERSION, resolve_game_path

logger = logging.getLogger('ChromaShift')

SAVE_VERSION = 4
PROFILE_SLOTS = 3
BACKUP_COUNT = 3


def saves_dir() -> str:
    path = resolve_game_path('saves')
    os.makedirs(path, exist_ok=True)
    return path


# =====================================================================
# МОДИФИКАТОРЫ ЗАБЕГА
# =====================================================================
class RunMods:
    """Все числовые модификаторы, которые собираются из дерева, корпуса, модулей,
    артефактов, сложности, напряжения и рисков. Игрок и директор волн читают только их."""

    def __init__(self) -> None:
        self.max_hp_add = 0.0
        self.max_hp_mult = 1.0
        self.damage_mult = 1.0
        self.mode_damage_mult = {m: 1.0 for m in ALL_MODES}
        self.fire_rate_mult = 1.0
        self.bullet_speed_mult = 1.0
        self.dash_cd_mult = 1.0
        self.dash_speed_mult = 1.0
        self.dash_invuln_add = 0.0
        self.refraction_window_add = 0.0
        self.refraction_window_mult = 1.0
        self.refraction_pierce = False
        self.refraction_ricochet = 0
        self.refraction_homing = False
        self.echo_duration_add = 0.0
        self.echo_threshold_add = 0
        self.resonance_threshold_add = 0
        self.resonance_radius_mult = 1.0
        self.resonance_lifetime_add = 0.0
        self.impulse_threshold_add = 0
        self.impulse_duration_add = 0.0
        self.beat_window_add = 0.0
        self.beat_groove = False
        self.accel_mult = {m: 1.0 for m in ALL_MODES}
        self.max_speed_mult = {m: 1.0 for m in ALL_MODES}
        self.decel_mult = {m: 1.0 for m in ALL_MODES}
        self.drift_mult = 1.0
        self.blue_aoe_mult = 1.0
        self.red_dash_trail = False
        self.green_afterimage = False
        self.blue_shockwave = False
        self.blue_split = False
        self.twin_barrel = False
        self.railgun_dash = False
        self.shield_charges = 0
        self.revives = 0
        self.invuln_time_mult = 1.0
        self.pickup_radius_mult = 1.0
        self.powerup_chance_add = 0.0
        self.no_heal = False
        self.cp_mult = 1.0
        self.score_mult = 1.0
        self.enemy_hp_mult = 1.0
        self.enemy_speed_mult = 1.0
        self.enemy_damage_mult = 1.0
        self.enemy_bullet_speed_mult = 1.0
        self.budget_mult = 1.0
        self.telegraph_add = 0.0
        self.elite_chance_add = 0.0
        # --- 0.7.0 ---
        self.violet_unlocked = False
        self.bullet_pierce = 0
        self.bullet_bounce = 0
        self.bullet_homing = False
        self.blue_gravity = False
        self.crit_add = 0.0
        self.crit_mult_add = 0.0
        self.overload_duration_add = 0.0
        self.overload_gain_mult = 1.0
        self.paint_chance_add = 0.0
        self.paint_radius_mult = 1.0
        self.chain_damage_mult = 1.0
        self.precise_mult = 1.5
        self.parry_touch_window_add = 0.0
        self.mix_cd_mult = 1.0
        self.skill_cd_mult = 1.0
        self.ability_cd_mult = 1.0
        self.phase_duration_add = 0.0
        self.shards_mult = 1.0
        self.boss_damage_mult = 1.0
        self.heal_on_kills = 0          # мастерство: +1 HP за каждые N убийств (0 — выкл.)
        self.swarm_mult = 1.0           # риск «Рой»/правила дня
        self.unstable_colors = False    # риск «Нестабильность»
        self.glass_mode = False         # риск «Стекло»
        self.always_dark = False        # риск «Затмение»
        self.wave_effects: List[Tuple[int, str, int]] = []  # узлы «от волны N»
        self.sources: List[str] = []  # что сформировало модификаторы (для экрана итогов)

    # Производные значения
    @property
    def refraction_window(self) -> float:
        return max(0.08, (CFG.PERFECT_REFRACTION_WINDOW + self.refraction_window_add) * self.refraction_window_mult)

    @property
    def resonance_threshold(self) -> int:
        return max(1, CFG.RESONANCE_KILL_THRESHOLD + self.resonance_threshold_add)

    @property
    def impulse_threshold(self) -> int:
        return max(2, CFG.IMPULSE_KILL_THRESHOLD + self.impulse_threshold_add)

    @property
    def echo_threshold(self) -> int:
        return max(1, CFG.ECHO_REFRACTION_THRESHOLD + self.echo_threshold_add)

    def all_speed(self, mult: float) -> None:
        for m in ALL_MODES:
            self.max_speed_mult[m] *= mult
            self.accel_mult[m] *= mult

    def to_dict(self) -> Dict[str, Any]:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in self.__dict__.items()
                if k not in ('sources', 'wave_effects')}


# =====================================================================
# ДЕРЕВО УЛУЧШЕНИЙ
# =====================================================================
BRANCHES = {
    'CORE': ('Ядро', (230, 240, 255)),
    'RED': ('Импульс', None),
    'BLUE': ('Якорь', None),
    'GREEN': ('Поток', None),
    'VIOLET': ('Фаза', None),
    'MASTER': ('Мастерство', (255, 210, 120)),
}


def _node(name: str, branch: str, costs: List[int], desc: str, effect: Callable[[RunMods, int], None],
          row: int, requires: Optional[List[str]] = None, tier_cp: int = 0, key: bool = False,
          group: Optional[str] = None, tradeoff: bool = False, legacy: Optional[str] = None,
          **extra: Any) -> Dict[str, Any]:
    d = {'name': name, 'branch': branch, 'costs': costs, 'max': len(costs), 'desc': desc,
         'effect': effect, 'row': row, 'requires': requires or [], 'tier_cp': tier_cp, 'key': key,
         'group': group, 'tradeoff': tradeoff, 'legacy': legacy,
         # 0.7.0: requires_any — хватит одного из узлов (мосты между ветками); hidden — скрытый узел
         # (функция профиля → открыт ли); hull — работает только с корпусом; toggle — можно выключать;
         # from_wave — эффект включается с волны N; grow — растёт от статистики; evolve — эволюция
         'requires_any': [], 'hidden': None, 'hidden_hint': '', 'hull': None, 'toggle': False,
         'from_wave': 0, 'grow': None, 'evolve': None, 'total_cp': 0, 'kind': 'normal'}
    d.update(extra)
    return d


def _m(attr: str, mode: str, per: float) -> Callable[[RunMods, int], None]:
    def f(m: RunMods, lvl: int) -> None:
        getattr(m, attr)[mode] *= (1 + per * lvl)
    return f


def _add(attr: str, per: float) -> Callable[[RunMods, int], None]:
    def f(m: RunMods, lvl: int) -> None:
        setattr(m, attr, getattr(m, attr) + per * lvl)
    return f


def _mul(attr: str, per: float) -> Callable[[RunMods, int], None]:
    def f(m: RunMods, lvl: int) -> None:
        setattr(m, attr, getattr(m, attr) * (per ** lvl))
    return f


def _flag(attr: str) -> Callable[[RunMods, int], None]:
    def f(m: RunMods, lvl: int) -> None:
        if lvl > 0:
            setattr(m, attr, True)
    return f


def _multi(*fs: Callable[[RunMods, int], None]) -> Callable[[RunMods, int], None]:
    def f(m: RunMods, lvl: int) -> None:
        for g in fs:
            g(m, lvl)
    return f


UPGRADES: Dict[str, Dict[str, Any]] = {
    # --- ЯДРО ---
    'core_hp': _node('Усиленный корпус', 'CORE', [20, 35, 55, 80, 110], '+15 к макс. HP за уровень',
                     _add('max_hp_add', 15), 0, legacy='max_hp'),
    'core_dash': _node('Фазовый привод', 'CORE', [30, 55, 90], '−10% перезарядки рывка за уровень',
                       _mul('dash_cd_mult', 0.9), 1, legacy='dash_cd'),
    'core_lens': _node('Темпоральная линза', 'CORE', [40, 70, 110], '+0.03 с к окну Преломления',
                       _add('refraction_window_add', 0.03), 2, legacy='refract_win'),
    'core_magnet': _node('Магнитный контур', 'CORE', [25, 45], '+30% радиус подбора бонусов',
                         _add('pickup_radius_mult', 0.3), 1),
    'core_luck': _node('Удача призмы', 'CORE', [30, 60], '+3% шанс выпадения бонуса',
                       _add('powerup_chance_add', 0.03), 2, requires=['core_magnet']),
    'core_shield': _node('Стартовый щит', 'CORE', [150], 'Забег начинается с 1 зарядом щита',
                         _add('shield_charges', 1), 3, tier_cp=150, key=True),
    'core_prism': _node('Призменная грань', 'CORE', [180], 'Отражённые пули пробивают врагов',
                        _flag('refraction_pierce'), 4, requires=['core_lens'], tier_cp=200, key=True),
    'core_revive': _node('Второй шанс', 'CORE', [250], 'Один раз за забег — воскрешение с 30% HP',
                         _add('revives', 1), 5, tier_cp=350, key=True),
    'core_glass': _node('Стеклянная пушка', 'CORE', [80], 'Компромисс: +25% урона, −25% макс. HP',
                        _multi(_mul('damage_mult', 1.25), _mul('max_hp_mult', 0.75)), 4,
                        tier_cp=100, group='core_style', tradeoff=True),
    'core_fortress': _node('Крепость', 'CORE', [80], 'Компромисс: +30% макс. HP, −10% урона',
                           _multi(_mul('max_hp_mult', 1.3), _mul('damage_mult', 0.9)), 4,
                           tier_cp=100, group='core_style', tradeoff=True),
    # --- RED: импульс и натиск ---
    'red_power': _node('Алая мощь', 'RED', [25, 45, 70], '+10% урона в RED за уровень',
                       _m('mode_damage_mult', 'RED', 0.10), 0),
    'red_thrust': _node('Форсаж', 'RED', [25, 45, 70], '+8% ускорения и +5% скорости RED',
                        _multi(_m('accel_mult', 'RED', 0.08), _m('max_speed_mult', 'RED', 0.05)), 1),
    'red_impulse': _node('Длинный импульс', 'RED', [40, 70], '+0.75 с длительности Импульса',
                         _add('impulse_duration_add', 0.75), 2, requires=['red_power']),
    'red_trail': _node('Огненный след', 'RED', [120], 'Рывок оставляет обжигающий след (ключевой)',
                       _flag('red_dash_trail'), 3, tier_cp=100, key=True, group='red_key'),
    'red_rail': _node('Рельсотрон', 'RED', [120], 'Рывок пронзает врагов и ранит их (ключевой)',
                      _flag('railgun_dash'), 3, tier_cp=100, key=True, group='red_key'),
    'red_overdrive': _node('Перегрузка', 'RED', [90], 'Компромисс: +20% скорострельности, −30% неуязвимости после удара',
                           _multi(_mul('fire_rate_mult', 1.2), _mul('invuln_time_mult', 0.7)), 4,
                           tier_cp=150, tradeoff=True),
    'red_chain': _node('Цепная реакция', 'RED', [60, 100], '−1 убийство до Импульса',
                       _add('impulse_threshold_add', -1), 5, requires=['red_impulse'], tier_cp=200),
    # --- BLUE: якорь и контроль ---
    'blue_power': _node('Кобальтовая мощь', 'BLUE', [25, 45, 70], '+10% урона в BLUE за уровень',
                        _m('mode_damage_mult', 'BLUE', 0.10), 0),
    'blue_aoe': _node('Широкая волна', 'BLUE', [25, 45, 70], '+15% радиус ударной волны BLUE',
                      _add('blue_aoe_mult', 0.15), 1),
    'blue_anchor': _node('Глубокий якорь', 'BLUE', [35, 60], '+10% торможения и +6% скорости BLUE',
                         _multi(_m('decel_mult', 'BLUE', 0.10), _m('max_speed_mult', 'BLUE', 0.06)), 2),
    'blue_shock': _node('Ударная смена', 'BLUE', [120], 'Переход в BLUE отталкивает и ранит врагов (ключевой)',
                        _flag('blue_shockwave'), 3, tier_cp=100, key=True, group='blue_key'),
    'blue_split': _node('Расщепление', 'BLUE', [120], 'BLUE стреляет веером из 3 пуль (ключевой)',
                        _flag('blue_split'), 3, tier_cp=100, key=True, group='blue_key'),
    'blue_bulwark': _node('Бастион', 'BLUE', [90], 'Компромисс: +1 щит, −15% скорости BLUE',
                          _multi(_add('shield_charges', 1), _m('max_speed_mult', 'BLUE', -0.15)), 4,
                          tier_cp=150, tradeoff=True),
    'blue_resonance': _node('Резонатор', 'BLUE', [60, 100], '+15% радиус и +1 с жизни Резонанса',
                            _multi(_add('resonance_radius_mult', 0.15), _add('resonance_lifetime_add', 1.0)),
                            5, requires=['blue_aoe'], tier_cp=200),
    # --- GREEN: поток и ритм ---
    'green_power': _node('Изумрудная мощь', 'GREEN', [25, 45, 70], '+10% урона в GREEN за уровень',
                         _m('mode_damage_mult', 'GREEN', 0.10), 0),
    'green_flow': _node('Чистый поток', 'GREEN', [25, 45, 70], '+6% скорости GREEN, −15% бокового дрейфа',
                        _multi(_m('max_speed_mult', 'GREEN', 0.06), _mul('drift_mult', 0.85)), 1),
    'green_groove': _node('Грув', 'GREEN', [40, 70], '+0.02 с к окну «в такт»',
                          _add('beat_window_add', 0.02), 2),
    'green_homing': _node('Искатель', 'GREEN', [120], 'Отражённые пули наводятся на врагов (ключевой)',
                          _flag('refraction_homing'), 3, tier_cp=100, key=True, group='green_key'),
    'green_ricochet': _node('Рикошет', 'GREEN', [120], 'Отражённые пули перескакивают 2 раза (ключевой)',
                            _add('refraction_ricochet', 2), 3, tier_cp=100, key=True, group='green_key'),
    'green_echo': _node('Долгое эхо', 'GREEN', [60, 100], '+1 с Эхо-камеры за уровень',
                        _add('echo_duration_add', 1.0), 4, requires=['green_groove'], tier_cp=150),
    'green_ghost': _node('Остаточный образ', 'GREEN', [90], 'Компромисс: рывок оставляет приманку, +15% перезарядки рывка',
                         _multi(_flag('green_afterimage'), _mul('dash_cd_mult', 1.15)), 5,
                         tier_cp=200, tradeoff=True),
}


def _set(attr: str, value: Any) -> Callable[[RunMods, int], None]:
    def f(m: RunMods, lvl: int) -> None:
        if lvl > 0:
            setattr(m, attr, value)
    return f


def _stat(key: str) -> Callable[[Dict[str, Any]], float]:
    return lambda data: float(data['stats'].get(key, 0) or 0)


UPGRADES.update({
    # --- VIOLET: фаза (новый, четвёртый цвет) ---
    'violet_root': _node('Фиолетовый спектр', 'VIOLET', [120], 'Открывает 4-й цвет VIOLET (клавиша 4): '
                         'быстрый, скользкий, пули пробивают 1 врага и бьют по цветным щитам на 50%',
                         _set('violet_unlocked', True), 0, total_cp=150, key=True, kind='root'),
    'violet_power': _node('Аметистовая мощь', 'VIOLET', [30, 50, 80], '+10% урона в VIOLET за уровень',
                          _m('mode_damage_mult', 'VIOLET', 0.10), 1, requires=['violet_root']),
    'violet_glide': _node('Скольжение', 'VIOLET', [30, 50], '+6% скорости и +8% ускорения VIOLET',
                          _multi(_m('max_speed_mult', 'VIOLET', 0.06), _m('accel_mult', 'VIOLET', 0.08)), 2,
                          requires=['violet_root']),
    'violet_phase': _node('Долгая фаза', 'VIOLET', [50, 90], '+0.3 с навыка «Фаза» (R в VIOLET)',
                          _add('phase_duration_add', 0.3), 3, requires=['violet_power']),
    'violet_drill': _node('Сверло', 'VIOLET', [140], 'Все пули пробивают ещё 1 врага (ключевой)',
                          _add('bullet_pierce', 1), 4, requires=['violet_root'], tier_cp=150, key=True,
                          group='violet_key'),
    'violet_bounce': _node('Призменный отскок', 'VIOLET', [140], 'Пули 1 раз отскакивают от стен (ключевой)',
                           _add('bullet_bounce', 1), 4, requires=['violet_root'], tier_cp=150, key=True,
                           group='violet_key'),
    'violet_seek': _node('Тяга спектра', 'VIOLET', [110], 'Компромисс: пули слегка наводятся, −10% урона',
                         _multi(_flag('bullet_homing'), _mul('damage_mult', 0.9)), 5, requires=['violet_root'],
                         tier_cp=250, tradeoff=True),
    # --- Новые узлы старых веток ---
    'core_crit': _node('Точка разлома', 'CORE', [40, 70, 110], '+3% шанс крита за уровень (крит ×2)',
                       _add('crit_add', 0.03), 6, tier_cp=250),
    'core_shards': _node('Сборщик осколков', 'CORE', [35, 60], '+25% осколков для магазина забега',
                         _add('shards_mult', 0.25), 6, tier_cp=120),
    'red_overload': _node('Ядерная перегрузка', 'RED', [50, 90], '+1 с к режиму Перегрузки',
                          _add('overload_duration_add', 1.0), 6, tier_cp=200),
    'blue_gravity': _node('Гравитационный якорь', 'BLUE', [130], 'Выстрел BLUE притягивает врагов к вам',
                          _flag('blue_gravity'), 6, tier_cp=250, key=True),
    'green_paint': _node('Палитра', 'GREEN', [40, 70], '+6% шанс краски при убийстве, +20% её радиус',
                         _multi(_add('paint_chance_add', 0.06), _add('paint_radius_mult', 0.2)), 6, tier_cp=150),
    # --- МАСТЕРСТВО: мосты, скрытые, корпусные, переключаемые, растущие, эволюция ---
    'x_magma': _node('Мост: Магма', 'MASTER', [90], 'RED + BLUE: цепные реакции бьют на 50% сильнее',
                     _mul('chain_damage_mult', 1.5), 0, requires=['red_power', 'blue_power'], kind='bridge'),
    'x_tide': _node('Мост: Прилив', 'MASTER', [90], 'BLUE + GREEN: окно парирования касанием +0.08 с',
                    _add('parry_touch_window_add', 0.08), 0, requires=['blue_power', 'green_power'], kind='bridge'),
    'x_storm': _node('Мост: Шторм', 'MASTER', [90], 'GREEN + RED: смешанные выстрелы перезаряжаются на 40% быстрее',
                     _mul('mix_cd_mult', 0.6), 0, requires=['green_power', 'red_power'], kind='bridge'),
    'x_prism': _node('Мост: Призма', 'MASTER', [120], 'Ядро + любая ветка VIOLET: перегрузка копится на 30% быстрее',
                     _mul('overload_gain_mult', 1.3), 1, requires=['core_hp'], requires_any=['violet_power', 'violet_glide'],
                     kind='bridge'),
    'm_red': _node('Мастер RED', 'MASTER', [200, 300], 'Мастерство (1 из 3): +12% урона RED, лечение 1 HP за 12 убийств',
                   _multi(_m('mode_damage_mult', 'RED', 0.12), _set('heal_on_kills', 12)), 2, group='mastery',
                   total_cp=800, kind='mastery'),
    'm_blue': _node('Мастер BLUE', 'MASTER', [200, 300], 'Мастерство (1 из 3): +25% радиус волны BLUE, +1 щит',
                    _multi(_add('blue_aoe_mult', 0.25), _add('shield_charges', 1)), 2, group='mastery',
                    total_cp=800, kind='mastery'),
    'm_green': _node('Мастер GREEN', 'MASTER', [200, 300], 'Мастерство (1 из 3): −15% перезарядки рывка и навыков',
                     _multi(_mul('dash_cd_mult', 0.85), _mul('skill_cd_mult', 0.85)), 2, group='mastery',
                     total_cp=800, kind='mastery'),
    'h_prime': _node('Сердце Прайма', 'MASTER', [150], 'Скрытый: +15% урона по боссам',
                     _mul('boss_damage_mult', 1.15), 3, hidden=lambda d: d['stats'].get('bosses', 0) >= 1,
                     hidden_hint='Победите любого босса', kind='hidden'),
    'h_mirror': _node('Зеркальная душа', 'MASTER', [150], 'Скрытый: +0.03 с к окну Преломления и Эхо +1 с',
                      _multi(_add('refraction_window_add', 0.03), _add('echo_duration_add', 1.0)), 3,
                      hidden=lambda d: d['stats'].get('refractions', 0) >= 150,
                      hidden_hint='Совершите 150 Преломлений', kind='hidden'),
    'h_swarm': _node('Жнец роя', 'MASTER', [120], 'Скрытый: цепные реакции от роя, +10% урона',
                     _mul('damage_mult', 1.1), 3, hidden=lambda d: d['stats']['codex'].get('swarm', 0) >= 300,
                     hidden_hint='Уничтожьте 300 врагов «Рой»', kind='hidden'),
    'hull_needle': _node('Заточка Иглы', 'MASTER', [80], 'Только с корпусом «Игла»: +12% урона',
                         _mul('damage_mult', 1.12), 4, hull='needle', kind='hull'),
    'hull_bastion': _node('Плиты Бастиона', 'MASTER', [80], 'Только с «Бастионом»: +20 HP, +10% волна BLUE',
                          _multi(_add('max_hp_add', 20), _add('blue_aoe_mult', 0.1)), 4, hull='bastion', kind='hull'),
    'hull_painter': _node('Кисть Художника', 'MASTER', [80], 'Только с «Художником»: краска бьёт врагов внутри',
                          _add('paint_radius_mult', 0.3), 4, hull='painter', kind='hull'),
    't_glass': _node('Хрупкий разгон', 'MASTER', [100], 'Переключаемый: +20% урона, но −20% HP (можно выключить)',
                     _multi(_mul('damage_mult', 1.2), _mul('max_hp_mult', 0.8)), 5, toggle=True, tradeoff=True,
                     kind='toggle'),
    'w_second_wind': _node('Второе дыхание', 'MASTER', [120], 'С 10-й волны забега: +15% урона и +10% скорости',
                           _multi(_mul('damage_mult', 1.15), lambda m, l: m.all_speed(1.1) if l else None), 5,
                           from_wave=10, kind='wave'),
    'g_veteran': _node('Ветеран', 'MASTER', [100], 'Растущий: +1% урона за каждые 500 убийств (макс. +10%)',
                       lambda m, l: None, 6, grow=('kills', 500, 0.01, 0.10), kind='grow'),
    'e_core': _node('Живой сплав', 'MASTER', [150, 200], '+10 HP за уровень. Эволюция: 3 победы над боссами — '
                    'ещё +1 щит', _add('max_hp_add', 10), 6,
                    evolve={'stat': 'bosses', 'goal': 3, 'name': 'Живой сплав II', 'effect': _add('shield_charges', 1)},
                    kind='evolve'),
})
NEW_IN_070 = {nid for nid in UPGRADES if nid.startswith(('violet_', 'x_', 'm_', 'h_', 'hull_', 't_', 'w_', 'g_', 'e_'))
              or nid in ('core_crit', 'core_shards', 'red_overload', 'blue_gravity', 'green_paint')}


def branch_spent(upgrades: Dict[str, int], branch: str) -> int:
    total = 0
    for nid, lvl in upgrades.items():
        node = UPGRADES.get(nid)
        if node and node['branch'] == branch:
            total += sum(node['costs'][:lvl])
    return total


def total_spent(upgrades: Dict[str, int]) -> int:
    return sum(branch_spent(upgrades, b) for b in BRANCHES)


def node_of_week(d: Optional[_dt.date] = None) -> str:
    """Узел недели: −30% цены (одинаковый у всех игроков)."""
    pool = sorted(nid for nid, n in UPGRADES.items() if n['kind'] in ('normal', 'bridge') and not n['key'])
    rng = random.Random(challenge_seed('weekly', d) + 17)
    return rng.choice(pool)


def node_cost(profile: 'Profile', nid: str, lvl: Optional[int] = None) -> int:
    """Нелинейная цена: базовая × (1 + 1% за каждый купленный уровень, не больше +40%), узел недели −30%."""
    node = UPGRADES[nid]
    lvl = profile.data['upgrades'].get(nid, 0) if lvl is None else lvl
    base = node['costs'][min(lvl, node['max'] - 1)]
    levels = sum(profile.data['upgrades'].values())
    k = 1.0 + min(0.4, 0.01 * levels)
    if nid == node_of_week():
        k *= 0.7
    return max(1, int(round(base * k)))


def node_visible(profile: 'Profile', nid: str) -> bool:
    h = UPGRADES[nid].get('hidden')
    if h is None or profile.data['upgrades'].get(nid, 0) > 0:
        return True
    try:
        return bool(h(profile.data))
    except (KeyError, TypeError):
        return False


def node_status(profile: 'Profile', nid: str) -> Tuple[str, str]:
    """Возвращает (статус, причина): maxed / hidden / locked / blocked / expensive / available."""
    node = UPGRADES[nid]
    ups = profile.data['upgrades']
    lvl = ups.get(nid, 0)
    if lvl >= node['max']:
        return 'maxed', 'Максимальный уровень'
    if not node_visible(profile, nid):
        return 'hidden', 'Скрытый узел: ' + (node.get('hidden_hint') or 'условие неизвестно')
    spent = branch_spent(ups, node['branch'])
    if spent < node['tier_cp']:
        return 'locked', f"Вложите в ветку ещё {node['tier_cp'] - spent} CP"
    if node.get('total_cp') and total_spent(ups) < node['total_cp']:
        return 'locked', f"Вложите в дерево всего ещё {node['total_cp'] - total_spent(ups)} CP"
    for req in node['requires']:
        if ups.get(req, 0) <= 0:
            return 'locked', f"Нужно: {UPGRADES[req]['name']}"
    if node.get('requires_any') and not any(ups.get(r, 0) > 0 for r in node['requires_any']):
        return 'locked', 'Нужно одно из: ' + ', '.join(UPGRADES[r]['name'] for r in node['requires_any'])
    if node['group']:
        for other, onode in UPGRADES.items():
            if other != nid and onode['group'] == node['group'] and ups.get(other, 0) > 0:
                return 'blocked', f"Взаимоисключает: {onode['name']}"
    cost = node_cost(profile, nid)
    if profile.cp < cost:
        return 'expensive', f"Нужно {cost} CP"
    return 'available', f"Цена: {cost} CP" + (' (узел недели −30%)' if nid == node_of_week() else '')


def preview_node(profile: 'Profile', nid: str) -> List[str]:
    """Предпросмотр: что изменится при покупке следующего уровня."""
    node = UPGRADES[nid]
    lvl = profile.data['upgrades'].get(nid, 0)
    before = RunMods()
    after = RunMods()
    node['effect'](before, lvl)
    node['effect'](after, min(node['max'], lvl + 1))
    lines = diff_mods(before, after)
    if node.get('from_wave'):
        lines.append(f"Действует с волны {node['from_wave']}")
    if node.get('hull'):
        lines.append(f"Только с корпусом «{HULLS.get(node['hull'], {}).get('name', node['hull'])}»")
    if node.get('grow'):
        stat, per, step, cap = node['grow']
        cur = min(cap, step * int(profile.data['stats'].get(stat, 0) // per))
        lines.append(f"Сейчас: +{cur * 100:.0f}% урона (до +{cap * 100:.0f}%)")
    if node.get('evolve'):
        ev = node['evolve']
        lines.append(f"Эволюция «{ev['name']}»: {profile.data['stats'].get(ev['stat'], 0)}/{ev['goal']}")
    return lines or ['Без численных изменений']


PRESTIGE_SPENT = 3000
PRESTIGE_CP_BONUS = 0.05

# Кап бонусов: чтобы стопка улучшений и артефактов не ломала игру
MOD_CAPS = {'damage_mult': (0.3, 3.0), 'fire_rate_mult': (0.4, 2.2), 'dash_cd_mult': (0.4, 2.0),
            'crit_add': (0.0, 0.35), 'pickup_radius_mult': (0.5, 3.0), 'powerup_chance_add': (0.0, 0.25),
            'refraction_window_add': (-0.1, 0.25), 'bullet_pierce': (0, 3), 'bullet_bounce': (0, 2),
            'shield_charges': (0, 5), 'revives': (0, 3)}


def apply_caps(m: RunMods) -> None:
    for k, (lo, hi) in MOD_CAPS.items():
        v = getattr(m, k)
        setattr(m, k, type(v)(max(lo, min(hi, v))))
    for mode in ALL_MODES:
        m.mode_damage_mult[mode] = max(0.3, min(2.5, m.mode_damage_mult[mode]))


MOD_LABELS = {'max_hp_add': 'Макс. HP', 'max_hp_mult': 'Множ. HP', 'damage_mult': 'Урон',
              'dash_cd_mult': 'Перезарядка рывка', 'refraction_window_add': 'Окно Преломления',
              'pickup_radius_mult': 'Радиус подбора', 'powerup_chance_add': 'Шанс бонуса',
              'fire_rate_mult': 'Скорострельность', 'invuln_time_mult': 'Неуязвимость',
              'impulse_duration_add': 'Длит. Импульса', 'impulse_threshold_add': 'Порог Импульса',
              'blue_aoe_mult': 'Радиус волны', 'resonance_radius_mult': 'Радиус Резонанса',
              'resonance_lifetime_add': 'Жизнь Резонанса', 'beat_window_add': 'Окно такта',
              'echo_duration_add': 'Длит. Эха', 'drift_mult': 'Дрейф', 'shield_charges': 'Щиты',
              'revives': 'Воскрешения', 'refraction_ricochet': 'Рикошеты', 'dash_speed_mult': 'Скорость рывка',
              'crit_add': 'Шанс крита', 'bullet_pierce': 'Пробивание', 'bullet_bounce': 'Отскоки',
              'violet_unlocked': 'Цвет VIOLET', 'shards_mult': 'Осколки', 'paint_chance_add': 'Шанс краски',
              'chain_damage_mult': 'Цепные реакции', 'overload_gain_mult': 'Набор перегрузки',
              'boss_damage_mult': 'Урон по боссам', 'skill_cd_mult': 'Перезарядка навыков',
              'mix_cd_mult': 'Перезарядка смешивания', 'phase_duration_add': 'Длит. фазы',
              'overload_duration_add': 'Длит. перегрузки', 'parry_touch_window_add': 'Окно парирования',
              'cp_mult': 'Множитель CP', 'enemy_damage_mult': 'Урон врагов', 'enemy_hp_mult': 'HP врагов'}


def diff_mods(a: RunMods, b: RunMods) -> List[str]:
    """Человекочитаемая разница модификаторов a → b (для предпросмотра, сборок и артефактов)."""
    lines = []
    da, db = a.to_dict(), b.to_dict()
    for k, v in db.items():
        if isinstance(v, dict):
            for mode, val in v.items():
                if abs(val - da[k].get(mode, 1.0)) > 1e-9:
                    lines.append(f"{k.replace('_mult', '').replace('_', ' ')} {mode}: ×{da[k].get(mode, 1.0):.2f} → ×{val:.2f}")
        elif v != da[k]:
            name = MOD_LABELS.get(k, k)
            if isinstance(v, bool):
                lines.append(f"{name}: {'включается' if v else 'выключается'}")
            elif isinstance(v, float) and 'mult' in k:
                lines.append(f"{name}: ×{da[k]:.2f} → ×{v:.2f}")
            elif isinstance(v, (int, float)):
                lines.append(f"{name}: {da[k]:g} → {v:g}")
    return lines


BUILD_PRESETS: Dict[str, Dict[str, Any]] = {
    'assault': {'name': 'Штурмовик', 'desc': 'RED, урон и Импульс',
                'upgrades': {'core_hp': 2, 'red_power': 3, 'red_thrust': 2, 'red_impulse': 2, 'red_trail': 1,
                             'core_crit': 2, 'red_chain': 1}},
    'control': {'name': 'Контролёр', 'desc': 'BLUE, волна и щиты',
                'upgrades': {'core_hp': 3, 'blue_power': 3, 'blue_aoe': 3, 'blue_anchor': 2, 'blue_shock': 1,
                             'core_shield': 1}},
    'dancer': {'name': 'Танцор', 'desc': 'GREEN, рывки и ритм',
               'upgrades': {'core_dash': 3, 'green_power': 2, 'green_flow': 3, 'green_groove': 2, 'green_echo': 1}},
    'parry': {'name': 'Преломитель', 'desc': 'Окно Преломления и отражённые пули',
              'upgrades': {'core_lens': 3, 'core_prism': 1, 'green_power': 1, 'green_flow': 1, 'green_groove': 2,
                           'green_homing': 1}},
    'phase': {'name': 'Фазовый', 'desc': 'Открытие VIOLET и пробивание',
              'upgrades': {'core_hp': 3, 'core_dash': 2, 'core_magnet': 2, 'violet_root': 1, 'violet_power': 2,
                           'violet_glide': 1}},
}


# =====================================================================
# КОРПУСА, МОДУЛИ, СИНЕРГИИ
# =====================================================================
HULLS: Dict[str, Dict[str, Any]] = {
    'prism': {'name': 'Призма', 'desc': 'Сбалансированный корпус', 'slots': 3, 'energy': 6, 'cost': 0, 'prisms': 0,
              'shape': 'circle', 'apply': lambda m: None},
    'needle': {'name': 'Игла', 'desc': '−20% HP, +10% скорости, −15% перезарядки рывка', 'slots': 3, 'energy': 5,
               'cost': 150, 'prisms': 1, 'shape': 'triangle',
               'apply': lambda m: (setattr(m, 'max_hp_mult', m.max_hp_mult * 0.8), m.all_speed(1.1),
                                   setattr(m, 'dash_cd_mult', m.dash_cd_mult * 0.85))},
    'bastion': {'name': 'Бастион', 'desc': '+30% HP, +1 щит, −10% скорости, 4 слота', 'slots': 4, 'energy': 7,
                'cost': 200, 'prisms': 2, 'shape': 'hex',
                'apply': lambda m: (setattr(m, 'max_hp_mult', m.max_hp_mult * 1.3), m.all_speed(0.9),
                                    setattr(m, 'shield_charges', m.shield_charges + 1))},
}

HULLS.update({
    'tank': {'name': 'Танк', 'desc': '+60% HP, −20% скорости, +20% волна BLUE, 4 слота', 'slots': 4, 'energy': 6,
             'cost': 260, 'prisms': 2, 'shape': 'hex',
             'apply': lambda m: (setattr(m, 'max_hp_mult', m.max_hp_mult * 1.6), m.all_speed(0.8),
                                 setattr(m, 'blue_aoe_mult', m.blue_aoe_mult * 1.2))},
    'ghost': {'name': 'Призрак', 'desc': '−30% HP, VIOLET открыт сразу, −30% перезарядки навыков', 'slots': 3,
              'energy': 5, 'cost': 240, 'prisms': 2, 'shape': 'diamond',
              'apply': lambda m: (setattr(m, 'max_hp_mult', m.max_hp_mult * 0.7), setattr(m, 'violet_unlocked', True),
                                  setattr(m, 'skill_cd_mult', m.skill_cd_mult * 0.7))},
    'painter': {'name': 'Художник', 'desc': '+15% шанс краски, краска шире на 40%, +10% урона в своей краске',
                'slots': 3, 'energy': 6, 'cost': 220, 'prisms': 1, 'shape': 'circle',
                'apply': lambda m: (setattr(m, 'paint_chance_add', m.paint_chance_add + 0.15),
                                    setattr(m, 'paint_radius_mult', m.paint_radius_mult * 1.4))},
})
HULL_CHALLENGES = {
    'prism': ('Дойдите до волны 15', 'best_wave', 15),
    'needle': ('Пройдите 5 волн без урона за забег', 'no_damage_waves', 5),
    'bastion': ('Победите босса', 'bosses', 1),
    'tank': ('Дойдите до волны 20', 'best_wave', 20),
    'ghost': ('Сделайте 300 убийств в VIOLET', 'kills_VIOLET', 300),
    'painter': ('Дойдите до волны 12', 'best_wave', 12),
}

MODULES: Dict[str, Dict[str, Any]] = {
    'twin': {'name': 'Двойной ствол', 'desc': '2 ствола, по 60% урона', 'energy': 3, 'cost': 120,
             'conflicts': [], 'apply': lambda m: setattr(m, 'twin_barrel', True)},
    'ricochet': {'name': 'Рикошетный блок', 'desc': '+1 рикошет отражённых пуль', 'energy': 2, 'cost': 80,
                 'conflicts': [], 'apply': lambda m: setattr(m, 'refraction_ricochet', m.refraction_ricochet + 1)},
    'magnet': {'name': 'Магнит', 'desc': '+50% радиус подбора', 'energy': 1, 'cost': 40,
               'conflicts': [], 'apply': lambda m: setattr(m, 'pickup_radius_mult', m.pickup_radius_mult + 0.5)},
    'capacitor': {'name': 'Конденсатор', 'desc': '+1 с Импульса', 'energy': 2, 'cost': 70,
                  'conflicts': [], 'apply': lambda m: setattr(m, 'impulse_duration_add', m.impulse_duration_add + 1.0)},
    'resonator': {'name': 'Резонатор', 'desc': '−1 убийство до Резонанса', 'energy': 3, 'cost': 110,
                  'conflicts': [], 'apply': lambda m: setattr(m, 'resonance_threshold_add', m.resonance_threshold_add - 1)},
    'lens': {'name': 'Линза', 'desc': '+0.03 с к окну Преломления', 'energy': 2, 'cost': 90,
             'conflicts': [], 'apply': lambda m: setattr(m, 'refraction_window_add', m.refraction_window_add + 0.03)},
    'shield_gen': {'name': 'Генератор щита', 'desc': '+1 заряд щита', 'energy': 3, 'cost': 120,
                   'conflicts': [], 'apply': lambda m: setattr(m, 'shield_charges', m.shield_charges + 1)},
    'overclock': {'name': 'Разгон', 'desc': '+15% скорострельности', 'energy': 2, 'cost': 80,
                  'conflicts': ['stabilizer'], 'apply': lambda m: setattr(m, 'fire_rate_mult', m.fire_rate_mult * 1.15)},
    'stabilizer': {'name': 'Стабилизатор', 'desc': '+30% неуязвимости после удара', 'energy': 1, 'cost': 50,
                   'conflicts': ['overclock'], 'apply': lambda m: setattr(m, 'invuln_time_mult', m.invuln_time_mult * 1.3)},
    'echo_amp': {'name': 'Усилитель эха', 'desc': '+1.5 с Эхо-камеры', 'energy': 2, 'cost': 70,
                 'conflicts': [], 'apply': lambda m: setattr(m, 'echo_duration_add', m.echo_duration_add + 1.5)},
    'groove': {'name': 'Грув-чип', 'desc': '+0.03 с окна такта; убийства в такт дают CP', 'energy': 1, 'cost': 60,
               'conflicts': [], 'apply': lambda m: (setattr(m, 'beat_window_add', m.beat_window_add + 0.03),
                                                    setattr(m, 'beat_groove', True))},
    'thrusters': {'name': 'Маневровые', 'desc': '−15% перезарядки рывка', 'energy': 2, 'cost': 70,
                  'conflicts': [], 'apply': lambda m: setattr(m, 'dash_cd_mult', m.dash_cd_mult * 0.85)},
}

SYNERGIES: List[Dict[str, Any]] = [
    {'modules': {'lens', 'ricochet'}, 'name': 'Призматическая сеть', 'desc': 'Отражённые пули пробивают',
     'apply': lambda m: setattr(m, 'refraction_pierce', True)},
    {'modules': {'capacitor', 'overclock'}, 'name': 'Перенапряжение', 'desc': '−1 убийство до Импульса',
     'apply': lambda m: setattr(m, 'impulse_threshold_add', m.impulse_threshold_add - 1)},
    {'modules': {'resonator', 'groove'}, 'name': 'Ритм-резонанс', 'desc': '+20% радиус Резонанса',
     'apply': lambda m: setattr(m, 'resonance_radius_mult', m.resonance_radius_mult * 1.2)},
    {'modules': {'shield_gen', 'stabilizer'}, 'name': 'Цитадель', 'desc': '+1 заряд щита',
     'apply': lambda m: setattr(m, 'shield_charges', m.shield_charges + 1)},
    {'modules': {'magnet', 'thrusters'}, 'name': 'Сборщик', 'desc': '+3% шанс бонуса',
     'apply': lambda m: setattr(m, 'powerup_chance_add', m.powerup_chance_add + 0.03)},
]


def loadout_energy(loadout: Dict[str, Any]) -> int:
    return sum(MODULES[m]['energy'] for m in loadout.get('modules', []) if m in MODULES)


def can_equip(loadout: Dict[str, Any], module_id: str) -> Tuple[bool, str]:
    hull = HULLS.get(loadout.get('hull'), HULLS['prism'])
    mods = loadout.get('modules', [])
    if module_id in mods:
        return True, ''
    if len(mods) >= hull['slots']:
        return False, 'Нет свободных слотов'
    if loadout_energy(loadout) + MODULES[module_id]['energy'] > hull['energy']:
        return False, 'Не хватает энергии'
    for other in mods:
        if other in MODULES[module_id]['conflicts'] or module_id in MODULES[other]['conflicts']:
            return False, f"Несовместим с «{MODULES[other]['name']}»"
    return True, ''


def active_synergies(modules: List[str]) -> List[Dict[str, Any]]:
    s = set(modules)
    return [syn for syn in SYNERGIES if syn['modules'] <= s]


# =====================================================================
# АРТЕФАКТЫ (выбор 1 из 3 каждые ARTIFACT_WAVE_INTERVAL волн)
# =====================================================================
ARTIFACTS: Dict[str, Dict[str, Any]] = {
    'red_core': {'name': 'Алое ядро', 'desc': '+20% урона в RED', 'arch': 'assault',
                 'apply': lambda m: m.mode_damage_mult.__setitem__('RED', m.mode_damage_mult['RED'] * 1.2)},
    'cobalt': {'name': 'Кобальтовый якорь', 'desc': '+30% радиус волны BLUE', 'arch': 'control',
               'apply': lambda m: setattr(m, 'blue_aoe_mult', m.blue_aoe_mult * 1.3)},
    'verdant': {'name': 'Изумрудный вихрь', 'desc': '+12% скорости GREEN', 'arch': 'dancer',
                'apply': lambda m: m.max_speed_mult.__setitem__('GREEN', m.max_speed_mult['GREEN'] * 1.12)},
    'mirror': {'name': 'Зеркальная грань', 'desc': '+0.04 с к окну Преломления', 'arch': 'parry',
               'apply': lambda m: setattr(m, 'refraction_window_add', m.refraction_window_add + 0.04)},
    'splinter': {'name': 'Осколок', 'desc': '+1 рикошет отражённых пуль', 'arch': 'parry',
                 'apply': lambda m: setattr(m, 'refraction_ricochet', m.refraction_ricochet + 1)},
    'seeker': {'name': 'Око искателя', 'desc': 'Отражённые пули наводятся', 'arch': 'parry', 'unique': True,
               'apply': lambda m: setattr(m, 'refraction_homing', True)},
    'metronome': {'name': 'Метроном', 'desc': '+0.03 с к окну такта', 'arch': 'dancer',
                  'apply': lambda m: setattr(m, 'beat_window_add', m.beat_window_add + 0.03)},
    'adrenaline': {'name': 'Адреналин', 'desc': '+15% скорострельности', 'arch': 'assault',
                   'apply': lambda m: setattr(m, 'fire_rate_mult', m.fire_rate_mult * 1.15)},
    'bulwark': {'name': 'Броневставка', 'desc': '+25 к макс. HP', 'arch': 'any',
                'apply': lambda m: setattr(m, 'max_hp_add', m.max_hp_add + 25)},
    'aegis': {'name': 'Эгида', 'desc': '+1 заряд щита', 'arch': 'any',
              'apply': lambda m: setattr(m, 'shield_charges', m.shield_charges + 1)},
    'phoenix': {'name': 'Перо феникса', 'desc': '+1 воскрешение', 'arch': 'any', 'unique': True, 'weight': 0.4,
                'apply': lambda m: setattr(m, 'revives', m.revives + 1)},
    'capacitor': {'name': 'Накопитель', 'desc': '+1.5 с Импульса', 'arch': 'assault',
                  'apply': lambda m: setattr(m, 'impulse_duration_add', m.impulse_duration_add + 1.5)},
    'tuning_fork': {'name': 'Камертон', 'desc': '−1 Преломление до Эха, +1 с Эха', 'arch': 'parry',
                    'apply': lambda m: (setattr(m, 'echo_threshold_add', m.echo_threshold_add - 1),
                                        setattr(m, 'echo_duration_add', m.echo_duration_add + 1.0))},
    'bloom': {'name': 'Цветение', 'desc': '−1 убийство до Резонанса', 'arch': 'control',
              'apply': lambda m: setattr(m, 'resonance_threshold_add', m.resonance_threshold_add - 1)},
    'halo': {'name': 'Ореол', 'desc': '+25% радиус и +2 с Резонанса', 'arch': 'control',
             'apply': lambda m: (setattr(m, 'resonance_radius_mult', m.resonance_radius_mult * 1.25),
                                 setattr(m, 'resonance_lifetime_add', m.resonance_lifetime_add + 2.0))},
    'quickstep': {'name': 'Лёгкий шаг', 'desc': '−20% перезарядки рывка', 'arch': 'dancer',
                  'apply': lambda m: setattr(m, 'dash_cd_mult', m.dash_cd_mult * 0.8)},
    'glass_heart': {'name': 'Стеклянное сердце', 'desc': '+30% урона, −20% макс. HP', 'arch': 'assault',
                    'apply': lambda m: (setattr(m, 'damage_mult', m.damage_mult * 1.3),
                                        setattr(m, 'max_hp_mult', m.max_hp_mult * 0.8))},
    'greed': {'name': 'Алчность', 'desc': '+25% CP, враги бьют на 10% сильнее', 'arch': 'any',
              'apply': lambda m: (setattr(m, 'cp_mult', m.cp_mult + 0.25),
                                  setattr(m, 'enemy_damage_mult', m.enemy_damage_mult * 1.1))},
    'prism_shard': {'name': 'Призменный осколок', 'desc': 'Отражённые пули пробивают', 'arch': 'parry', 'unique': True,
                    'apply': lambda m: setattr(m, 'refraction_pierce', True)},
    'graviton': {'name': 'Гравитон', 'desc': '+50% радиус подбора, +4% шанс бонуса', 'arch': 'any',
                 'apply': lambda m: (setattr(m, 'pickup_radius_mult', m.pickup_radius_mult + 0.5),
                                     setattr(m, 'powerup_chance_add', m.powerup_chance_add + 0.04))},
    'twins': {'name': 'Близнецы', 'desc': 'Двойной ствол', 'arch': 'assault', 'unique': True,
              'apply': lambda m: setattr(m, 'twin_barrel', True)},
    'ember': {'name': 'Тлеющий уголь', 'desc': 'Рывок оставляет огненный след', 'arch': 'assault', 'unique': True,
              'apply': lambda m: setattr(m, 'red_dash_trail', True)},
    'afterimage': {'name': 'Мираж', 'desc': 'Рывок оставляет приманку', 'arch': 'dancer', 'unique': True,
                   'apply': lambda m: setattr(m, 'green_afterimage', True)},
}


ARTIFACTS.update({
    # Легендарные: редкие и мощные
    'spectrum_heart': {'name': 'Сердце спектра', 'desc': '+25% урона всеми цветами, +1 щит', 'arch': 'any',
                       'rarity': 'legendary', 'unique': True, 'weight': 0.25,
                       'apply': lambda m: (setattr(m, 'damage_mult', m.damage_mult * 1.25),
                                           setattr(m, 'shield_charges', m.shield_charges + 1))},
    'violet_key': {'name': 'Аметистовый ключ', 'desc': 'Открывает VIOLET на этот забег, +10% урона VIOLET',
                   'arch': 'any', 'rarity': 'legendary', 'unique': True, 'weight': 0.3,
                   'apply': lambda m: (setattr(m, 'violet_unlocked', True),
                                       m.mode_damage_mult.__setitem__('VIOLET', m.mode_damage_mult['VIOLET'] * 1.1))},
    'drill_core': {'name': 'Буровое ядро', 'desc': 'Все пули пробивают +1 врага', 'arch': 'assault',
                   'rarity': 'legendary', 'unique': True, 'weight': 0.3,
                   'apply': lambda m: setattr(m, 'bullet_pierce', m.bullet_pierce + 1)},
    # Проклятые: сильный плюс и ощутимый минус
    'blood_prism': {'name': 'Кровавая призма', 'desc': 'Проклятый: +45% урона, но лечение отключено', 'arch': 'assault',
                    'rarity': 'cursed', 'unique': True, 'weight': 0.4,
                    'apply': lambda m: (setattr(m, 'damage_mult', m.damage_mult * 1.45), setattr(m, 'no_heal', True))},
    'void_lens': {'name': 'Линза пустоты', 'desc': 'Проклятый: +0.06 с окна Преломления, враги +20% HP',
                  'arch': 'parry', 'rarity': 'cursed', 'unique': True, 'weight': 0.4,
                  'apply': lambda m: (setattr(m, 'refraction_window_add', m.refraction_window_add + 0.06),
                                      setattr(m, 'enemy_hp_mult', m.enemy_hp_mult * 1.2))},
    'gambler': {'name': 'Кость игрока', 'desc': 'Проклятый: +10% шанс крита, −20% макс. HP', 'arch': 'any',
                'rarity': 'cursed', 'unique': True, 'weight': 0.4,
                'apply': lambda m: (setattr(m, 'crit_add', m.crit_add + 0.10), setattr(m, 'max_hp_mult', m.max_hp_mult * 0.8))},
    # Набор «Триада»: 3 предмета → бонус
    'triad_red': {'name': 'Триада: алый осколок', 'desc': '+8% урона RED. Набор «Триада» (3 шт.)', 'arch': 'any',
                  'set': 'triad', 'unique': True,
                  'apply': lambda m: m.mode_damage_mult.__setitem__('RED', m.mode_damage_mult['RED'] * 1.08)},
    'triad_blue': {'name': 'Триада: синий осколок', 'desc': '+8% урона BLUE. Набор «Триада» (3 шт.)', 'arch': 'any',
                   'set': 'triad', 'unique': True,
                   'apply': lambda m: m.mode_damage_mult.__setitem__('BLUE', m.mode_damage_mult['BLUE'] * 1.08)},
    'triad_green': {'name': 'Триада: зелёный осколок', 'desc': '+8% урона GREEN. Набор «Триада» (3 шт.)', 'arch': 'any',
                    'set': 'triad', 'unique': True,
                    'apply': lambda m: m.mode_damage_mult.__setitem__('GREEN', m.mode_damage_mult['GREEN'] * 1.08)},
})
ARTIFACT_SETS = {
    'triad': {'name': 'Триада', 'need': 3, 'desc': 'Полный набор: цепные реакции ×2 и +15% урона',
              'apply': lambda m: (setattr(m, 'chain_damage_mult', m.chain_damage_mult * 2.0),
                                  setattr(m, 'damage_mult', m.damage_mult * 1.15))},
}
RARITY_NAMES = {'common': 'Обычный', 'legendary': 'Легендарный', 'cursed': 'Проклятый'}


def completed_sets(owned: List[str]) -> List[str]:
    out = []
    for sid, sd in ARTIFACT_SETS.items():
        if sum(1 for a in owned if ARTIFACTS.get(a, {}).get('set') == sid) >= sd['need']:
            out.append(sid)
    return out


def artifact_preview(mods: RunMods, aid: str) -> List[str]:
    """Сравнение статов «до → после» для экрана выбора артефакта."""
    after = copy.deepcopy(mods)
    ARTIFACTS[aid]['apply'](after)
    return diff_mods(mods, after)

def roll_artifacts(rng: random.Random, archetype: str, owned: List[str], count: int = 3) -> List[str]:
    """Взвешенный выбор: артефакты под стиль игрока выпадают в 2.5 раза чаще."""
    pool = [a for a, d in ARTIFACTS.items() if not (d.get('unique') and a in owned)]
    picks: List[str] = []
    while pool and len(picks) < count:
        weights = []
        for a in pool:
            d = ARTIFACTS[a]
            w = d.get('weight', 1.0)
            if d['arch'] == archetype:
                w *= 2.5
            elif d['arch'] == 'any':
                w *= 1.2
            weights.append(w)
        choice = rng.choices(pool, weights=weights, k=1)[0]
        picks.append(choice)
        pool.remove(choice)
    return picks


# =====================================================================
# НАПРЯЖЕНИЕ, РИСКИ, СЛОЖНОСТЬ
# =====================================================================
TENSION_LEVELS: List[Dict[str, Any]] = [
    {'desc': 'Базовая игра'},
    {'desc': 'Враги +8% HP'},
    {'desc': 'Враги бьют на 6% сильнее'},
    {'desc': 'Элиты появляются чаще'},
    {'desc': 'Бюджет волн +10%'},
    {'desc': 'Телеграф спавна короче'},
    {'desc': 'Пули врагов быстрее на 10%'},
    {'desc': 'Окно Преломления −10%'},
    {'desc': 'Бюджет волн +20%'},
    {'desc': 'Враги быстрее на 8%'},
    {'desc': 'Хроматический предел'},
]


def apply_tension(m: RunMods, level: int) -> None:
    level = max(0, min(10, level))
    if level <= 0:
        return
    m.enemy_hp_mult *= 1 + 0.08 * level
    if level >= 2:
        m.enemy_damage_mult *= 1 + 0.06 * (level - 1)
    if level >= 3:
        m.elite_chance_add += 0.05
    if level >= 4:
        m.budget_mult *= 1.10
    if level >= 5:
        m.telegraph_add -= 0.2
    if level >= 6:
        m.enemy_bullet_speed_mult *= 1.10
    if level >= 7:
        m.refraction_window_mult *= 0.9
    if level >= 8:
        m.budget_mult *= 1.2
    if level >= 9:
        m.enemy_speed_mult *= 1.08
    if level >= 10:
        m.elite_chance_add += 0.1
    m.cp_mult += 0.10 * level
    m.sources.append(f"Напряжение {level}")


RISKS: Dict[str, Dict[str, Any]] = {
    'fragile': {'name': 'Хрупкость', 'desc': '−40% макс. HP', 'cp': 0.25,
                'apply': lambda m: setattr(m, 'max_hp_mult', m.max_hp_mult * 0.6)},
    'squall': {'name': 'Шквал', 'desc': 'Пули врагов на 25% быстрее', 'cp': 0.20,
               'apply': lambda m: setattr(m, 'enemy_bullet_speed_mult', m.enemy_bullet_speed_mult * 1.25)},
    'hunger': {'name': 'Голод', 'desc': 'Нет лечения', 'cp': 0.20,
               'apply': lambda m: setattr(m, 'no_heal', True)},
    'horde': {'name': 'Орда', 'desc': 'Бюджет волн +30%', 'cp': 0.25,
              'apply': lambda m: setattr(m, 'budget_mult', m.budget_mult * 1.3)},
    'heavy': {'name': 'Тяжёлые враги', 'desc': 'Враги +30% HP', 'cp': 0.20,
              'apply': lambda m: setattr(m, 'enemy_hp_mult', m.enemy_hp_mult * 1.3)},
    'blind': {'name': 'Узкая грань', 'desc': 'Окно Преломления −30%', 'cp': 0.20,
              'apply': lambda m: setattr(m, 'refraction_window_mult', m.refraction_window_mult * 0.7)},
}
RISKS.update({
    'eclipse': {'name': 'Затмение', 'desc': 'Каждая волна — тёмная', 'cp': 0.20,
                'apply': lambda m: setattr(m, 'always_dark', True)},
    'swarming': {'name': 'Рой', 'desc': 'Роёв вдвое больше', 'cp': 0.15,
                 'apply': lambda m: setattr(m, 'swarm_mult', m.swarm_mult * 2.0)},
    'unstable': {'name': 'Нестабильность', 'desc': 'Каждые 20 с цвет меняется сам', 'cp': 0.20,
                 'apply': lambda m: setattr(m, 'unstable_colors', True)},
    'glass': {'name': 'Стекло', 'desc': 'Любой удар отнимает минимум 25 HP', 'cp': 0.30,
              'apply': lambda m: setattr(m, 'glass_mode', True)},
})
# Орда 0.7.0: действительно много врагов
RISKS['horde'] = {'name': 'Орда', 'desc': f"Бюджет волн ×{CFG.HORDE_BUDGET_MULT:g}, короткие паузы, больше роёв",
                  'cp': 0.30, 'apply': lambda m: (setattr(m, 'budget_mult', m.budget_mult * CFG.HORDE_BUDGET_MULT),
                                                  setattr(m, 'swarm_mult', m.swarm_mult * 1.5))}

DIFFICULTIES: Dict[str, Dict[str, Any]] = {
    'story': {'name': 'Сюжет', 'enemy_hp': 0.8, 'enemy_damage': 0.6, 'enemy_speed': 0.9, 'refraction_window': 1.4, 'cp': 0.7},
    'normal': {'name': 'Норма', 'enemy_hp': 1.0, 'enemy_damage': 1.0, 'enemy_speed': 1.0, 'refraction_window': 1.0, 'cp': 1.0},
    'master': {'name': 'Мастер', 'enemy_hp': 1.2, 'enemy_damage': 1.3, 'enemy_speed': 1.1, 'refraction_window': 0.8, 'cp': 1.3},
    'custom': {'name': 'Своя', 'cp': 1.0},
}


def apply_difficulty(m: RunMods, settings: Any) -> None:
    key = settings.get('difficulty', 'normal') if settings is not None else 'normal'
    d = dict(DIFFICULTIES.get(key, DIFFICULTIES['normal']))
    if key == 'custom':
        c = settings.get('custom_difficulty', {})
        d.update({k: float(c.get(k, 1.0)) for k in ('enemy_hp', 'enemy_damage', 'enemy_speed', 'refraction_window')})
        harder = (d['enemy_hp'] + d['enemy_damage'] + d['enemy_speed'] + 1 / max(0.3, d['refraction_window'])) / 4
        d['cp'] = max(0.5, min(1.4, harder))
    m.enemy_hp_mult *= d['enemy_hp']
    m.enemy_damage_mult *= d['enemy_damage']
    m.enemy_speed_mult *= d['enemy_speed']
    m.refraction_window_mult *= d['refraction_window']
    m.cp_mult *= d['cp']
    phys = settings.get('physics', {}) if settings is not None else {}
    for mode in MODES:
        k = float(phys.get(mode, 1.0))
        k = max(0.8, min(1.2, k))  # тонкая настройка физики ±20%
        m.max_speed_mult[mode] *= k
        m.accel_mult[mode] *= k


# =====================================================================
# ДОСТИЖЕНИЯ, КОСМЕТИКА, КОНТРАКТЫ
# =====================================================================
COSMETICS = {
    'ship_shape': {'circle': 'Сфера', 'triangle': 'Стрела', 'diamond': 'Ромб', 'hex': 'Сота'},
    'trail_style': {'mode': 'Цвет режима', 'white': 'Белый', 'gold': 'Золото', 'rainbow': 'Радуга'},
    'title': {'': 'Без титула', 'Новичок': 'Новичок', 'Преломитель': 'Преломитель', 'Дирижёр': 'Дирижёр',
              'Охотник на прайма': 'Охотник на прайма', 'Хромант': 'Хромант', 'Танцор': 'Танцор'},
}
DEFAULT_COSMETICS = ['ship_shape:circle', 'trail_style:mode', 'title:']


def _s(key: str) -> Callable[[Dict[str, Any], Dict[str, Any]], float]:
    return lambda p, r: p['stats'].get(key, 0)


def _r(key: str) -> Callable[[Dict[str, Any], Dict[str, Any]], float]:
    return lambda p, r: (r or {}).get(key, 0)


# (id, название, описание, функция значения, цель, награда CP, косметика)
ACHIEVEMENTS: List[Tuple[str, str, str, Callable, float, int, Optional[str]]] = [
    ('first_run', 'Первый свет', 'Завершите первый забег', _s('runs'), 1, 10, 'title:Новичок'),
    ('runs_10', 'Постоянство', 'Сыграйте 10 забегов', _s('runs'), 10, 30, None),
    ('runs_50', 'Ветеран спектра', 'Сыграйте 50 забегов', _s('runs'), 50, 80, None),
    ('wave_5', 'Разогрев', 'Дойдите до волны 5', _s('best_wave'), 5, 15, None),
    ('wave_10', 'Десятка', 'Дойдите до волны 10', _s('best_wave'), 10, 40, 'ship_shape:diamond'),
    ('wave_15', 'Глубже', 'Дойдите до волны 15', _s('best_wave'), 15, 60, None),
    ('wave_20', 'Двадцатка', 'Дойдите до волны 20', _s('best_wave'), 20, 100, 'trail_style:gold'),
    ('wave_30', 'За гранью', 'Дойдите до волны 30', _s('best_wave'), 30, 200, 'title:Хромант'),
    ('kills_100', 'Сотня', 'Уничтожьте 100 врагов', _s('kills'), 100, 15, None),
    ('kills_1000', 'Тысяча', 'Уничтожьте 1000 врагов', _s('kills'), 1000, 60, None),
    ('kills_5000', 'Лавина', 'Уничтожьте 5000 врагов', _s('kills'), 5000, 150, None),
    ('red_200', 'Алый натиск', '200 убийств в RED', lambda p, r: p['stats']['mode_kills'].get('RED', 0), 200, 30, None),
    ('blue_200', 'Синий якорь', '200 убийств в BLUE', lambda p, r: p['stats']['mode_kills'].get('BLUE', 0), 200, 30, None),
    ('green_200', 'Зелёный поток', '200 убийств в GREEN', lambda p, r: p['stats']['mode_kills'].get('GREEN', 0), 200, 30, None),
    ('refract_1', 'Первое Преломление', 'Отразите пулю', _s('refractions'), 1, 10, None),
    ('refract_100', 'Призматик', '100 Преломлений', _s('refractions'), 100, 50, 'title:Преломитель'),
    ('refract_run_15', 'Зеркальный забег', '15 Преломлений за забег', _r('refractions'), 15, 40, None),
    ('echo_1', 'Эхо', 'Включите Эхо-камеру', _s('echoes'), 1, 15, None),
    ('impulse_1', 'Импульс', 'Получите Импульс', _s('impulses'), 1, 15, None),
    ('resonance_25', 'Резонатор', 'Создайте 25 Резонансов', _s('resonances'), 25, 30, None),
    ('beat_50', 'В ритме', '50 убийств в такт', _s('beat_kills'), 50, 30, 'title:Дирижёр'),
    ('beat_run_30', 'Метроном', '30 убийств в такт за забег', _r('beat_kills'), 30, 40, None),
    ('boss_1', 'Прайм повержен', 'Победите Диссонанс-Прайм', _s('bosses'), 1, 50, 'title:Охотник на прайма'),
    ('boss_5', 'Гроза праймов', 'Победите 5 боссов', _s('bosses'), 5, 120, None),
    ('elite_25', 'Охота на элиту', 'Уничтожьте 25 элит', _s('elites'), 25, 40, None),
    ('dissonance_10', 'Гармония', 'Уничтожьте 10 Диссонансов', lambda p, r: p['stats']['codex'].get('dissonance', 0), 10, 30, None),
    ('nodmg_3', 'Неприкасаемый', '3 волны без урона за забег', _r('no_damage_waves'), 3, 30, None),
    ('nodmg_10', 'Призрак', '10 волн без урона за забег', _r('no_damage_waves'), 10, 80, 'ship_shape:triangle'),
    ('combo_30', 'Комбо 30', 'Комбо 30', _r('max_combo'), 30, 25, None),
    ('combo_75', 'Комбо 75', 'Комбо 75', _r('max_combo'), 75, 60, None),
    ('score_25k', '25 000', 'Наберите 25 000 очков', _s('best_score'), 25000, 30, None),
    ('score_100k', '100 000', 'Наберите 100 000 очков', _s('best_score'), 100000, 100, 'trail_style:rainbow'),
    ('dash_500', 'Танцор', '500 рывков', _s('dashes'), 500, 40, 'title:Танцор'),
    ('switch_1000', 'Хамелеон', '1000 смен цвета', _s('switches'), 1000, 40, 'trail_style:white'),
    ('daily_1', 'Ежедневник', 'Пройдите ежедневное испытание', _s('daily_runs'), 1, 20, None),
    ('weekly_1', 'Неделя спектра', 'Пройдите еженедельное испытание', _s('weekly_runs'), 1, 30, None),
    ('tension_3', 'Напряжение III', 'Дойдите до волны 10 на напряжении 3+', _s('tension_cleared'), 3, 60, None),
    ('tension_7', 'Напряжение VII', 'Дойдите до волны 10 на напряжении 7+', _s('tension_cleared'), 7, 150, 'ship_shape:hex'),
    ('pure_10', 'Чистый спектр', 'Волна 10 в Чистом режиме', _s('pure_best_wave'), 10, 80, None),
    ('upgrades_10', 'Инженер', 'Купите 10 уровней улучшений', lambda p, r: sum(p['upgrades'].values()), 10, 40, None),
    ('artifacts_10', 'Коллекционер', 'Возьмите 10 артефактов', _s('artifacts'), 10, 30, None),
    ('contracts_10', 'Наёмник', 'Выполните 10 контрактов', _s('contracts_done'), 10, 50, None),
]
ACHIEVEMENTS += [
    ('violet_100', 'Фиолетовая фаза', '100 убийств в VIOLET', lambda p, r: p['stats']['mode_kills'].get('VIOLET', 0), 100, 40, None),
    ('warden_1', 'Страж повержен', 'Победите мини-босса', lambda p, r: p['stats']['codex'].get('warden', 0), 1, 30, None),
    ('hydra_1', 'Три головы', 'Победите Хроматическую Гидру', _s('hydra_kills'), 1, 80, None),
    ('spectrum_1', 'Абсолютный Спектр', 'Победите финального босса', _s('spectrum_kills'), 1, 150, 'title:Спектр'),
    ('victory_1', 'Победа', 'Пройдите 30 волн стандартного забега', _s('victories'), 1, 200, 'trail_style:rainbow'),
    ('swarm_500', 'Против роя', 'Уничтожьте 500 врагов «Рой»', lambda p, r: p['stats']['codex'].get('swarm', 0), 500, 40, None),
    ('vortex_10', 'Вихрь', '10 раз запустите Хроматический вихрь', _s('vortexes'), 10, 30, None),
    ('parry_touch_20', 'Касание', '20 парирований касанием', _s('touch_parries'), 20, 30, None),
    ('chain_50', 'Цепная реакция', '50 цепных реакций', _s('chains'), 50, 30, None),
    ('precise_200', 'Точность', '200 «точных» убийств', _s('precise_kills'), 200, 40, None),
    ('absorb_100', 'Поглотитель', 'Поглотите 100 цветных пуль', _s('absorbed'), 100, 30, None),
    ('horde_15', 'Орда', 'Дойдите до волны 15 с риском «Орда»', _s('horde_best_wave'), 15, 80, None),
    ('blitz_50k', 'Блиц', 'Наберите 50 000 очков в Блице', _s('blitz_best'), 50000, 60, None),
    ('bossrush_1', 'Босс-раш', 'Пройдите Босс-раш', _s('bossrush_clears'), 1, 120, None),
    ('shop_10', 'Покупатель', 'Купите 10 вещей в магазине забега', _s('shop_buys'), 10, 20, None),
    ('trial_all', 'Ученик цвета', 'Пройдите все испытания тренировки', lambda p, r: len(p.get('trials_done', [])), 5, 50, None),
    ('prestige_1', 'Престиж', 'Получите престиж дерева', lambda p, r: p.get('prestige', 0), 1, 0, None),
    ('gamble_5', 'Азарт', 'Выиграйте 5 ставок на волну', _s('gambles_won'), 5, 30, None),
]
ACH_BY_ID = {a[0]: a for a in ACHIEVEMENTS}
COSMETICS['title']['Спектр'] = 'Спектр'

CONTRACT_TEMPLATES: List[Tuple[str, str, str, int, int]] = [
    # (id, описание, ключ статистики забега, цель, награда)
    ('kills_red', 'Уничтожьте {n} врагов в RED', 'kills_RED', 60, 25),
    ('kills_blue', 'Уничтожьте {n} врагов в BLUE', 'kills_BLUE', 60, 25),
    ('kills_green', 'Уничтожьте {n} врагов в GREEN', 'kills_GREEN', 60, 25),
    ('refract', 'Совершите {n} Преломлений', 'refractions', 12, 30),
    ('beat', 'Уничтожьте {n} врагов в такт', 'beat_kills', 25, 25),
    ('waves', 'Пройдите {n} волн суммарно', 'waves_cleared', 15, 25),
    ('nodmg', 'Пройдите {n} волн без урона', 'no_damage_waves', 4, 30),
    ('elites', 'Уничтожьте {n} элит', 'elites', 6, 30),
    ('dashes', 'Сделайте {n} рывков', 'dashes', 80, 20),
    ('resonance', 'Создайте {n} Резонансов', 'resonances', 8, 25),
    ('kills_violet', 'Уничтожьте {n} врагов в VIOLET', 'kills_VIOLET', 40, 30),
    ('precise', 'Сделайте {n} «точных» убийств', 'precise_kills', 30, 25),
    ('absorb', 'Поглотите {n} цветных пуль', 'absorbed', 15, 25),
]
WEEKLY_CONTRACT_TEMPLATES: List[Tuple[str, str, str, int, int]] = [
    ('w_kills', 'За неделю уничтожьте {n} врагов', 'kills', 1500, 120),
    ('w_waves', 'За неделю пройдите {n} волн', 'waves_cleared', 80, 120),
    ('w_bosses', 'За неделю победите {n} боссов', 'bosses', 3, 150),
    ('w_refract', 'За неделю совершите {n} Преломлений', 'refractions', 100, 120),
    ('w_chains', 'За неделю устройте {n} цепных реакций', 'chains', 60, 100),
    ('w_swarm', 'За неделю уничтожьте {n} врагов «Рой» (по кодексу)', 'swarm_kills', 400, 100),
]
DAILY_RULES = {
    'none': ('Без особого правила', ''),
    'swarm_day': ('День роя', 'Роёв вдвое больше'),
    'violet_day': ('Фиолетовый день', 'VIOLET открыт для всех'),
    'glass_day': ('Стеклянный день', '+30% урона, −30% HP'),
    'rush_day': ('День спешки', 'Короткие паузы между волнами'),
    'crit_day': ('День удачи', '+10% шанс крита'),
}


def date_key(d: Optional[_dt.date] = None) -> str:
    return (d or _dt.date.today()).isoformat()


def week_key(d: Optional[_dt.date] = None) -> str:
    y, w, _ = (d or _dt.date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def challenge_seed(kind: str, d: Optional[_dt.date] = None) -> int:
    key = date_key(d) if kind == 'daily' else week_key(d)
    return sum((i + 1) * ord(c) for i, c in enumerate(kind + key)) * 7919 % 2_147_483_647


def challenge_setup(kind: str, d: Optional[_dt.date] = None) -> Dict[str, Any]:
    """Одинаковые для всех условия: арена, риски, стартовый цвет — из seed по дате/неделе."""
    rng = random.Random(challenge_seed(kind, d))
    risks = rng.sample(sorted(RISKS), 1 if kind == 'daily' else 2)
    rule = rng.choice(sorted(r for r in DAILY_RULES if r != 'none'))
    return {'seed': challenge_seed(kind, d), 'arena': rng.choice(['classic', 'pillars', 'prism', 'portals']),
            'risks': risks, 'start_mode': rng.choice(MODES), 'tension': 0 if kind == 'daily' else 2,
            'key': date_key(d) if kind == 'daily' else week_key(d), 'rule': rule}


def apply_daily_rule(m: RunMods, rule: str) -> None:
    if rule == 'swarm_day':
        m.swarm_mult *= 2.0
    elif rule == 'violet_day':
        m.violet_unlocked = True
    elif rule == 'glass_day':
        m.damage_mult *= 1.3
        m.max_hp_mult *= 0.7
    elif rule == 'crit_day':
        m.crit_add += 0.10
    if rule in DAILY_RULES and rule != 'none':
        m.sources.append(f"Правило дня «{DAILY_RULES[rule][0]}»")


# =====================================================================
# ПРОФИЛЬ
# =====================================================================
def default_loadout(i: int) -> Dict[str, Any]:
    return {'name': f'Пресет {i + 1}', 'hull': 'prism', 'modules': []}


def default_profile(name: str = 'Пилот') -> Dict[str, Any]:
    return {
        'version': SAVE_VERSION, 'game_version': GAME_VERSION, 'name': name,
        'created': date_key(), 'cp': 0, 'prisms': 0, 'cp_earned_total': 0,
        'upgrades': {}, 'legacy_migrated': False,
        'hulls': ['prism'], 'modules': [], 'loadouts': [default_loadout(i) for i in range(3)], 'active_loadout': 0,
        'stats': {'runs': 0, 'kills': 0, 'best_wave': 0, 'best_score': 0, 'refractions': 0, 'refraction_fails': 0,
                  'echoes': 0, 'impulses': 0, 'resonances': 0, 'beat_kills': 0, 'bosses': 0, 'elites': 0,
                  'dashes': 0, 'switches': 0, 'play_time': 0.0, 'daily_runs': 0, 'weekly_runs': 0,
                  'tension_cleared': -1, 'pure_best_wave': 0, 'artifacts': 0, 'contracts_done': 0,
                  'mode_kills': {m: 0 for m in ALL_MODES}, 'mode_time': {m: 0.0 for m in ALL_MODES},
                  'codex': {}, 'deaths_by': {}, 'waves_cleared': 0,
                  'hydra_kills': 0, 'spectrum_kills': 0, 'victories': 0, 'vortexes': 0, 'touch_parries': 0,
                  'chains': 0, 'precise_kills': 0, 'absorbed': 0, 'horde_best_wave': 0, 'blitz_best': 0,
                  'bossrush_clears': 0, 'shop_buys': 0, 'gambles_won': 0, 'endless_best_wave': 0},
        'records': {}, 'history': [], 'leaderboard': [],
        'achievements': {}, 'cosmetics': {'ship_shape': 'circle', 'trail_style': 'mode', 'title': ''},
        'unlocked_cosmetics': list(DEFAULT_COSMETICS),
        'contracts': {'date': '', 'list': []},
        'daily': {'key': '', 'best': 0, 'claimed_first': ''}, 'weekly': {'key': '', 'best': 0},
        'tension_unlocked': 0, 'ghost': {'score': 0, 'wave_times': []},
        'death_streak': 0, 'assist_declined': False, 'seen_tips': [], 'archetype': 'balanced',
        'last_first_run_day': '',
        # 0.7.0
        'builds': [None, None, None], 'disabled_nodes': [], 'node_paid': {}, 'seen_nodes': [],
        'last_free_reset': '', 'prestige': 0, 'node_stats': {}, 'hull_stats': {}, 'hull_challenges': [],
        'weekly_contracts': {'week': '', 'list': []}, 'trials_done': [], 'seen_enemies': [],
        'codex_seen': [], 'victory_seen': False,
    }


def _deep_fill(target: Dict[str, Any], defaults: Dict[str, Any]) -> None:
    for k, v in defaults.items():
        if k not in target:
            target[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(target[k], dict) and k not in ('upgrades', 'records', 'achievements', 'codex', 'deaths_by'):
            _deep_fill(target[k], v)


def migrate_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Миграция версий сохранения. v1 = chromashift_save.json (v6), v2 = зарезервировано."""
    if not isinstance(data, dict):
        raise ValueError('Профиль должен быть объектом JSON')
    if 'upgrade_tree' in data and 'version' not in data:
        legacy = data
        data = default_profile()
        data['cp'] = max(0, int(legacy.get('chromatic_points', 0) or 0))  # в v6 баланс мог уйти в минус
        for nid, node in UPGRADES.items():
            key = node.get('legacy')
            if key and key in legacy.get('upgrade_tree', {}):
                lvl = int(legacy['upgrade_tree'][key].get('current_lvl', 0) or 0)
                data['upgrades'][nid] = max(0, min(node['max'], lvl))
        data['legacy_migrated'] = True
    data.setdefault('version', 1)
    _deep_fill(data, default_profile(data.get('name', 'Пилот')))
    # Валидация
    data['cp'] = max(0, int(data.get('cp', 0)))
    data['prisms'] = max(0, int(data.get('prisms', 0)))
    data['upgrades'] = {k: max(0, min(UPGRADES[k]['max'], int(v))) for k, v in data['upgrades'].items() if k in UPGRADES}
    data['hulls'] = [h for h in data['hulls'] if h in HULLS] or ['prism']
    if 'prism' not in data['hulls']:
        data['hulls'].insert(0, 'prism')
    data['modules'] = [m for m in data['modules'] if m in MODULES]
    loadouts = [lo for lo in data['loadouts'] if isinstance(lo, dict)][:3]
    while len(loadouts) < 3:
        loadouts.append(default_loadout(len(loadouts)))
    for i, lo in enumerate(loadouts):
        lo.setdefault('name', f'Пресет {i + 1}')
        if lo.get('hull') not in data['hulls']:
            lo['hull'] = 'prism'
        lo['modules'] = [m for m in lo.get('modules', []) if m in data['modules']]
        valid: List[str] = []
        for m in lo['modules']:
            ok, _ = can_equip({'hull': lo['hull'], 'modules': valid}, m)
            if ok:
                valid.append(m)
        lo['modules'] = valid
    data['loadouts'] = loadouts
    data['active_loadout'] = max(0, min(2, int(data.get('active_loadout', 0))))
    data['history'] = data['history'][-20:]
    data['leaderboard'] = sorted(data['leaderboard'], key=lambda e: -e.get('score', 0))[:10]
    data['tension_unlocked'] = max(0, min(10, int(data.get('tension_unlocked', 0))))
    # 0.7.0: сборки, переключатели, престиж
    data['builds'] = (list(data.get('builds') or []) + [None, None, None])[:3]
    data['disabled_nodes'] = [n for n in data.get('disabled_nodes', []) if n in UPGRADES]
    data['node_paid'] = {k: int(v) for k, v in data.get('node_paid', {}).items() if k in data['upgrades']}
    data['prestige'] = max(0, int(data.get('prestige', 0)))
    for i in range(1, data['prestige'] + 1):
        COSMETICS['title'][f'Престиж {i}'] = f'Престиж {i}'
    if int(data.get('version', 1)) < 4:
        # Узлы, существовавшие до 0.7.0, помечаем как «просмотренные», чтобы «НОВОЕ» горело только у новых
        data['seen_nodes'] = sorted(set(data.get('seen_nodes', [])) | (set(UPGRADES) - NEW_IN_070))
    data['version'] = SAVE_VERSION
    data['game_version'] = GAME_VERSION
    return data


def atomic_write_json(path: str, data: Any) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


class Profile:
    """Один слот профиля: saves/profile_N.json + ротация бэкапов .bak1…bak3."""

    def __init__(self, slot: int, data: Optional[Dict[str, Any]] = None):
        self.slot = slot
        self.data = data if data is not None else default_profile()
        self.load_warning = ''

    @property
    def path(self) -> str:
        return os.path.join(saves_dir(), f'profile_{self.slot + 1}.json')

    @property
    def cp(self) -> int:
        return self.data['cp']

    @property
    def name(self) -> str:
        return self.data.get('name', 'Пилот')

    @staticmethod
    def exists(slot: int) -> bool:
        return os.path.exists(os.path.join(saves_dir(), f'profile_{slot + 1}.json'))

    @classmethod
    def load(cls, slot: int) -> 'Profile':
        prof = cls(slot)
        candidates = [prof.path] + [f"{prof.path}.bak{i}" for i in range(1, BACKUP_COUNT + 1)]
        for i, path in enumerate(candidates):
            if not os.path.exists(path):
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    prof.data = migrate_profile(json.load(f))
                if i > 0:
                    prof.load_warning = f'Основной файл повреждён — восстановлено из резервной копии {i}'
                return prof
            except (OSError, ValueError, TypeError, KeyError) as e:
                logger.warning(f'Профиль {path} не читается: {e}')
                if i == 0:
                    try:
                        shutil.copy2(path, path + '.corrupt')
                    except OSError:
                        pass
        # Нет профиля: миграция из сохранения v6 (только для первого слота)
        legacy = resolve_game_path('chromashift_save.json')
        if slot == 0 and os.path.exists(legacy):
            try:
                with open(legacy, 'r', encoding='utf-8') as f:
                    prof.data = migrate_profile(json.load(f))
                prof.load_warning = 'Прогресс v6 перенесён в профиль 1'
                prof.save()
            except (OSError, ValueError, TypeError) as e:
                logger.warning(f'Старое сохранение не читается: {e}')
        return prof

    def save(self) -> bool:
        try:
            path = self.path
            if os.path.exists(path):
                for i in range(BACKUP_COUNT, 1, -1):
                    older = f"{path}.bak{i - 1}"
                    if os.path.exists(older):
                        os.replace(older, f"{path}.bak{i}")
                shutil.copy2(path, f"{path}.bak1")
            atomic_write_json(path, self.data)
            return True
        except OSError as e:
            logger.error(f'Не удалось сохранить профиль: {e}')
            return False

    def delete(self) -> None:
        for suffix in [''] + [f'.bak{i}' for i in range(1, BACKUP_COUNT + 1)]:
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass

    def export(self) -> str:
        path = os.path.join(saves_dir(), f'export_profile_{self.slot + 1}.json')
        atomic_write_json(path, self.data)
        return path

    def import_file(self, path: Optional[str] = None) -> Tuple[bool, str]:
        path = path or os.path.join(saves_dir(), 'import.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.data = migrate_profile(json.load(f))
        except (OSError, ValueError, TypeError) as e:
            return False, f'Импорт не удался: {e}'
        self.save()
        return True, 'Профиль импортирован'

    # --- Экономика и дерево ---
    def add_cp(self, amount: int) -> None:
        amount = max(0, int(amount))
        self.data['cp'] += amount
        self.data['cp_earned_total'] += amount

    def buy_upgrade(self, nid: str) -> Tuple[bool, str]:
        status, reason = node_status(self, nid)
        if status != 'available':
            return False, reason
        lvl = self.data['upgrades'].get(nid, 0)
        cost = node_cost(self, nid)
        self.data['cp'] -= cost
        self.data['upgrades'][nid] = lvl + 1
        self.data.setdefault('node_paid', {})
        self.data['node_paid'][nid] = self.data['node_paid'].get(nid, 0) + cost
        if nid not in self.data['seen_nodes']:
            self.data['seen_nodes'].append(nid)
        return True, f"{UPGRADES[nid]['name']}: уровень {lvl + 1}"

    def paid_for(self, nid: str) -> int:
        lvl = self.data['upgrades'].get(nid, 0)
        paid = self.data.get('node_paid', {}).get(nid)
        if paid is None:
            paid = sum(UPGRADES[nid]['costs'][:lvl]) if nid in UPGRADES else 0
        return int(paid)

    def reset_fee_free(self) -> bool:
        return self.data.get('last_free_reset', '') != date_key()

    def reset_upgrades(self, branch: Optional[str] = None) -> int:
        """Сброс с возвратом CP. Раз в день — бесплатно, дальше удерживается 10%.
        branch — частичный сброс одной ветки."""
        nodes = [nid for nid in list(self.data['upgrades']) if nid in UPGRADES
                 and (branch is None or UPGRADES[nid]['branch'] == branch)]
        refund = sum(self.paid_for(nid) for nid in nodes)
        if refund <= 0:
            return 0
        if self.reset_fee_free():
            self.data['last_free_reset'] = date_key()
        else:
            refund = int(refund * 0.9)
        self.data['cp'] += refund
        for nid in nodes:
            self.data['upgrades'].pop(nid, None)
            self.data.get('node_paid', {}).pop(nid, None)
        # Узлы, потерявшие требования, тоже снимаются (с возвратом)
        changed = True
        while changed:
            changed = False
            for nid in list(self.data['upgrades']):
                node = UPGRADES[nid]
                if any(self.data['upgrades'].get(r, 0) <= 0 for r in node['requires']):
                    self.data['cp'] += self.paid_for(nid)
                    refund += self.paid_for(nid)
                    self.data['upgrades'].pop(nid)
                    self.data.get('node_paid', {}).pop(nid, None)
                    changed = True
        return refund

    # --- Сборки дерева ---
    def save_build(self, slot: int, name: str = '') -> str:
        builds = self.data['builds']
        while len(builds) <= slot:
            builds.append(None)
        builds[slot] = {'name': name or f'Сборка {slot + 1}', 'upgrades': dict(self.data['upgrades']),
                        'disabled': list(self.data['disabled_nodes'])}
        return f"Сохранено: {builds[slot]['name']}"

    def apply_build(self, upgrades: Dict[str, int], name: str = 'сборка') -> Tuple[bool, str]:
        """Сбрасывает дерево и покупает узлы сборки по порядку, пока хватает CP."""
        self.reset_upgrades()
        order = sorted(upgrades, key=lambda n: (UPGRADES[n]['tier_cp'] + UPGRADES[n].get('total_cp', 0),
                                                UPGRADES[n]['row']) if n in UPGRADES else (1e9, 0))
        bought = missing = 0
        for _ in range(3):  # несколько проходов — требования внутри сборки
            for nid in order:
                want = int(upgrades.get(nid, 0))
                while nid in UPGRADES and self.data['upgrades'].get(nid, 0) < min(want, UPGRADES[nid]['max']):
                    ok, _ = self.buy_upgrade(nid)
                    if not ok:
                        break
                    bought += 1
        for nid in order:
            if nid in UPGRADES:
                missing += max(0, min(int(upgrades[nid]), UPGRADES[nid]['max']) - self.data['upgrades'].get(nid, 0))
        msg = f"«{name}»: куплено уровней {bought}" + (f", не хватило CP/условий на {missing}" if missing else '')
        return missing == 0, msg

    def build_code(self, upgrades: Optional[Dict[str, int]] = None) -> str:
        import base64
        ups = self.data['upgrades'] if upgrades is None else upgrades
        raw = ';'.join(f"{k}:{v}" for k, v in sorted(ups.items()) if v > 0)
        return 'CS7-' + base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')

    @staticmethod
    def parse_build_code(code: str) -> Optional[Dict[str, int]]:
        import base64
        code = (code or '').strip()
        if not code.startswith('CS7-'):
            return None
        body = code[4:]
        try:
            raw = base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)).decode('utf-8')
            out = {}
            for part in filter(None, raw.split(';')):
                k, v = part.split(':')
                if k in UPGRADES:
                    out[k] = max(0, min(UPGRADES[k]['max'], int(v)))
            return out
        except (ValueError, UnicodeDecodeError):
            return None

    def compare_build(self, upgrades: Dict[str, int]) -> List[str]:
        """Сравнение текущего дерева и сборки по итоговым модификаторам."""
        cur, other = RunMods(), RunMods()
        for nid, lvl in self.data['upgrades'].items():
            if nid in UPGRADES and lvl > 0:
                UPGRADES[nid]['effect'](cur, lvl)
        for nid, lvl in upgrades.items():
            if nid in UPGRADES and lvl > 0:
                UPGRADES[nid]['effect'](other, lvl)
        return diff_mods(cur, other)

    def can_prestige(self) -> bool:
        return total_spent(self.data['upgrades']) >= PRESTIGE_SPENT

    def prestige(self) -> Tuple[bool, str]:
        if not self.can_prestige():
            return False, f"Нужно вложить в дерево {PRESTIGE_SPENT} CP"
        self.reset_upgrades()
        self.data['cp'] = int(self.data['cp'] * 0.5)  # половина CP «сгорает» в престиже
        self.data['prestige'] += 1
        cos = f"title:Престиж {self.data['prestige']}"
        if cos not in self.data['unlocked_cosmetics']:
            self.data['unlocked_cosmetics'].append(cos)
            COSMETICS['title'][cos.split(':', 1)[1]] = cos.split(':', 1)[1]
        return True, f"Престиж {self.data['prestige']}: +{int(PRESTIGE_CP_BONUS * 100)}% CP навсегда"

    def recommended_upgrade(self) -> Optional[str]:
        arch = self.data.get('archetype', 'balanced')
        pref = {'assault': 'RED', 'control': 'BLUE', 'dancer': 'GREEN', 'parry': 'CORE'}.get(arch, 'CORE')
        best, best_score = None, -1e9
        for nid, node in UPGRADES.items():
            status, _ = node_status(self, nid)
            if status not in ('available', 'expensive'):
                continue
            lvl = self.data['upgrades'].get(nid, 0)
            score = -node['costs'][lvl] / 50.0
            if node['branch'] == pref:
                score += 3
            if status == 'available':
                score += 2
            if node['key']:
                score += 1
            if arch == 'parry' and nid in ('core_lens', 'core_prism', 'green_homing', 'green_ricochet'):
                score += 2
            if score > best_score:
                best, best_score = nid, score
        return best

    def buy_hull(self, hid: str) -> Tuple[bool, str]:
        h = HULLS[hid]
        if hid in self.data['hulls']:
            return False, 'Уже открыт'
        if self.cp < h['cost'] or self.data['prisms'] < h['prisms']:
            return False, f"Нужно {h['cost']} CP и {h['prisms']} призм"
        self.data['cp'] -= h['cost']
        self.data['prisms'] -= h['prisms']
        self.data['hulls'].append(hid)
        return True, f"Корпус «{h['name']}» открыт"

    def buy_module(self, mid: str) -> Tuple[bool, str]:
        m = MODULES[mid]
        if mid in self.data['modules']:
            return False, 'Уже открыт'
        if self.cp < m['cost']:
            return False, f"Нужно {m['cost']} CP"
        self.data['cp'] -= m['cost']
        self.data['modules'].append(mid)
        return True, f"Модуль «{m['name']}» открыт"

    @property
    def loadout(self) -> Dict[str, Any]:
        return self.data['loadouts'][self.data['active_loadout']]

    def toggle_module(self, mid: str) -> Tuple[bool, str]:
        lo = self.loadout
        if mid in lo['modules']:
            lo['modules'].remove(mid)
            return True, 'Снят'
        if mid not in self.data['modules']:
            return False, 'Модуль не открыт'
        ok, reason = can_equip(lo, mid)
        if ok:
            lo['modules'].append(mid)
            return True, 'Установлен'
        return False, reason

    def set_hull(self, hid: str) -> None:
        lo = self.loadout
        lo['hull'] = hid
        valid: List[str] = []
        for m in lo['modules']:
            if can_equip({'hull': hid, 'modules': valid}, m)[0]:
                valid.append(m)
        lo['modules'] = valid

    # --- Сборка модификаторов забега ---
    def build_mods(self, run_type: str, settings: Any, tension: int = 0, risks: Optional[List[str]] = None,
                   trial_node: Optional[str] = None) -> RunMods:
        m = RunMods()
        pure = run_type in ('pure', 'training')
        ups = dict(self.data['upgrades'])
        if trial_node and trial_node in UPGRADES:  # пробный режим: узел на следующем уровне
            ups[trial_node] = min(UPGRADES[trial_node]['max'], ups.get(trial_node, 0) + 1)
            pure = False
        lo = self.loadout
        if not pure:
            disabled = set(self.data.get('disabled_nodes', []))
            for nid, lvl in ups.items():
                node = UPGRADES.get(nid)
                if not node or lvl <= 0 or nid in disabled:
                    continue
                if node.get('hull') and node['hull'] != lo['hull']:
                    continue
                if node.get('from_wave'):
                    m.wave_effects.append((node['from_wave'], nid, lvl))
                    continue
                node['effect'](m, lvl)
                if node.get('grow'):
                    stat, per, step, cap = node['grow']
                    bonus = min(cap, step * int(self.data['stats'].get(stat, 0) // per))
                    m.damage_mult *= 1 + bonus
                ev = node.get('evolve')
                if ev and lvl >= node['max'] and self.data['stats'].get(ev['stat'], 0) >= ev['goal']:
                    ev['effect'](m, 1)
            m.sources.append('Дерево улучшений')
            hull = HULLS.get(lo['hull'], HULLS['prism'])
            hull['apply'](m)
            m.sources.append(f"Корпус «{hull['name']}»")
            hm = self.hull_mastery(lo['hull'])
            if hm:
                m.damage_mult *= 1 + 0.02 * hm
                m.sources.append(f"Мастерство корпуса {hm}")
            for mid in lo['modules']:
                MODULES[mid]['apply'](m)
            for syn in active_synergies(lo['modules']):
                syn['apply'](m)
                m.sources.append(f"Синергия «{syn['name']}»")
            if self.data.get('prestige', 0):
                m.cp_mult += PRESTIGE_CP_BONUS * self.data['prestige']
                m.sources.append(f"Престиж {self.data['prestige']}")
        if run_type == 'training':
            m.violet_unlocked = True  # в тренировке можно попробовать все цвета
        apply_difficulty(m, settings)
        apply_tension(m, tension)
        for rid in risks or []:
            if rid in RISKS:
                RISKS[rid]['apply'](m)
                m.cp_mult += RISKS[rid]['cp']
                m.sources.append(f"Риск «{RISKS[rid]['name']}»")
        if run_type == 'training':
            m.cp_mult = 0.0
        apply_caps(m)
        return m

    def apply_wave_effects(self, m: RunMods, wave: int) -> List[str]:
        """Включает узлы «с волны N». Возвращает названия включённых."""
        on = []
        for item in list(m.wave_effects):
            w, nid, lvl = item
            if wave >= w:
                UPGRADES[nid]['effect'](m, lvl)
                m.wave_effects.remove(item)
                on.append(UPGRADES[nid]['name'])
        if on:
            apply_caps(m)
        return on

    # --- Корпуса: мастерство и испытания ---
    def hull_mastery(self, hid: str) -> int:
        """Уровень мастерства корпуса 0–5: растёт от пройденных на нём волн."""
        waves = self.data['hull_stats'].get(hid, {}).get('waves', 0)
        return min(5, int(waves // 40))

    def toggle_node(self, nid: str) -> Tuple[bool, str]:
        node = UPGRADES.get(nid)
        if not node or not node.get('toggle') or self.data['upgrades'].get(nid, 0) <= 0:
            return False, 'Этот узел нельзя переключать'
        dis = self.data['disabled_nodes']
        if nid in dis:
            dis.remove(nid)
            return True, f"«{node['name']}» включён"
        dis.append(nid)
        return True, f"«{node['name']}» выключен"

    # --- Контракты ---
    def refresh_contracts(self, today: Optional[_dt.date] = None) -> None:
        key = date_key(today)
        c = self.data['contracts']
        if c.get('date') == key and c.get('list'):
            return
        rng = random.Random(challenge_seed('daily', today) + self.slot)
        picks = rng.sample(CONTRACT_TEMPLATES, 3)
        c['date'] = key
        c['list'] = [{'id': t[0], 'desc': t[1].format(n=t[3]), 'stat': t[2], 'goal': t[3],
                      'reward': t[4], 'progress': 0, 'done': False} for t in picks]

    def refresh_weekly_contracts(self, today: Optional[_dt.date] = None) -> None:
        key = week_key(today)
        c = self.data['weekly_contracts']
        if c.get('week') == key and c.get('list'):
            return
        rng = random.Random(challenge_seed('weekly', today) + 31 * (self.slot + 1))
        picks = rng.sample(WEEKLY_CONTRACT_TEMPLATES, 3)
        c['week'] = key
        c['list'] = [{'id': t[0], 'desc': t[1].format(n=t[3]), 'stat': t[2], 'goal': t[3],
                      'reward': t[4], 'progress': 0, 'done': False} for t in picks]

    def advance_contracts(self, run: Dict[str, Any]) -> List[str]:
        done = []
        for c in self.data['contracts'].get('list', []):
            if c['done']:
                continue
            c['progress'] = min(c['goal'], c['progress'] + int(run.get(c['stat'], 0)))
            if c['progress'] >= c['goal']:
                c['done'] = True
                self.add_cp(c['reward'])
                self.data['stats']['contracts_done'] += 1
                done.append(f"Контракт выполнен: {c['desc']} (+{c['reward']} CP)")
        self.refresh_weekly_contracts()
        for c in self.data['weekly_contracts'].get('list', []):
            if c['done']:
                continue
            val = run.get('codex', {}).get('swarm', 0) if c['stat'] == 'swarm_kills' else run.get(c['stat'], 0)
            c['progress'] = min(c['goal'], c['progress'] + int(val))
            if c['progress'] >= c['goal']:
                c['done'] = True
                self.add_cp(c['reward'])
                self.data['stats']['contracts_done'] += 1
                done.append(f"Недельный контракт: {c['desc']} (+{c['reward']} CP)")
        return done

    # --- Достижения ---
    def check_achievements(self, run: Optional[Dict[str, Any]] = None) -> List[str]:
        unlocked = []
        for aid, name, desc, fn, goal, reward, cosmetic in ACHIEVEMENTS:
            if aid in self.data['achievements']:
                continue
            try:
                value = fn(self.data, run)
            except (KeyError, TypeError):
                value = 0
            if value >= goal:
                self.data['achievements'][aid] = date_key()
                self.add_cp(reward)
                text = f"Достижение: {name} (+{reward} CP)"
                if cosmetic and cosmetic not in self.data['unlocked_cosmetics']:
                    self.data['unlocked_cosmetics'].append(cosmetic)
                    kind, val = cosmetic.split(':', 1)
                    text += f", открыто: {COSMETICS[kind].get(val, val)}"
                unlocked.append(text)
        return unlocked

    def achievement_progress(self, aid: str) -> Tuple[float, float]:
        a = ACH_BY_ID[aid]
        try:
            return float(a[3](self.data, None)), float(a[4])
        except (KeyError, TypeError):
            return 0.0, float(a[4])

    # --- Итоги забега ---
    def record_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        """Применяет итоги забега к профилю. Возвращает разбор начисления CP и уведомления."""
        st = self.data['stats']
        result: Dict[str, Any] = {'notices': [], 'cp_lines': [], 'cp_total': 0, 'new_record': False}
        run_type = run.get('run_type', 'standard')
        if run_type == 'training':
            return result
        st['runs'] += 1
        for key in ('kills', 'refractions', 'refraction_fails', 'echoes', 'impulses', 'resonances',
                    'beat_kills', 'bosses', 'elites', 'dashes', 'switches', 'artifacts', 'waves_cleared',
                    'hydra_kills', 'spectrum_kills', 'vortexes', 'touch_parries', 'chains', 'precise_kills',
                    'absorbed', 'shop_buys', 'gambles_won'):
            st[key] = st.get(key, 0) + int(run.get(key, 0))
        wv = int(run.get('wave', 1))
        if run.get('victory'):
            st['victories'] = st.get('victories', 0) + 1
        if 'horde' in run.get('risks', []):
            st['horde_best_wave'] = max(st.get('horde_best_wave', 0), wv)
        if run_type == 'blitz':
            st['blitz_best'] = max(st.get('blitz_best', 0), int(run.get('score', 0)))
        if run_type == 'bossrush' and run.get('victory'):
            st['bossrush_clears'] = st.get('bossrush_clears', 0) + 1
        if run_type == 'endless':
            st['endless_best_wave'] = max(st.get('endless_best_wave', 0), wv)
        # Статистика узлов (с какими узлами вы доходите дальше)
        for nid, lvl in self.data['upgrades'].items():
            if lvl > 0:
                ns = self.data['node_stats'].setdefault(nid, {'runs': 0, 'waves': 0, 'best': 0})
                ns['runs'] += 1
                ns['waves'] += wv
                ns['best'] = max(ns['best'], wv)
        # Корпус: мастерство и испытание
        hid = run.get('hull') or self.loadout['hull']
        hs = self.data['hull_stats'].setdefault(hid, {'runs': 0, 'waves': 0, 'best': 0})
        hs['runs'] += 1
        hs['waves'] += int(run.get('waves_cleared', 0))
        hs['best'] = max(hs['best'], wv)
        ch = HULL_CHALLENGES.get(hid)
        if ch and hid not in self.data['hull_challenges']:
            val = wv if ch[1] == 'best_wave' else int(run.get(ch[1], 0))
            if val >= ch[2]:
                self.data['hull_challenges'].append(hid)
                self.data['prisms'] += 1
                result['notices'].append(f"Испытание корпуса «{HULLS[hid]['name']}» пройдено: +1 призма")
        st['play_time'] += float(run.get('time', 0.0))
        for m in ALL_MODES:
            st['mode_kills'][m] = st['mode_kills'].get(m, 0) + int(run.get(f'kills_{m}', 0))
            st['mode_time'][m] = st['mode_time'].get(m, 0.0) + float(run.get(f'time_{m}', 0.0))
        for kind in run.get('codex', {}):
            if kind not in self.data['seen_enemies']:
                self.data['seen_enemies'].append(kind)
        for kind, n in run.get('codex', {}).items():
            st['codex'][kind] = st['codex'].get(kind, 0) + n
        cause = run.get('death_cause', '')
        if cause:
            st['deaths_by'][cause] = st['deaths_by'].get(cause, 0) + 1
        wave, score = int(run.get('wave', 1)), int(run.get('score', 0))
        prev_best = st['best_score']
        st['best_wave'] = max(st['best_wave'], wave)
        st['best_score'] = max(st['best_score'], score)
        if run_type == 'pure':
            st['pure_best_wave'] = max(st['pure_best_wave'], wave)
        tension = int(run.get('tension', 0))
        if wave >= 10:
            st['tension_cleared'] = max(st['tension_cleared'], tension)
            if tension >= self.data['tension_unlocked'] and tension < 10:
                self.data['tension_unlocked'] = tension + 1
                result['notices'].append(f"Открыто Напряжение {tension + 1}")
        bosses = int(run.get('bosses', 0))
        if bosses:
            self.data['prisms'] += bosses
            result['notices'].append(f"+{bosses} призм(ы) за боссов")

        # Рекорды по режимам
        rec_key = run_type
        rec = self.data['records'].setdefault(rec_key, {'score': 0, 'wave': 0})
        if score > rec['score']:
            rec.update({'score': score, 'wave': wave, 'date': date_key()})
            result['new_record'] = score > 0
        # Экономика CP (с разбором)
        lines = run.get('cp_lines', [])
        base = sum(v for _, v in lines)
        mult = float(run.get('cp_mult', 1.0))
        total = int(round(base * mult))
        result['cp_lines'] = list(lines)
        if abs(mult - 1.0) > 1e-6:
            result['cp_lines'].append((f"Множитель ×{mult:.2f}", total - base))
        today = date_key()
        if self.data.get('last_first_run_day') != today:
            self.data['last_first_run_day'] = today
            result['cp_lines'].append(('Первый забег дня', CFG.CP_DAILY_FIRST_RUN))
            total += CFG.CP_DAILY_FIRST_RUN
        if score > prev_best and prev_best > 0:
            result['cp_lines'].append(('Новый личный рекорд', CFG.CP_RECORD_BONUS))
            total += CFG.CP_RECORD_BONUS
        if run_type in ('daily', 'weekly'):
            slot = self.data[run_type]
            if slot.get('key') != run.get('challenge_key'):
                slot['key'] = run.get('challenge_key', '')
                slot['best'] = 0
            slot['best'] = max(slot['best'], score)
            st[f'{run_type}_runs'] += 1
        self.add_cp(total)
        result['cp_total'] = total
        # Призрак рекорда
        if score >= self.data['ghost'].get('score', 0) and run.get('wave_times'):
            self.data['ghost'] = {'score': score, 'wave_times': list(run['wave_times'])}
        # История и таблица рекордов
        entry = {'date': date_key(), 'score': score, 'wave': wave, 'type': run_type, 'tension': tension,
                 'archetype': run.get('archetype', 'balanced'), 'cause': cause, 'cp': total,
                 'time': round(float(run.get('time', 0.0)), 1)}
        self.data['history'] = (self.data['history'] + [entry])[-20:]
        lb = self.data['leaderboard'] + [dict(entry, name=self.name)]
        self.data['leaderboard'] = sorted(lb, key=lambda e: -e['score'])[:10]
        self.data['archetype'] = run.get('archetype', self.data.get('archetype', 'balanced'))
        # Помощь после серии ранних смертей
        if wave < 5:
            self.data['death_streak'] += 1
        else:
            self.data['death_streak'] = 0
        result['notices'] += self.advance_contracts(run)
        result['notices'] += self.check_achievements(run)
        return result


ARCHETYPES = {
    'assault': ('Штурмовик', 'Предпочитает RED и натиск'),
    'control': ('Контролёр', 'Держит позицию в BLUE'),
    'dancer': ('Танцор', 'Скользит в GREEN и часто рвётся'),
    'parry': ('Преломитель', 'Живёт отражёнными пулями'),
    'balanced': ('Хромант', 'Равномерно использует все цвета'),
}


def detect_archetype(run: Dict[str, Any]) -> str:
    t = max(1.0, float(run.get('time', 1.0)))
    if run.get('refractions', 0) / (t / 60.0) >= 4:
        return 'parry'
    times = {m: float(run.get(f'time_{m}', 0.0)) for m in MODES}
    total = sum(times.values()) or 1.0
    top = max(times, key=times.get)
    if times[top] / total < 0.45:
        return 'balanced'
    if top == 'GREEN' or run.get('dashes', 0) / (t / 60.0) > 20:
        return 'dancer' if top != 'RED' else 'assault'
    return {'RED': 'assault', 'BLUE': 'control'}.get(top, 'balanced')

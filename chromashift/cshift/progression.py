"""Метагейм ChromaShift 0.6.5: модификаторы забега, дерево улучшений, корпуса и модули,
артефакты, профили и сохранения, статистика, достижения, контракты, испытания."""
import copy
import datetime as _dt
import json
import logging
import os
import random
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import CFG, MODES, GAME_VERSION, resolve_game_path

logger = logging.getLogger('ChromaShift')

SAVE_VERSION = 3
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
        self.mode_damage_mult = {m: 1.0 for m in MODES}
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
        self.accel_mult = {m: 1.0 for m in MODES}
        self.max_speed_mult = {m: 1.0 for m in MODES}
        self.decel_mult = {m: 1.0 for m in MODES}
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
        for m in MODES:
            self.max_speed_mult[m] *= mult
            self.accel_mult[m] *= mult

    def to_dict(self) -> Dict[str, Any]:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in self.__dict__.items() if k != 'sources'}


# =====================================================================
# ДЕРЕВО УЛУЧШЕНИЙ
# =====================================================================
BRANCHES = {
    'CORE': ('Ядро', (230, 240, 255)),
    'RED': ('Импульс', None),
    'BLUE': ('Якорь', None),
    'GREEN': ('Поток', None),
}


def _node(name: str, branch: str, costs: List[int], desc: str, effect: Callable[[RunMods, int], None],
          row: int, requires: Optional[List[str]] = None, tier_cp: int = 0, key: bool = False,
          group: Optional[str] = None, tradeoff: bool = False, legacy: Optional[str] = None) -> Dict[str, Any]:
    return {'name': name, 'branch': branch, 'costs': costs, 'max': len(costs), 'desc': desc,
            'effect': effect, 'row': row, 'requires': requires or [], 'tier_cp': tier_cp, 'key': key,
            'group': group, 'tradeoff': tradeoff, 'legacy': legacy}


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


def branch_spent(upgrades: Dict[str, int], branch: str) -> int:
    total = 0
    for nid, lvl in upgrades.items():
        node = UPGRADES.get(nid)
        if node and node['branch'] == branch:
            total += sum(node['costs'][:lvl])
    return total


def node_status(profile: 'Profile', nid: str) -> Tuple[str, str]:
    """Возвращает (статус, причина): maxed / locked / blocked / expensive / available."""
    node = UPGRADES[nid]
    lvl = profile.data['upgrades'].get(nid, 0)
    if lvl >= node['max']:
        return 'maxed', 'Максимальный уровень'
    spent = branch_spent(profile.data['upgrades'], node['branch'])
    if spent < node['tier_cp']:
        return 'locked', f"Вложите в ветку ещё {node['tier_cp'] - spent} CP"
    for req in node['requires']:
        if profile.data['upgrades'].get(req, 0) <= 0:
            return 'locked', f"Нужно: {UPGRADES[req]['name']}"
    if node['group']:
        for other, onode in UPGRADES.items():
            if other != nid and onode['group'] == node['group'] and profile.data['upgrades'].get(other, 0) > 0:
                return 'blocked', f"Взаимоисключает: {onode['name']}"
    cost = node['costs'][lvl]
    if profile.cp < cost:
        return 'expensive', f"Нужно {cost} CP"
    return 'available', f"Цена: {cost} CP"


def preview_node(profile: 'Profile', nid: str) -> List[str]:
    """Предпросмотр: что изменится при покупке следующего уровня."""
    node = UPGRADES[nid]
    lvl = profile.data['upgrades'].get(nid, 0)
    before = RunMods()
    after = RunMods()
    node['effect'](before, lvl)
    node['effect'](after, min(node['max'], lvl + 1))
    lines = []
    b, a = before.to_dict(), after.to_dict()
    labels = {'max_hp_add': 'Макс. HP', 'max_hp_mult': 'Множ. HP', 'damage_mult': 'Урон',
              'dash_cd_mult': 'Перезарядка рывка', 'refraction_window_add': 'Окно Преломления',
              'pickup_radius_mult': 'Радиус подбора', 'powerup_chance_add': 'Шанс бонуса',
              'fire_rate_mult': 'Скорострельность', 'invuln_time_mult': 'Неуязвимость',
              'impulse_duration_add': 'Длит. Импульса', 'impulse_threshold_add': 'Порог Импульса',
              'blue_aoe_mult': 'Радиус волны', 'resonance_radius_mult': 'Радиус Резонанса',
              'resonance_lifetime_add': 'Жизнь Резонанса', 'beat_window_add': 'Окно такта',
              'echo_duration_add': 'Длит. Эха', 'drift_mult': 'Дрейф', 'shield_charges': 'Щиты',
              'revives': 'Воскрешения', 'refraction_ricochet': 'Рикошеты', 'dash_speed_mult': 'Скорость рывка'}
    for k, v in a.items():
        if isinstance(v, dict):
            for mode, val in v.items():
                if abs(val - b[k][mode]) > 1e-9:
                    lines.append(f"{k.replace('_mult', '').replace('_', ' ')} {mode}: ×{b[k][mode]:.2f} → ×{val:.2f}")
        elif v != b[k]:
            name = labels.get(k, k)
            if isinstance(v, bool):
                lines.append(f"{name}: включается")
            elif isinstance(v, float) and ('mult' in k):
                lines.append(f"{name}: ×{b[k]:.2f} → ×{v:.2f}")
            else:
                lines.append(f"{name}: {b[k]:g} → {v:g}")
    return lines or ['Без численных изменений']


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
ACH_BY_ID = {a[0]: a for a in ACHIEVEMENTS}

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
]


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
    return {'seed': challenge_seed(kind, d), 'arena': rng.choice(['classic', 'pillars', 'prism']),
            'risks': risks, 'start_mode': rng.choice(MODES), 'tension': 0 if kind == 'daily' else 2,
            'key': date_key(d) if kind == 'daily' else week_key(d)}


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
                  'mode_kills': {m: 0 for m in MODES}, 'mode_time': {m: 0.0 for m in MODES},
                  'codex': {}, 'deaths_by': {}, 'waves_cleared': 0},
        'records': {}, 'history': [], 'leaderboard': [],
        'achievements': {}, 'cosmetics': {'ship_shape': 'circle', 'trail_style': 'mode', 'title': ''},
        'unlocked_cosmetics': list(DEFAULT_COSMETICS),
        'contracts': {'date': '', 'list': []},
        'daily': {'key': '', 'best': 0, 'claimed_first': ''}, 'weekly': {'key': '', 'best': 0},
        'tension_unlocked': 0, 'ghost': {'score': 0, 'wave_times': []},
        'death_streak': 0, 'assist_declined': False, 'seen_tips': [], 'archetype': 'balanced',
        'last_first_run_day': '',
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
        self.data['cp'] -= UPGRADES[nid]['costs'][lvl]
        self.data['upgrades'][nid] = lvl + 1
        return True, f"{UPGRADES[nid]['name']}: уровень {lvl + 1}"

    def reset_upgrades(self) -> int:
        refund = sum(branch_spent(self.data['upgrades'], b) for b in BRANCHES)
        self.data['cp'] += refund
        self.data['upgrades'] = {}
        return refund

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
    def build_mods(self, run_type: str, settings: Any, tension: int = 0, risks: Optional[List[str]] = None) -> RunMods:
        m = RunMods()
        pure = run_type in ('pure', 'training')
        if not pure:
            for nid, lvl in self.data['upgrades'].items():
                if lvl > 0:
                    UPGRADES[nid]['effect'](m, lvl)
            m.sources.append('Дерево улучшений')
            lo = self.loadout
            HULLS[lo['hull']]['apply'](m)
            m.sources.append(f"Корпус «{HULLS[lo['hull']]['name']}»")
            for mid in lo['modules']:
                MODULES[mid]['apply'](m)
            for syn in active_synergies(lo['modules']):
                syn['apply'](m)
                m.sources.append(f"Синергия «{syn['name']}»")
        apply_difficulty(m, settings)
        apply_tension(m, tension)
        for rid in risks or []:
            if rid in RISKS:
                RISKS[rid]['apply'](m)
                m.cp_mult += RISKS[rid]['cp']
                m.sources.append(f"Риск «{RISKS[rid]['name']}»")
        if run_type == 'training':
            m.cp_mult = 0.0
        return m

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
                    'beat_kills', 'bosses', 'elites', 'dashes', 'switches', 'artifacts', 'waves_cleared'):
            st[key] = st.get(key, 0) + int(run.get(key, 0))
        st['play_time'] += float(run.get('time', 0.0))
        for m in MODES:
            st['mode_kills'][m] = st['mode_kills'].get(m, 0) + int(run.get(f'kills_{m}', 0))
            st['mode_time'][m] = st['mode_time'].get(m, 0.0) + float(run.get(f'time_{m}', 0.0))
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

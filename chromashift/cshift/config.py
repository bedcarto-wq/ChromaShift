"""Конфигурация ChromaShift: версия, пути, все балансные параметры."""
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

GAME_VERSION = "0.7.0"

logging.basicConfig(level=logging.WARNING, format='[%(levelname)s] %(message)s')
logger = logging.getLogger('ChromaShift')

# Папка с данными игрока: рядом с exe (PyInstaller) или рядом с исходниками.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    # Встроенные в exe ресурсы распаковываются во временную папку _MEIPASS
    RESOURCE_DIR = getattr(sys, '_MEIPASS', BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RESOURCE_DIR = BASE_DIR


def resolve_game_path(path: str) -> str:
    """Относительные пути данных игрока считаются от папки игры."""
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def resource_path(*parts: str) -> str:
    return os.path.join(RESOURCE_DIR, *parts)


MODES = ('RED', 'BLUE', 'GREEN')
# Четвёртый цвет открывается в дереве (ветка «Цвет»). Базовые враги и щиты используют только MODES.
ALL_MODES = ('RED', 'BLUE', 'GREEN', 'VIOLET')


class GameConfig:
    """Singleton-конфигурация с hot-reload из chromashift_config.json."""
    _instance: Optional['GameConfig'] = None
    _file_mtime: float = 0.0
    _config_path: str = resolve_game_path("chromashift_config.json")

    def __new__(cls) -> 'GameConfig':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._defaults = self._get_defaults()
        self._values: Dict[str, Any] = dict(self._defaults)
        self._load()

    def _get_defaults(self) -> Dict[str, Any]:
        return {
            'SCREEN_WIDTH': 1280, 'SCREEN_HEIGHT': 720, 'TARGET_FPS': 60,
            'DEBUG_MODE': False,  # G = god mode, только для отладки

            'COLOR_BG': (10, 12, 20), 'COLOR_BG2': (22, 28, 45),
            'COLOR_PRIMARY': (230, 240, 255), 'COLOR_ACCENT': (255, 215, 100),
            'COLOR_DANGER': (255, 60, 80), 'COLOR_SUCCESS': (100, 255, 150),
            'COLOR_TEXT': (240, 245, 255),
            'COLOR_RED': (255, 50, 80), 'COLOR_BLUE': (60, 140, 255),
            'COLOR_GREEN': (80, 255, 140),

            # Физика режимов (семантика: RED импульс, BLUE якорь, GREEN текучесть)
            'RED_ACCEL': 2400.0, 'RED_DECEL': 3.5, 'RED_MAX_SPEED': 520.0, 'RED_RECOIL': 0.05,
            'BLUE_ACCEL': 900.0, 'BLUE_DECEL': 32.0, 'BLUE_MAX_SPEED': 280.0,
            'BLUE_RECOIL': 0.15, 'BLUE_AOE_RADIUS': 80.0,
            'GREEN_ACCEL': 1400.0, 'GREEN_DECEL': 5.5, 'GREEN_MAX_SPEED': 420.0,
            'GREEN_RECOIL': 0.0, 'GREEN_LATERAL_DRIFT': 0.12,

            'PLAYER_RADIUS': 14, 'PLAYER_MAX_HP': 100,
            'PLAYER_INVULN_TIME': 1.2, 'PLAYER_SQUASH_DURATION': 0.15,

            # Dash: неуязвимость длится DASH_INVULN_FRAMES (чуть дольше самого рывка)
            'DASH_SPEED': 900.0, 'DASH_DURATION': 0.15, 'DASH_COOLDOWN': 1.5,
            'DASH_KILL_REDUCTION': 0.3, 'DASH_INVULN_FRAMES': 0.2,

            'FIRE_COOLDOWN': 0.14, 'BULLET_SPEED': 820.0,
            'BULLET_LIFETIME': 1.6, 'BULLET_RADIUS': 4, 'BULLET_DAMAGE': 25,

            'IMPULSE_KILL_THRESHOLD': 5, 'IMPULSE_DURATION': 3.0,
            'ECHO_REFRACTION_THRESHOLD': 3, 'ECHO_DURATION': 5.0, 'ECHO_SLOWDOWN_MULT': 0.7,

            'PERFECT_REFRACTION_WINDOW': 0.25,
            'PARRY_INDICATOR_RADIUS': 90.0, 'PARRY_WARNING_RADIUS': 200.0,

            'CHASER_SPEED': 155.0, 'CHASER_HP': 50, 'CHASER_RADIUS': 13, 'CHASER_DAMAGE': 15,
            'SHOOTER_SPEED': 95.0, 'SHOOTER_HP': 40, 'SHOOTER_RADIUS': 14,
            'SHOOTER_FIRE_INTERVAL': 1.6, 'SHOOTER_BULLET_SPEED': 310.0,
            'SHOOTER_BULLET_DAMAGE': 10, 'SHOOTER_BULLET_RADIUS': 5,
            'SHOOTER_PANIC_DISTANCE': 150.0,
            'KAMIKAZE_SPEED': 290.0, 'KAMIKAZE_HP': 30, 'KAMIKAZE_RADIUS': 12,
            'KAMIKAZE_EXPLOSION_RADIUS': 65, 'KAMIKAZE_EXPLOSION_DAMAGE': 30,
            'KAMIKAZE_WARN_TIME': 1.0, 'KAMIKAZE_WARN_RADIUS': 80.0,
            # 0.7.0: Диссонанс больше не «губка» — 90 HP и цветная броня вместо 250 HP
            'DISSONANCE_HP': 90, 'DISSONANCE_RADIUS': 15, 'DISSONANCE_SPEED': 125.0,
            'DISSONANCE_NORMAL_DAMAGE_MULT': 0.2, 'DISSONANCE_HOMING_STRENGTH': 0.3,
            'DISSONANCE_ARMOR_MULT': 0.15, 'DISSONANCE_COLOR_TIME': 3.5, 'DISSONANCE_JAM_RADIUS': 130.0,
            'DISSONANCE_JAM_INTERVAL': 5.0, 'DISSONANCE_JAM_TIME': 1.6, 'DISSONANCE_DAMAGE': 16,
            'VIOLET_ACCEL': 1100.0, 'VIOLET_DECEL': 1.4, 'VIOLET_MAX_SPEED': 460.0, 'VIOLET_RECOIL': 0.02,
            'BOSS_HP': 1600, 'BOSS_RADIUS': 34, 'BOSS_SPEED': 70.0,
            'BOSS_OFF_COLOR_DAMAGE_MULT': 0.4,

            # === Волны (бюджетная система) ===
            # 0.7.0: врагов заметно больше (бюджет +40%, лимит на экране 30 → 60, дешёвые рои)
            'WAVE_BUDGET_BASE': 7.0, 'WAVE_BUDGET_GROWTH': 3.1, 'WAVE_BUDGET_EXPONENT': 1.25,
            'WAVE_COST_CHASER': 1.0, 'WAVE_COST_KAMIKAZE': 1.2, 'WAVE_COST_SHOOTER': 2.0,
            'WAVE_COST_DISSONANCE': 3.0, 'WAVE_COST_ELITE_EXTRA': 2.0,
            'WAVE_COST_SWARM': 0.3, 'WAVE_COST_PRISM': 2.5, 'WAVE_COST_MIRROR': 2.5, 'WAVE_COST_CHAMELEON': 2.0,
            'WAVE_COST_SHIELDBEARER': 3.0, 'WAVE_COST_MINER': 2.2, 'WAVE_COST_LASER': 3.0,
            'WAVE_COST_DEVOURER': 3.0, 'WAVE_COST_SUMMONER': 3.5, 'WAVE_COST_TELEPORTER': 2.0,
            'WAVE_COST_RESONATOR': 2.5, 'WAVE_COST_LEADER': 3.0,
            'WAVE_MAX_ACTIVE_ENEMIES': 60, 'WAVE_MAX_SHOOTERS': 8, 'WAVE_MAX_KAMIKAZE': 8,
            'WAVE_MAX_ENEMY_BULLETS': 90, 'WAVE_REINFORCE_AFTER': 12.0,
            'HORDE_BUDGET_MULT': 2.0, 'HORDE_INTERMISSION_MULT': 0.4,
            'MINIBOSS_HP': 650, 'BLITZ_DURATION': 600.0, 'SURVIVE_DURATION': 45.0,
            'GAMBLE_BUDGET_MULT': 1.4, 'GAMBLE_SCORE_MULT': 1.6, 'GAMBLE_CP': 2,
            'CRIT_CHANCE': 0.06, 'CRIT_MULT': 2.0, 'SHARDS_PER_KILL': 1, 'SHOP_WAVE_INTERVAL': 3,
            'OVERLOAD_MAX': 12, 'PAINT_CHANCE': 0.12, 'MIX_WINDOW': 0.35, 'MIX_COOLDOWN': 2.5,
            'PARRY_SWITCH_WINDOW': 0.18, 'COLOR_SKILL_COOLDOWN': 7.0, 'REPLAY_SECONDS': 10.0,
            'WAVE_SUBWAVE_RELEASE_FRACTION': 0.3, 'WAVE_SUBWAVE_MAX_GAP': 8.0,
            'WAVE_SPAWN_STAGGER': 0.12, 'WAVE_TELEGRAPH_TIME': 0.7,
            'WAVE_SAFE_RADIUS': 250.0, 'WAVE_FAR_EDGE_BIAS': 0.7,
            'WAVE_INTERMISSION': 2.5, 'BREATHER_WAVE_INTERVAL': 5, 'BREATHER_BUDGET_MULT': 0.5,
            'BOSS_WAVE_INTERVAL': 10, 'ARTIFACT_WAVE_INTERVAL': 5,
            'SPECIAL_WAVE_CHANCE': 0.22, 'SPECIAL_WAVE_MIN': 7,
            'ELITE_CHANCE_PER_WAVE': 0.03, 'ELITE_START_WAVE': 4, 'ELITE_MAX_CHANCE': 0.35,
            'ENEMY_HP_SCALE': 0.04, 'ENEMY_HP_SCALE_MAX': 2.2,
            'ENEMY_SPEED_SCALE': 0.015, 'ENEMY_SPEED_SCALE_MAX': 1.35,
            'ENEMY_DAMAGE_SCALE': 0.02, 'ENEMY_DAMAGE_SCALE_MAX': 1.6,
            'WAVE_REWARD_SCORE': 200, 'WAVE_NO_DAMAGE_BONUS': 0.5,
            'WAVE_PAR_SECONDS_PER_BUDGET': 1.6, 'OVERHEAT_BUDGET_MULT': 1.1,
            'DDA_MIN': 0.85, 'DDA_MAX': 1.15,

            'MAX_PARTICLES': 300, 'PARTICLE_POOL_SIZE': 500,
            'PARTICLE_LIFETIME': 0.8, 'ENEMY_DEATH_PARTICLES': 18,
            'SHOOT_PARTICLES': 10, 'PLAYER_DEATH_PARTICLES': 35,
            'HIT_PARTICLES': 6, 'REFRACTION_PARTICLES': 25,
            'SHAKE_DURATION': 0.25, 'SHAKE_DECAY': 8.0,
            'FLASH_DURATION': 0.12, 'HITSTOP_DURATION': 0.07,

            # Ритм: окно сужено с 0.18 до 0.10 (было ~72% времени «в такт», стало ~40%)
            'BEAT_INTERVAL': 0.5, 'BEAT_WINDOW': 0.10,

            'POWERUP_SPEED': 50.0, 'POWERUP_RADIUS': 11,
            'POWERUP_LIFETIME': 12.0, 'POWERUP_HEAL_AMOUNT': 30,
            'POWERUP_INVULN_DURATION': 5.0, 'POWERUP_SPAWN_CHANCE': 0.12,

            'HP_BAR_WIDTH': 280, 'HP_BAR_HEIGHT': 18, 'HP_BAR_MARGIN': 20,
            'CRYSTAL_STAGE_1': 3, 'CRYSTAL_STAGE_2': 7,

            'RESONANCE_RADIUS': 100.0, 'RESONANCE_LIFETIME': 8.0,
            'RESONANCE_KILL_THRESHOLD': 3, 'RESONANCE_SPEED_BOOST': 0.25,
            'RESONANCE_FIRE_RATE_MULT': 0.7,
            'RESONANCE_DAMAGE_BOOST': 0.50, 'RESONANCE_DRIFT_SPEED': 20.0,

            # Экономика Chroma Points (за забег)
            'CP_PER_WAVE': 3, 'CP_PER_10_KILLS': 1, 'CP_PER_REFRACTION': 2,
            'CP_PER_BOSS': 25, 'CP_DAILY_FIRST_RUN': 25, 'CP_RECORD_BONUS': 30,

            'SPATIAL_CELL_SIZE': 100,
        }

    def _load(self) -> None:
        try:
            if os.path.exists(self._config_path):
                GameConfig._file_mtime = os.path.getmtime(self._config_path)
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if key in self._defaults:
                            default = self._defaults[key]
                            if isinstance(default, tuple) and isinstance(value, list):
                                value = tuple(value)
                            self._values[key] = value
        except (OSError, ValueError) as e:
            logger.warning(f"Config load error: {e}")

    def check_for_changes(self) -> bool:
        try:
            if os.path.exists(self._config_path):
                mtime = os.path.getmtime(self._config_path)
                if mtime > GameConfig._file_mtime:
                    GameConfig._file_mtime = mtime
                    self._load()
                    return True
        except OSError:
            pass
        return False

    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            raise AttributeError(name)
        if name in self._values:
            return self._values[name]
        raise AttributeError(f"Config has no attribute '{name}'")

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set_override(self, key: str, value: Any) -> None:
        """Для тестов и режимов: временная замена параметра."""
        self._values[key] = value


CFG = GameConfig()

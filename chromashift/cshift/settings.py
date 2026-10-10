"""Глобальные настройки (saves/settings.json) и ввод: клавиатура, мышь, геймпад."""
import copy
import json
import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .config import MODES
from .utils import set_palette, set_visual, vec_length, vec_normalize

logger = logging.getLogger('ChromaShift')

DEFAULT_KEYS = {
    'up': 'w', 'down': 's', 'left': 'a', 'right': 'd',
    'mode_red': '1', 'mode_blue': '2', 'mode_green': '3',
    'cycle_next': 'e', 'cycle_prev': 'q', 'radial': 'left shift',
    'dash': 'space', 'fire': 'j', 'pause': 'escape',
}
ACTION_NAMES = {
    'up': 'Вверх', 'down': 'Вниз', 'left': 'Влево', 'right': 'Вправо',
    'mode_red': 'Режим RED', 'mode_blue': 'Режим BLUE', 'mode_green': 'Режим GREEN',
    'cycle_next': 'Следующий цвет', 'cycle_prev': 'Предыдущий цвет', 'radial': 'Радиальное меню (удерж.)',
    'dash': 'Рывок', 'fire': 'Огонь (клавиша)', 'pause': 'Пауза',
}

PHYSICS_PRESETS = {
    'standard': {'RED': 1.0, 'BLUE': 1.0, 'GREEN': 1.0},
    'arcade': {'RED': 1.1, 'BLUE': 1.15, 'GREEN': 1.1},
    'heavy': {'RED': 0.9, 'BLUE': 0.85, 'GREEN': 0.9},
}

DEFAULTS: Dict[str, Any] = {
    'version': 1,
    'keys': dict(DEFAULT_KEYS),
    'mouse_wheel_switch': True,
    'radial_menu': True,
    'fire_mode': 'hold',            # hold / toggle / auto
    'dash_direction': 'aim',        # aim / move
    'difficulty': 'normal',
    'custom_difficulty': {'enemy_hp': 1.0, 'enemy_damage': 1.0, 'enemy_speed': 1.0, 'refraction_window': 1.0},
    'dda': True,
    'adaptive_windows': True,
    'assist_prompt': True,
    'palette': 'default',
    'shapes': False,
    'shake': 1.0,
    'flash': 1.0,
    'glow': 1.0,
    'ui_scale': 1.0,
    'physics_preset': 'standard',
    'physics': dict(PHYSICS_PRESETS['standard']),
    'sound_pack': 'studio',
    'volume': 0.8,
    'music': True,
    'bg_theme': 'grid',
    'show_fps': False,
    'fullscreen': False,
    'tips': True,
    'gamepad_deadzone': 0.25,
    'aim_assist': 0.3,
    'last_profile': 0,
}

CHOICES = {
    'fire_mode': ['hold', 'toggle', 'auto'],
    'dash_direction': ['aim', 'move'],
    'difficulty': ['story', 'normal', 'master', 'custom'],
    'palette': ['default', 'deuteranopia', 'protanopia', 'tritanopia', 'high_contrast'],
    'physics_preset': ['standard', 'arcade', 'heavy', 'custom'],
    'sound_pack': ['studio', 'retro'],
    'bg_theme': ['grid', 'stars', 'waves', 'minimal'],
}
CHOICE_NAMES = {
    'hold': 'Удержание', 'toggle': 'Переключение', 'auto': 'Автоогонь', 'aim': 'По прицелу', 'move': 'По движению',
    'story': 'Сюжет', 'normal': 'Норма', 'master': 'Мастер', 'custom': 'Своя',
    'default': 'Стандартная', 'deuteranopia': 'Дейтеранопия', 'protanopia': 'Протанопия',
    'tritanopia': 'Тританопия', 'high_contrast': 'Высокий контраст',
    'standard': 'Стандарт', 'arcade': 'Аркада', 'heavy': 'Тяжёлая',
    'studio': 'Студийный (WAV)', 'retro': 'Ретро (синтез)',
    'grid': 'Сетка', 'stars': 'Звёзды', 'waves': 'Волны', 'minimal': 'Минимализм',
}
RANGES = {
    'shake': (0.0, 1.0, 0.25), 'flash': (0.0, 1.0, 0.25), 'glow': (0.3, 1.5, 0.1), 'ui_scale': (0.8, 1.4, 0.1),
    'volume': (0.0, 1.0, 0.1), 'gamepad_deadzone': (0.1, 0.5, 0.05), 'aim_assist': (0.0, 1.0, 0.1),
}


class Settings:
    def __init__(self, path: Optional[str] = None):
        from .progression import saves_dir
        self.path = path or os.path.join(saves_dir(), 'settings.json')
        self.data: Dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        if key == 'physics_preset' and value in PHYSICS_PRESETS:
            self.data['physics'] = dict(PHYSICS_PRESETS[value])
        self.apply_visuals()

    def load(self) -> None:
        if not os.path.exists(self.path):
            self.apply_visuals()
            return
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError('settings.json должен быть объектом')
            for k, v in loaded.items():
                if k in DEFAULTS and type(v) is type(DEFAULTS[k]) or (k in DEFAULTS and isinstance(DEFAULTS[k], float) and isinstance(v, (int, float))):
                    self.data[k] = v
            keys = dict(DEFAULT_KEYS)
            keys.update({a: k for a, k in self.data.get('keys', {}).items() if a in DEFAULT_KEYS and self.key_code(k)})
            self.data['keys'] = keys
            for k, vals in CHOICES.items():
                if self.data[k] not in vals:
                    self.data[k] = DEFAULTS[k]
            for k, (lo, hi, _) in RANGES.items():
                self.data[k] = max(lo, min(hi, float(self.data[k])))
        except (OSError, ValueError, TypeError) as e:
            logger.warning(f'settings.json не читается, используются значения по умолчанию: {e}')
        self.apply_visuals()

    def save(self) -> None:
        from .progression import atomic_write_json
        try:
            atomic_write_json(self.path, self.data)
        except OSError as e:
            logger.error(f'Не удалось сохранить настройки: {e}')

    def apply_visuals(self) -> None:
        set_palette(self.data['palette'])
        set_visual(glow=self.data['glow'], shake=self.data['shake'], flash=self.data['flash'],
                   ui_scale=self.data['ui_scale'], shapes=self.data['shapes'])

    def cycle(self, key: str, step: int = 1) -> None:
        vals = CHOICES[key]
        i = vals.index(self.data[key]) if self.data[key] in vals else 0
        self.set(key, vals[(i + step) % len(vals)])

    def nudge(self, key: str, step: int) -> None:
        lo, hi, inc = RANGES[key]
        self.set(key, round(max(lo, min(hi, float(self.data[key]) + inc * step)), 3))

    @staticmethod
    def key_code(name: str) -> Optional[int]:
        try:
            return pygame.key.key_code(name)
        except (ValueError, TypeError):
            return None

    def bind(self, action: str, keycode: int) -> None:
        name = pygame.key.name(keycode)
        # Снимаем эту клавишу с других действий, чтобы не было конфликтов
        for a, k in list(self.data['keys'].items()):
            if k == name and a != action:
                self.data['keys'][a] = self.data['keys'][action]
        self.data['keys'][action] = name


# =====================================================================
# ВВОД
# =====================================================================
# Раскладка Xbox в SDL: A=0 B=1 X=2 Y=3 LB=4 RB=5 Back=6 Start=7
PAD_A, PAD_B, PAD_X, PAD_Y, PAD_LB, PAD_RB, PAD_BACK, PAD_START = range(8)


class InputManager:
    """Превращает события в действия. Непрерывное состояние: move, aim, fire."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.joysticks: Dict[int, Any] = {}
        self.fire_toggled = False
        self.radial_open = False
        self.radial_choice: Optional[str] = None
        self.using_pad = False
        self.pad_aim = (0.0, -1.0)
        self.waiting_bind: Optional[str] = None
        self.virtual_move: Optional[Tuple[float, float]] = None  # для тестов/бота
        self.virtual_aim: Optional[Tuple[float, float]] = None
        self.virtual_fire: Optional[bool] = None
        self.mouse_pos = pygame.mouse.get_pos  # Game подменяет на преобразование окна → логических координат
        try:
            pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                self._add_pad(i)
        except pygame.error:
            pass

    def _add_pad(self, index: int) -> None:
        try:
            js = pygame.joystick.Joystick(index)
            js.init()
            self.joysticks[js.get_instance_id()] = js
        except pygame.error as e:
            logger.warning(f'Геймпад не инициализирован: {e}')

    def _key(self, action: str) -> Optional[int]:
        return Settings.key_code(self.settings.data['keys'].get(action, ''))

    def _axis(self, js: Any, i: int) -> float:
        try:
            v = js.get_axis(i) if js.get_numaxes() > i else 0.0
        except pygame.error:
            return 0.0
        dz = self.settings.get('gamepad_deadzone', 0.25)
        return 0.0 if abs(v) < dz else (v - math.copysign(dz, v)) / (1 - dz)

    def process_event(self, event: Any, in_game: bool) -> List[str]:
        """Возвращает список действий. В меню: up/down/left/right/confirm/back/delete/char:X."""
        acts: List[str] = []
        if event.type == pygame.JOYDEVICEADDED:
            self._add_pad(event.device_index)
            return acts
        if event.type == pygame.JOYDEVICEREMOVED:
            self.joysticks.pop(event.instance_id, None)
            return acts
        if event.type == pygame.KEYDOWN:
            self.using_pad = False
            if self.waiting_bind:
                if event.key != pygame.K_ESCAPE:
                    self.settings.bind(self.waiting_bind, event.key)
                self.waiting_bind = None
                return ['bound']
            if in_game:
                k = event.key
                for action in ('mode_red', 'mode_blue', 'mode_green', 'cycle_next', 'cycle_prev', 'dash', 'pause'):
                    if k == self._key(action):
                        acts.append(action)
                if k == self._key('fire') and self.settings.get('fire_mode') == 'toggle':
                    self.fire_toggled = not self.fire_toggled
                if k == self._key('radial') and self.settings.get('radial_menu'):
                    self.radial_open = True
                    self.radial_choice = None
                if k == pygame.K_F11:
                    acts.append('fullscreen')
                if k == pygame.K_F3:
                    acts.append('fps')
                if k == pygame.K_g:
                    acts.append('god')
            else:
                nav = {pygame.K_UP: 'up', pygame.K_w: 'up', pygame.K_DOWN: 'down', pygame.K_s: 'down',
                       pygame.K_LEFT: 'left', pygame.K_a: 'left', pygame.K_RIGHT: 'right', pygame.K_d: 'right',
                       pygame.K_RETURN: 'confirm', pygame.K_KP_ENTER: 'confirm', pygame.K_SPACE: 'confirm',
                       pygame.K_ESCAPE: 'back', pygame.K_BACKSPACE: 'delete', pygame.K_TAB: 'tab',
                       pygame.K_r: 'reset', pygame.K_F11: 'fullscreen', pygame.K_PAGEUP: 'pageup',
                       pygame.K_PAGEDOWN: 'pagedown'}
                if event.key in nav:
                    acts.append(nav[event.key])
                if event.unicode and event.unicode.isprintable() and event.key not in (pygame.K_RETURN, pygame.K_TAB):
                    acts.append('char:' + event.unicode)
        elif event.type == pygame.KEYUP:
            if in_game and event.key == self._key('radial') and self.radial_open:
                self.radial_open = False
                if self.radial_choice:
                    acts.append('mode_' + self.radial_choice.lower())
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.using_pad = False
            if in_game:
                if event.button == 1 and self.settings.get('fire_mode') == 'toggle':
                    self.fire_toggled = not self.fire_toggled
                if event.button == 3:
                    acts.append('dash')
                if event.button in (4, 5) and self.settings.get('mouse_wheel_switch'):
                    acts.append('cycle_prev' if event.button == 4 else 'cycle_next')
            else:
                if event.button == 1:
                    acts.append('click')
                elif event.button == 4:
                    acts.append('up')
                elif event.button == 5:
                    acts.append('down')
        elif event.type == pygame.MOUSEWHEEL and in_game and self.settings.get('mouse_wheel_switch'):
            pass  # обрабатывается через MOUSEBUTTONDOWN 4/5 (совместимость pygame 2)
        elif event.type == pygame.JOYBUTTONDOWN:
            self.using_pad = True
            b = event.button
            if in_game:
                acts += {PAD_A: ['dash'], PAD_X: ['mode_red'], PAD_B: ['mode_blue'], PAD_Y: ['mode_green'],
                         PAD_LB: ['cycle_prev'], PAD_RB: ['cycle_next'], PAD_START: ['pause']}.get(b, [])
            else:
                acts += {PAD_A: ['confirm'], PAD_B: ['back'], PAD_START: ['confirm'], PAD_BACK: ['back'],
                         PAD_LB: ['left'], PAD_RB: ['right'], PAD_X: ['reset']}.get(b, [])
        elif event.type == pygame.JOYHATMOTION:
            self.using_pad = True
            x, y = event.value
            if y == 1:
                acts.append('up')
            elif y == -1:
                acts.append('down')
            if x == -1:
                acts.append('left')
            elif x == 1:
                acts.append('right')
        elif event.type == pygame.JOYAXISMOTION and not in_game and event.axis in (0, 1):
            # Навигация стиком в меню (с гистерезисом)
            v = event.value
            key = f'_axis_latch_{event.axis}'
            latched = getattr(self, key, False)
            if abs(v) > 0.6 and not latched:
                setattr(self, key, True)
                acts.append(('left' if v < 0 else 'right') if event.axis == 0 else ('up' if v < 0 else 'down'))
            elif abs(v) < 0.3:
                setattr(self, key, False)
        return acts

    def move_vector(self) -> Tuple[float, float]:
        if self.virtual_move is not None:
            return self.virtual_move
        keys = pygame.key.get_pressed()
        dx = dy = 0.0

        def pressed(action: str) -> bool:
            code = self._key(action)
            try:
                return code is not None and bool(keys[code])
            except IndexError:
                return False
        if pressed('left') or keys[pygame.K_LEFT]:
            dx -= 1
        if pressed('right') or keys[pygame.K_RIGHT]:
            dx += 1
        if pressed('up') or keys[pygame.K_UP]:
            dy -= 1
        if pressed('down') or keys[pygame.K_DOWN]:
            dy += 1
        for js in self.joysticks.values():
            ax, ay = self._axis(js, 0), self._axis(js, 1)
            if abs(ax) + abs(ay) > 0:
                dx, dy = ax, ay
                self.using_pad = True
        return dx, dy

    def aim_point(self, player: Any, enemies: List[Any]) -> Tuple[float, float]:
        if self.virtual_aim is not None:
            return self.virtual_aim
        if self.using_pad and self.joysticks:
            js = next(iter(self.joysticks.values()))
            rx, ry = self._axis(js, 2), self._axis(js, 3)
            if js.get_numaxes() >= 6 and abs(rx) + abs(ry) < 0.01:
                rx, ry = self._axis(js, 3), self._axis(js, 4)
            if vec_length(rx, ry) > 0.2:
                self.pad_aim = vec_normalize(rx, ry)
            ax, ay = self.pad_aim
            assist = self.settings.get('aim_assist', 0.3)
            if assist > 0:
                best, best_dot = None, math.cos(0.35 + 0.3 * assist)
                for e in enemies:
                    ex, ey = vec_normalize(e.x - player.x, e.y - player.y)
                    dot = ex * ax + ey * ay
                    if dot > best_dot:
                        best, best_dot = (ex, ey), dot
                if best:
                    ax = ax + (best[0] - ax) * assist
                    ay = ay + (best[1] - ay) * assist
                    ax, ay = vec_normalize(ax, ay)
            return player.x + ax * 200, player.y + ay * 200
        return self.mouse_pos()

    def fire_held(self) -> bool:
        if self.virtual_fire is not None:
            return self.virtual_fire
        mode = self.settings.get('fire_mode', 'hold')
        if mode == 'auto':
            return True
        if mode == 'toggle':
            return self.fire_toggled
        try:
            if pygame.mouse.get_pressed()[0]:
                return True
            code = self._key('fire')
            if code is not None and pygame.key.get_pressed()[code]:
                return True
        except (pygame.error, IndexError):
            pass
        for js in self.joysticks.values():
            if js.get_numaxes() > 5 and js.get_axis(5) > 0.3:
                return True
            if js.get_numaxes() > 3 and vec_length(self._axis(js, 2), self._axis(js, 3)) > 0.5:
                return True
        return False

    def update_radial(self, player_pos: Tuple[float, float], aim: Tuple[float, float]) -> None:
        """Радиальное меню: выбор сектора направлением прицела, применяется при отпускании."""
        if not self.radial_open:
            return
        dx, dy = aim[0] - player_pos[0], aim[1] - player_pos[1]
        if vec_length(dx, dy) < 25:
            self.radial_choice = None
            return
        ang = (math.degrees(math.atan2(dy, dx)) + 90) % 360  # 0 = вверх
        self.radial_choice = MODES[int(((ang + 60) % 360) // 120)]


def radial_sectors() -> List[Tuple[str, float]]:
    """Центральные углы секторов радиального меню (в радианах, экранные координаты)."""
    out = []
    for i, m in enumerate(MODES):
        out.append((m, math.radians(i * 120 - 90)))
    return out

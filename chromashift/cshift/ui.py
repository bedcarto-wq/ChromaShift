"""Интерфейс ChromaShift 0.7.0: HUD, отрисовка мира и все экраны меню."""
import math
from typing import Any, Callable, Dict, List, Optional, Tuple

import pygame

from .config import ALL_MODES, CFG, GAME_VERSION, MODES
from .entities import MODE_SHAPES, ENEMY_NAMES, ELITE_MODS, BossEnemy, draw_shape
from .progression import (ACHIEVEMENTS, ARCHETYPES, ARTIFACTS, BRANCHES, COSMETICS, DIFFICULTIES, HULLS,
                          MODULES, PROFILE_SLOTS, RISKS, TENSION_LEVELS, UPGRADES, Profile, active_synergies,
                          branch_spent, challenge_setup, loadout_energy, node_status, preview_node)
from .settings import ACTION_NAMES, CHOICE_NAMES, radial_sectors
from .hires import get_scale, layer
from .utils import clamp, color_lerp, get_font, mode_color, visual

FONT = 'arial'


# =====================================================================
# ПРИМИТИВЫ
# =====================================================================
def text(surf: pygame.Surface, s: str, size: int, color: Tuple[int, int, int], pos: Tuple[float, float],
         align: str = 'left', bold: bool = False, scaled: bool = True) -> pygame.Rect:
    img = get_font(FONT, size, bold, scaled).render(str(s), True, color)
    r = img.get_rect()
    if align == 'center':
        r.midtop = (int(pos[0]), int(pos[1]))
    elif align == 'right':
        r.topright = (int(pos[0]), int(pos[1]))
    else:
        r.topleft = (int(pos[0]), int(pos[1]))
    surf.blit(img, r)
    return r


def wrap(s: str, size: int, width: int) -> List[str]:
    font = get_font(FONT, size, False, True)
    lines: List[str] = []
    for para in str(s).split('\n'):
        cur = ''
        for word in para.split(' '):
            trial = (cur + ' ' + word).strip()
            if font.size(trial)[0] <= width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def text_block(surf: pygame.Surface, s: str, size: int, color: Tuple[int, int, int], x: int, y: int,
               width: int, line_gap: int = 4) -> int:
    h = get_font(FONT, size, False, True).get_height()
    for line in wrap(s, size, width):
        text(surf, line, size, color, (x, y))
        y += h + line_gap
    return y


_PANEL_CACHE: Dict[Tuple[int, int, int], pygame.Surface] = {}


def panel(surf: pygame.Surface, rect: Tuple[int, int, int, int], alpha: int = 200,
          border: Optional[Tuple[int, int, int]] = None) -> None:
    x, y, w, h = [int(v) for v in rect]
    key = (w, h, alpha, get_scale())
    s = _PANEL_CACHE.get(key)
    if s is None:
        if len(_PANEL_CACHE) > 64:
            _PANEL_CACHE.clear()
        s = layer((max(1, w), max(1, h)), pygame.SRCALPHA)
        s.fill((14, 18, 30, alpha))
        _PANEL_CACHE[key] = s
    surf.blit(s, (x, y))
    pygame.draw.rect(surf, border or (60, 70, 100), (x, y, w, h), 1)


def bar(surf: pygame.Surface, rect: Tuple[int, int, int, int], frac: float, color: Tuple[int, int, int],
        bg: Tuple[int, int, int] = (35, 40, 58)) -> None:
    x, y, w, h = [int(v) for v in rect]
    pygame.draw.rect(surf, bg, (x, y, w, h))
    pygame.draw.rect(surf, color, (x, y, int(w * clamp(frac, 0, 1)), h))
    pygame.draw.rect(surf, (90, 100, 130), (x, y, w, h), 1)


def mode_label(mode: str) -> str:
    return mode


# =====================================================================
# ФОН И МИР
# =====================================================================
def draw_background(game: Any, surf: pygame.Surface, menu: bool = False) -> None:
    surf.fill(CFG.COLOR_BG)
    theme = game.settings.get('bg_theme', 'grid')
    t = game.menu_time if menu else game.game_time
    wave = game.director.wave if game.in_run else 1
    if theme == 'minimal':
        return
    if theme == 'stars':
        for i, (x, y, z) in enumerate(game._stars):
            yy = (y + t * 30 * z) % CFG.SCREEN_HEIGHT
            c = int(80 + 150 * z)
            surf.fill((c, c, min(255, c + 30)), (int(x), int(yy), 2 if z > 0.7 else 1, 2 if z > 0.7 else 1))
        return
    if wave < 6:
        grid = CFG.COLOR_BG2
    elif wave < 11:
        grid = (40, 22, 38)
    else:
        grid = color_lerp(CFG.COLOR_BG2, CFG.COLOR_ACCENT, (0.5 + 0.5 * math.sin(t * 2)) * 0.3)
    if theme == 'waves':
        for k in range(9):
            pts = [(x, CFG.SCREEN_HEIGHT * (k + 1) / 10 + math.sin(x / 120 + t + k) * 14)
                   for x in range(0, CFG.SCREEN_WIDTH + 40, 40)]
            pygame.draw.lines(surf, grid, False, pts, 1)
        return
    size = 60
    off = int(t * 20) % size
    for x in range(-size + off, CFG.SCREEN_WIDTH + size, size):
        pygame.draw.line(surf, grid, (x, 0), (x, CFG.SCREEN_HEIGHT), 1)
    for y in range(-size + off, CFG.SCREEN_HEIGHT + size, size):
        pygame.draw.line(surf, grid, (0, y), (CFG.SCREEN_WIDTH, y), 1)


def clear_ui_caches() -> None:
    """Вызывается при смене масштаба рендера."""
    _PANEL_CACHE.clear()


def _dark_overlay(game: Any) -> pygame.Surface:
    if game._dark_surf is None or getattr(game._dark_surf, 's', 1.0) != get_scale():
        r = 280
        s = layer((r * 2, r * 2), pygame.SRCALPHA)
        s.fill((0, 0, 0, 235))
        for i in range(r, 0, -4):
            a = int(235 * (i / r) ** 2)
            pygame.draw.circle(s, (0, 0, 0, a), (r, r), i)
        game._dark_surf = s
    return game._dark_surf


def draw_world(game: Any, surf: pygame.Surface) -> None:
    draw_background(game, surf)
    t = game.game_time
    for z in getattr(game, 'paints', ()):
        z.draw(surf)
    for r in game.resonances:
        r.draw(surf)
    for pt in getattr(game, 'portals', ()):
        pt.draw(surf, t)
    cm = getattr(game, 'color_mech', None)
    if cm is not None:
        for w in cm.wells:
            k = 0.5 + 0.5 * math.sin(t * 5)
            pygame.draw.circle(surf, color_lerp(CFG.COLOR_BG, mode_color('BLUE'), 0.3 + 0.3 * k),
                               (int(w.x), int(w.y)), int(w.radius), 1)
            pygame.draw.circle(surf, mode_color('BLUE'), (int(w.x), int(w.y)), int(10 + 6 * k), 2)
    for mn in getattr(game, 'mines', ()):
        mn.draw(surf, t)
    for pl in game.pillars:
        pl.draw(surf)
    for h in game.hazards:
        h.draw(surf)
    for d in game.decoys:
        d.draw(surf)
    # Телеграф спавна
    for tg in game.director.telegraphs:
        if tg['delay'] > 0:
            continue
        k = clamp(tg['t'] / max(0.01, game.director.telegraph_time()), 0, 1)
        r = int(22 + 20 * k) if tg['kind'] != 'boss' else int(50 + 30 * k)
        col = (255, 140, 220) if tg['elite'] else CFG.COLOR_DANGER
        if tg['shield']:
            col = mode_color(tg['shield'])
        pulse = 0.5 + 0.5 * math.sin(t * 18)
        pygame.draw.circle(surf, color_lerp(CFG.COLOR_BG, col, 0.4 + 0.6 * pulse), (int(tg['x']), int(tg['y'])), r, 2)
        pygame.draw.arc(surf, col, (tg['x'] - 14, tg['y'] - 14, 28, 28), 0, (1 - k) * 2 * math.pi, 3)
    for pu in game.powerups:
        pu.draw(surf)
    for b in game.enemy_bullets:
        b.draw(surf)
    for b in game.player_bullets:
        b.draw(surf)
    for e in game.enemies:
        e.draw(surf)
        e.draw_overlay(surf, t)
        if e.stun_t > 0:
            pygame.draw.circle(surf, CFG.COLOR_ACCENT, (int(e.x), int(e.y)), int(e.radius + 5), 1)
        if e.is_leader:
            draw_shape(surf, 'triangle', CFG.COLOR_ACCENT, e.x, e.y - e.radius - 9, 5, -math.pi / 2, 0)
    for wl in getattr(game, 'walls', ()):
        wl.draw(surf)
    for bm in getattr(game, 'beams', ()):
        bm.draw(surf)
    p = game.player
    if game.dying_timer < 0 and game.in_run:
        p.draw(surf, t)
        game.parry_indicator.draw(surf, p.x, p.y)
        game.crystal.draw(surf, p.x, p.y, p.mode, game.combo, t)
    game.particles.draw(surf)
    dark_on = ((game.director.special == 'darkness' and game.director.state == 'active')
               or (getattr(game.mods, 'always_dark', False) and game.in_run and not game.is_training))
    if dark_on:
        dark = _dark_overlay(game)
        r = dark.get_width() // 2
        cover = layer((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.SRCALPHA)
        cover.fill((0, 0, 0, 235))
        cover.fill((0, 0, 0, 0), (int(p.x - r), int(p.y - r), r * 2, r * 2))
        surf.blit(cover, (0, 0))
        surf.blit(dark, (int(p.x - r), int(p.y - r)))
    # Индикаторы угроз за экраном/за пределами видимости
    for e in game.enemies:
        if not e.alive:
            continue
        hidden = dark_on and math.hypot(e.x - p.x, e.y - p.y) > 260
        off = e.x < 0 or e.y < 0 or e.x > CFG.SCREEN_WIDTH or e.y > CFG.SCREEN_HEIGHT
        if hidden or off:
            ang = math.atan2(e.y - p.y, e.x - p.x)
            ex = clamp(p.x + math.cos(ang) * 1000, 18, CFG.SCREEN_WIDTH - 18)
            ey = clamp(p.y + math.sin(ang) * 1000, 18, CFG.SCREEN_HEIGHT - 18)
            if hidden and not off:
                ex, ey = p.x + math.cos(ang) * 240, p.y + math.sin(ang) * 240
            pts = [(ex + math.cos(ang) * 10, ey + math.sin(ang) * 10),
                   (ex + math.cos(ang + 2.5) * 8, ey + math.sin(ang + 2.5) * 8),
                   (ex + math.cos(ang - 2.5) * 8, ey + math.sin(ang - 2.5) * 8)]
            pygame.draw.polygon(surf, CFG.COLOR_DANGER, pts)
    for ft in game.floating_texts:
        ft.draw(surf)
    # Радиальное меню
    if game.input.radial_open:
        for m, ang in radial_sectors():
            cx, cy = p.x + math.cos(ang) * 70, p.y + math.sin(ang) * 70
            sel = game.input.radial_choice == m
            pygame.draw.circle(surf, mode_color(m), (int(cx), int(cy)), 26 if sel else 20, 0 if sel else 3)
            text(surf, m, 14, CFG.COLOR_TEXT, (cx, cy + 28), 'center', True)
    if game.flash_alpha > 0:
        fs = layer((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.SRCALPHA)
        fs.fill((*game.flash_color, int(255 * clamp(game.flash_alpha, 0, 1))))
        surf.blit(fs, (0, 0))


# =====================================================================
# HUD
# =====================================================================
class HUD:
    def __init__(self, game: Any):
        self.game = game

    def draw(self, surf: pygame.Surface) -> None:
        g = self.game
        p = g.player
        m = CFG.HP_BAR_MARGIN
        # HP / щиты / рывок
        bar(surf, (m, m, CFG.HP_BAR_WIDTH, CFG.HP_BAR_HEIGHT), p.hp / max(1, p.max_hp),
            CFG.COLOR_SUCCESS if p.hp > p.max_hp * 0.3 else CFG.COLOR_DANGER)
        text(surf, f"{int(max(0, p.hp))}/{p.max_hp}", 14, CFG.COLOR_TEXT, (m + 6, m + 1))
        y = m + CFG.HP_BAR_HEIGHT + 6
        for i in range(p.shield_charges):
            pygame.draw.circle(surf, CFG.COLOR_PRIMARY, (m + 8 + i * 18, y + 7), 7, 2)
        for i in range(p.revives):
            pygame.draw.circle(surf, CFG.COLOR_ACCENT, (m + 8 + (p.shield_charges + i) * 18, y + 7), 7)
        y += 18
        dash_frac = 1 - clamp(p.dash_cooldown / max(0.01, p.dash_cooldown_max), 0, 1)
        bar(surf, (m, y, 120, 6), dash_frac, CFG.COLOR_ACCENT if dash_frac >= 1 else (120, 110, 70))
        text(surf, 'Рывок', 12, (170, 180, 200), (m + 126, y - 4))
        y += 14
        # Режимы
        keys = g.settings.get('keys', {})
        for i, mode in enumerate(g.available_modes() if hasattr(g, 'available_modes') else MODES):
            x = m + i * 46
            sel = p.mode == mode
            col = mode_color(mode)
            if visual('shapes'):
                draw_shape(surf, MODE_SHAPES[mode], col, x + 16, y + 16, 12 if sel else 9, 0, 0 if sel else 2)
            else:
                pygame.draw.circle(surf, col, (x + 16, y + 16), 13 if sel else 9, 0 if sel else 2)
            text(surf, keys.get(f'mode_{mode.lower()}', str(i + 1)).upper(), 11, (170, 180, 200), (x + 16, y + 32), 'center')
        y += 50
        cm = getattr(g, 'color_mech', None)
        if cm is not None and not g.settings.get('hud_compact', False):
            # Перегрузка, навык цвета (R), способность (F), осколки
            if cm.overload_t > 0:
                bar(surf, (m, y, 120, 6), cm.overload_t / (5.0 + g.mods.overload_duration_add), CFG.COLOR_ACCENT)
                text(surf, 'ПЕРЕГРУЗКА', 12, CFG.COLOR_ACCENT, (m + 126, y - 4), bold=True)
            else:
                bar(surf, (m, y, 120, 6), cm.overload / CFG.OVERLOAD_MAX, (200, 170, 255))
                text(surf, 'Перегрузка', 12, (170, 180, 200), (m + 126, y - 4))
            y += 14
            from .mechanics import ABILITIES, COLOR_SKILLS
            skill_max = CFG.COLOR_SKILL_COOLDOWN * g.mods.skill_cd_mult
            bar(surf, (m, y, 120, 6), 1 - clamp(cm.skill_cd / max(0.01, skill_max), 0, 1), mode_color(p.mode))
            text(surf, f"{keys.get('skill', 'r').upper()}: {COLOR_SKILLS[p.mode][0]}", 12, (170, 180, 200), (m + 126, y - 4))
            y += 14
            ab = ABILITIES.get(cm.ability, ABILITIES['nova'])
            bar(surf, (m, y, 120, 6), 1 - clamp(cm.ability_cd / max(0.01, ab['cd'] * g.mods.ability_cd_mult), 0, 1),
                CFG.COLOR_PRIMARY)
            text(surf, f"{keys.get('ability', 'f').upper()}: {ab['name']}", 12, (170, 180, 200), (m + 126, y - 4))
            y += 14
            text(surf, f"Осколки: {cm.shards}", 12, (200, 190, 255), (m, y))
            y += 18
        if p.color_lock_t > 0 and p.color_lock_t < 9000:
            text(surf, f"ЦВЕТ ЗАБЛОКИРОВАН {p.color_lock_t:.1f} c", 14, (170, 170, 190), (m, y), bold=True)
            y += 18
        if p.impulse_active:
            text(surf, f"ИМПУЛЬС {p.impulse_timer:.1f} c", 16, mode_color(p.mode), (m, y), bold=True)
            y += 20
        if g.echo_chamber_active:
            text(surf, f"ЭХО-КАМЕРА {g.echo_chamber_timer:.1f} c", 16, CFG.COLOR_ACCENT, (m, y), bold=True)
            y += 20
        if p.in_resonance:
            text(surf, 'РЕЗОНАНС', 16, mode_color(p.mode), (m, y), bold=True)
            y += 20
        # Очки, комбо, волна
        W = CFG.SCREEN_WIDTH
        text(surf, f"{int(g.score):,}".replace(',', ' '), 28, CFG.COLOR_TEXT, (W - m, m - 4), 'right', True)
        if g.combo > 1:
            text(surf, f"Комбо ×{g.combo}", 18, CFG.COLOR_ACCENT, (W - m, m + 30), 'right', True)
        d = g.director
        if g.is_training:
            text(surf, 'ТРЕНИРОВКА · Esc — меню', 18, CFG.COLOR_ACCENT, (W / 2, m), 'center', True)
        else:
            label = f"Волна {max(1, d.wave)}"
            if d.state == 'intermission' and d.wave > 0:
                label += f" · следующая через {max(0.0, d.timer):.0f}"
            text(surf, label, 18, CFG.COLOR_TEXT, (W / 2, m - 6), 'center', True)
            bar(surf, (W / 2 - 150, m + 18, 300, 6), d.progress(), CFG.COLOR_ACCENT)
            tags = []
            if g.run_type != 'standard':
                from .game import RUN_TYPES
                tags.append(RUN_TYPES[g.run_type])
            if g.tension:
                tags.append(f"Напряжение {g.tension}")
            if d.overheat:
                tags.append('ПЕРЕГРЕВ')
            if d.gamble:
                tags.append('СТАВКА')
            elif d.gamble_next:
                tags.append('Ставка на следующую волну')
            if d.tempo:
                tags.append('ТЕМП')
            if getattr(g, 'daily_rule', 'none') != 'none':
                from .progression import DAILY_RULES
                tags.append(DAILY_RULES[g.daily_rule][0])
            if g.run_type == 'blitz':
                tags.append(f"Осталось {int(g.blitz_left // 60)}:{int(g.blitz_left % 60):02d}")
            if d.special == 'survive' and d.state == 'active':
                tags.append(f"Продержитесь ещё {max(0.0, d.survive_left):.0f} c")
            if d.state == 'intermission' and d.wave > 0:
                tags.append(f"{keys.get('gamble', 'b').upper()} — ставка")
            if tags:
                text(surf, ' · '.join(tags), 12, (180, 170, 140), (W / 2, m + 28), 'center')
            # Призрак рекорда
            ghost = g.profile.data['ghost'].get('wave_times', [])
            if ghost:
                gw = sum(1 for tt in ghost if tt <= g.game_time) + 1
                text(surf, f"Призрак рекорда: волна {gw}", 12, (150, 160, 190), (W - m, m + 54), 'right')
        # Босс
        boss = next((e for e in g.enemies if e.alive and (isinstance(e, BossEnemy) or getattr(e, 'boss_like', False))),
                    None)
        if boss is not None:
            bw = 520
            bx = W / 2 - bw / 2
            vm = boss.vulnerable_mode
            bar(surf, (bx, 52, bw, 12), max(0.0, boss.hp) / boss.max_hp, mode_color(vm) if vm else CFG.COLOR_DANGER)
            title = getattr(boss, 'title', None) or boss.name
            ph = getattr(boss, 'phase', 1)
            weak = f" · уязвим к {vm}" if vm else (' · сначала головы' if getattr(boss, 'heads', None)
                                                  and any(h.alive for h in boss.heads) else '')
            text(surf, f"{title} · фаза {ph}{weak}", 14, CFG.COLOR_TEXT, (W / 2, 66), 'center', True)
        # Такт
        since = g.game_time - g.beat_tracker.last_beat_time
        pulse = clamp(1 - since / CFG.BEAT_INTERVAL, 0, 1)
        on_beat = g.beat_tracker.is_on_beat(g.game_time)
        pygame.draw.circle(surf, CFG.COLOR_ACCENT if on_beat else (80, 80, 110),
                           (W - m - 10, CFG.SCREEN_HEIGHT - m - 10), int(5 + 5 * pulse), 0 if on_beat else 2)
        # Объявление волны
        if g.announcement:
            title, sub, tl = g.announcement
            a = clamp(tl / 0.6, 0, 1)
            col = color_lerp(CFG.COLOR_BG, CFG.COLOR_ACCENT, a)
            text(surf, title, 40, col, (W / 2, CFG.SCREEN_HEIGHT / 2 - 150), 'center', True)
            if sub:
                text(surf, sub, 20, color_lerp(CFG.COLOR_BG, CFG.COLOR_TEXT, a), (W / 2, CFG.SCREEN_HEIGHT / 2 - 100), 'center')
        # Итоги волны
        ws = getattr(g, 'wave_summary', None)
        if ws:
            s = ws[0]
            bx, by = W / 2 - 170, CFG.SCREEN_HEIGHT - 150
            panel(surf, (bx, by, 340, 110), 190)
            text(surf, f"Волна {s['wave']} пройдена", 18, CFG.COLOR_ACCENT, (W / 2, by + 8), 'center', True)
            text(surf, f"Время {s['time']} c (пар {s['par']} c) · убийств {s['kills']}", 14, CFG.COLOR_TEXT, (W / 2, by + 36), 'center')
            nd = 'без урона! ' if s['no_damage'] else f"урон {s['damage']} · "
            text(surf, f"{nd}+{s['score_bonus']} очков · +{s['cp']} CP", 14, CFG.COLOR_TEXT, (W / 2, by + 58), 'center')
            if s.get('next_overheat'):
                text(surf, 'Слишком легко — следующая волна перегрета', 13, CFG.COLOR_DANGER, (W / 2, by + 82), 'center')

    def draw_toasts(self, surf: pygame.Surface) -> None:
        y = CFG.SCREEN_HEIGHT - 60
        for msg, tl in reversed(self.game.toasts):
            lines = wrap(msg, 15, 420)
            h = 12 + 20 * len(lines)
            y -= h + 6
            a = clamp(tl / 0.5, 0, 1)
            panel(surf, (CFG.SCREEN_WIDTH - 470, y, 450, h), int(210 * a), CFG.COLOR_ACCENT)
            for i, line in enumerate(lines):
                text(surf, line, 15, CFG.COLOR_TEXT, (CFG.SCREEN_WIDTH - 460, y + 6 + i * 20))


# =====================================================================
# ФРЕЙМВОРК ЭКРАНОВ
# =====================================================================
class UIManager:
    def __init__(self, game: Any):
        self.game = game
        self.stack: List['Screen'] = []

    def top(self) -> Optional['Screen']:
        return self.stack[-1] if self.stack else None

    def push(self, screen: 'Screen') -> None:
        self.stack.append(screen)

    def pop(self) -> None:
        if self.stack:
            self.stack.pop()
        if not self.stack and not self.game.in_run:
            self.stack.append(MainMenu(self.game))

    def clear(self) -> None:
        self.stack = []

    def replace(self, screen: 'Screen') -> None:
        if self.stack:
            self.stack.pop()
        self.stack.append(screen)


class Screen:
    show_world = False

    def __init__(self, game: Any):
        self.game = game
        self.time = 0.0

    def update(self, dt: float) -> None:
        self.time += dt

    def on_action(self, act: str) -> None:
        if act == 'back':
            self.game.ui.pop()

    def on_mouse(self, pos: Tuple[float, float], click: bool) -> None:
        pass

    def draw(self, surf: pygame.Surface) -> None:
        pass

    def snd(self, name: str = 'ui_move') -> None:
        self.game.sound_manager.play(name, 0.35)


class Item:
    def __init__(self, label: Any, value: Optional[Callable[[], str]] = None, confirm: Optional[Callable[[], Any]] = None,
                 left: Optional[Callable[[], Any]] = None, right: Optional[Callable[[], Any]] = None,
                 desc: Any = '', enabled: Callable[[], bool] = lambda: True, color: Optional[Tuple[int, int, int]] = None):
        self.label = label
        self.value = value
        self.confirm = confirm
        self.left = left
        self.right = right
        self.desc = desc
        self.enabled = enabled
        self.color = color

    def get_label(self) -> str:
        return self.label() if callable(self.label) else self.label

    def get_desc(self) -> str:
        return self.desc() if callable(self.desc) else self.desc


class ListScreen(Screen):
    title = ''
    rows_visible = 12

    def __init__(self, game: Any):
        super().__init__(game)
        self.index = 0
        self.scroll = 0
        self.items: List[Item] = []
        self.row_rects: List[Tuple[int, pygame.Rect]] = []
        self.message = ''
        self.message_t = 0.0
        self.build()

    def build(self) -> None:
        pass

    def say(self, msg: str) -> None:
        self.message = msg
        self.message_t = 3.0

    def update(self, dt: float) -> None:
        super().update(dt)
        if self.message_t > 0:
            self.message_t -= dt

    def subtitle(self) -> str:
        return ''

    def move(self, step: int) -> None:
        if not self.items:
            return
        self.index = (self.index + step) % len(self.items)
        self.snd()

    def on_action(self, act: str) -> None:
        if not self.items:
            return super().on_action(act)
        it = self.items[self.index]
        if act == 'up':
            self.move(-1)
        elif act == 'down':
            self.move(1)
        elif act == 'pageup':
            self.index = max(0, self.index - self.rows_visible)
        elif act == 'pagedown':
            self.index = min(len(self.items) - 1, self.index + self.rows_visible)
        elif act == 'left' and it.left and it.enabled():
            it.left()
            self.snd()
        elif act == 'right' and it.right and it.enabled():
            it.right()
            self.snd()
        elif act == 'confirm':
            if not it.enabled():
                self.say('Недоступно')
                return
            if it.confirm:
                self.snd('ui_select')
                r = it.confirm()
                if isinstance(r, str):
                    self.say(r)
            elif it.right:
                it.right()
                self.snd()
        else:
            super().on_action(act)

    def on_mouse(self, pos: Tuple[float, float], click: bool) -> None:
        for i, r in self.row_rects:
            if r.collidepoint(pos):
                if i != self.index:
                    self.index = i
                if click:
                    self.on_action('confirm')
                return

    def list_rect(self) -> pygame.Rect:
        return pygame.Rect(80, 130, 560, 520)

    def draw_side(self, surf: pygame.Surface, rect: pygame.Rect, item: Optional[Item]) -> None:
        if item is None:
            return
        desc = item.get_desc()
        if desc:
            text_block(surf, desc, 17, (200, 210, 230), rect.x + 16, rect.y + 16, rect.w - 32)

    def draw(self, surf: pygame.Surface) -> None:
        W = CFG.SCREEN_WIDTH
        if self.show_world:
            veil = layer((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.SRCALPHA)
            veil.fill((5, 6, 12, 170))
            surf.blit(veil, (0, 0))
        text(surf, self.title, 40, CFG.COLOR_ACCENT, (80, 40), bold=True)
        sub = self.subtitle()
        if sub:
            text(surf, sub, 16, (170, 180, 205), (82, 92))
        lr = self.list_rect()
        panel(surf, (lr.x - 10, lr.y - 10, lr.w + 20, lr.h + 20), 150)
        row_h = 40
        self.rows_visible = max(1, lr.h // row_h)
        if self.index < self.scroll:
            self.scroll = self.index
        elif self.index >= self.scroll + self.rows_visible:
            self.scroll = self.index - self.rows_visible + 1
        self.row_rects = []
        for vis, i in enumerate(range(self.scroll, min(len(self.items), self.scroll + self.rows_visible))):
            it = self.items[i]
            r = pygame.Rect(lr.x, lr.y + vis * row_h, lr.w, row_h - 4)
            self.row_rects.append((i, r))
            sel = i == self.index
            if sel:
                pulse = 0.5 + 0.5 * math.sin(self.time * 6)
                pygame.draw.rect(surf, color_lerp((30, 36, 60), (60, 70, 110), pulse), r)
                pygame.draw.rect(surf, CFG.COLOR_ACCENT, r, 2)
            col = it.color or (CFG.COLOR_TEXT if it.enabled() else (110, 115, 135))
            text(surf, it.get_label(), 19, col, (r.x + 14, r.y + 7), bold=sel)
            if it.value:
                v = it.value()
                arrow = ('◀ ' + v + ' ▶') if (it.left or it.right) and sel else v
                text(surf, arrow, 17, CFG.COLOR_ACCENT if sel else (180, 190, 210), (r.right - 14, r.y + 9), 'right')
        if len(self.items) > self.rows_visible:
            frac = self.scroll / max(1, len(self.items) - self.rows_visible)
            pygame.draw.rect(surf, (90, 100, 140), (lr.right + 4, lr.y + int(frac * (lr.h - 30)), 4, 30))
        side = pygame.Rect(lr.right + 40, lr.y - 10, W - lr.right - 120, lr.h + 20)
        panel(surf, side, 150)
        self.draw_side(surf, side, self.items[self.index] if self.items else None)
        hint = '↑↓ — выбор · ←→ — изменить · Enter — подтвердить · Esc — назад'
        text(surf, hint, 14, (130, 140, 165), (80, CFG.SCREEN_HEIGHT - 34))
        if self.message_t > 0 and self.message:
            text(surf, self.message, 18, CFG.COLOR_ACCENT, (W / 2, CFG.SCREEN_HEIGHT - 70), 'center', True)


class ConfirmScreen(ListScreen):
    def __init__(self, game: Any, title: str, question: str, on_yes: Callable[[], Any], show_world: bool = False):
        self.question = question
        self.on_yes = on_yes
        self.title = title
        self.show_world = show_world
        super().__init__(game)

    def build(self) -> None:
        def yes() -> None:
            self.game.ui.pop()
            self.on_yes()
        self.items = [Item('Да', confirm=yes, desc=self.question), Item('Нет', confirm=self.game.ui.pop, desc=self.question)]
        self.index = 1


class TextInputScreen(Screen):
    def __init__(self, game: Any, title: str, initial: str, on_done: Callable[[str], Any], max_len: int = 16):
        super().__init__(game)
        self.title = title
        self.value = initial
        self.on_done = on_done
        self.max_len = max_len

    def on_action(self, act: str) -> None:
        if act.startswith('char:'):
            if len(self.value) < self.max_len:
                self.value += act[5:]
        elif act == 'delete':
            self.value = self.value[:-1]
        elif act == 'confirm':
            v = self.value.strip() or 'Пилот'
            self.game.ui.pop()
            self.on_done(v)
        elif act == 'back':
            self.game.ui.pop()

    def draw(self, surf: pygame.Surface) -> None:
        W, H = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        panel(surf, (W / 2 - 300, H / 2 - 100, 600, 200), 230, CFG.COLOR_ACCENT)
        text(surf, self.title, 26, CFG.COLOR_ACCENT, (W / 2, H / 2 - 80), 'center', True)
        caret = '|' if int(self.time * 2) % 2 == 0 else ' '
        text(surf, self.value + caret, 30, CFG.COLOR_TEXT, (W / 2, H / 2 - 20), 'center')
        text(surf, 'Enter — готово · Backspace — стереть · Esc — отмена', 14, (150, 160, 185), (W / 2, H / 2 + 50), 'center')


# =====================================================================
# ГЛАВНОЕ МЕНЮ
# =====================================================================
class MainMenu(ListScreen):
    title = 'CHROMASHIFT'

    def build(self) -> None:
        g = self.game
        self.items = [
            Item('Играть', confirm=lambda: g.ui.push(PlayMenu(g)), desc='Выбор режима, напряжения и рисков'),
            Item('Ангар', confirm=lambda: g.ui.push(HangarScreen(g)), desc='Корпус, модули, синергии и пресеты'),
            Item('Дерево улучшений', confirm=lambda: g.ui.push(UpgradeTreeScreen(g)),
                 desc='Постоянные улучшения за Chroma Points'),
            Item('Внешний вид', confirm=lambda: g.ui.push(CosmeticsScreen(g)), desc='Форма корабля, след и титул'),
            Item('Профили', confirm=lambda: g.ui.push(ProfilesScreen(g)), desc='3 слота, экспорт и импорт'),
            Item('Статистика', confirm=lambda: g.ui.push(StatsScreen(g)), desc='Итоги, история, график прогресса'),
            Item('Рекорды', confirm=lambda: g.ui.push(RecordsScreen(g)), desc='Рекорды по режимам и таблица лучших'),
            Item('Достижения', confirm=lambda: g.ui.push(AchievementsScreen(g)), desc='Цели, награды и косметика'),
            Item('Кодекс', confirm=lambda: g.ui.push(CodexScreen(g)), desc='Враги и механики'),
            Item('Настройки', confirm=lambda: g.ui.push(SettingsScreen(g)), desc='Управление, сложность, доступность, звук'),
            Item('Выход', confirm=g.quit, desc='Прогресс сохраняется автоматически'),
        ]

    def subtitle(self) -> str:
        p = self.game.profile
        title = p.data['cosmetics'].get('title', '')
        return (f"v{GAME_VERSION} · Пилот: {p.name}{' «' + title + '»' if title else ''} · "
                f"CP: {p.cp} · Призмы: {p.data['prisms']}")

    def on_action(self, act: str) -> None:
        if act == 'back':
            return
        super().on_action(act)

    def draw_side(self, surf: pygame.Surface, rect: pygame.Rect, item: Optional[Item]) -> None:
        super().draw_side(surf, rect, item)
        p = self.game.profile
        y = rect.y + 80
        text(surf, 'Контракты на сегодня', 18, CFG.COLOR_ACCENT, (rect.x + 16, y), bold=True)
        y += 28
        for c in p.data['contracts'].get('list', []):
            col = CFG.COLOR_SUCCESS if c['done'] else CFG.COLOR_TEXT
            y = text_block(surf, f"{'✓ ' if c['done'] else ''}{c['desc']} — {c['progress']}/{c['goal']} (+{c['reward']} CP)",
                           15, col, rect.x + 16, y, rect.w - 32)
            y += 4
        y += 12
        st = p.data['stats']
        text(surf, f"Лучшая волна: {st['best_wave']} · Лучший счёт: {st['best_score']}", 15, (180, 190, 210), (rect.x + 16, y))
        y += 22
        arch = ARCHETYPES.get(p.data.get('archetype', 'balanced'), ARCHETYPES['balanced'])
        text(surf, f"Ваш стиль: {arch[0]} — {arch[1]}", 15, (180, 190, 210), (rect.x + 16, y))
        # Цветовая подпись
        for i, m in enumerate(MODES):
            pygame.draw.circle(surf, mode_color(m), (rect.x + 40 + i * 50, rect.bottom - 40),
                               12 + int(3 * math.sin(self.time * 3 + i)))


# =====================================================================
# ВЫБОР РЕЖИМА
# =====================================================================
class PlayMenu(ListScreen):
    title = 'Новый забег'

    def build(self) -> None:
        g = self.game
        self.run_types = ['standard', 'daily', 'weekly', 'pure', 'training']
        self.rt = 0
        self.arenas = ['classic', 'pillars', 'prism']
        self.arena = 0
        self.tension = min(g.profile.data['tension_unlocked'], 0)
        self.start_mode = 0
        self.risks: List[str] = []
        from .game import ARENAS, RUN_TYPES
        self.ARENAS, self.RUN_TYPES = ARENAS, RUN_TYPES

        def rt_step(s: int) -> None:
            self.rt = (self.rt + s) % len(self.run_types)

        def ar_step(s: int) -> None:
            self.arena = (self.arena + s) % len(self.arenas)

        def te_step(s: int) -> None:
            self.tension = int(clamp(self.tension + s, 0, g.profile.data['tension_unlocked']))

        def sm_step(s: int) -> None:
            self.start_mode = (self.start_mode + s) % 3
        self.items = [
            Item('Режим', lambda: self.RUN_TYPES[self.run_types[self.rt]], left=lambda: rt_step(-1), right=lambda: rt_step(1),
                 desc=self.mode_desc),
            Item('Арена', lambda: self.ARENAS[self.arenas[self.arena]] if not self.fixed() else 'по испытанию',
                 left=lambda: ar_step(-1), right=lambda: ar_step(1), enabled=lambda: not self.fixed(),
                 desc='Классика — открытое поле; Колонны — укрытия гасят пули; Призма — постоянные зоны Резонанса'),
            Item('Стартовый цвет', lambda: MODES[self.start_mode], left=lambda: sm_step(-1), right=lambda: sm_step(1),
                 enabled=lambda: not self.fixed(), desc='С какого режима начнётся забег'),
            Item('Хроматическое напряжение', lambda: str(self.tension) if not self.fixed() else 'по испытанию',
                 left=lambda: te_step(-1), right=lambda: te_step(1), enabled=lambda: self.allow_mods(),
                 desc=self.tension_desc),
        ]
        for rid, r in RISKS.items():
            self.items.append(Item(f"Риск: {r['name']}", (lambda rid=rid: 'ВКЛ' if rid in self.risks else 'выкл'),
                                   confirm=(lambda rid=rid: self.toggle_risk(rid)), left=(lambda rid=rid: self.toggle_risk(rid)),
                                   right=(lambda rid=rid: self.toggle_risk(rid)), enabled=self.allow_mods,
                                   desc=f"{r['desc']}. Награда: +{int(r['cp'] * 100)}% CP"))
        self.items.append(Item('СТАРТ', confirm=self.start, color=CFG.COLOR_ACCENT, desc=self.summary))

    def fixed(self) -> bool:
        return self.run_types[self.rt] in ('daily', 'weekly')

    def allow_mods(self) -> bool:
        return self.run_types[self.rt] in ('standard', 'pure')

    def toggle_risk(self, rid: str) -> None:
        if rid in self.risks:
            self.risks.remove(rid)
        else:
            self.risks.append(rid)

    def mode_desc(self) -> str:
        rt = self.run_types[self.rt]
        p = self.game.profile
        return {
            'standard': 'Обычный забег: дерево улучшений, ангар и артефакты',
            'daily': f"Одинаковые условия на день. Лучший результат сегодня: {p.data['daily'].get('best', 0) if p.data['daily'].get('key') == challenge_setup('daily')['key'] else 0}",
            'weekly': f"Сложнее ежедневного, условия на неделю. Лучший: {p.data['weekly'].get('best', 0) if p.data['weekly'].get('key') == challenge_setup('weekly')['key'] else 0}",
            'pure': 'Без улучшений, модулей и артефактов — честный навык. Отдельный рекорд',
            'training': 'Манекены и турели, урон отключён, награды не начисляются',
        }[rt]

    def tension_desc(self) -> str:
        t = self.tension
        lines = [f"Открыто до {self.game.profile.data['tension_unlocked']}. Каждый уровень +10% CP."]
        for i in range(1, t + 1):
            lines.append(f"{i}: {TENSION_LEVELS[i]['desc']}")
        lines.append('Дойдите до волны 10, чтобы открыть следующий уровень')
        return '\n'.join(lines)

    def summary(self) -> str:
        rt = self.run_types[self.rt]
        if self.fixed():
            s = challenge_setup(rt)
            return (f"Арена: {self.ARENAS[s['arena']]}, старт: {s['start_mode']}, напряжение {s['tension']}, "
                    f"риски: {', '.join(RISKS[r]['name'] for r in s['risks'])}")
        mods = self.game.profile.build_mods(rt, self.game.settings, self.tension, self.risks if self.allow_mods() else [])
        return (f"Множитель CP: ×{mods.cp_mult:.2f}\nВраги: HP ×{mods.enemy_hp_mult:.2f}, урон ×{mods.enemy_damage_mult:.2f}\n"
                f"Окно Преломления: {mods.refraction_window:.2f} c\nИсточники: {', '.join(mods.sources) or 'нет'}")

    def start(self) -> None:
        rt = self.run_types[self.rt]
        self.game.start_run(rt, self.tension if self.allow_mods() else 0, self.risks if self.allow_mods() else [],
                            self.arenas[self.arena], MODES[self.start_mode])


# =====================================================================
# ДЕРЕВО УЛУЧШЕНИЙ (визуальное)
# =====================================================================
class UpgradeTreeScreen(Screen):
    def __init__(self, game: Any):
        super().__init__(game)
        self.branches = list(BRANCHES)
        self.col = 0
        self.row = 0
        self.message = ''
        self.message_t = 0.0
        self.node_rects: List[Tuple[str, pygame.Rect]] = []

    def column(self, b: str) -> List[str]:
        return sorted([nid for nid, n in UPGRADES.items() if n['branch'] == b],
                      key=lambda nid: (UPGRADES[nid]['row'], nid))

    def current(self) -> str:
        col = self.column(self.branches[self.col])
        self.row = int(clamp(self.row, 0, len(col) - 1))
        return col[self.row]

    def say(self, m: str) -> None:
        self.message, self.message_t = m, 3.0

    def update(self, dt: float) -> None:
        super().update(dt)
        self.message_t -= dt

    def on_action(self, act: str) -> None:
        p = self.game.profile
        if act == 'left':
            self.col = (self.col - 1) % len(self.branches)
            self.snd()
        elif act == 'right':
            self.col = (self.col + 1) % len(self.branches)
            self.snd()
        elif act == 'up':
            self.row -= 1
            self.snd()
        elif act == 'down':
            self.row += 1
            self.snd()
        elif act == 'confirm':
            ok, msg = p.buy_upgrade(self.current())
            self.say(msg)
            if ok:
                p.save()
                self.snd('ui_select')
        elif act == 'reset':
            def do_reset() -> None:
                refund = p.reset_upgrades()
                p.save()
                self.say(f"Сброс: возвращено {refund} CP")
            self.game.ui.push(ConfirmScreen(self.game, 'Сброс дерева', 'Вернуть все вложенные CP и сбросить улучшения?', do_reset))
        elif act == 'back':
            self.game.ui.pop()

    def on_mouse(self, pos: Tuple[float, float], click: bool) -> None:
        for nid, r in self.node_rects:
            if r.collidepoint(pos):
                b = UPGRADES[nid]['branch']
                self.col = self.branches.index(b)
                self.row = self.column(b).index(nid)
                if click:
                    self.on_action('confirm')

    def draw(self, surf: pygame.Surface) -> None:
        g = self.game
        p = g.profile
        text(surf, 'Дерево улучшений', 36, CFG.COLOR_ACCENT, (60, 24), bold=True)
        text(surf, f"CP: {p.cp}", 22, CFG.COLOR_TEXT, (CFG.SCREEN_WIDTH - 60, 32), 'right', True)
        rec = p.recommended_upgrade()
        self.node_rects = []
        col_w = 220
        x0 = 60
        cur = self.current()
        for ci, b in enumerate(self.branches):
            name, col = BRANCHES[b]
            col = col or mode_color(b)
            x = x0 + ci * (col_w + 12)
            text(surf, f"{name} ({branch_spent(p.data['upgrades'], b)} CP)", 18, col, (x, 78), bold=True)
            nodes = self.column(b)
            positions = {}
            for ri, nid in enumerate(nodes):
                y = 108 + ri * 54
                r = pygame.Rect(x, y, col_w, 46)
                positions[nid] = r
                self.node_rects.append((nid, r))
            for nid in nodes:
                for req in UPGRADES[nid]['requires']:
                    if req in positions:
                        a, bb = positions[req], positions[nid]
                        pygame.draw.line(surf, (80, 90, 120), (a.x + 8, a.centery), (bb.x + 8, bb.centery), 2)
            for nid in nodes:
                r = positions[nid]
                node = UPGRADES[nid]
                status, _ = node_status(p, nid)
                lvl = p.data['upgrades'].get(nid, 0)
                fill = {'maxed': (30, 60, 45), 'available': (35, 45, 75), 'expensive': (40, 40, 55),
                        'locked': (22, 24, 32), 'blocked': (45, 25, 30)}.get(status, (18, 18, 24))
                pygame.draw.rect(surf, fill, r)
                border = col if status in ('available', 'maxed') else (70, 75, 95)
                if nid == cur:
                    border = CFG.COLOR_ACCENT
                pygame.draw.rect(surf, border, r, 3 if nid == cur else 1)
                if node['key']:
                    draw_shape(surf, 'diamond', CFG.COLOR_ACCENT, r.right - 12, r.y + 12, 6)
                if node['tradeoff']:
                    text(surf, '⇄', 14, CFG.COLOR_DANGER, (r.right - 28, r.y + 3))
                if nid == rec:
                    text(surf, '★', 16, CFG.COLOR_ACCENT, (r.right - 46, r.y + 2))
                tcol = CFG.COLOR_TEXT if status != 'locked' else (110, 115, 135)
                text(surf, node['name'], 15, tcol, (r.x + 8, r.y + 4), bold=nid == cur)
                text(surf, f"{lvl}/{node['max']}", 13, (170, 180, 205), (r.x + 8, r.y + 25))
                if lvl < node['max']:
                    text(surf, f"{node['costs'][lvl]} CP", 13, CFG.COLOR_ACCENT if status == 'available' else (130, 130, 150),
                         (r.right - 8, r.y + 25), 'right')
        # Панель описания
        node = UPGRADES[cur]
        status, reason = node_status(p, cur)
        side = pygame.Rect(60, 560, CFG.SCREEN_WIDTH - 120, 130)
        panel(surf, side, 190)
        text(surf, node['name'] + ('  (ключевой узел)' if node['key'] else '') + ('  (компромисс)' if node['tradeoff'] else ''),
             20, CFG.COLOR_ACCENT, (side.x + 14, side.y + 8), bold=True)
        text(surf, node['desc'], 16, CFG.COLOR_TEXT, (side.x + 14, side.y + 36))
        text(surf, reason, 15, CFG.COLOR_SUCCESS if status == 'available' else (200, 160, 160), (side.x + 14, side.y + 60))
        pv = preview_node(p, cur) if status != 'maxed' else []
        text(surf, 'Предпросмотр: ' + '; '.join(pv[:3]) if pv else '', 15, (180, 200, 230), (side.x + 14, side.y + 84))
        if rec:
            text(surf, f"★ Рекомендация под ваш стиль: {UPGRADES[rec]['name']}", 14, CFG.COLOR_ACCENT, (side.right - 14, side.y + 8), 'right')
        text(surf, '←→ ветка · ↑↓ узел · Enter — купить · R — полный сброс с возвратом CP · Esc — назад', 14,
             (130, 140, 165), (60, CFG.SCREEN_HEIGHT - 26))
        if self.message_t > 0:
            text(surf, self.message, 18, CFG.COLOR_ACCENT, (CFG.SCREEN_WIDTH / 2, 530), 'center', True)


# =====================================================================
# АНГАР
# =====================================================================
class HangarScreen(ListScreen):
    title = 'Ангар'

    def build(self) -> None:
        g = self.game
        p = g.profile
        self.items = []

        def preset_step(s: int) -> None:
            p.data['active_loadout'] = (p.data['active_loadout'] + s) % 3
            p.save()
            self.build()
        self.items.append(Item('Пресет', lambda: f"{p.data['active_loadout'] + 1}: {p.loadout['name']}",
                               left=lambda: preset_step(-1), right=lambda: preset_step(1),
                               desc='Три сохранённых комплекта корпуса и модулей'))

        def rename() -> None:
            def done(v: str) -> None:
                p.loadout['name'] = v[:16]
                p.save()
            g.ui.push(TextInputScreen(g, 'Название пресета', p.loadout['name'], done))
        self.items.append(Item('Переименовать пресет', confirm=rename))
        for hid, h in HULLS.items():
            def hull_action(hid: str = hid) -> str:
                if hid not in p.data['hulls']:
                    ok, msg = p.buy_hull(hid)
                    p.save()
                    return msg
                p.set_hull(hid)
                p.save()
                return f"Корпус: {HULLS[hid]['name']}"
            self.items.append(Item(f"Корпус: {h['name']}",
                                   (lambda hid=hid: '✓ выбран' if p.loadout['hull'] == hid else
                                    ('открыт' if hid in p.data['hulls'] else f"{HULLS[hid]['cost']} CP + {HULLS[hid]['prisms']} пр.")),
                                   confirm=hull_action,
                                   desc=f"{h['desc']}. Слотов: {h['slots']}, энергия: {h['energy']}"))
        for mid, m in MODULES.items():
            def mod_action(mid: str = mid) -> str:
                if mid not in p.data['modules']:
                    ok, msg = p.buy_module(mid)
                    p.save()
                    return msg
                ok, msg = p.toggle_module(mid)
                p.save()
                return msg
            conflicts = ', '.join(MODULES[c]['name'] for c in m['conflicts'])
            self.items.append(Item(f"Модуль: {m['name']}",
                                   (lambda mid=mid: '✓ установлен' if mid in p.loadout['modules'] else
                                    ('открыт' if mid in p.data['modules'] else f"{MODULES[mid]['cost']} CP")),
                                   confirm=mod_action,
                                   desc=f"{m['desc']}. Энергия: {m['energy']}" + (f". Несовместим: {conflicts}" if conflicts else '')))

    def subtitle(self) -> str:
        p = self.game.profile
        lo = p.loadout
        h = HULLS[lo['hull']]
        return (f"CP: {p.cp} · Призмы: {p.data['prisms']} · Слоты {len(lo['modules'])}/{h['slots']} · "
                f"Энергия {loadout_energy(lo)}/{h['energy']}")

    def draw_side(self, surf: pygame.Surface, rect: pygame.Rect, item: Optional[Item]) -> None:
        super().draw_side(surf, rect, item)
        p = self.game.profile
        lo = p.loadout
        y = rect.y + 110
        text(surf, 'Установлено:', 17, CFG.COLOR_ACCENT, (rect.x + 16, y), bold=True)
        y += 26
        for mid in lo['modules']:
            text(surf, '• ' + MODULES[mid]['name'], 15, CFG.COLOR_TEXT, (rect.x + 16, y))
            y += 20
        syn = active_synergies(lo['modules'])
        y += 10
        text(surf, 'Синергии:', 17, CFG.COLOR_ACCENT, (rect.x + 16, y), bold=True)
        y += 26
        if not syn:
            text(surf, 'нет (сочетайте модули)', 15, (150, 155, 175), (rect.x + 16, y))
            y += 20
        for s in syn:
            text(surf, f"• {s['name']}: {s['desc']}", 15, CFG.COLOR_SUCCESS, (rect.x + 16, y))
            y += 20
        y += 10
        text(surf, 'Возможные синергии:', 15, (150, 160, 185), (rect.x + 16, y))
        y += 22
        for s in self_synergy_list():
            text(surf, s, 13, (140, 150, 170), (rect.x + 16, y))
            y += 18
        h = HULLS[lo['hull']]
        draw_shape(surf, h['shape'], CFG.COLOR_PRIMARY, rect.right - 60, rect.y + 60, 26, self.time, 2)


def self_synergy_list() -> List[str]:
    from .progression import SYNERGIES
    return [f"{' + '.join(MODULES[m]['name'] for m in sorted(s['modules']))} → {s['name']}" for s in SYNERGIES]


# =====================================================================
# ВНЕШНИЙ ВИД
# =====================================================================
class CosmeticsScreen(ListScreen):
    title = 'Внешний вид'

    def build(self) -> None:
        p = self.game.profile
        self.items = []
        names = {'ship_shape': 'Форма корабля', 'trail_style': 'След', 'title': 'Титул'}
        for kind, label in names.items():
            def step(s: int, kind: str = kind) -> None:
                opts = [k for k in COSMETICS[kind] if f"{kind}:{k}" in p.data['unlocked_cosmetics']]
                cur = p.data['cosmetics'].get(kind, opts[0])
                i = opts.index(cur) if cur in opts else 0
                p.data['cosmetics'][kind] = opts[(i + s) % len(opts)]
                p.save()
            self.items.append(Item(label, (lambda kind=kind: COSMETICS[kind].get(p.data['cosmetics'].get(kind, ''), '—')),
                                   left=(lambda kind=kind: step(-1, kind)), right=(lambda kind=kind: step(1, kind)),
                                   desc=(lambda kind=kind: 'Открыто: ' + ', '.join(
                                       COSMETICS[kind][k] for k in COSMETICS[kind] if f"{kind}:{k}" in p.data['unlocked_cosmetics'])
                                       + '\nОстальное открывается достижениями')))

    def draw_side(self, surf: pygame.Surface, rect: pygame.Rect, item: Optional[Item]) -> None:
        super().draw_side(surf, rect, item)
        c = self.game.profile.data['cosmetics']
        cx, cy = rect.centerx, rect.y + 300
        for i in range(6):
            col = {'mode': mode_color(MODES[int(self.time) % 3]), 'white': CFG.COLOR_PRIMARY, 'gold': CFG.COLOR_ACCENT,
                   'rainbow': mode_color(MODES[i % 3])}.get(c.get('trail_style', 'mode'))
            pygame.draw.circle(surf, col, (int(cx - 30 - i * 18), cy), max(2, 10 - i))
        draw_shape(surf, c.get('ship_shape', 'circle'), mode_color(MODES[int(self.time) % 3]), cx, cy, 18, self.time)


# =====================================================================
# НАСТРОЙКИ
# =====================================================================
def _choice_item(g: Any, label: str, key: str, desc: str = '') -> Item:
    return Item(label, lambda: CHOICE_NAMES.get(g.settings.get(key), str(g.settings.get(key))),
                left=lambda: g.settings.cycle(key, -1), right=lambda: g.settings.cycle(key, 1), desc=desc)


def _bool_item(g: Any, label: str, key: str, desc: str = '') -> Item:
    def flip() -> None:
        g.settings.set(key, not g.settings.get(key))
    return Item(label, lambda: 'Вкл' if g.settings.get(key) else 'Выкл', confirm=flip, left=flip, right=flip, desc=desc)


def _range_item(g: Any, label: str, key: str, desc: str = '', pct: bool = True) -> Item:
    return Item(label, lambda: f"{int(round(g.settings.get(key) * 100))}%" if pct else f"{g.settings.get(key):.2f}",
                left=lambda: g.settings.nudge(key, -1), right=lambda: g.settings.nudge(key, 1), desc=desc)


class SettingsScreen(ListScreen):
    title = 'Настройки'

    def build(self) -> None:
        g = self.game
        self.items = [
            Item('Управление', confirm=lambda: g.ui.push(ControlsScreen(g)), desc='Переназначение клавиш, схемы смены цвета, огонь, геймпад'),
            Item('Сложность', confirm=lambda: g.ui.push(DifficultyScreen(g)), desc='Пресеты, своя сложность, DDA, адаптивные окна'),
            Item('Доступность', confirm=lambda: g.ui.push(AccessibilityScreen(g)), desc='Палитры, формы, тряска, вспышки, масштаб UI'),
            Item('Физика режимов', confirm=lambda: g.ui.push(PhysicsScreen(g)), desc='Пресеты и тонкая настройка ±20%'),
            Item('Звук и графика', confirm=lambda: g.ui.push(AudioVideoScreen(g)), desc='Звуковой пак, громкость, фон, FPS'),
            Item('Имя пилота', lambda: g.profile.name, confirm=self.rename),
        ]

    def rename(self) -> None:
        g = self.game

        def done(v: str) -> None:
            g.profile.data['name'] = v[:16]
            g.profile.save()
        g.ui.push(TextInputScreen(g, 'Имя пилота', g.profile.name, done))

    def on_action(self, act: str) -> None:
        if act == 'back':
            self.game.settings.save()
        super().on_action(act)


class ControlsScreen(ListScreen):
    title = 'Управление'

    def build(self) -> None:
        g = self.game
        self.items = [
            _bool_item(g, 'Смена цвета колесом мыши', 'mouse_wheel_switch'),
            _bool_item(g, 'Радиальное меню (удержание)', 'radial_menu', 'Удерживайте клавишу, наведите прицел на сектор и отпустите'),
            _choice_item(g, 'Режим огня', 'fire_mode', 'Удержание ЛКМ, переключение кликом или постоянный автоогонь'),
            _choice_item(g, 'Направление рывка', 'dash_direction', 'Рывок туда, куда целитесь, или туда, куда движетесь'),
            _range_item(g, 'Мёртвая зона стика', 'gamepad_deadzone'),
            _range_item(g, 'Помощь прицеливания (геймпад)', 'aim_assist'),
        ]
        for action, name in ACTION_NAMES.items():
            self.items.append(Item(name, (lambda a=action: g.settings.data['keys'].get(a, '?').upper()),
                                   confirm=(lambda a=action: self.start_bind(a)),
                                   desc='Enter — назначить новую клавишу (Esc — отмена). Занятая клавиша поменяется местами'))
        self.items.append(Item('Сбросить клавиши', confirm=self.reset_keys))

    def subtitle(self) -> str:
        pads = len(self.game.input.joysticks)
        s = f"Геймпадов подключено: {pads}. Геймпад: A — рывок, X/B/Y — цвета, LB/RB — цикл, RT/правый стик — огонь"
        if self.game.input.waiting_bind:
            s = f"Нажмите клавишу для «{ACTION_NAMES[self.game.input.waiting_bind]}»…"
        return s

    def start_bind(self, action: str) -> None:
        self.game.input.waiting_bind = action

    def reset_keys(self) -> str:
        from .settings import DEFAULT_KEYS
        self.game.settings.data['keys'] = dict(DEFAULT_KEYS)
        return 'Клавиши сброшены'


class DifficultyScreen(ListScreen):
    title = 'Сложность'

    def build(self) -> None:
        g = self.game
        self.items = [_choice_item(g, 'Пресет', 'difficulty', lambda: self.diff_desc())]
        for k, label in (('enemy_hp', 'HP врагов'), ('enemy_damage', 'Урон врагов'), ('enemy_speed', 'Скорость врагов'),
                         ('refraction_window', 'Окно Преломления')):
            def step(s: int, k: str = k) -> None:
                c = g.settings.data['custom_difficulty']
                c[k] = round(clamp(c.get(k, 1.0) + 0.1 * s, 0.5, 1.6), 2)
                g.settings.set('difficulty', 'custom')
            self.items.append(Item(f"Своя: {label}", (lambda k=k: f"×{g.settings.data['custom_difficulty'].get(k, 1.0):.1f}"),
                                   left=(lambda k=k: step(-1, k)), right=(lambda k=k: step(1, k)),
                                   desc='Изменение любого ползунка включает пресет «Своя»'))
        self.items += [
            _bool_item(g, 'Динамическая сложность (DDA)', 'dda', 'Мягко подстраивает число врагов (±15%), не трогая урон. Отключена в испытаниях'),
            _bool_item(g, 'Адаптивные окна', 'adaptive_windows', 'После серии неудачных Преломлений окно чуть расширяется (до +0.06 c)'),
            _bool_item(g, 'Предлагать помощь', 'assist_prompt', 'После 3 ранних поражений подряд предложить сюжетную сложность'),
            _bool_item(g, 'Подсказки', 'tips'),
        ]

    def diff_desc(self) -> str:
        d = DIFFICULTIES[self.game.settings.get('difficulty')]
        if self.game.settings.get('difficulty') == 'custom':
            return 'Своя сложность: настройте ползунки ниже. Множитель CP зависит от итоговой сложности'
        return (f"{d['name']}: HP ×{d['enemy_hp']}, урон ×{d['enemy_damage']}, скорость ×{d['enemy_speed']}, "
                f"окно ×{d['refraction_window']}, CP ×{d['cp']}")


class AccessibilityScreen(ListScreen):
    title = 'Доступность'

    def build(self) -> None:
        g = self.game
        self.items = [
            _choice_item(g, 'Цветовая палитра', 'palette', 'Палитры для разных типов цветовосприятия'),
            _bool_item(g, 'Формы режимов', 'shapes', 'RED — треугольник, BLUE — квадрат, GREEN — круг. Дублирует цвет формой'),
            _range_item(g, 'Тряска экрана', 'shake'),
            _range_item(g, 'Вспышки', 'flash', 'Яркость вспышек при уроне и событиях'),
            _range_item(g, 'Яркость неона', 'glow'),
            _range_item(g, 'Масштаб интерфейса', 'ui_scale'),
        ]

    def draw_side(self, surf: pygame.Surface, rect: pygame.Rect, item: Optional[Item]) -> None:
        super().draw_side(surf, rect, item)
        for i, m in enumerate(MODES):
            x = rect.x + 60 + i * 110
            draw_shape(surf, MODE_SHAPES[m], mode_color(m), x, rect.y + 220, 24, 0, 0)
            text(surf, m, 16, CFG.COLOR_TEXT, (x, rect.y + 256), 'center', True)


class PhysicsScreen(ListScreen):
    title = 'Физика режимов'

    def build(self) -> None:
        g = self.game
        self.items = [_choice_item(g, 'Пресет', 'physics_preset', 'Стандарт / Аркада (резвее) / Тяжёлая (инертнее)')]
        for m in MODES:
            def step(s: int, m: str = m) -> None:
                ph = g.settings.data['physics']
                ph[m] = round(clamp(ph.get(m, 1.0) + 0.05 * s, 0.8, 1.2), 2)
                g.settings.data['physics_preset'] = 'custom'
            self.items.append(Item(f"Скорость и ускорение {m}", (lambda m=m: f"{int(round(g.settings.data['physics'].get(m, 1.0) * 100))}%"),
                                   left=(lambda m=m: step(-1, m)), right=(lambda m=m: step(1, m)),
                                   desc='Тонкая настройка в пределах ±20%. Характер режимов сохраняется: RED — импульс, BLUE — якорь, GREEN — текучесть'))


class AudioVideoScreen(ListScreen):
    title = 'Звук и графика'

    def build(self) -> None:
        g = self.game

        def pack_step(s: int) -> None:
            g.settings.cycle('sound_pack', s)
            g.sound_manager.load_pack(g.settings.get('sound_pack'))

        def vol_step(s: int) -> None:
            g.settings.nudge('volume', s)
            g.sound_manager.volume = g.settings.get('volume')
            g.sound_manager.play('ui_select', 0.6)
        from .audio import USER_SOUND_DIR
        self.items = [
            Item('Звуковой пак', lambda: CHOICE_NAMES[g.settings.get('sound_pack')], left=lambda: pack_step(-1), right=lambda: pack_step(1),
                 desc=f"Студийный — WAV-файлы (можно заменить своими в {USER_SOUND_DIR}); Ретро — синтез на лету"),
            Item('Громкость', lambda: f"{int(round(g.settings.get('volume') * 100))}%", left=lambda: vol_step(-1), right=lambda: vol_step(1)),
            _bool_item(g, 'Музыка', 'music', 'Процедурная музыка подстраивается под ваш стиль и давление волны'),
            _choice_item(g, 'Тема фона', 'bg_theme'),
            _bool_item(g, 'Показывать FPS', 'show_fps'),
            Item('Полный экран', lambda: 'Вкл' if g.settings.get('fullscreen') else 'Выкл', confirm=g.toggle_fullscreen, desc='Также F11'),
        ]

    def on_action(self, act: str) -> None:
        super().on_action(act)
        self.game.show_fps = bool(self.game.settings.get('show_fps'))


# =====================================================================
# ПРОФИЛИ
# =====================================================================
class ProfilesScreen(ListScreen):
    title = 'Профили'

    def build(self) -> None:
        g = self.game
        self.items = []
        for slot in range(PROFILE_SLOTS):
            self.items.append(Item((lambda s=slot: self.slot_label(s)), confirm=(lambda s=slot: self.select(s)),
                                   desc=(lambda s=slot: self.slot_desc(s))))
        self.items += [
            Item('Новый профиль в пустой слот', confirm=self.create),
            Item('Экспорт текущего профиля', confirm=lambda: f"Сохранено: {g.profile.export()}"),
            Item('Импорт в текущий слот', confirm=self.do_import,
                 desc='Положите файл import.json в папку saves рядом с игрой. Текущий профиль будет заменён'),
            Item('Удалить текущий профиль', confirm=self.delete, color=CFG.COLOR_DANGER),
        ]

    def slot_label(self, s: int) -> str:
        cur = ' (активен)' if s == self.game.profile.slot else ''
        if s == self.game.profile.slot:
            return f"Слот {s + 1}: {self.game.profile.name}{cur}"
        return f"Слот {s + 1}: " + (Profile.load(s).name if Profile.exists(s) else 'пусто')

    def slot_desc(self, s: int) -> str:
        p = self.game.profile if s == self.game.profile.slot else (Profile.load(s) if Profile.exists(s) else None)
        if p is None:
            return 'Пустой слот'
        st = p.data['stats']
        return f"CP {p.cp}, забегов {st['runs']}, лучшая волна {st['best_wave']}, рекорд {st['best_score']}"

    def select(self, s: int) -> str:
        g = self.game
        g.profile.save()
        g.profile = Profile.load(s)
        g.profile.refresh_contracts()
        g.profile.save()
        g.settings.set('last_profile', s)
        g.settings.save()
        return f"Активен профиль: {g.profile.name}"

    def create(self) -> str:
        free = [s for s in range(PROFILE_SLOTS) if not Profile.exists(s) and s != self.game.profile.slot]
        if not free:
            return 'Нет пустых слотов'

        def done(name: str) -> None:
            from .progression import default_profile
            p = Profile(free[0], default_profile(name))
            p.refresh_contracts()
            p.save()
            self.select(free[0])
        self.game.ui.push(TextInputScreen(self.game, 'Имя нового пилота', 'Пилот', done))
        return ''

    def do_import(self) -> str:
        ok, msg = self.game.profile.import_file()
        return msg

    def delete(self) -> None:
        g = self.game

        def do() -> None:
            g.profile.delete()
            from .progression import default_profile
            g.profile = Profile(g.profile.slot, default_profile())
            g.profile.refresh_contracts()
            g.profile.save()
        g.ui.push(ConfirmScreen(g, 'Удаление', f"Удалить профиль «{g.profile.name}» и его резервные копии?", do))


# =====================================================================
# СТАТИСТИКА, РЕКОРДЫ, ДОСТИЖЕНИЯ, КОДЕКС
# =====================================================================
class StatsScreen(Screen):
    def on_action(self, act: str) -> None:
        if act in ('back', 'confirm'):
            self.game.ui.pop()

    def draw(self, surf: pygame.Surface) -> None:
        p = self.game.profile
        st = p.data['stats']
        text(surf, 'Статистика', 36, CFG.COLOR_ACCENT, (60, 30), bold=True)
        rows = [
            ('Забегов', st['runs']), ('Время в игре', f"{st['play_time'] / 60:.0f} мин"), ('Убийств', st['kills']),
            ('Лучшая волна', st['best_wave']), ('Лучший счёт', st['best_score']),
            ('Преломлений', f"{st['refractions']} (промахов {st.get('refraction_fails', 0)})"),
            ('Эхо-камер', st['echoes']), ('Импульсов', st['impulses']), ('Резонансов', st['resonances']),
            ('Убийств в такт', st['beat_kills']), ('Боссов', st['bosses']), ('Элит', st['elites']),
            ('Рывков', st['dashes']), ('Смен цвета', st['switches']), ('CP заработано', p.data['cp_earned_total']),
        ]
        for i, (k, v) in enumerate(rows):
            text(surf, f"{k}:", 16, (170, 180, 205), (60, 90 + i * 24))
            text(surf, str(v), 16, CFG.COLOR_TEXT, (300, 90 + i * 24), bold=True)
        y = 90 + len(rows) * 24 + 10
        total_t = sum(st['mode_time'].values()) or 1
        for i, m in enumerate(MODES):
            frac = st['mode_time'].get(m, 0) / total_t
            bar(surf, (60, y + i * 22, 240, 14), frac, mode_color(m))
            text(surf, f"{m}: {frac * 100:.0f}% времени, {st['mode_kills'].get(m, 0)} убийств", 14, CFG.COLOR_TEXT, (310, y + i * 22 - 2))
        # График прогресса: последние 20 забегов
        gx, gy, gw, gh = 640, 90, 580, 300
        panel(surf, (gx, gy, gw, gh), 160)
        text(surf, 'Прогресс: счёт и волна за последние забеги', 16, CFG.COLOR_ACCENT, (gx + 10, gy + 6), bold=True)
        hist = p.data['history']
        if len(hist) >= 2:
            ms = max(1, max(h['score'] for h in hist))
            mw = max(1, max(h['wave'] for h in hist))
            pts_s, pts_w = [], []
            for i, h in enumerate(hist):
                x = gx + 20 + i * (gw - 40) / (len(hist) - 1)
                pts_s.append((x, gy + gh - 20 - (gh - 60) * h['score'] / ms))
                pts_w.append((x, gy + gh - 20 - (gh - 60) * h['wave'] / mw))
            pygame.draw.lines(surf, CFG.COLOR_ACCENT, False, pts_s, 2)
            pygame.draw.lines(surf, mode_color('BLUE'), False, pts_w, 2)
            text(surf, f"— счёт (макс {ms})", 13, CFG.COLOR_ACCENT, (gx + 10, gy + gh - 18))
            text(surf, f"— волна (макс {mw})", 13, mode_color('BLUE'), (gx + 200, gy + gh - 18))
        else:
            text(surf, 'Сыграйте хотя бы 2 забега', 15, (150, 155, 175), (gx + 10, gy + 40))
        # История и причины смерти
        y2 = gy + gh + 16
        text(surf, 'Последние забеги', 16, CFG.COLOR_ACCENT, (gx, y2), bold=True)
        for i, h in enumerate(reversed(hist[-8:])):
            arch = ARCHETYPES.get(h.get('archetype', 'balanced'), ('?', ''))[0]
            text(surf, f"{h['date']} · {h['type']} · волна {h['wave']} · {h['score']} · {arch} · {h.get('cause', '')}"[:80],
                 13, CFG.COLOR_TEXT, (gx, y2 + 24 + i * 19))
        deaths = sorted(st['deaths_by'].items(), key=lambda kv: -kv[1])[:4]
        if deaths:
            text(surf, 'Чаще всего побеждают: ' + ', '.join(f"{k} ({v})" for k, v in deaths), 14, (220, 170, 170),
                 (60, CFG.SCREEN_HEIGHT - 60))
        text(surf, 'Esc — назад', 14, (130, 140, 165), (60, CFG.SCREEN_HEIGHT - 30))


class RecordsScreen(Screen):
    def on_action(self, act: str) -> None:
        if act in ('back', 'confirm'):
            self.game.ui.pop()

    def draw(self, surf: pygame.Surface) -> None:
        from .game import RUN_TYPES
        p = self.game.profile
        text(surf, 'Рекорды', 36, CFG.COLOR_ACCENT, (60, 30), bold=True)
        y = 100
        for rt, name in RUN_TYPES.items():
            if rt == 'training':
                continue
            rec = p.data['records'].get(rt, {})
            text(surf, f"{name}: {rec.get('score', 0)} очков, волна {rec.get('wave', 0)}", 18, CFG.COLOR_TEXT, (60, y))
            y += 30
        text(surf, f"Ежедневное ({p.data['daily'].get('key', '—')}): {p.data['daily'].get('best', 0)}", 16, (180, 190, 210), (60, y + 10))
        text(surf, f"Еженедельное ({p.data['weekly'].get('key', '—')}): {p.data['weekly'].get('best', 0)}", 16, (180, 190, 210), (60, y + 36))
        gx = 640
        text(surf, 'Таблица лучших (локальная)', 20, CFG.COLOR_ACCENT, (gx, 100), bold=True)
        for i, e in enumerate(p.data['leaderboard']):
            text(surf, f"{i + 1:>2}. {e.get('name', '?')} — {e['score']} · волна {e['wave']} · {RUN_TYPES.get(e['type'], e['type'])} · {e['date']}",
                 15, CFG.COLOR_TEXT if i else CFG.COLOR_ACCENT, (gx, 136 + i * 26))
        text(surf, 'Esc — назад', 14, (130, 140, 165), (60, CFG.SCREEN_HEIGHT - 30))


class AchievementsScreen(ListScreen):
    title = 'Достижения'

    def build(self) -> None:
        p = self.game.profile
        self.items = []
        for aid, name, desc, fn, goal, reward, cosmetic in ACHIEVEMENTS:
            got = aid in p.data['achievements']
            cur, g = p.achievement_progress(aid)
            extra = ''
            if cosmetic:
                k, v = cosmetic.split(':', 1)
                extra = f"\nНаграда-косметика: {COSMETICS[k].get(v, v)}"
            self.items.append(Item(('✓ ' if got else '') + name,
                                   (lambda got=got, cur=cur, g=g: 'получено' if got else (f"{int(min(cur, g))}/{int(g)}" if g > 1 else '—')),
                                   desc=f"{desc}. Награда: {reward} CP{extra}",
                                   color=CFG.COLOR_SUCCESS if got else None))

    def subtitle(self) -> str:
        p = self.game.profile
        return f"Получено {len(p.data['achievements'])} из {len(ACHIEVEMENTS)}"


class CodexScreen(ListScreen):
    title = 'Кодекс'
    ENTRIES = {
        'chaser': 'Преследует игрока. Контактный урон. Слаб, но приходит отрядами',
        'shooter': 'Держит дистанцию и стреляет. Его пули можно отразить сменой цвета',
        'kamikaze': 'Предупреждает красным кругом и взрывается. Рывок даёт неуязвимость',
        'dissonance': 'Почти неуязвим к обычным пулям. Убивается отражённой пулей мгновенно',
        'boss': 'Каждые 10 волн. Три фазы: залпы, таран, спираль с призывом. Уязвим к цвету оболочки',
    }
    MECHANICS = {
        'Преломление': 'Смена цвета за мгновение до попадания отражает пулю с тройным уроном',
        'Резонанс': 'Серия убийств одним цветом создаёт зону: +скорость, +урон, быстрее стрельба',
        'Импульс': 'Отдельная серия убийств одним цветом даёт пробивающие пули на несколько секунд',
        'Эхо-камера': 'Несколько Преломлений подряд замедляют вражеские пули',
        'В такт': 'Убийства в ритм музыки дают ×1.5 очков',
        'Элиты': ', '.join(v[0] for v in ELITE_MODS.values()) + '. Цветной щит — урон только своим цветом',
    }

    def build(self) -> None:
        p = self.game.profile
        codex = p.data['stats']['codex']
        self.items = []
        for kind, desc in self.ENTRIES.items():
            n = codex.get(kind, 0)
            seen = n > 0 or kind in ('chaser',)
            self.items.append(Item(ENEMY_NAMES[kind] if seen else '???', (lambda n=n: f"уничтожено: {n}"),
                                   desc=desc if seen else 'Встретьте этого врага, чтобы открыть запись'))
        for name, desc in self.MECHANICS.items():
            self.items.append(Item(f"Механика: {name}", desc=desc))


# =====================================================================
# ВНУТРИИГРОВЫЕ ЭКРАНЫ
# =====================================================================
class PauseScreen(ListScreen):
    title = 'Пауза'
    show_world = True

    def build(self) -> None:
        g = self.game
        self.items = [
            Item('Продолжить', confirm=g.ui.pop),
            Item('Настройки', confirm=lambda: g.ui.push(SettingsScreen(g))),
            Item('Закончить забег', confirm=lambda: g.ui.push(ConfirmScreen(g, 'Закончить забег', 'Итоги и CP будут начислены', lambda: g.end_run('quit'), True))),
        ]

    def subtitle(self) -> str:
        g = self.game
        arts = ', '.join(ARTIFACTS[a]['name'] for a in g.artifacts) or 'нет'
        return f"Волна {g.director.wave} · Счёт {int(g.score)} · Артефакты: {arts}"

    def draw_side(self, surf: pygame.Surface, rect: pygame.Rect, item: Optional[Item]) -> None:
        m = self.game.mods
        lines = [f"Урон ×{m.damage_mult:.2f}", f"Скорострельность ×{m.fire_rate_mult:.2f}",
                 f"Окно Преломления {self.game.chromatic_buffer.window:.2f} c",
                 f"Порог Резонанса {m.resonance_threshold}, Импульса {m.impulse_threshold}, Эха {m.echo_threshold}",
                 'Источники: ' + (', '.join(m.sources) or '—')]
        y = rect.y + 16
        for ln in lines:
            y = text_block(surf, ln, 16, CFG.COLOR_TEXT, rect.x + 16, y, rect.w - 32) + 4


class ArtifactScreen(Screen):
    show_world = True

    def __init__(self, game: Any, choices: List[str]):
        super().__init__(game)
        self.choices = choices
        self.index = 0
        self.rects: List[pygame.Rect] = []

    def on_action(self, act: str) -> None:
        if act == 'left':
            self.index = (self.index - 1) % len(self.choices)
            self.snd()
        elif act == 'right':
            self.index = (self.index + 1) % len(self.choices)
            self.snd()
        elif act == 'confirm':
            self.game.take_artifact(self.choices[self.index])
            self.game.ui.pop()

    def on_mouse(self, pos: Tuple[float, float], click: bool) -> None:
        for i, r in enumerate(self.rects):
            if r.collidepoint(pos):
                self.index = i
                if click:
                    self.on_action('confirm')

    def draw(self, surf: pygame.Surface) -> None:
        W, H = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        veil = layer((W, H), pygame.SRCALPHA)
        veil.fill((5, 6, 12, 180))
        surf.blit(veil, (0, 0))
        text(surf, 'Выберите артефакт', 36, CFG.COLOR_ACCENT, (W / 2, 120), 'center', True)
        text(surf, 'Действует до конца забега. Чаще выпадают артефакты под ваш стиль', 16, (180, 190, 210), (W / 2, 168), 'center')
        self.rects = []
        cw = 300
        x0 = W / 2 - (len(self.choices) * (cw + 30) - 30) / 2
        for i, aid in enumerate(self.choices):
            a = ARTIFACTS[aid]
            r = pygame.Rect(int(x0 + i * (cw + 30)), 230, cw, 260)
            self.rects.append(r)
            sel = i == self.index
            panel(surf, r, 220, CFG.COLOR_ACCENT if sel else None)
            arch = ARCHETYPES.get(a['arch'], ('Универсальный', ''))[0] if a['arch'] != 'any' else 'Универсальный'
            col = {'assault': mode_color('RED'), 'control': mode_color('BLUE'), 'dancer': mode_color('GREEN')}.get(a['arch'], CFG.COLOR_ACCENT)
            draw_shape(surf, 'diamond', col, r.centerx, r.y + 60, 26 + (4 * math.sin(self.time * 4) if sel else 0), self.time if sel else 0)
            text(surf, a['name'], 22, CFG.COLOR_TEXT, (r.centerx, r.y + 110), 'center', True)
            text_block(surf, a['desc'], 16, (200, 210, 230), r.x + 20, r.y + 150, cw - 40)
            text(surf, arch, 14, col, (r.centerx, r.bottom - 30), 'center')
        text(surf, '←→ — выбор · Enter — взять', 14, (150, 160, 185), (W / 2, 520), 'center')


class ResultsScreen(ListScreen):
    title = 'Итоги забега'

    def __init__(self, game: Any, run: Dict[str, Any], result: Dict[str, Any]):
        self.run = run
        self.result = result
        super().__init__(game)

    def build(self) -> None:
        g = self.game
        last = (self.run['run_type'], self.run.get('tension', 0), list(self.run.get('risks', [])), self.run.get('arena', 'classic'))
        self.items = [
            Item('Ещё раз', confirm=lambda: g.start_run(last[0], last[1], last[2], last[3])),
            Item('Дерево улучшений', confirm=lambda: (g.ui.clear(), g.ui.push(MainMenu(g)), g.ui.push(UpgradeTreeScreen(g)))),
            Item('В главное меню', confirm=lambda: (g.ui.clear(), g.ui.push(MainMenu(g)))),
        ]
        p = g.profile
        if (g.settings.get('assist_prompt') and p.data['death_streak'] >= 3 and g.settings.get('difficulty') != 'story'
                and not p.data.get('assist_declined')):
            def accept() -> str:
                g.settings.set('difficulty', 'story')
                g.settings.save()
                p.data['death_streak'] = 0
                return 'Включена сюжетная сложность (можно вернуть в настройках)'

            def decline() -> str:
                p.data['assist_declined'] = True
                p.save()
                return 'Больше не предлагаем'
            self.items.insert(0, Item('Включить помощь: сюжетная сложность', confirm=accept, color=CFG.COLOR_SUCCESS,
                                      desc='Несколько ранних поражений подряд. Сюжет: враги слабее, окно Преломления шире'))
            self.items.insert(1, Item('Не предлагать помощь', confirm=decline))

    def on_action(self, act: str) -> None:
        if act == 'back':
            self.game.ui.clear()
            self.game.ui.push(MainMenu(self.game))
            return
        super().on_action(act)

    def list_rect(self) -> pygame.Rect:
        return pygame.Rect(80, 470, 420, 200)

    def analysis(self) -> List[str]:
        r = self.run
        tips = []
        src = sorted(r.get('damage_sources', {}).items(), key=lambda kv: -kv[1])
        if src:
            k, v = src[0]
            tips.append(f"Больше всего урона: {k} ({int(v)})")
            if 'стрелк' in k or 'залп' in k:
                tips.append('Совет: смените цвет за мгновение до попадания — пуля отразится')
            elif 'Камикадзе' in k:
                tips.append('Совет: рывок сквозь взрыв даёт неуязвимость')
            elif 'Преследователь' in k:
                tips.append('Совет: BLUE ударная волна отталкивает плотные группы')
        fails, ok = r.get('refraction_fails', 0), r.get('refractions', 0)
        if fails + ok >= 5:
            tips.append(f"Преломления: {ok} из {ok + fails} ({100 * ok / (ok + fails):.0f}%)")
        shots = max(1, r.get('shots', 0))
        tips.append(f"Точность: {100 * r.get('hits', 0) / shots:.0f}% · убийств в такт: {r.get('beat_kills', 0)}")
        return tips

    def draw(self, surf: pygame.Surface) -> None:
        r = self.run
        W = CFG.SCREEN_WIDTH
        from .game import RUN_TYPES
        text(surf, 'Итоги забега', 40, CFG.COLOR_ACCENT, (80, 30), bold=True)
        if self.result.get('new_record'):
            text(surf, 'НОВЫЙ РЕКОРД!', 26, CFG.COLOR_SUCCESS, (W - 80, 40), 'right', True)
        arch = ARCHETYPES.get(r.get('archetype', 'balanced'), ARCHETYPES['balanced'])
        lines = [
            f"{RUN_TYPES.get(r['run_type'], r['run_type'])} · волна {r['wave']} · счёт {r['score']} · время {r['time'] / 60:.1f} мин",
            f"Причина: {r.get('death_cause') or '—'}",
            f"Убийств {r['kills']} · элит {r['elites']} · боссов {r['bosses']} · макс. комбо {r['max_combo']}",
            f"Стиль: {arch[0]} — {arch[1]}",
            'Артефакты: ' + (', '.join(ARTIFACTS[a]['name'] for a in r.get('artifacts_list', [])) or 'нет'),
        ]
        y = 100
        for ln in lines:
            text(surf, ln, 18, CFG.COLOR_TEXT, (80, y))
            y += 28
        y += 8
        text(surf, 'Разбор', 20, CFG.COLOR_ACCENT, (80, y), bold=True)
        y += 30
        for tline in self.analysis():
            text(surf, '• ' + tline, 16, (200, 210, 230), (80, y))
            y += 24
        # CP
        px = 700
        panel(surf, (px, 100, 500, 340), 170)
        text(surf, f"Chroma Points: +{self.result.get('cp_total', 0)}", 22, CFG.COLOR_ACCENT, (px + 16, 112), bold=True)
        yy = 150
        for name, v in self.result.get('cp_lines', [])[-11:]:
            text(surf, name, 15, CFG.COLOR_TEXT, (px + 16, yy))
            text(surf, f"{v:+d}", 15, CFG.COLOR_ACCENT, (px + 484, yy), 'right')
            yy += 22
        if r['run_type'] == 'training':
            text(surf, 'Тренировка: награды не начисляются', 15, (180, 180, 200), (px + 16, yy))
        super_draw_list(self, surf)


def super_draw_list(screen: ListScreen, surf: pygame.Surface) -> None:
    """Рисует только список (без заголовка и боковой панели) — для экрана итогов."""
    lr = screen.list_rect()
    panel(surf, (lr.x - 10, lr.y - 10, lr.w + 20, min(lr.h, len(screen.items) * 40) + 20), 150)
    screen.row_rects = []
    for i, it in enumerate(screen.items):
        rr = pygame.Rect(lr.x, lr.y + i * 40, lr.w, 36)
        screen.row_rects.append((i, rr))
        sel = i == screen.index
        if sel:
            pygame.draw.rect(surf, (50, 60, 95), rr)
            pygame.draw.rect(surf, CFG.COLOR_ACCENT, rr, 2)
        text(surf, it.get_label(), 18, it.color or CFG.COLOR_TEXT, (rr.x + 12, rr.y + 7), bold=sel)
    desc = screen.items[screen.index].get_desc() if screen.items else ''
    if desc:
        text_block(surf, desc, 15, (180, 190, 210), lr.right + 30, lr.y, 600)
    if screen.message_t > 0:
        text(surf, screen.message, 18, CFG.COLOR_ACCENT, (CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT - 40), 'center', True)

"""Экраны 0.7.0: дерево улучшений (6 веток), сборки, магазин забега, победа, испытания,
редактор своих волн, повтор последних секунд, график урона."""
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .config import ALL_MODES, CFG, MODES
from .entities import draw_shape
from .hires import layer
from .progression import (BRANCHES, BUILD_PRESETS, NEW_IN_070, PRESTIGE_SPENT, UPGRADES, branch_spent, node_cost,
                          node_of_week, node_status, preview_node, saves_dir, total_spent)
from .ui import (ConfirmScreen, Item, ListScreen, Screen, TextInputScreen, panel, text, text_block, wrap)
from .utils import clamp, color_lerp, mode_color

TREE_FILTERS = [('all', 'Все'), ('available', 'Доступные'), ('owned', 'Купленные'), ('new', 'Новые'),
                ('key', 'Ключевые')]
STATUS_FILL = {'maxed': (30, 60, 45), 'available': (35, 45, 75), 'expensive': (40, 40, 55),
               'locked': (22, 24, 32), 'blocked': (45, 25, 30), 'hidden': (16, 16, 22)}


def branch_color(b: str) -> Tuple[int, int, int]:
    col = BRANCHES[b][1]
    return col or mode_color(b)


def node_ancestors(nid: str) -> List[str]:
    """Все узлы-предки (requires + первый из requires_any) в порядке покупки."""
    out: List[str] = []

    def walk(n: str) -> None:
        node = UPGRADES[n]
        reqs = list(node['requires']) + (node.get('requires_any') or [])[:1]
        for r in reqs:
            if r in UPGRADES and r not in out:
                walk(r)
                out.append(r)
    walk(nid)
    return out


def node_path(profile: Any, nid: str) -> Tuple[List[str], int]:
    """Некупленные узлы на пути к nid (включая его самого) и их суммарная цена."""
    ups = profile.data['upgrades']
    path = [n for n in node_ancestors(nid) if ups.get(n, 0) <= 0]
    if ups.get(nid, 0) < UPGRADES[nid]['max']:
        path.append(nid)
    cost = sum(node_cost(profile, n, 0 if n != nid else None) for n in path)
    return path, cost


def is_new_node(profile: Any, nid: str) -> bool:
    """«НОВОЕ» — узел, добавленный в 0.7.0, который игрок ещё не смотрел."""
    return nid in NEW_IN_070 and nid not in profile.data.get('seen_nodes', [])


def tree_filter_ok(profile: Any, nid: str, flt: str, query: str) -> bool:
    node = UPGRADES[nid]
    status, _ = node_status(profile, nid)
    if query:
        q = query.lower()
        if status == 'hidden' or (q not in node['name'].lower() and q not in node['desc'].lower()):
            return False
    lvl = profile.data['upgrades'].get(nid, 0)
    if flt == 'available':
        return status == 'available'
    if flt == 'owned':
        return lvl > 0
    if flt == 'new':
        return is_new_node(profile, nid) and status != 'hidden'
    if flt == 'key':
        return bool(node['key'])
    return True


class UpgradeTreeScreen(Screen):
    """Дерево из 6 веток: фильтры, поиск, путь к узлу, «НОВОЕ», переключаемые и скрытые узлы."""
    ROW_H = 50
    TOP = 104
    VISIBLE = 8

    def __init__(self, game: Any):
        super().__init__(game)
        self.branches = list(BRANCHES)
        self.col = 0
        self.row = 0
        self.filter = 0
        self.query = ''
        self.scroll: Dict[str, int] = {b: 0 for b in self.branches}
        self.message = ''
        self.message_t = 0.0
        self.node_rects: List[Tuple[str, pygame.Rect]] = []
        self.dirty_seen = False

    # --- данные
    def column(self, b: str) -> List[str]:
        p = self.game.profile
        flt = TREE_FILTERS[self.filter][0]
        nodes = sorted([nid for nid, n in UPGRADES.items() if n['branch'] == b],
                       key=lambda nid: (UPGRADES[nid]['row'], nid))
        return [n for n in nodes if tree_filter_ok(p, n, flt, self.query)]

    def current(self) -> Optional[str]:
        col = self.column(self.branches[self.col])
        if not col:
            return None
        self.row = int(clamp(self.row, 0, len(col) - 1))
        return col[self.row]

    def say(self, m: str) -> None:
        self.message, self.message_t = m, 3.0

    def update(self, dt: float) -> None:
        super().update(dt)
        self.message_t -= dt
        cur = self.current()
        p = self.game.profile
        if cur and node_status(p, cur)[0] != 'hidden' and cur not in p.data.setdefault('seen_nodes', []):
            p.data['seen_nodes'].append(cur)
            self.dirty_seen = True

    # --- действия
    def step_col(self, s: int) -> None:
        for _ in range(len(self.branches)):
            self.col = (self.col + s) % len(self.branches)
            if self.column(self.branches[self.col]):
                break
        self.snd()

    def buy(self) -> None:
        p = self.game.profile
        cur = self.current()
        if cur is None:
            return
        node = UPGRADES[cur]
        if node.get('toggle') and p.data['upgrades'].get(cur, 0) >= node['max']:
            return self.toggle()
        ok, msg = p.buy_upgrade(cur)
        self.say(msg)
        if ok:
            p.save()
            self.snd('ui_select')

    def toggle(self) -> None:
        cur = self.current()
        if cur is None:
            return
        ok, msg = self.game.profile.toggle_node(cur)
        self.say(msg)
        if ok:
            self.game.profile.save()

    def try_node(self) -> None:
        cur = self.current()
        if cur is None:
            return
        if self.game.profile.data['upgrades'].get(cur, 0) >= UPGRADES[cur]['max']:
            self.say('Узел уже на максимуме')
            return
        self.game.ui.clear()
        self.game.start_run('training', trial_node=cur)
        self.game.toast(f"Пробный узел: {UPGRADES[cur]['name']} (+1 уровень, только в тренировке)", 5.0)

    def open_search(self) -> None:
        def done(v: str) -> None:
            self.query = '' if v == 'Пилот' else v.strip()
            self.row = 0
        self.game.ui.push(TextInputScreen(self.game, 'Поиск узла (пусто — сброс)', self.query, done, 24))

    def open_reset(self) -> None:
        self.game.ui.push(TreeResetScreen(self.game, self.branches[self.col]))

    def on_action(self, act: str) -> None:
        if act == 'left':
            self.step_col(-1)
        elif act == 'right':
            self.step_col(1)
        elif act == 'up':
            self.row -= 1
            self.snd()
        elif act == 'down':
            self.row += 1
            self.snd()
        elif act == 'pageup':
            self.row -= self.VISIBLE
        elif act == 'pagedown':
            self.row += self.VISIBLE
        elif act == 'confirm':
            self.buy()
        elif act == 'tab':
            self.filter = (self.filter + 1) % len(TREE_FILTERS)
            self.row = 0
            if not self.column(self.branches[self.col]):
                self.step_col(1)
            self.snd()
        elif act == 'reset':
            self.open_reset()
        elif act in ('char:f', 'char:а', 'char:/', 'char:.'):
            self.open_search()
        elif act in ('char:t', 'char:е'):
            self.toggle()
        elif act in ('char:b', 'char:и'):
            self.game.ui.push(BuildsScreen(self.game))
        elif act in ('char:p', 'char:з'):
            self.try_node()
        elif act == 'delete' and self.query:
            self.query = ''
        elif act == 'back':
            if self.dirty_seen:
                self.game.profile.save()
            self.game.ui.pop()

    def on_mouse(self, pos: Tuple[float, float], click: bool) -> None:
        for nid, r in self.node_rects:
            if r.collidepoint(pos):
                b = UPGRADES[nid]['branch']
                self.col = self.branches.index(b)
                col = self.column(b)
                if nid in col:
                    self.row = col.index(nid)
                if click:
                    self.buy()
                return

    # --- отрисовка
    def draw(self, surf: pygame.Surface) -> None:
        g = self.game
        p = g.profile
        W, H = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        text(surf, 'Дерево улучшений', 34, CFG.COLOR_ACCENT, (30, 18), bold=True)
        pres = p.data.get('prestige', 0)
        text(surf, f"CP: {p.cp}" + (f"  ·  Престиж {pres}" if pres else ''), 22, CFG.COLOR_TEXT, (W - 30, 26), 'right', True)
        flt = TREE_FILTERS[self.filter][1]
        week = node_of_week()
        info = (f"Фильтр (Tab): {flt}  ·  Поиск (F): {self.query or '—'}  ·  Вложено: {total_spent(p.data['upgrades'])} CP"
                f"  ·  Узел недели −30%: {UPGRADES[week]['name']}")
        text(surf, info, 15, (170, 180, 205), (32, 66))
        rec = p.recommended_upgrade()
        cur = self.current()
        anc = set(node_ancestors(cur)) if cur else set()
        self.node_rects = []
        x0, gap = 30, 10
        col_w = int((W - 2 * x0 - gap * (len(self.branches) - 1)) / len(self.branches))
        seen = set(p.data.get('seen_nodes', []))
        disabled = set(p.data.get('disabled_nodes', []))
        for ci, b in enumerate(self.branches):
            name = BRANCHES[b][0]
            col = branch_color(b)
            x = x0 + ci * (col_w + gap)
            hdr = pygame.Rect(x, 84, col_w, 18)
            if ci == self.col:
                pygame.draw.rect(surf, (40, 46, 70), hdr)
            text(surf, f"{name} · {branch_spent(p.data['upgrades'], b)}", 15, col, (x + 4, 84), bold=True)
            nodes = self.column(b)
            sc = self.scroll.get(b, 0)
            if ci == self.col and cur in nodes:
                ri = nodes.index(cur)
                if ri < sc:
                    sc = ri
                elif ri >= sc + self.VISIBLE:
                    sc = ri - self.VISIBLE + 1
            sc = int(clamp(sc, 0, max(0, len(nodes) - self.VISIBLE)))
            self.scroll[b] = sc
            positions: Dict[str, pygame.Rect] = {}
            for vi, nid in enumerate(nodes[sc:sc + self.VISIBLE]):
                r = pygame.Rect(x, self.TOP + vi * self.ROW_H, col_w, self.ROW_H - 6)
                positions[nid] = r
                self.node_rects.append((nid, r))
            for nid, r in positions.items():
                for req in UPGRADES[nid]['requires'] + list(UPGRADES[nid].get('requires_any') or []):
                    if req in positions:
                        a = positions[req]
                        on_path = (nid == cur or nid in anc) and req in anc
                        lc = CFG.COLOR_ACCENT if on_path else (70, 80, 110)
                        pygame.draw.line(surf, lc, (a.x + 6, a.bottom), (r.x + 6, r.y), 3 if on_path else 1)
            for nid, r in positions.items():
                self.draw_node(surf, p, nid, r, col, nid == cur, nid in anc, nid == rec, nid == week,
                               nid in NEW_IN_070 and nid not in seen, nid in disabled)
            if len(nodes) > self.VISIBLE:
                frac = sc / max(1, len(nodes) - self.VISIBLE)
                pygame.draw.rect(surf, (90, 100, 140), (x + col_w - 3, self.TOP + int(frac * (self.VISIBLE * self.ROW_H - 30)), 3, 30))
                text(surf, f"{sc + 1}–{min(len(nodes), sc + self.VISIBLE)} из {len(nodes)}", 12, (130, 140, 165),
                     (x + col_w, self.TOP + self.VISIBLE * self.ROW_H - 2), 'right')
            if not nodes:
                text(surf, 'нет узлов', 14, (110, 115, 135), (x + 6, self.TOP + 6))
        self.draw_details(surf, p, cur, rec)
        text(surf, '←→↑↓ узел · Enter купить · Tab фильтр · F поиск · T вкл/выкл · P попробовать · B сборки и престиж · '
             'R сброс · Esc назад', 13, (130, 140, 165), (30, H - 22))
        if self.message_t > 0:
            text(surf, self.message, 18, CFG.COLOR_ACCENT, (W / 2, 520), 'center', True)

    def draw_node(self, surf: pygame.Surface, p: Any, nid: str, r: pygame.Rect, col: Tuple[int, int, int], sel: bool,
                  on_path: bool, rec: bool, week: bool, new: bool, disabled: bool) -> None:
        node = UPGRADES[nid]
        status, _ = node_status(p, nid)
        lvl = p.data['upgrades'].get(nid, 0)
        pygame.draw.rect(surf, STATUS_FILL.get(status, (18, 18, 24)), r)
        border = col if status in ('available', 'maxed') else (70, 75, 95)
        if on_path:
            border = color_lerp(border, CFG.COLOR_ACCENT, 0.6)
        if sel:
            border = CFG.COLOR_ACCENT
        pygame.draw.rect(surf, border, r, 3 if sel else (2 if on_path else 1))
        if status == 'hidden':
            text(surf, '???', 16, (120, 120, 140), (r.x + 8, r.y + 4), bold=sel)
            text(surf, 'скрытый узел', 12, (110, 110, 130), (r.x + 8, r.y + 25))
            return
        tcol = CFG.COLOR_TEXT if status != 'locked' else (110, 115, 135)
        name = node['name']
        max_chars = max(6, (r.w - 34) // 8)
        if len(name) > max_chars:
            name = name[:max_chars - 1] + '…'
        text(surf, name, 14, tcol, (r.x + 8, r.y + 4), bold=sel)
        lv = f"{lvl}/{node['max']}" + ('  ВЫКЛ' if disabled else '')
        text(surf, lv, 12, (230, 120, 120) if disabled else (170, 180, 205), (r.x + 8, r.y + 25))
        if lvl < node['max']:
            cost = node_cost(p, nid)
            text(surf, f"{cost}", 12, CFG.COLOR_ACCENT if status == 'available' else (130, 130, 150),
                 (r.right - 8, r.y + 25), 'right')
        tags = []
        if node['key']:
            draw_shape(surf, 'diamond', CFG.COLOR_ACCENT, r.right - 10, r.y + 10, 5)
        if node['tradeoff']:
            tags.append(('±', CFG.COLOR_DANGER))
        if rec:
            tags.append(('*', CFG.COLOR_ACCENT))
        if week:
            tags.append(('%', CFG.COLOR_SUCCESS))
        if node.get('toggle'):
            tags.append(('I/O', (180, 200, 255)))
        tx = r.right - 22
        for t, c in tags:
            text(surf, t, 13, c, (tx, r.y + 3), 'right')
            tx -= 14
        if new:
            nr = pygame.Rect(r.x + 62, r.bottom - 17, 40, 12)
            pygame.draw.rect(surf, CFG.COLOR_SUCCESS, nr)
            text(surf, 'НОВОЕ', 10, (15, 25, 15), (nr.centerx, nr.y), 'center', True)

    def draw_details(self, surf: pygame.Surface, p: Any, cur: Optional[str], rec: Optional[str]) -> None:
        W = CFG.SCREEN_WIDTH
        side = pygame.Rect(30, 512 + 22, W - 60, 150)
        panel(surf, side, 190)
        if cur is None:
            text(surf, 'Нет узлов под фильтр/поиск. Tab — сменить фильтр, Backspace — сбросить поиск', 16,
                 CFG.COLOR_TEXT, (side.x + 14, side.y + 12))
            return
        node = UPGRADES[cur]
        status, reason = node_status(p, cur)
        if status == 'hidden':
            text(surf, 'Скрытый узел', 20, CFG.COLOR_ACCENT, (side.x + 14, side.y + 8), bold=True)
            text(surf, reason, 16, (200, 200, 220), (side.x + 14, side.y + 38))
            return
        tags = [t for t, ok in (('ключевой', node['key']), ('компромисс', node['tradeoff']),
                                ('переключаемый', node.get('toggle')), ('мост', node.get('kind') == 'bridge'),
                                (f"с волны {node.get('from_wave')}", node.get('from_wave'))) if ok]
        text(surf, node['name'] + (f"  ({', '.join(tags)})" if tags else ''), 20, CFG.COLOR_ACCENT,
             (side.x + 14, side.y + 8), bold=True)
        text_block(surf, node['desc'], 15, CFG.COLOR_TEXT, side.x + 14, side.y + 36, side.w // 2 - 20)
        text(surf, reason, 15, CFG.COLOR_SUCCESS if status == 'available' else (210, 170, 170), (side.x + 14, side.y + 100))
        rx = side.x + side.w // 2 + 10
        pv = preview_node(p, cur) if status != 'maxed' else []
        y = side.y + 36
        if pv:
            y = text_block(surf, 'Предпросмотр: ' + '; '.join(pv[:3]), 14, (180, 200, 230), rx, y, side.w // 2 - 30) + 2
        if status in ('locked', 'expensive'):
            path, cost = node_path(p, cur)
            if len(path) > 1:
                y = text_block(surf, 'Путь: ' + ' → '.join(UPGRADES[n]['name'] for n in path) + f" (≈{cost} CP)", 14,
                               (230, 210, 150), rx, y, side.w // 2 - 30) + 2
        hull = node.get('hull')
        if hull:
            text(surf, f"Работает только с корпусом: {hull}", 14, (200, 180, 255), (rx, y))
        if rec:
            text(surf, f"* Рекомендация: {UPGRADES[rec]['name']}", 14, CFG.COLOR_ACCENT, (side.right - 14, side.y + 8), 'right')


class TreeResetScreen(ListScreen):
    title = 'Сброс дерева'

    def __init__(self, game: Any, branch: str):
        self.branch = branch
        super().__init__(game)

    def build(self) -> None:
        g, p = self.game, self.game.profile
        fee = 'бесплатно (раз в день)' if p.reset_fee_free() else 'удерживается 10%'

        def do(branch: Optional[str]) -> None:
            refund = p.reset_upgrades(branch)
            p.save()
            g.ui.pop()
            g.toast(f"Сброс: возвращено {refund} CP")
        name = BRANCHES[self.branch][0]
        self.items = [
            Item(f"Сбросить ветку «{name}»", confirm=lambda: g.ui.push(ConfirmScreen(
                g, 'Сброс ветки', f"Вернуть CP за ветку «{name}»? Сброс: {fee}", lambda: do(self.branch))),
                desc=f"Возвращается уплаченное за узлы ветки. Зависимые узлы других веток тоже снимаются. {fee}"),
            Item('Сбросить всё дерево', confirm=lambda: g.ui.push(ConfirmScreen(
                g, 'Полный сброс', f"Вернуть все вложенные CP? Сброс: {fee}", lambda: do(None))),
                desc=f"Возвращаются все уплаченные CP. {fee}"),
            Item('Отмена', confirm=g.ui.pop),
        ]


# =====================================================================
# СБОРКИ И ПРЕСТИЖ
# =====================================================================
def export_build_code(code: str) -> str:
    """Код сборки пишется в файл рядом с сохранениями (буфер обмена в pygame ненадёжен)."""
    try:
        path = os.path.join(saves_dir(), 'build_code.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code + '\n')
        return path
    except OSError:
        return ''


class BuildsScreen(ListScreen):
    title = 'Сборки дерева'

    def build(self) -> None:
        g, p = self.game, self.game.profile
        self.items = []
        for i in range(3):
            self.items.append(Item((lambda i=i: self.slot_label(i)), confirm=(lambda i=i: self.slot_menu(i)),
                                   desc=(lambda i=i: self.slot_desc(i))))
        for key, pre in BUILD_PRESETS.items():
            self.items.append(Item(f"Пресет: {pre['name']}", confirm=(lambda key=key: self.apply(BUILD_PRESETS[key]['upgrades'], BUILD_PRESETS[key]['name'])),
                                   desc=(lambda key=key: BUILD_PRESETS[key]['desc'] + '\n\nОтносительно текущего дерева:\n' +
                                         self.compare_text(BUILD_PRESETS[key]['upgrades']))))
        self.items += [
            Item('Код текущего дерева', confirm=self.show_code,
                 desc='Создаёт код CS7-… и сохраняет его в build_code.txt в папке сохранений — им можно поделиться'),
            Item('Ввести код сборки', confirm=self.enter_code, desc='Вставьте/наберите код CS7-…: покажем сравнение и применим'),
            Item((lambda: f"Престиж ({p.data.get('prestige', 0)})"), confirm=self.prestige, color=(255, 210, 120),
                 desc=(lambda: f"Нужно вложить в дерево {PRESTIGE_SPENT} CP (сейчас {total_spent(p.data['upgrades'])}). "
                               'Дерево сбрасывается, половина CP сгорает, взамен +5% CP навсегда и титул')),
        ]

    def subtitle(self) -> str:
        return f"CP: {self.game.profile.cp} · Применение сборки сбрасывает дерево и покупает узлы, пока хватает CP"

    def slot_label(self, i: int) -> str:
        b = self.game.profile.data['builds'][i]
        return f"Слот {i + 1}: {b['name']}" if b else f"Слот {i + 1}: пусто"

    def slot_desc(self, i: int) -> str:
        b = self.game.profile.data['builds'][i]
        if not b:
            return 'Enter — сохранить текущее дерево в этот слот'
        return 'Enter — сохранить / применить / переименовать\n\nОтносительно текущего:\n' + self.compare_text(b['upgrades'])

    def compare_text(self, ups: Dict[str, int]) -> str:
        diff = self.game.profile.compare_build(ups)
        return '\n'.join(diff[:8]) if diff else 'Без отличий по модификаторам'

    def slot_menu(self, i: int) -> None:
        g, p = self.game, self.game.profile
        b = p.data['builds'][i]
        if not b:
            msg = p.save_build(i)
            p.save()
            return msg
        g.ui.push(BuildSlotScreen(g, i))

    def apply(self, ups: Dict[str, int], name: str) -> None:
        g, p = self.game, self.game.profile

        def go() -> None:
            ok, msg = p.apply_build(ups, name)
            p.save()
            self.say(msg)
        g.ui.push(ConfirmScreen(g, 'Применить сборку', f"Сбросить дерево и купить «{name}»?", go))

    def show_code(self) -> str:
        code = self.game.profile.build_code()
        path = export_build_code(code)
        return f"{code}" + (f"  (сохранён в {os.path.basename(path)})" if path else '')

    def enter_code(self) -> None:
        g, p = self.game, self.game.profile

        def done(v: str) -> None:
            ups = p.parse_build_code(v)
            if ups is None:
                self.say('Неверный код: ожидается CS7-…')
                return
            self.apply(ups, 'код')
        g.ui.push(TextInputScreen(g, 'Код сборки (CS7-…)', 'CS7-', done, 400))

    def prestige(self) -> str:
        g, p = self.game, self.game.profile
        if not p.can_prestige():
            return f"Нужно вложить в дерево {PRESTIGE_SPENT} CP"

        def go() -> None:
            ok, msg = p.prestige()
            p.save()
            self.say(msg)
        g.ui.push(ConfirmScreen(g, 'Престиж', 'Сбросить дерево, сжечь половину CP и получить +5% CP навсегда?', go))
        return ''


class BuildSlotScreen(ListScreen):
    def __init__(self, game: Any, slot: int):
        self.slot = slot
        self.title = f"Слот {slot + 1}"
        super().__init__(game)

    def build(self) -> None:
        g, p = self.game, self.game.profile
        b = p.data['builds'][self.slot]

        def save() -> str:
            msg = p.save_build(self.slot, b['name'] if b else '')
            p.save()
            return msg

        def apply() -> None:
            def go() -> None:
                ok, msg = p.apply_build(b['upgrades'], b['name'])
                p.data['disabled_nodes'] = [n for n in b.get('disabled', []) if n in p.data['upgrades']]
                p.save()
                g.toast(msg)
                g.ui.pop()
            g.ui.push(ConfirmScreen(g, 'Применить', f"Сбросить дерево и купить «{b['name']}»?", go))

        def rename() -> None:
            def done(v: str) -> None:
                b['name'] = v[:20]
                p.save()
            g.ui.push(TextInputScreen(g, 'Название сборки', b['name'], done, 20))

        def code() -> str:
            c = p.build_code(b['upgrades'])
            export_build_code(c)
            return c
        self.items = [Item('Применить', confirm=apply), Item('Перезаписать текущим деревом', confirm=save),
                      Item('Переименовать', confirm=rename), Item('Показать код', confirm=code),
                      Item('Назад', confirm=g.ui.pop)]


# =====================================================================
# МАГАЗИН ЗАБЕГА И ПОБЕДА
# =====================================================================
class ShopScreen(ListScreen):
    title = 'Магазин осколков'
    show_world = True

    def __init__(self, game: Any, offer: List[str]):
        self.offer = list(offer)
        super().__init__(game)

    def build(self) -> None:
        from .mechanics import SHOP_ITEMS, TEMP_NODES
        g = self.game
        self.items = [Item('Продолжить бой', confirm=g.ui.pop, color=CFG.COLOR_ACCENT,
                           desc='Неистраченные осколки сохраняются до следующего магазина')]
        for it in self.offer:
            info = SHOP_ITEMS.get(it) or TEMP_NODES.get(it)
            if not info:
                continue
            self.items.append(Item(info['name'], (lambda c=info['cost']: f"{c} ♦"),
                                   confirm=(lambda it=it: self.buy(it)), desc=info['desc'],
                                   enabled=(lambda c=info['cost']: g.color_mech.shards >= c)))

    def buy(self, it: str) -> str:
        ok, msg = self.game.color_mech.buy(it)
        if ok and it not in ('heal', 'shield', 'reroll', 'dmg', 'rate'):
            self.offer.remove(it)
            idx = self.index
            self.build()
            self.index = min(idx, len(self.items) - 1)
        return msg

    def subtitle(self) -> str:
        cm = self.game.color_mech
        return (f"Осколки: {cm.shards} ♦ · Перебросов артефактов: {cm.rerolls} · Временные узлы действуют до конца забега"
                + (f" · Взято: {len(cm.temp_nodes)}" if cm.temp_nodes else ''))


class VictoryScreen(ListScreen):
    title = 'ПОБЕДА!'
    show_world = True

    def build(self) -> None:
        g = self.game
        from .waves import VICTORY_WAVE
        self.items = [
            Item('Продолжить бесконечно', confirm=self.go_on, color=CFG.COLOR_ACCENT,
                 desc=f"Волна {VICTORY_WAVE} пройдена. Дальше — бесконечный режим: волны растут, рекорды пишутся, "
                      'бонус «Победа» уже засчитан'),
            Item('Завершить забег с победой', confirm=lambda: (g.ui.pop(), g.end_run('victory')),
                 desc='Итоги и CP начисляются сразу, с бонусом +60 CP за победу'),
        ]

    def go_on(self) -> None:
        self.game.ui.pop()
        self.game.toast('Бесконечный режим: удачи!', 4.0)

    def on_action(self, act: str) -> None:
        if act == 'back':
            return
        super().on_action(act)

    def subtitle(self) -> str:
        g = self.game
        return f"Счёт {int(g.score)} · Убийств {g.stats.get('kills', 0)} · Время {g.game_time / 60:.1f} мин"


# =====================================================================
# ИСПЫТАНИЯ ТРЕНИРОВКИ
# =====================================================================
class TrialsScreen(ListScreen):
    title = 'Испытания цвета'

    def build(self) -> None:
        from .mechanics import TRIALS
        g, p = self.game, self.game.profile
        self.items = []
        for tid, t in TRIALS.items():
            done = tid in p.data.get('trials_done', [])
            self.items.append(Item(t['name'], (lambda done=done, t=t: '√ пройдено' if done else f"+{t['reward']} CP"),
                                   confirm=(lambda tid=tid: (g.ui.clear(), g.start_run('training', trial=tid))),
                                   color=CFG.COLOR_SUCCESS if done else None,
                                   desc=f"{t['desc']}\nЦвет: {t['mode']} · время {int(t['time'])} с\n"
                                        'Награда — только за первое прохождение. F5 — перезапуск, Esc — выход'))

    def subtitle(self) -> str:
        from .mechanics import TRIALS
        return f"Пройдено {len(self.game.profile.data.get('trials_done', []))} из {len(TRIALS)}"


# =====================================================================
# РЕДАКТОР СВОИХ ВОЛН
# =====================================================================
SPECIAL_CHOICES = [None, 'darkness', 'haste', 'mono', 'survive', 'ambush', 'onecolor', 'inversion', 'gravity', 'mirror']
BOSS_CHOICES = [None, 'boss', 'hydra', 'spectrum']
MAX_CUSTOM_WAVES = 15


def editor_kinds() -> List[str]:
    from .game import ENEMY_CLASSES
    return [k for k in ENEMY_CLASSES if k not in ('hydra_head',)]


def wave_summary(w: Dict[str, Any]) -> str:
    from .entities import ENEMY_NAMES
    from .enemies_ext import EXT_NAMES
    names = dict(ENEMY_NAMES)
    names.update(EXT_NAMES)
    parts = [f"{names.get(k, k)}×{c}" for k, c in w.get('members', []) if c > 0]
    if w.get('boss'):
        parts.insert(0, f"БОСС {w['boss']}")
    if w.get('special'):
        parts.append(f"[{w['special']}]")
    return ', '.join(parts) or 'пусто'


def validate_custom_waves(waves: Any) -> List[Dict[str, Any]]:
    """Чистит сохранённые волны: известные враги, 0–40 штук, известные спецволны/боссы."""
    kinds = set(editor_kinds())
    out = []
    for w in (waves or [])[:MAX_CUSTOM_WAVES]:
        if not isinstance(w, dict):
            continue
        members = []
        for m in w.get('members', []):
            try:
                k, c = m[0], int(m[1])
            except (TypeError, ValueError, IndexError):
                continue
            if k in kinds and c > 0:
                members.append([k, min(40, c)])
        out.append({'members': members, 'special': w.get('special') if w.get('special') in SPECIAL_CHOICES else None,
                    'boss': w.get('boss') if w.get('boss') in BOSS_CHOICES else None})
    return out


class WaveEditorScreen(ListScreen):
    title = 'Свои волны'

    def waves(self) -> List[Dict[str, Any]]:
        p = self.game.profile
        p.data['custom_waves'] = validate_custom_waves(p.data.get('custom_waves'))
        return p.data['custom_waves']

    def build(self) -> None:
        g = self.game
        ws = self.waves()
        self.items = []
        for i, w in enumerate(ws):
            self.items.append(Item(f"Волна {i + 1}", (lambda w=w: wave_summary(w)[:38]),
                                   confirm=(lambda i=i: g.ui.push(WaveEditScreen(g, i, self))),
                                   desc=(lambda w=w: wave_summary(w) + '\n\nEnter — редактировать')))
        self.items += [
            Item('+ Добавить волну', confirm=self.add, enabled=lambda: len(self.waves()) < MAX_CUSTOM_WAVES,
                 desc=f"До {MAX_CUSTOM_WAVES} волн. Новая волна копирует предыдущую"),
            Item('− Удалить последнюю', confirm=self.remove, enabled=lambda: bool(self.waves())),
            Item('СТАРТ', confirm=self.start, color=CFG.COLOR_ACCENT,
                 desc='Забег идёт по вашим волнам; после последней — победа. Улучшения дерева работают, '
                      'CP начисляются как в стандарте'),
        ]

    def subtitle(self) -> str:
        return 'Соберите свой сценарий: состав врагов, спецволна и босс для каждой волны'

    def add(self) -> None:
        ws = self.waves()
        ws.append({'members': [list(m) for m in ws[-1]['members']] if ws else [['chaser', 6], ['shooter', 2]],
                   'special': None, 'boss': None})
        self.game.profile.save()
        self.build()

    def remove(self) -> None:
        ws = self.waves()
        if ws:
            ws.pop()
            self.game.profile.save()
        self.build()
        self.index = min(self.index, len(self.items) - 1)

    def start(self) -> str:
        ws = [w for w in self.waves() if w['members'] or w['boss']]
        if not ws:
            return 'Добавьте хотя бы одну непустую волну'
        self.game.profile.save()
        self.game.ui.clear()
        self.game.start_run('custom', custom_waves=ws)
        return ''


class WaveEditScreen(ListScreen):
    def __init__(self, game: Any, idx: int, parent: WaveEditorScreen):
        self.idx = idx
        self.parent = parent
        self.title = f"Волна {idx + 1}"
        super().__init__(game)

    def wave(self) -> Dict[str, Any]:
        return self.game.profile.data['custom_waves'][self.idx]

    def count(self, k: str) -> int:
        for m in self.wave()['members']:
            if m[0] == k:
                return int(m[1])
        return 0

    def set_count(self, k: str, v: int) -> None:
        v = int(clamp(v, 0, 40))
        ms = self.wave()['members']
        for m in ms:
            if m[0] == k:
                m[1] = v
                break
        else:
            ms.append([k, v])
        self.wave()['members'] = [m for m in ms if m[1] > 0]

    def cycle(self, key: str, choices: List[Any], s: int) -> None:
        w = self.wave()
        cur = choices.index(w.get(key)) if w.get(key) in choices else 0
        w[key] = choices[(cur + s) % len(choices)]

    def build(self) -> None:
        from .entities import ENEMY_NAMES
        from .enemies_ext import EXT_HINTS, EXT_NAMES
        names = dict(ENEMY_NAMES)
        names.update(EXT_NAMES)
        self.items = [
            Item('Спецволна', lambda: str(self.wave().get('special') or 'нет'),
                 left=lambda: self.cycle('special', SPECIAL_CHOICES, -1), right=lambda: self.cycle('special', SPECIAL_CHOICES, 1),
                 desc='Особые условия волны: темнота, ускорение, один цвет, выживание, засада, инверсия, гравитация, зеркало'),
            Item('Босс', lambda: str(self.wave().get('boss') or 'нет'),
                 left=lambda: self.cycle('boss', BOSS_CHOICES, -1), right=lambda: self.cycle('boss', BOSS_CHOICES, 1),
                 desc='Классический босс, Гидра (делится на головы) или Спектр (меняет уязвимый цвет)'),
        ]
        for k in editor_kinds():
            self.items.append(Item(names.get(k, k), (lambda k=k: str(self.count(k))),
                                   left=(lambda k=k: self.set_count(k, self.count(k) - 1)),
                                   right=(lambda k=k: self.set_count(k, self.count(k) + 1)),
                                   desc=EXT_HINTS.get(k, 'Базовый враг') + '\n←→ — количество (0–40), PgUp/PgDn — листать'))
        self.items.append(Item('Готово', confirm=self.done, color=CFG.COLOR_ACCENT))

    def done(self) -> None:
        self.game.profile.save()
        self.game.ui.pop()
        self.parent.build()

    def on_action(self, act: str) -> None:
        if act == 'back':
            self.done()
            return
        super().on_action(act)

    def subtitle(self) -> str:
        return wave_summary(self.wave())[:110]


# =====================================================================
# ПОВТОР ПОСЛЕДНИХ СЕКУНД И ГРАФИК УРОНА
# =====================================================================
class ReplayScreen(Screen):
    """Проигрывает кольцевой буфер color_mech.replay (снимки раз в 0.05 с, ~10 с)."""

    def __init__(self, game: Any, frames: Optional[List[Any]] = None):
        super().__init__(game)
        src = frames if frames is not None else list(getattr(getattr(game, 'color_mech', None), 'replay', []) or [])
        self.frames = list(src)
        self.pos = 0.0
        self.speed = 1.0
        self.paused = False

    def update(self, dt: float) -> None:
        super().update(dt)
        if self.frames and not self.paused:
            self.pos += dt / 0.05 * self.speed
            if self.pos >= len(self.frames):
                self.pos = 0.0

    def on_action(self, act: str) -> None:
        if act == 'confirm':
            self.paused = not self.paused
        elif act == 'left':
            self.pos = max(0.0, self.pos - 20)
        elif act == 'right':
            self.pos = min(len(self.frames) - 1.0, self.pos + 20) if self.frames else 0.0
        elif act == 'up':
            self.speed = min(2.0, self.speed * 2)
        elif act == 'down':
            self.speed = max(0.25, self.speed / 2)
        elif act == 'back':
            self.game.ui.pop()

    def draw(self, surf: pygame.Surface) -> None:
        W, H = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        surf.fill((8, 9, 16))
        for x in range(0, W, 64):
            pygame.draw.line(surf, (18, 20, 32), (x, 0), (x, H))
        for y in range(0, H, 64):
            pygame.draw.line(surf, (18, 20, 32), (0, y), (W, y))
        if not self.frames:
            text(surf, 'Повтор пуст: запись идёт во время забега', 22, CFG.COLOR_TEXT, (W / 2, H / 2), 'center')
            text(surf, 'Esc — назад', 14, (150, 160, 185), (W / 2, H / 2 + 40), 'center')
            return
        fr = self.frames[int(self.pos) % len(self.frames)]
        (px, py, pm), enemies, ebul, pbul = fr
        for (x, y, r, c) in enemies:
            col = mode_color(c) if c in ALL_MODES else (200, 90, 90)
            pygame.draw.circle(surf, col, (int(x), int(y)), max(3, int(r)), 2)
        for (x, y, c) in ebul:
            col = mode_color(c) if c in ALL_MODES else (255, 120, 120)
            pygame.draw.circle(surf, col, (int(x), int(y)), 4)
        for (x, y, m) in pbul:
            pygame.draw.circle(surf, mode_color(m) if m in ALL_MODES else (240, 240, 240), (int(x), int(y)), 3)
        pygame.draw.circle(surf, mode_color(pm) if pm in ALL_MODES else (255, 255, 255), (int(px), int(py)), 14)
        pygame.draw.circle(surf, (255, 255, 255), (int(px), int(py)), 14, 2)
        t = self.pos * 0.05
        total = len(self.frames) * 0.05
        panel(surf, (20, H - 70, W - 40, 50), 200)
        pygame.draw.rect(surf, (60, 66, 90), (40, H - 40, W - 80, 6))
        pygame.draw.rect(surf, CFG.COLOR_ACCENT, (40, H - 40, int((W - 80) * self.pos / max(1, len(self.frames))), 6))
        text(surf, f"ПОВТОР  {t:4.1f} / {total:.1f} c  ×{self.speed:g}" + ('  ||' if self.paused else ''), 16,
             CFG.COLOR_TEXT, (40, H - 64))
        text(surf, 'Enter — пауза · ←→ — перемотка · ↑↓ — скорость · Esc — назад', 14, (150, 160, 185),
             (W - 40, H - 64), 'right')


def draw_damage_chart(surf: pygame.Surface, rect: Tuple[int, int, int, int], run: Dict[str, Any]) -> None:
    """Столбцы урона по цветам + линия полученного урона по времени."""
    x, y, w, h = rect
    panel(surf, rect, 170)
    text(surf, 'Урон по цветам', 16, CFG.COLOR_ACCENT, (x + 12, y + 8), bold=True)
    dbm = run.get('damage_by_mode') or {}
    total = max(1.0, sum(float(v) for v in dbm.values()))
    bx = x + 12
    bw = (w // 2 - 30) // max(1, len(ALL_MODES))
    top, base = y + 34, y + h - 26
    mx = max([float(v) for v in dbm.values()] + [1.0])
    for m in ALL_MODES:
        v = float(dbm.get(m, 0))
        bh = int((base - top) * v / mx)
        pygame.draw.rect(surf, mode_color(m), (bx, base - bh, bw - 8, bh))
        text(surf, f"{100 * v / total:.0f}%", 12, CFG.COLOR_TEXT, (bx + (bw - 8) / 2, base + 4), 'center')
        bx += bw
    # линия полученного урона
    lx, lw = x + w // 2, w // 2 - 14
    text(surf, 'Полученный урон', 16, CFG.COLOR_ACCENT, (lx, y + 8), bold=True)
    tl = list(run.get('damage_timeline') or [])
    pygame.draw.line(surf, (80, 90, 120), (lx, base), (lx + lw, base))
    if len(tl) >= 2:
        t_max = max(1, tl[-1][0])
        d_max = max(1, max(d for _, d in tl))
        pts = [(lx + int(lw * t / t_max), base - int((base - top) * d / d_max)) for t, d in tl]
        pygame.draw.lines(surf, CFG.COLOR_DANGER, False, pts, 2)
        text(surf, f"{int(d_max)} HP за {t_max // 60}:{t_max % 60:02d}", 12, (190, 190, 210), (lx + lw, base + 4), 'right')
    else:
        text(surf, 'мало данных', 12, (150, 150, 170), (lx, base - 20))

"""Тесты ChromaShift 0.7.0: дерево из 6 веток, сборки/код/престиж, магазин, победа, новые режимы,
испытания, редактор волн, повтор, чёткий рендер, звуки, проверка обновлений, отчёт о вылете."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_v065 import GAME_DIR, _TMP, bot_step, make_game  # noqa: E402,F401

import pygame  # noqa: E402

from cshift import progression as pr  # noqa: E402
from cshift import ui, ui_ext  # noqa: E402
from cshift.config import ALL_MODES, CFG  # noqa: E402
from cshift.mechanics import SHOP_ITEMS, TEMP_NODES, TRIALS  # noqa: E402
from cshift.waves import BOSS_CYCLE, SPECIAL_WAVES, SQUADS, VICTORY_WAVE  # noqa: E402

ACTIONS = ['down', 'down', 'right', 'left', 'up', 'tab', 'pagedown', 'pageup', 'char:x', 'delete']


def exercise(g, screen):
    g.ui.push(screen)
    for a in ACTIONS:
        screen.on_action(a)
        screen.update(0.1)
        g.draw()
    screen.on_mouse((300, 200), False)
    g.draw()


class TestTreeScreen(unittest.TestCase):
    def test_six_branches_and_draw(self):
        g = make_game()
        g.profile.data['cp'] = 3000
        s = ui.UpgradeTreeScreen(g)
        self.assertIs(ui.UpgradeTreeScreen, ui_ext.UpgradeTreeScreen)
        self.assertEqual(len(s.branches), 6)
        exercise(g, s)

    def test_filter_and_search(self):
        g = make_game()
        g.profile.data['cp'] = 10 ** 6
        s = ui.UpgradeTreeScreen(g)
        g.ui.push(s)
        s.query = 'zzzнетузла'
        self.assertTrue(all(not s.column(b) for b in s.branches))
        self.assertIsNone(s.current())
        g.draw()  # пустой результат не роняет отрисовку
        s.query = ''
        s.filter = [f for f, _ in ui_ext.TREE_FILTERS].index('owned')
        self.assertTrue(all(not s.column(b) for b in s.branches))
        s.filter = 0
        s.on_action('confirm')
        s.filter = [f for f, _ in ui_ext.TREE_FILTERS].index('owned')
        self.assertEqual(sum(len(s.column(b)) for b in s.branches), 1)

    def test_seen_marks_and_path(self):
        g = make_game()
        s = ui.UpgradeTreeScreen(g)
        g.ui.push(s)
        s.update(0.1)
        self.assertIn(s.current(), g.profile.data['seen_nodes'])
        deep = max((n for n in pr.UPGRADES if pr.UPGRADES[n]['requires']),
                   key=lambda n: len(ui_ext.node_ancestors(n)))
        path, cost = ui_ext.node_path(g.profile, deep)
        self.assertGreaterEqual(len(path), 2)
        self.assertEqual(path[-1], deep)
        self.assertGreater(cost, 0)

    def test_branch_reset_menu(self):
        g = make_game()
        g.profile.data['cp'] = 500
        s = ui.UpgradeTreeScreen(g)
        g.ui.push(s)
        s.on_action('confirm')
        spent = 500 - g.profile.cp
        s.on_action('reset')
        self.assertIsInstance(g.ui.top(), ui_ext.TreeResetScreen)
        g.ui.top().on_action('confirm')  # ветка текущей колонки
        g.ui.top().on_action('up')
        g.ui.top().on_action('confirm')
        self.assertEqual(g.profile.data['upgrades'], {})
        self.assertEqual(g.profile.cp, 500)
        self.assertGreater(spent, 0)

    def test_try_node_starts_training(self):
        g = make_game()
        s = ui.UpgradeTreeScreen(g)
        g.ui.push(s)
        nid = s.current()
        s.on_action('char:p')
        self.assertTrue(g.in_run)
        self.assertEqual(g.run_type, 'training')
        self.assertEqual(g.trial_node, nid)


class TestBuilds(unittest.TestCase):
    def test_code_roundtrip_and_apply(self):
        g = make_game()
        p = g.profile
        p.data['cp'] = 5000
        p.buy_upgrade('core_hp')
        code = p.build_code()
        self.assertTrue(code.startswith('CS7-'))
        self.assertEqual(pr.Profile.parse_build_code(code), {'core_hp': 1})
        self.assertIsNone(pr.Profile.parse_build_code('мусор'))
        bs = ui_ext.BuildsScreen(g)
        exercise(g, bs)
        msg = bs.show_code()
        self.assertIn('CS7-', msg)
        self.assertTrue(os.path.exists(os.path.join(_TMP, 'build_code.txt')))

    def test_slot_save_and_apply(self):
        g = make_game()
        p = g.profile
        p.data['cp'] = 5000
        p.buy_upgrade('core_hp')
        bs = ui_ext.BuildsScreen(g)
        g.ui.push(bs)
        bs.on_action('confirm')  # пустой слот → сохранить
        self.assertEqual(p.data['builds'][0]['upgrades'], {'core_hp': 1})
        p.reset_upgrades()
        ok, _ = p.apply_build(p.data['builds'][0]['upgrades'])
        self.assertTrue(ok)
        self.assertEqual(p.data['upgrades'].get('core_hp'), 1)

    def test_prestige(self):
        g = make_game()
        p = g.profile
        self.assertFalse(p.can_prestige())
        p.data['cp'] = 10 ** 6
        for _ in range(400):
            cands = [n for n in pr.UPGRADES if pr.node_status(p, n)[0] == 'available']
            if not cands or p.can_prestige():
                break
            p.buy_upgrade(cands[0])
        self.assertTrue(p.can_prestige())
        ok, _ = p.prestige()
        self.assertTrue(ok)
        self.assertEqual(p.data['prestige'], 1)
        self.assertEqual(p.data['upgrades'], {})
        mods = p.build_mods('standard', g.settings)
        self.assertTrue(any('Престиж' in s for s in mods.sources))


class TestInRunScreens(unittest.TestCase):
    def test_shop_buy_and_continue(self):
        g = make_game()
        g.start_run('standard')
        g.color_mech.shards = 200
        offer = g.color_mech.shop_offer(random.Random(1))
        self.assertTrue(set(SHOP_ITEMS) <= set(offer))
        self.assertTrue(any(o in TEMP_NODES for o in offer))
        shop = ui_ext.ShopScreen(g, offer)
        g.ui.push(shop)
        g.draw()
        self.assertEqual(shop.index, 0)  # первым идёт «Продолжить бой»
        dmg = g.mods.damage_mult
        shop.index = 1 + offer.index('dmg')
        shop.on_action('confirm')
        self.assertGreater(g.mods.damage_mult, dmg)
        self.assertEqual(g.color_mech.shards, 200 - SHOP_ITEMS['dmg']['cost'])
        shop.index = 0
        shop.on_action('confirm')
        self.assertIsNone(g.ui.top())

    def test_shop_opens_after_wave(self):
        g = make_game()
        g.start_run('standard')
        g.director.wave = CFG.SHOP_WAVE_INTERVAL
        g.on_wave_cleared({'wave': CFG.SHOP_WAVE_INTERVAL, 'score_bonus': 0, 'cp': 1, 'no_damage': False})
        self.assertIsInstance(g.ui.top(), ui_ext.ShopScreen)

    def test_victory_screen(self):
        g = make_game()
        g.start_run('standard')
        g.on_victory()
        self.assertTrue(g.victory)
        v = g.ui.top()
        self.assertIsInstance(v, ui_ext.VictoryScreen)
        g.draw()
        v.on_action('back')  # нельзя случайно закрыть
        self.assertIs(g.ui.top(), v)
        v.index = 1
        v.on_action('confirm')
        self.assertFalse(g.in_run)
        res = g.ui.top()
        self.assertIsInstance(res, ui.ResultsScreen)
        self.assertTrue(res.run['victory'])
        self.assertIn(('Победа', 60), res.run['cp_lines'])
        g.draw()

    def test_victory_continue(self):
        g = make_game()
        g.start_run('standard')
        g.on_victory()
        g.ui.top().on_action('confirm')
        self.assertTrue(g.in_run)
        self.assertIsNone(g.ui.top())

    def test_artifact_reroll(self):
        g = make_game()
        g.start_run('standard')
        scr = ui.ArtifactScreen(g, ['bulwark', 'aegis', 'mirror'])
        g.ui.push(scr)
        self.assertFalse(scr.reroll())
        g.color_mech.rerolls = 1
        scr.on_action('reset')
        self.assertEqual(g.color_mech.rerolls, 0)
        g.draw()

    def test_replay_screen(self):
        g = make_game()
        g.start_run('standard')
        for _ in range(60):
            g.step(1 / 60, [])
        self.assertGreater(len(g.color_mech.replay), 5)
        r = ui_ext.ReplayScreen(g)
        exercise(g, r)
        empty = ui_ext.ReplayScreen(g, [])
        exercise(g, empty)

    def test_results_chart_and_replay_item(self):
        g = make_game()
        g.start_run('standard')
        for _ in range(30):
            g.step(1 / 60, [])
        g.stats['damage_by_mode']['RED'] = 500
        g.stats['damage_timeline'] = [(0, 0), (10, 20), (20, 55)]
        g.end_run('quit')
        res = g.ui.top()
        self.assertTrue(any('Повтор' in it.get_label() for it in res.items))
        g.draw()


class TestModesAndEditor(unittest.TestCase):
    def test_new_run_types_start(self):
        for rt in ('endless', 'blitz', 'bossrush'):
            g = make_game()
            g.start_run(rt)
            self.assertEqual(g.run_type, rt)
            for _ in range(30):
                g.step(1 / 60, [])
            g.draw()

    def test_blitz_ends_by_timer(self):
        g = make_game()
        g.start_run('blitz')
        self.assertAlmostEqual(g.blitz_left, 600.0)
        g.blitz_left = 0.05
        for _ in range(30):
            g.step(1 / 60, [])
        self.assertFalse(g.in_run)
        self.assertIsInstance(g.ui.top(), ui.ResultsScreen)

    def test_bossrush_bot_victory(self):
        g = make_game()
        g.start_run('bossrush')
        bot_step(g, 60 * 60 * 6, god=True)
        self.assertTrue(g.victory)
        self.assertGreaterEqual(g.stats['bosses'], 3)

    def test_play_menu_has_new_modes_and_portals(self):
        g = make_game()
        pm = ui.PlayMenu(g)
        for rt in ('endless', 'blitz', 'bossrush'):
            self.assertIn(rt, pm.run_types)
        self.assertIn('portals', pm.arenas)
        pm.rt = pm.run_types.index('endless')
        self.assertTrue(pm.mode_desc())

    def test_trials_screen_starts_trial(self):
        g = make_game()
        ts = ui_ext.TrialsScreen(g)
        self.assertEqual(len(ts.items), len(TRIALS))
        g.ui.push(ts)
        ts.on_action('confirm')
        self.assertTrue(g.in_run)
        self.assertEqual(g.run_type, 'training')
        self.assertIsNotNone(g.color_mech.trial)

    def test_wave_editor_flow(self):
        g = make_game()
        ed = ui_ext.WaveEditorScreen(g)
        g.ui.push(ed)
        self.assertEqual(ed.start(), 'Добавьте хотя бы одну непустую волну')
        ed.add()
        ed.add()
        self.assertEqual(len(g.profile.data['custom_waves']), 2)
        we = ui_ext.WaveEditScreen(g, 0, ed)
        exercise(g, we)
        we.set_count('swarm', 12)
        we.cycle('boss', ui_ext.BOSS_CHOICES, 1)
        self.assertEqual(we.count('swarm'), 12)
        self.assertEqual(g.profile.data['custom_waves'][0]['boss'], 'boss')
        g.ui.clear()
        g.ui.push(ed)
        ed.start()
        self.assertTrue(g.in_run)
        self.assertEqual(g.run_type, 'custom')
        self.assertEqual(len(g.custom_waves), 2)

    def test_validate_custom_waves(self):
        bad = [{'members': [['chaser', 999], ['nope', 3], ['x']], 'special': 'warp', 'boss': 'god'}, 'мусор']
        out = ui_ext.validate_custom_waves(bad)
        self.assertEqual(out, [{'members': [['chaser', 40]], 'special': None, 'boss': None}])

    def test_boss_cycle_and_specials(self):
        g = make_game()
        g.start_run('standard')
        d = g.director
        self.assertEqual([d.boss_kind_for(n)[0] for n in (10, 20, 30, 40)], ['boss', 'hydra', 'spectrum', 'boss'])
        self.assertEqual(set(BOSS_CYCLE), {'boss', 'hydra', 'spectrum'})
        self.assertGreaterEqual(len(SPECIAL_WAVES), 9)
        self.assertGreaterEqual(len(SQUADS), 25)
        self.assertEqual(VICTORY_WAVE, 30)


class TestRenderAndExtras(unittest.TestCase):
    def test_render_scale_quality(self):
        g = make_game()
        g.headless = False
        g.settings.set('render_quality', 'native')
        self.assertAlmostEqual(g.render_scale_for(2560, 1440), 2.0)
        self.assertAlmostEqual(g.render_scale_for(1920, 1080), 1.5)
        g.settings.set('render_quality', 'balanced')
        self.assertAlmostEqual(g.render_scale_for(2560, 1440), 1.5)
        g.settings.set('render_quality', 'classic')
        self.assertAlmostEqual(g.render_scale_for(2560, 1440), 1.0)
        g.headless = True

    def test_text_cache_keeps_alpha(self):
        # Регресс: повторный текст из кэша рисовался сплошным прямоугольником
        from cshift import hires
        old = hires.get_scale()
        for sc in (1.0, 2.0):
            hires.set_scale(sc)
            surf = hires.HiSurface((200, 40))
            surf.fill((0, 0, 0))
            for i in range(3):
                r = ui.text(surf, '0/2', 14, (250, 250, 250), (10 + 60 * i, 5))
            corner = pygame.Surface.get_at(surf, (int(r.x * sc), int(r.y * sc)))
            self.assertLess(corner.r + corner.g + corner.b, 200, sc)
        hires.set_scale(old)

    def test_post_fx_and_minimap_draw(self):
        g = make_game()
        g.settings.set('minimap', True)
        g.settings.set('post_fx', True)
        g.start_run('standard')
        for _ in range(60):
            g.step(1 / 60, [])
        g.player.hp = 1
        g.draw()

    def test_new_sounds_have_recipes(self):
        from cshift.sound_design import RECIPES
        for n in ('mode_violet', 'shoot_violet', 'absorb', 'overload', 'parry_touch', 'skill', 'ability', 'portal'):
            self.assertIn(n, RECIPES)
            data = RECIPES[n]()
            self.assertGreater(len(data), 100)
        g = make_game()
        g.sound_manager.play('нет_такого_звука')  # неизвестный звук не роняет игру

    def test_update_version_compare(self):
        from cshift import updates
        self.assertTrue(updates.is_newer('v0.7.1', '0.7.0'))
        self.assertTrue(updates.is_newer('v1.0', '0.7.0'))
        self.assertFalse(updates.is_newer('v0.7.0', '0.7.0'))
        self.assertFalse(updates.is_newer('v0.6.5', '0.7.0'))
        self.assertEqual(updates.parse_version('v0.7.0-beta'), (0, 7, 0))

    def test_crash_report(self):
        sys.path.insert(0, GAME_DIR)
        import main as game_main
        try:
            raise RuntimeError('тестовый вылет')
        except RuntimeError:
            path = game_main.write_crash_report(_TMP)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding='utf-8') as f:
            body = f.read()
        self.assertIn('тестовый вылет', body)
        self.assertIn('ChromaShift', body)

    def test_codex_has_new_enemies(self):
        g = make_game()
        g.profile.data['codex_seen'] = ['swarm']
        cs = ui.CodexScreen(g)
        labels = [it.get_label() for it in cs.items]
        self.assertIn('Рой', labels)
        self.assertGreater(len(cs.items), 20)

    def test_settings_screens_new_items(self):
        g = make_game()
        av = ui.AudioVideoScreen(g)
        labels = [it.get_label() for it in av.items]
        for want in ('Качество рендера', 'Ограничение FPS', 'Миникарта', 'Проверять обновления'):
            self.assertIn(want, labels)
        exercise(g, av)
        mm = ui.MainMenu(g)
        labels = [it.get_label() for it in mm.items]
        for want in ('Сборки и престиж', 'Испытания цвета', 'Свои волны'):
            self.assertIn(want, labels)

    def test_all_modes_include_violet(self):
        self.assertIn('VIOLET', ALL_MODES)


if __name__ == '__main__':
    unittest.main()

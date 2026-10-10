"""Headless-тесты ChromaShift 0.6.5 (пакет cshift).

Запуск из папки chromashift:  python -m unittest discover -s tests -v
Сохранения пишутся во временную папку, окно не открывается (SDL dummy).
"""
import datetime
import json
import os
import random
import shutil
import sys
import tempfile
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GAME_DIR)

import pygame  # noqa: E402

from cshift import progression as pr  # noqa: E402
from cshift.config import CFG, GAME_VERSION, MODES  # noqa: E402

_TMP = tempfile.mkdtemp(prefix='cs065_')
pr.saves_dir = lambda: _TMP  # все сохранения тестов — во временной папке

from cshift import ui  # noqa: E402
from cshift.entities import BossEnemy, EnemyBullet, ShooterEnemy  # noqa: E402
from cshift.game import Game  # noqa: E402
from cshift.settings import InputManager, Settings  # noqa: E402
from cshift.waves import WaveDirector, wave_budget  # noqa: E402


def clean_saves():
    for f in os.listdir(_TMP):
        p = os.path.join(_TMP, f)
        if os.path.isfile(p):
            os.remove(p)


def make_game():
    clean_saves()
    g = Game(headless=True)
    g.profile = pr.Profile(0, pr.default_profile('Тест'))
    g.profile.refresh_contracts()
    return g


def bot_step(g, frames, god=False, switch=True):
    g.god_mode = god
    g.input.virtual_move = (0.0, 0.0)
    g.input.virtual_fire = True
    for i in range(frames):
        alive = [e for e in g.enemies if e.alive]
        if alive:
            e = min(alive, key=lambda e: (e.x - g.player.x) ** 2 + (e.y - g.player.y) ** 2)
            g.input.virtual_aim = (e.x, e.y)
        else:
            g.input.virtual_aim = (g.player.x, g.player.y - 100)
        if switch and i % 40 == 0:
            g.handle_game_action(['mode_red', 'mode_blue', 'mode_green'][(i // 40) % 3])
        if g.in_run and g.ui.top() is not None:
            g.ui.top().on_action('confirm')
        g.step(1 / 60, [])
        if not g.in_run:
            break


class TestConfigAndMods(unittest.TestCase):
    def test_version(self):
        self.assertEqual(GAME_VERSION, '0.7.0')
        with open(os.path.join(GAME_DIR, '..', 'VERSION'), encoding='utf-8') as f:
            self.assertEqual(f.read().strip(), GAME_VERSION)

    def test_build_mods_tree_hull_modules_synergy(self):
        p = pr.Profile(0, pr.default_profile())
        p.data['upgrades'] = {'core_hp': 2, 'red_power': 3}
        p.data['hulls'] = ['prism', 'bastion']
        p.data['modules'] = ['lens', 'ricochet']
        p.loadout['hull'] = 'bastion'
        p.loadout['modules'] = ['lens', 'ricochet']
        m = p.build_mods('standard', Settings(os.path.join(_TMP, 's.json')))
        self.assertEqual(m.max_hp_add, 30)
        self.assertAlmostEqual(m.max_hp_mult, 1.3)
        self.assertAlmostEqual(m.mode_damage_mult['RED'], 1.3)
        self.assertEqual(m.shield_charges, 1)
        self.assertTrue(m.refraction_pierce)  # синергия «Призматическая сеть»
        self.assertAlmostEqual(m.refraction_window, CFG.PERFECT_REFRACTION_WINDOW + 0.03)
        pure = p.build_mods('pure', Settings(os.path.join(_TMP, 's.json')))
        self.assertEqual(pure.max_hp_add, 0)
        self.assertFalse(pure.refraction_pierce)

    def test_tension_and_risks_raise_cp(self):
        p = pr.Profile(0, pr.default_profile())
        s = Settings(os.path.join(_TMP, 's.json'))
        base = p.build_mods('standard', s)
        hard = p.build_mods('standard', s, 5, ['fragile', 'horde'])
        self.assertGreater(hard.cp_mult, base.cp_mult)
        self.assertGreater(hard.enemy_hp_mult, base.enemy_hp_mult)
        self.assertLess(hard.max_hp_mult, base.max_hp_mult)
        self.assertGreater(hard.budget_mult, base.budget_mult)

    def test_difficulty_presets_and_physics_clamp(self):
        s = Settings(os.path.join(_TMP, 's.json'))
        s.set('difficulty', 'story')
        s.data['physics'] = {'RED': 5.0, 'BLUE': 0.1, 'GREEN': 1.0}
        m = pr.RunMods()
        pr.apply_difficulty(m, s)
        self.assertLess(m.enemy_damage_mult, 1.0)
        self.assertGreater(m.refraction_window_mult, 1.0)
        self.assertAlmostEqual(m.max_speed_mult['RED'], 1.2)
        self.assertAlmostEqual(m.max_speed_mult['BLUE'], 0.8)


class TestUpgradeTree(unittest.TestCase):
    def setUp(self):
        self.p = pr.Profile(0, pr.default_profile())
        self.p.data['cp'] = 10000

    def test_buy_and_levels(self):
        ok, _ = self.p.buy_upgrade('core_hp')
        self.assertTrue(ok)
        self.assertEqual(self.p.data['upgrades']['core_hp'], 1)
        self.assertEqual(self.p.cp, 10000 - 20)

    def test_tier_lock_and_requirements(self):
        status, _ = pr.node_status(self.p, 'core_shield')
        self.assertEqual(status, 'locked')
        status, _ = pr.node_status(self.p, 'core_luck')
        self.assertEqual(status, 'locked')
        self.p.buy_upgrade('core_magnet')
        self.assertEqual(pr.node_status(self.p, 'core_luck')[0], 'available')

    def test_exclusive_group(self):
        for _ in range(4):
            self.p.buy_upgrade('red_power')
        self.p.buy_upgrade('red_thrust')
        self.assertTrue(self.p.buy_upgrade('red_trail')[0])
        self.assertEqual(pr.node_status(self.p, 'red_rail')[0], 'blocked')

    def test_reset_refunds_everything(self):
        self.p.buy_upgrade('core_hp')
        self.p.buy_upgrade('core_hp')
        self.p.buy_upgrade('blue_power')
        paid = 10000 - self.p.cp  # 0.7.0: цены нелинейные — возвращаем ровно уплаченное
        refund = self.p.reset_upgrades()
        self.assertEqual(refund, paid)
        self.assertEqual(self.p.cp, 10000)
        self.assertEqual(self.p.data['upgrades'], {})

    def test_preview_and_recommendation(self):
        lines = pr.preview_node(self.p, 'core_hp')
        self.assertTrue(any('HP' in ln for ln in lines))
        self.assertIsNotNone(self.p.recommended_upgrade())

    def test_every_node_effect_applies(self):
        for nid, node in pr.UPGRADES.items():
            m = pr.RunMods()
            node['effect'](m, node['max'])
            if node.get('grow'):  # растущий узел действует через статистику профиля
                continue
            self.assertNotEqual(m.to_dict(), pr.RunMods().to_dict(), nid)


class TestHangar(unittest.TestCase):
    def test_slots_energy_conflicts(self):
        p = pr.Profile(0, pr.default_profile())
        p.data['modules'] = list(pr.MODULES)
        self.assertTrue(p.toggle_module('overclock')[0])
        ok, reason = p.toggle_module('stabilizer')
        self.assertFalse(ok)
        self.assertIn('Несовместим', reason)
        self.assertTrue(p.toggle_module('twin')[0])  # 2+3 = 5 энергии
        ok, reason = p.toggle_module('shield_gen')  # +3 > 6
        self.assertFalse(ok)

    def test_hull_change_drops_invalid_modules(self):
        p = pr.Profile(0, pr.default_profile())
        p.data['modules'] = list(pr.MODULES)
        p.data['hulls'] = list(pr.HULLS)
        p.set_hull('bastion')
        for mid in ('twin', 'shield_gen'):
            self.assertTrue(p.toggle_module(mid)[0])
        p.set_hull('needle')  # энергия 5 < 6
        self.assertLessEqual(pr.loadout_energy(p.loadout), pr.HULLS['needle']['energy'])

    def test_buy_hull_requires_prisms(self):
        p = pr.Profile(0, pr.default_profile())
        p.data['cp'] = 1000
        self.assertFalse(p.buy_hull('needle')[0])
        p.data['prisms'] = 1
        self.assertTrue(p.buy_hull('needle')[0])


class TestSaves(unittest.TestCase):
    def setUp(self):
        clean_saves()

    def test_legacy_migration(self):
        legacy = {'chromatic_points': -5, 'upgrade_tree': {
            'max_hp': {'current_lvl': 3}, 'dash_cd': {'current_lvl': 3}, 'refract_win': {'current_lvl': 2}}}
        data = pr.migrate_profile(legacy)
        self.assertEqual(data['cp'], 0)
        self.assertEqual(data['upgrades'], {'core_hp': 3, 'core_dash': 3, 'core_lens': 2})
        self.assertEqual(data['version'], pr.SAVE_VERSION)

    def test_real_legacy_file_migrates(self):
        with open(os.path.join(GAME_DIR, 'chromashift_save.json'), encoding='utf-8') as f:
            data = pr.migrate_profile(json.load(f))
        self.assertGreaterEqual(data['cp'], 0)
        self.assertTrue(data['legacy_migrated'])

    def test_validation_clamps_garbage(self):
        d = pr.default_profile()
        d['upgrades'] = {'core_hp': 99, 'unknown': 3}
        d['cp'] = -50
        d['loadouts'][0]['modules'] = ['twin', 'nonexistent']
        d['history'] = [{'score': i, 'wave': 1} for i in range(50)]
        out = pr.migrate_profile(d)
        self.assertEqual(out['upgrades'], {'core_hp': 5})
        self.assertEqual(out['cp'], 0)
        self.assertEqual(out['loadouts'][0]['modules'], [])  # модуль не открыт
        self.assertEqual(len(out['history']), 20)

    def test_save_rotation_and_corrupt_recovery(self):
        p = pr.Profile(1, pr.default_profile('A'))
        for i in range(5):
            p.data['cp'] = i
            p.save()
        self.assertTrue(os.path.exists(p.path + '.bak1'))
        self.assertTrue(os.path.exists(p.path + '.bak3'))
        with open(p.path, 'w') as f:
            f.write('{broken')
        q = pr.Profile.load(1)
        self.assertEqual(q.data['cp'], 3)  # из .bak1
        self.assertIn('резервной', q.load_warning)
        self.assertTrue(os.path.exists(p.path + '.corrupt'))

    def test_export_import(self):
        p = pr.Profile(2, pr.default_profile('Экспорт'))
        p.data['cp'] = 77
        path = p.export()
        shutil.copy(path, os.path.join(_TMP, 'import.json'))
        q = pr.Profile(0, pr.default_profile('Другой'))
        ok, _ = q.import_file()
        self.assertTrue(ok)
        self.assertEqual(q.data['cp'], 77)
        self.assertEqual(q.name, 'Экспорт')

    def test_settings_validation_and_bind_swap(self):
        path = os.path.join(_TMP, 'settings_test.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'fire_mode': 'laser', 'volume': 7, 'keys': {'dash': 'nonsense-key'}, 'shake': 0.5}, f)
        s = Settings(path)
        self.assertEqual(s.get('fire_mode'), 'hold')
        self.assertEqual(s.get('volume'), 1.0)
        self.assertEqual(s.get('keys')['dash'], 'space')
        self.assertEqual(s.get('shake'), 0.5)
        s.bind('dash', pygame.key.key_code('1'))
        self.assertEqual(s.get('keys')['dash'], '1')
        self.assertEqual(s.get('keys')['mode_red'], 'space')  # поменялись местами


class TestRunRecording(unittest.TestCase):
    def run_dict(self, **kw):
        r = {'run_type': 'standard', 'wave': 10, 'score': 5000, 'kills': 120, 'refractions': 15, 'time': 300.0,
             'beat_kills': 30, 'cp_lines': [('Волна 1', 3)], 'cp_mult': 1.0, 'wave_times': [10.0, 20.0],
             'kills_RED': 60, 'time_RED': 200.0, 'tension': 0, 'no_damage_waves': 4}
        r.update(kw)
        return r

    def test_record_run_economy_and_unlocks(self):
        p = pr.Profile(0, pr.default_profile())
        p.refresh_contracts()
        res = p.record_run(self.run_dict())
        names = [n for n, _ in res['cp_lines']]
        self.assertIn('Первый забег дня', names)
        self.assertEqual(p.data['tension_unlocked'], 1)
        self.assertIn('first_run', p.data['achievements'])
        self.assertIn('refract_run_15', p.data['achievements'])
        self.assertGreater(p.cp, 0)
        self.assertEqual(p.data['ghost']['wave_times'], [10.0, 20.0])
        res2 = p.record_run(self.run_dict(score=9000))
        names2 = [n for n, _ in res2['cp_lines']]
        self.assertNotIn('Первый забег дня', names2)
        self.assertIn('Новый личный рекорд', names2)

    def test_history_and_leaderboard_caps(self):
        p = pr.Profile(0, pr.default_profile())
        for i in range(25):
            p.record_run(self.run_dict(score=i * 10, wave=1))
        self.assertEqual(len(p.data['history']), 20)
        self.assertEqual(len(p.data['leaderboard']), 10)
        self.assertEqual(p.data['leaderboard'][0]['score'], 240)
        self.assertGreaterEqual(p.data['death_streak'], 3)

    def test_training_gives_nothing(self):
        p = pr.Profile(0, pr.default_profile())
        p.record_run(self.run_dict(run_type='training'))
        self.assertEqual(p.cp, 0)
        self.assertEqual(p.data['stats']['runs'], 0)

    def test_contracts_progress(self):
        p = pr.Profile(0, pr.default_profile())
        p.refresh_contracts(datetime.date(2026, 1, 5))
        self.assertEqual(len(p.data['contracts']['list']), 3)
        big = {c['stat']: 10_000 for c in p.data['contracts']['list']}
        done = p.advance_contracts(big)
        self.assertEqual(len(done), 3)
        self.assertEqual(p.data['stats']['contracts_done'], 3)

    def test_challenge_seed_deterministic(self):
        d = datetime.date(2026, 3, 1)
        self.assertEqual(pr.challenge_setup('daily', d), pr.challenge_setup('daily', d))
        self.assertNotEqual(pr.challenge_seed('daily', d), pr.challenge_seed('daily', d + datetime.timedelta(days=1)))
        self.assertEqual(pr.challenge_seed('weekly', d), pr.challenge_seed('weekly', d + datetime.timedelta(days=0)))

    def test_artifact_roll_weighting_and_unique(self):
        rng = random.Random(1)
        counts = {'parry': 0, 'other': 0}
        for _ in range(300):
            for a in pr.roll_artifacts(rng, 'parry', []):
                counts['parry' if pr.ARTIFACTS[a]['arch'] == 'parry' else 'other'] += 1
        n_parry = sum(1 for a in pr.ARTIFACTS.values() if a['arch'] == 'parry')
        share_expected_uniform = n_parry / len(pr.ARTIFACTS)
        self.assertGreater(counts['parry'] / sum(counts.values()), share_expected_uniform)
        picks = pr.roll_artifacts(random.Random(2), 'any', ['seeker', 'phoenix', 'twins'], 40)
        self.assertNotIn('seeker', picks)
        self.assertEqual(len(picks), len(set(picks)))

    def test_archetypes(self):
        self.assertEqual(pr.detect_archetype({'time': 60, 'refractions': 10}), 'parry')
        self.assertEqual(pr.detect_archetype({'time': 60, 'time_BLUE': 50, 'time_RED': 5, 'time_GREEN': 5}), 'control')
        self.assertEqual(pr.detect_archetype({'time': 60, 'time_BLUE': 20, 'time_RED': 20, 'time_GREEN': 20}), 'balanced')


class TestWaves(unittest.TestCase):
    def setUp(self):
        self.g = make_game()
        self.g.start_run('standard')

    def test_budget_grows_smoothly(self):
        vals = [wave_budget(n) for n in range(1, 40)]
        self.assertTrue(all(b > a for a, b in zip(vals, vals[1:])))
        self.assertLess(vals[1] / vals[0], 2.0)

    def test_compose_respects_budget_and_unlocks(self):
        d = WaveDirector(self.g, random.Random(5))
        squads = d.compose(1, 6.0)
        kinds = {k for s in squads for k, _ in s['members']}
        self.assertEqual(kinds, {'chaser'})
        from cshift.waves import squad_cost
        total = sum(squad_cost(s['members']) for s in d.compose(8, 30.0))
        self.assertLessEqual(total, 31.0)

    def test_spawn_points_keep_safe_distance(self):
        d = self.g.director
        for f in ('arc', 'line', 'ring', 'pincer', 'cluster'):
            for x, y in d.formation_points(f, 5, (640, 360)):
                self.assertGreaterEqual(((x - 640) ** 2 + (y - 360) ** 2) ** 0.5, CFG.WAVE_SAFE_RADIUS - 1)

    def test_telegraph_then_spawn(self):
        d = self.g.director
        d.timer = 0
        self.g.step(1 / 60, [])
        self.assertEqual(d.state, 'active')
        self.assertTrue(d.telegraphs)
        self.assertEqual(len([e for e in self.g.enemies if e.alive]), 0)
        for _ in range(90):
            self.g.step(1 / 60, [])
        self.assertGreater(len(self.g.enemies), 0)

    def test_boss_wave(self):
        d = self.g.director
        d.wave = 9
        d.begin_wave()
        self.assertTrue(d.is_boss_wave)
        self.assertTrue(any(t['kind'] == 'boss' for t in d.telegraphs))
        self.g.god_mode = True
        for _ in range(200):
            self.g.step(1 / 60, [])
        self.assertTrue(any(isinstance(e, BossEnemy) for e in self.g.enemies))

    def test_breather_offers_choice(self):
        d = self.g.director
        d.wave = 4
        d.begin_wave()
        self.assertTrue(d.is_breather)
        groups = [p.group for p in self.g.powerups]
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], groups[1])
        # Взяли один — второй исчез
        pu = self.g.powerups[0]
        self.g.player.x, self.g.player.y = pu.x, pu.y
        self.g.collisions()
        self.assertEqual(len(self.g.powerups), 0)

    def test_elite_chance_capped(self):
        d = self.g.director
        self.assertEqual(d.elite_chance(1), 0.0)
        self.assertLessEqual(d.elite_chance(500), CFG.ELITE_MAX_CHANCE + 1e-9)

    def test_active_enemy_cap(self):
        d = self.g.director
        d.wave = 29
        self.g.god_mode = True
        d.begin_wave()
        for _ in range(600):
            self.g.input.virtual_fire = False
            self.g.input.virtual_move = (0, 0)
            self.g.step(1 / 60, [])
            self.assertLessEqual(len([e for e in self.g.enemies if e.alive and e.counted]), CFG.WAVE_MAX_ACTIVE_ENEMIES)
            self.assertLessEqual(len([e for e in self.g.enemies if e.alive and e.kind == 'shooter']), CFG.WAVE_MAX_SHOOTERS)

    def test_daily_is_reproducible(self):
        g = self.g
        comps = []
        for _ in range(2):
            g.start_run('daily')
            comps.append([(s['id']) for s in g.director.compose(6, 25.0)])
        self.assertEqual(comps[0], comps[1])


class TestMechanics(unittest.TestCase):
    def setUp(self):
        self.g = make_game()
        self.g.start_run('standard')
        self.g.director.state = 'paused-for-test'

    def kill(self, mode):
        from cshift.entities import ChaserEnemy
        e = ChaserEnemy(100, 100)
        self.g.enemies.append(e)
        self.g.on_enemy_killed(e, mode)

    def test_resonance_and_impulse_independent(self):
        for _ in range(5):
            self.kill('RED')
        self.assertEqual(len(self.g.resonances), 1)  # на 3-м убийстве
        self.assertTrue(self.g.player.impulse_active)  # на 5-м (раньше никогда)

    def test_perfect_refraction(self):
        g = self.g
        p = g.player
        g.set_player_mode('BLUE')
        b = EnemyBullet(p.x, p.y, 1, 0)
        g.enemy_bullets.append(b)
        hp = p.hp
        g.collisions()
        self.assertEqual(p.hp, hp)
        self.assertTrue(any(pb.is_refracted for pb in g.player_bullets))
        self.assertEqual(g.stats['refractions'], 1)

    def test_failed_refraction_and_adaptive_window(self):
        g = self.g
        p = g.player
        base = g.chromatic_buffer.window
        for _ in range(4):
            g.chromatic_buffer.last_change_time = -10
            p.invuln_timer = 0
            g.enemy_bullets.append(EnemyBullet(p.x, p.y, 1, 0))
            g.collisions()
        self.assertEqual(g.stats['refraction_fails'], 4)
        self.assertGreater(g.chromatic_buffer.window, base)
        self.assertLess(p.hp, p.max_hp)

    def test_echo_chamber(self):
        g = self.g
        for _ in range(g.mods.echo_threshold):
            g.perfect_refraction(EnemyBullet(10, 10, 1, 0))
        self.assertTrue(g.echo_chamber_active)

    def test_artifact_applies_mid_run(self):
        g = self.g
        hp_before = g.player.max_hp
        g.take_artifact('bulwark')
        self.assertEqual(g.player.max_hp, hp_before + 25)
        sh = g.player.shield_charges
        g.take_artifact('aegis')
        self.assertEqual(g.player.shield_charges, sh + 1)
        g.take_artifact('mirror')
        self.assertAlmostEqual(g.chromatic_buffer.window, g.mods.refraction_window)

    def test_shield_blocks_damage(self):
        p = self.g.player
        p.shield_charges = 1
        hp = p.hp
        p.take_damage(30, self.g, 0, 0, 'тест')
        self.assertEqual(p.hp, hp)
        self.assertEqual(p.shield_charges, 0)

    def test_dash_invulnerability_and_move_direction(self):
        g = self.g
        g.settings.set('dash_direction', 'move')
        p = g.player
        p.move_x, p.move_y = 1.0, 0.0
        self.assertTrue(p.start_dash(g))
        self.assertEqual(p.dash_dir, (1.0, 0.0))
        self.assertFalse(p.can_be_damaged(g))

    def test_bullet_cap_blocks_shooters(self):
        g = self.g
        g.enemy_bullets = [EnemyBullet(5, 5, 0, 1) for _ in range(CFG.WAVE_MAX_ENEMY_BULLETS)]
        s = ShooterEnemy(600, 300)
        s.fire_timer = 0
        g.enemies.append(s)
        n = len(g.enemy_bullets)
        g.update_playing(1 / 60)
        self.assertLessEqual(len(g.enemy_bullets), n)

    def test_radial_menu(self):
        inp = self.g.input
        inp.radial_open = True
        inp.update_radial((100, 100), (100, 20))
        self.assertEqual(inp.radial_choice, 'RED')
        inp.update_radial((100, 100), (180, 150))
        self.assertEqual(inp.radial_choice, 'BLUE')
        inp.update_radial((100, 100), (20, 150))
        self.assertEqual(inp.radial_choice, 'GREEN')

    def test_keyboard_events_switch_modes(self):
        g = self.g
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0, unicode='2', scancode=0))
        self.assertEqual(g.player.mode, 'BLUE')
        g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=5, pos=(0, 0)))
        self.assertEqual(g.player.mode, 'GREEN')
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode='', scancode=0))
        self.assertIsInstance(g.ui.top(), ui.PauseScreen)


class TestFullRuns(unittest.TestCase):
    def test_death_records_profile_and_results(self):
        g = make_game()
        g.start_run('standard')
        g.player.hp = 1
        g.player.take_damage(50, g, 0, 0, 'тест')
        for _ in range(120):
            g.step(1 / 60, [])
        self.assertFalse(g.in_run)
        self.assertIsInstance(g.ui.top(), ui.ResultsScreen)
        self.assertEqual(g.profile.data['stats']['runs'], 1)
        self.assertTrue(os.path.exists(g.profile.path))
        g.draw()

    def test_bot_reaches_and_beats_boss(self):
        g = make_game()
        g.start_run('standard')
        t0 = time.time()
        bot_step(g, 60 * 60 * 12, god=True)
        self.assertGreaterEqual(g.director.wave, 11, g.director.log[-1:] if g.director.log else None)
        self.assertGreaterEqual(g.stats['bosses'], 1)
        self.assertGreaterEqual(len(g.artifacts), 2)  # волны 5 и 10
        g.end_run('quit')
        self.assertGreater(g.profile.cp, 0)
        print(f"\n[bot] волна {g.director.wave}, убийств {g.stats['kills']}, за {time.time() - t0:.1f} c")

    def test_bot_without_god_mode_eventually_dies_or_survives(self):
        g = make_game()
        g.start_run('standard')
        bot_step(g, 60 * 120)
        self.assertGreaterEqual(g.director.wave, 2)

    def test_all_run_types_and_arenas(self):
        g = make_game()
        for rt in ('standard', 'daily', 'weekly', 'pure', 'training'):
            for arena in ('classic', 'pillars', 'prism'):
                g.start_run(rt, arena=arena)
                bot_step(g, 240, god=True)
                g.draw()
                self.assertTrue(g.in_run, (rt, arena))
        g.start_run('training')
        bot_step(g, 600)
        self.assertTrue(g.in_run)
        self.assertEqual(g.player.hp, g.player.max_hp)

    def test_special_waves(self):
        g = make_game()
        g.start_run('standard')
        g.god_mode = True
        for sp in ('darkness', 'haste', 'mono'):
            d = g.director
            g.enemies = []
            d.wave = 7
            CFG.set_override('SPECIAL_WAVE_CHANCE', 1.0)
            d.rng = random.Random(0)
            while True:
                d.begin_wave()
                if d.special == sp:
                    break
                d.wave = 7
                g.director.telegraphs = []
            for _ in range(120):
                g.step(1 / 60, [])
            g.draw()
            if sp == 'mono':
                self.assertTrue(all(e.vulnerable_mode == d.mono_mode for e in g.enemies if e.kind != 'dissonance'))
        CFG.set_override('SPECIAL_WAVE_CHANCE', 0.15)

    def test_stress_performance(self):
        g = make_game()
        g.start_run('standard')
        g.god_mode = True
        g.director.state = 'test'
        for i in range(30):
            g.spawn_enemy(['chaser', 'shooter', 'kamikaze', 'dissonance'][i % 4], 100 + i * 35, 80 + (i % 5) * 120)
        g.enemy_bullets = [EnemyBullet(50 + i * 10, 50, 0, 1) for i in range(60)]
        t0 = time.time()
        g.input.virtual_fire = True
        for i in range(300):
            g.step(1 / 60, [])
            g.draw()
        dt = time.time() - t0
        print(f"\n[stress 0.6.5] 300 кадров с отрисовкой: {dt:.2f} c ({300 / dt:.0f} кадров/с)")
        self.assertLess(dt, 20.0)


class TestScreens(unittest.TestCase):
    ACTIONS = ['down', 'down', 'right', 'left', 'up', 'down', 'right', 'pagedown', 'pageup']

    def exercise(self, g, screen, confirm=False):
        g.ui.push(screen)
        for a in self.ACTIONS:
            screen.on_action(a)
            screen.update(0.1)
            g.draw()
        screen.on_mouse((300, 200), False)
        if confirm:
            screen.on_action('confirm')
        g.draw()

    def test_every_menu_screen(self):
        g = make_game()
        g.profile.data['cp'] = 5000
        g.profile.data['prisms'] = 5
        g.profile.data['history'] = [{'date': '2026-01-01', 'score': i * 100, 'wave': i, 'type': 'standard',
                                      'archetype': 'parry', 'cause': 'тест'} for i in range(5)]
        screens = [ui.MainMenu(g), ui.PlayMenu(g), ui.UpgradeTreeScreen(g), ui.HangarScreen(g), ui.CosmeticsScreen(g),
                   ui.ProfilesScreen(g), ui.StatsScreen(g), ui.RecordsScreen(g), ui.AchievementsScreen(g),
                   ui.CodexScreen(g), ui.SettingsScreen(g), ui.ControlsScreen(g), ui.DifficultyScreen(g),
                   ui.AccessibilityScreen(g), ui.PhysicsScreen(g), ui.AudioVideoScreen(g),
                   ui.TextInputScreen(g, 'Имя', 'А', lambda v: None),
                   ui.ConfirmScreen(g, 'Да?', 'Вопрос', lambda: None)]
        for s in screens:
            self.exercise(g, s)

    def test_upgrade_screen_buys_and_resets(self):
        g = make_game()
        g.profile.data['cp'] = 500
        s = ui.UpgradeTreeScreen(g)
        g.ui.push(s)
        s.on_action('confirm')
        self.assertEqual(g.profile.data['upgrades'].get('core_hp'), 1)
        s.on_action('reset')
        g.ui.top().on_action('up')  # «Да»
        g.ui.top().on_action('confirm')
        self.assertEqual(g.profile.data['upgrades'], {})
        self.assertEqual(g.profile.cp, 500)

    def test_play_menu_starts_run(self):
        g = make_game()
        pm = ui.PlayMenu(g)
        g.ui.push(pm)
        pm.index = len(pm.items) - 1
        pm.on_action('confirm')
        self.assertTrue(g.in_run)
        self.assertIsNone(g.ui.top())

    def test_rebinding_flow(self):
        g = make_game()
        cs = ui.ControlsScreen(g)
        g.ui.push(cs)
        cs.start_bind('dash')
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0, unicode='f', scancode=0))
        self.assertEqual(g.settings.get('keys')['dash'], 'f')

    def test_in_run_overlays(self):
        g = make_game()
        g.start_run('standard')
        g.ui.push(ui.ArtifactScreen(g, ['bulwark', 'aegis', 'mirror']))
        t = g.game_time
        g.step(1 / 60, [])
        self.assertEqual(g.game_time, t)  # модальное окно ставит игру на паузу
        g.draw()
        g.ui.top().on_action('right')
        g.ui.top().on_action('confirm')
        self.assertEqual(g.artifacts, ['aegis'])
        g.ui.push(ui.PauseScreen(g))
        self.exercise(g, g.ui.top())
        g.ui.clear()
        g.end_run('quit')
        res = g.ui.top()
        self.assertIsInstance(res, ui.ResultsScreen)
        self.exercise(g, res)

    def test_assist_offer_after_three_early_deaths(self):
        g = make_game()
        g.profile.data['death_streak'] = 3
        g.start_run('standard')
        g.end_run('death')
        labels = [it.get_label() for it in g.ui.top().items]
        self.assertTrue(any('помощь' in lb.lower() for lb in labels))
        g.ui.top().on_action('confirm')
        self.assertEqual(g.settings.get('difficulty'), 'story')

    def test_palettes_and_ui_scale_render(self):
        g = make_game()
        g.start_run('standard')
        bot_step(g, 120, god=True)
        for pal in ('default', 'deuteranopia', 'protanopia', 'tritanopia', 'high_contrast'):
            g.settings.set('palette', pal)
            g.settings.set('shapes', True)
            g.settings.set('ui_scale', 1.4)
            for theme in ('grid', 'stars', 'waves', 'minimal'):
                g.settings.set('bg_theme', theme)
                g.draw()
        g.settings.set('ui_scale', 1.0)
        g.settings.set('shapes', False)


class TestAudio(unittest.TestCase):
    def test_generate_all_sounds(self):
        from cshift import sound_design
        d = tempfile.mkdtemp()
        n = sound_design.generate_all(d, overwrite=True)
        files = [f for f in os.listdir(d) if f.endswith('.wav')]
        self.assertEqual(len(files), len(sound_design.RECIPES))
        self.assertGreaterEqual(len(files), 30)
        self.assertTrue(n is None or n >= 0)

    def test_sound_manager_packs_never_crash(self):
        from cshift.audio import SoundManager
        for pack in ('studio', 'retro', 'unknown'):
            sm = SoundManager(pack, 0.5)
            for name in ('shoot_red', 'refraction_perfect', 'boss_phase', 'missing_sound'):
                sm.play(name, 0.5)


if __name__ == '__main__':
    unittest.main()

"""Headless-тесты архивной версии v6.1 (legacy/67.py).

Запуск из папки chromashift:
    python -m unittest discover -s tests -v

Тесты используют SDL dummy-драйверы и временный файл сохранения,
поэтому не открывают окно и не трогают chromashift_save.json.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("chromashift_game", os.path.join(GAME_DIR, "legacy", "67.py"))
cs = importlib.util.module_from_spec(_spec)
sys.modules["chromashift_game"] = cs
_spec.loader.exec_module(cs)
CFG = cs.CFG


class FakeKeys:
    def __init__(self, *pressed):
        self.pressed = set(pressed)

    def __getitem__(self, key):
        return key in self.pressed


def keydown(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)


class GameTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.save_path = os.path.join(self.tmpdir, "save.json")
        CFG._values["META_SAVE_FILE"] = self.save_path
        self.game = cs.Game()
        self.game.handle_event(keydown(pygame.K_RETURN))
        self.assertEqual(self.game.state, "PLAYING")
        # Изолируем механики от случайного спавна волн
        self.game.wave_enemies_remaining = 0
        self.game.enemies.append(cs.ChaserEnemy(-500, -500))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def kill(self, mode):
        enemy = cs.ChaserEnemy(300, 300)
        self.game.enemies.append(enemy)
        enemy.take_damage(10_000, self.game, mode)
        return enemy


class TestStateLifecycle(GameTestCase):
    def test_full_cycle_menu_play_pause_death_restart(self):
        g = self.game
        for _ in range(30):
            g.update(1 / 60)
            g.draw()
        g.handle_event(keydown(pygame.K_ESCAPE))
        self.assertEqual(g.state, "PAUSED")
        t = g.game_time
        g.player.dash_cooldown = 1.0
        for _ in range(30):
            g.update(1 / 60)
            g.draw()
        self.assertEqual(g.game_time, t, "пауза не должна продвигать время")
        self.assertEqual(g.player.dash_cooldown, 1.0, "пауза не должна тратить таймеры")
        g.handle_event(keydown(pygame.K_ESCAPE))
        self.assertEqual(g.state, "PLAYING")

        g.player.hp = 1
        g.player.take_damage(50, g, 0, 0)
        self.assertEqual(g.state, "GAME_OVER")
        self.assertFalse(g.music_system.active)
        g.draw()

        g.handle_event(keydown(pygame.K_r))
        self.assertEqual(g.state, "PLAYING")
        self.assertEqual(g.player.hp, g.player.max_hp)
        self.assertEqual(g.score, 0)
        self.assertFalse(g.echo_chamber_active)
        self.assertFalse(g.player.impulse_active)
        self.assertEqual(g.resonances, [])

        g.state = "GAME_OVER"
        g.handle_event(keydown(pygame.K_ESCAPE))
        self.assertEqual(g.state, "MENU")
        g.draw()

    def test_music_starts_with_run_when_audio_available(self):
        self.assertEqual(self.game.music_system.active, self.game.sound_manager.enabled)


class TestKillStreakMechanics(GameTestCase):
    def test_impulse_activates_despite_resonance_reset(self):
        for i in range(CFG.IMPULSE_KILL_THRESHOLD):
            self.kill("RED")
        self.assertTrue(self.game.player.impulse_active)
        self.assertGreaterEqual(len(self.game.resonances), 1)

    def test_color_change_breaks_streaks(self):
        for _ in range(CFG.IMPULSE_KILL_THRESHOLD - 1):
            self.kill("RED")
        self.kill("BLUE")
        self.assertFalse(self.game.player.impulse_active)
        self.assertEqual(self.game.impulse_streak["RED"], 0)

    def test_resonance_threshold(self):
        for _ in range(CFG.RESONANCE_KILL_THRESHOLD):
            self.kill("GREEN")
        self.assertEqual(len(self.game.resonances), 1)
        self.assertEqual(self.game.resonances[0].color_mode, "GREEN")


class TestCombat(GameTestCase):
    def test_piercing_bullet_hits_all_overlapping_enemies_once(self):
        g = self.game
        g.enemies.clear()
        e1, e2 = cs.ChaserEnemy(400, 300), cs.ChaserEnemy(402, 300)
        g.enemies += [e1, e2]
        b = cs.PlayerBullet(401, 300, 1, 0, "RED", is_piercing=True)
        b.speed = 0
        g.player_bullets.append(b)
        g.player.x, g.player.y = 100, 100
        g.update_playing(1 / 60)
        self.assertLess(e1.hp, CFG.CHASER_HP)
        self.assertLess(e2.hp, CFG.CHASER_HP)
        hp1 = e1.hp
        g.update_playing(1 / 60)
        self.assertEqual(e1.hp, hp1, "повторный урон от одной пробивающей пули")

    def test_normal_bullet_hits_one_enemy(self):
        g = self.game
        g.enemies.clear()
        e1, e2 = cs.ChaserEnemy(400, 300), cs.ChaserEnemy(402, 300)
        g.enemies += [e1, e2]
        b = cs.PlayerBullet(401, 300, 1, 0, "RED")
        b.speed = 0
        g.player_bullets.append(b)
        g.player.x, g.player.y = 100, 100
        g.update_playing(1 / 60)
        damaged = [e for e in (e1, e2) if e.hp < CFG.CHASER_HP]
        self.assertEqual(len(damaged), 1)
        self.assertEqual(g.player_bullets, [])

    def test_perfect_refraction_and_echo_chamber(self):
        g = self.game
        for _ in range(CFG.ECHO_REFRACTION_THRESHOLD):
            g.chromatic_buffer.record_change(g.game_time, "BLUE")
            bullet = cs.EnemyBullet(g.player.x, g.player.y, 1, 0)
            g.enemy_bullets.append(bullet)
            hp = g.player.hp
            g.update_playing(1 / 60)
            g.hitstop_timer = 0
            self.assertEqual(g.player.hp, hp)
        self.assertTrue(g.echo_chamber_active)
        for _ in range(int(CFG.ECHO_DURATION * 60) + 5):
            g.update_playing(1 / 60)
        self.assertFalse(g.echo_chamber_active)
        b = cs.EnemyBullet(100, 100, 1, 0, speed=100)
        b.update(1.0, g)
        self.assertAlmostEqual(b.x, 200.0)

    def test_missed_refraction_counts_in_telemetry(self):
        g = self.game
        g.chromatic_buffer.last_change_time = -100
        g.enemy_bullets.append(cs.EnemyBullet(g.player.x, g.player.y, 1, 0))
        g.update_playing(1 / 60)
        self.assertEqual(g.telemetry.refraction_attempts, 1)
        self.assertEqual(g.telemetry.refraction_successes, 0)


class TestDashAndPhysics(GameTestCase):
    def test_holding_space_does_not_redash(self):
        g, p = self.game, self.game.player
        for _ in range(200):
            p.update(1 / 60, FakeKeys(pygame.K_SPACE), (900, 300), g)
        self.assertFalse(p.is_dashing)

    def test_keydown_dash_once_and_finishes(self):
        g, p = self.game, self.game.player
        g.handle_event(keydown(pygame.K_SPACE))
        self.assertTrue(p.is_dashing)
        cd = p.dash_cooldown
        g.handle_event(keydown(pygame.K_SPACE))
        self.assertEqual(p.dash_cooldown, cd)
        for _ in range(30):
            p.update(1 / 60, FakeKeys(), (900, 300), g)
        self.assertFalse(p.is_dashing)
        self.assertFalse(p.dash_invuln)

    def test_mode_switch_keeps_velocity(self):
        g, p = self.game, self.game.player
        for _ in range(30):
            p.update(1 / 60, FakeKeys(pygame.K_d), (900, 300), g)
        vx = p.vx
        self.assertGreater(vx, 0)
        g.handle_event(keydown(pygame.K_3))
        self.assertEqual(p.mode, "GREEN")
        self.assertEqual(p.vx, vx)

    def test_modes_feel_different(self):
        results = {}
        for mode in ("RED", "BLUE", "GREEN"):
            g = self.game
            g.reset_game()
            p = g.player
            p.set_mode(mode, g)
            for _ in range(60):
                p.update(1 / 60, FakeKeys(pygame.K_d), (900, 300), g)
            top = abs(p.vx)
            for _ in range(10):
                p.update(1 / 60, FakeKeys(), (900, 300), g)
            results[mode] = (top, abs(p.vx) / max(top, 1e-6))
        self.assertGreater(results["RED"][0], results["BLUE"][0])
        self.assertLess(results["BLUE"][1], results["RED"][1], "BLUE тормозит резче")


class TestBeatSync(GameTestCase):
    def test_beat_clock_runs_without_music(self):
        g = self.game
        g.music_system.active = False
        g.beat_tracker = cs.BeatSyncTracker()
        g.game_time = 0
        for _ in range(int(CFG.BEAT_INTERVAL * 60 * 4)):
            g.game_time += 1 / 60
            g.beat_tracker.update(1 / 60, g.game_time)
        self.assertGreater(g.beat_tracker.last_beat_time, 0)

    def test_off_beat_kill_not_counted(self):
        g = self.game
        g.beat_tracker.last_beat_time = 10.0
        g.game_time = 10.0 + CFG.BEAT_INTERVAL / 2
        self.assertFalse(g.beat_tracker.is_on_beat(g.game_time))
        g.game_time = 10.0 + 0.01
        self.assertTrue(g.beat_tracker.is_on_beat(g.game_time))


class TestMetaProgression(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.save_path = os.path.join(self.tmpdir, "save.json")
        CFG._values["META_SAVE_FILE"] = self.save_path

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_negative_points_clamped_and_levels_capped(self):
        with open(self.save_path, "w") as f:
            json.dump({"chromatic_points": -5, "upgrade_tree": {"max_hp": {"current_lvl": 99}}}, f)
        meta = cs.MetaProgression()
        self.assertEqual(meta.chromatic_points, 0)
        self.assertEqual(meta.upgrade_tree["max_hp"]["current_lvl"], 3)

    def test_corrupt_save_is_backed_up_not_lost(self):
        with open(self.save_path, "w") as f:
            f.write("{broken json")
        meta = cs.MetaProgression()
        self.assertEqual(meta.chromatic_points, 0)
        backups = [n for n in os.listdir(self.tmpdir) if ".corrupt-" in n]
        self.assertEqual(len(backups), 1)

    def test_save_roundtrip_and_old_format(self):
        with open(self.save_path, "w") as f:
            json.dump({"chromatic_points": 700, "upgrades": {"dash_cd": 2}}, f)
        meta = cs.MetaProgression()
        self.assertEqual(meta.upgrade_tree["dash_cd"]["current_lvl"], 2)
        self.assertTrue(meta.purchase("max_hp"))
        meta2 = cs.MetaProgression()
        self.assertEqual(meta2.chromatic_points, 600)
        self.assertEqual(meta2.upgrade_tree["max_hp"]["current_lvl"], 1)
        self.assertFalse(os.path.exists(self.save_path + ".tmp"))

    def test_temporal_lens_extends_refraction_window(self):
        with open(self.save_path, "w") as f:
            json.dump({"chromatic_points": 0, "upgrade_tree": {"refract_win": 2}}, f)
        game = cs.Game()
        game.start_run()
        expected = CFG.PERFECT_REFRACTION_WINDOW + 0.06
        self.assertAlmostEqual(game.chromatic_buffer.window, expected)
        self.assertAlmostEqual(game.parry_indicator.max_timer, expected)


class TestInfrastructure(unittest.TestCase):
    def test_surface_cache_is_bounded(self):
        cs.SurfaceCache.clear()
        for r in range(60, 110):
            for a in range(0, 256):
                cs.SurfaceCache.get_circle(r, (255, 0, 0), a)
        self.assertLessEqual(len(cs.SurfaceCache._cache), cs.SurfaceCache.MAX_ENTRIES)
        cs.SurfaceCache.clear()

    def test_spatial_hash_no_duplicates(self):
        h = cs.SpatialHash(50)
        e = cs.ChaserEnemy(100, 100)
        e.radius = 80
        h.insert(e)
        self.assertEqual(h.query(100, 100, 200).count(e), 1)

    def test_sound_fallback_without_numpy(self):
        sm = cs.SoundManager()
        if not sm.enabled:
            self.skipTest("mixer недоступен")
        old = cs.NUMPY_AVAILABLE
        cs.NUMPY_AVAILABLE = False
        try:
            self.assertIsNotNone(sm._synth(440, 440, 30, "sine", 0.2))
        finally:
            cs.NUMPY_AVAILABLE = old

    def test_paths_resolve_next_to_game(self):
        self.assertEqual(os.path.dirname(cs.resolve_game_path("x.json")), os.path.join(GAME_DIR, "legacy"))


class TestStress(GameTestCase):
    def test_heavy_load_stays_bounded(self):
        g = self.game
        g.enemies.clear()
        for i in range(120):
            cls = (cs.ChaserEnemy, cs.ShooterEnemy, cs.KamikazeEnemy, cs.DissonanceEnemy)[i % 4]
            g.enemies.append(cls(50 + (i * 37) % 1180, 50 + (i * 53) % 620))
        for i in range(300):
            g.enemy_bullets.append(cs.EnemyBullet(640, 360, 1 if i % 2 else -1, 0))
        g.god_mode = True
        start = time.perf_counter()
        frames = 300
        for f in range(frames):
            g.player.fire_cooldown = 0
            g.player.shoot(g)
            g.update(1 / 60)
            g.draw()
        elapsed = time.perf_counter() - start
        self.assertLessEqual(len(g.particles.active), CFG.MAX_PARTICLES)
        self.assertLessEqual(len(cs.SurfaceCache._cache), cs.SurfaceCache.MAX_ENTRIES)
        print(f"\n[stress] {frames} кадров, 120 врагов, 300 пуль: "
              f"{elapsed:.2f} c ({frames / elapsed:.0f} кадров/с, headless, dummy video)")


if __name__ == "__main__":
    unittest.main()

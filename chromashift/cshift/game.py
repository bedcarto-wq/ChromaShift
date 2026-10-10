"""Игровое ядро ChromaShift 0.6.5: цикл, забег, механики цвета, арены, тренировка."""
import logging
import math
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .audio import CONDUCTOR_RESTORE_EVENT, BeatSyncTracker, MusicSystem, SoundManager
from .config import CFG, GAME_VERSION, MODES
from .entities import (BossEnemy, ChaserEnemy, ChromaticBuffer, Decoy, DissonanceEnemy, DummyEnemy,
                       Enemy, EnemyBullet, Hazard, KamikazeEnemy, Pillar, Player, PlayerBullet, PowerUp,
                       ShooterEnemy, TurretEnemy)
from .fx import (ChromaticResonance, FloatingText, JuiceSystem, ParryIndicator, ParticleManager,
                 PrismaticCrystal, ScreenShake)
from .progression import (ARTIFACTS, Profile, challenge_setup, detect_archetype, roll_artifacts)
from .settings import InputManager, Settings
from .utils import SpatialHash, circle_collision, clamp, mode_color, vec_distance, vec_normalize, visual
from .waves import WaveDirector

logger = logging.getLogger('ChromaShift')

ENEMY_CLASSES = {'chaser': ChaserEnemy, 'shooter': ShooterEnemy, 'kamikaze': KamikazeEnemy,
                 'dissonance': DissonanceEnemy}
KILL_SCORE = {'chaser': 100, 'shooter': 150, 'kamikaze': 120, 'dissonance': 500, 'boss': 5000}
ARENAS = {'classic': 'Классика', 'pillars': 'Колонны', 'prism': 'Призма'}
RUN_TYPES = {'standard': 'Стандарт', 'daily': 'Ежедневное испытание', 'weekly': 'Еженедельное испытание',
             'pure': 'Чистый режим', 'training': 'Тренировка'}


class Game:
    def __init__(self, headless: bool = False):
        pygame.init()
        self.headless = headless
        self.settings = Settings()
        flags = pygame.RESIZABLE
        self.window = pygame.display.set_mode((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), flags)
        pygame.display.set_caption(f"CHROMASHIFT {GAME_VERSION}")
        if self.settings.get('fullscreen') and not headless:
            self.toggle_fullscreen(force=True)
        self.clock = pygame.time.Clock()
        self.render_surface = pygame.Surface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT))
        self.view_scale = 1.0
        self.view_offset = (0, 0)
        self.running = True
        self.show_fps = bool(self.settings.get('show_fps'))
        self.god_mode = False

        self.profile = Profile.load(int(self.settings.get('last_profile', 0)) % 3)
        self.profile.refresh_contracts()
        self.sound_manager = SoundManager(self.settings.get('sound_pack', 'studio'), self.settings.get('volume', 0.8))
        self.input = InputManager(self.settings)
        self.input.mouse_pos = self.mouse_logical
        self.particles = ParticleManager()
        self.screen_shake = ScreenShake()
        self.floating_texts: List[FloatingText] = []
        self.toasts: List[List[Any]] = []
        self.time = 0.0
        self.menu_time = 0.0
        self.in_run = False
        self.run_over = False
        self._stars = [(random.uniform(0, CFG.SCREEN_WIDTH), random.uniform(0, CFG.SCREEN_HEIGHT),
                        random.uniform(0.2, 1.0)) for _ in range(140)]
        self._dark_surf: Optional[pygame.Surface] = None
        self.reset_run_state()

        from .ui import HUD, MainMenu, UIManager  # отложенный импорт: ui зависит от game
        self.hud = HUD(self)
        self.ui = UIManager(self)
        self.ui.push(MainMenu(self))
        if self.profile.load_warning:
            self.toast(self.profile.load_warning)

    # ------------------------------------------------------------------ окно
    def toggle_fullscreen(self, force: bool = False) -> None:
        if self.headless:
            return
        fs = force or not (self.window.get_flags() & pygame.FULLSCREEN)
        try:
            if fs:
                self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                self.window = pygame.display.set_mode((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), pygame.RESIZABLE)
        except pygame.error as e:
            logger.warning(f'Полноэкранный режим недоступен: {e}')
        self.settings.data['fullscreen'] = fs

    def mouse_logical(self) -> Tuple[float, float]:
        mx, my = pygame.mouse.get_pos()
        return ((mx - self.view_offset[0]) / self.view_scale, (my - self.view_offset[1]) / self.view_scale)

    # ------------------------------------------------------------------ уведомления
    def toast(self, text: str, duration: float = 4.0) -> None:
        self.toasts.append([text, duration])
        self.toasts = self.toasts[-5:]

    def tip(self, tip_id: str, text: str) -> None:
        seen = self.profile.data['seen_tips']
        if self.settings.get('tips', True) and tip_id not in seen:
            seen.append(tip_id)
            self.toast('Подсказка: ' + text, 6.0)

    def announce(self, title: str, subtitle: str = '') -> None:
        self.announcement = [title, subtitle, 2.8]

    def floating_title(self, title: str) -> None:
        self.floating_texts.append(FloatingText(CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2 - 120, title,
                                                CFG.COLOR_ACCENT, 2.0, 40))

    def flash(self, color: Tuple[int, int, int], alpha: float) -> None:
        self.flash_color = color
        self.flash_alpha = max(self.flash_alpha, alpha * visual('flash'))

    # ------------------------------------------------------------------ забег
    def reset_run_state(self) -> None:
        pygame.time.set_timer(CONDUCTOR_RESTORE_EVENT, 0)
        self.run_type = 'standard'
        self.arena = 'classic'
        self.tension = 0
        self.risks: List[str] = []
        self.challenge_key = ''
        self.seed: Optional[int] = None
        self.mods = self.profile.build_mods('standard', self.settings)
        self.player = Player(CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2, self.mods, self.settings)
        self.enemies: List[Enemy] = []
        self.player_bullets: List[PlayerBullet] = []
        self.enemy_bullets: List[EnemyBullet] = []
        self.powerups: List[PowerUp] = []
        self.resonances: List[ChromaticResonance] = []
        self.pillars: List[Pillar] = []
        self.hazards: List[Hazard] = []
        self.decoys: List[Decoy] = []
        self.floating_texts = []
        self.particles.clear()
        self.spatial_hash = SpatialHash()
        self.juice_system = JuiceSystem()
        self._last_impact_x = self._last_impact_y = 0.0
        self.crystal = PrismaticCrystal()
        self.beat_tracker = BeatSyncTracker(self.mods.beat_window_add)
        self.chromatic_buffer = ChromaticBuffer(self.mods.refraction_window)
        self.parry_indicator = ParryIndicator(self.mods.refraction_window)
        self.music_system = MusicSystem(self.sound_manager, self.profile.data.get('archetype', 'balanced'))
        self.director = WaveDirector(self, random.Random())
        self.game_time = 0.0
        self.score = 0
        self.combo = 0
        self.combo_timer = 0.0
        self.max_combo = 0
        self.hitstop_timer = 0.0
        self.flash_alpha = 0.0
        self.flash_color = CFG.COLOR_PRIMARY
        self.kill_streak = {m: 0 for m in MODES}
        self.impulse_streak = {m: 0 for m in MODES}
        self.echo_chamber_active = False
        self.echo_chamber_timer = 0.0
        self.refraction_streak = 0
        self.refraction_fail_streak = 0
        self.adaptive_bonus = 0.0
        self.dash_trail_timer = 0.0
        self.rail_hits: List[int] = []
        self.artifacts: List[str] = []
        self.wave_times: List[float] = []
        self.cp_lines: List[Tuple[str, int]] = []
        self.dying_timer = -1.0
        self.announcement: Optional[List[Any]] = None
        self.powerup_group = 0
        self.bg_offset = 0.0
        self.is_training = False
        self.enemy_damage_mult = 1.0
        self.enemy_bullet_speed_mult = 1.0
        self.stats: Dict[str, Any] = {'kills': 0, 'shots': 0, 'hits': 0, 'refractions': 0, 'refraction_fails': 0,
                                      'echoes': 0, 'impulses': 0, 'resonances': 0, 'beat_kills': 0,
                                      'bosses': 0, 'elites': 0, 'dashes': 0, 'switches': 0, 'damage_taken': 0,
                                      'no_damage_waves': 0, 'waves_cleared': 0, 'artifacts': 0, 'codex': {},
                                      'damage_sources': {}, 'groove_cp': 0}
        for m in MODES:
            self.stats[f'kills_{m}'] = 0
            self.stats[f'time_{m}'] = 0.0
        self.last_run: Optional[Dict[str, Any]] = None

    def start_run(self, run_type: str = 'standard', tension: int = 0, risks: Optional[List[str]] = None,
                  arena: str = 'classic', start_mode: str = 'RED') -> None:
        self.reset_run_state()
        self.run_type = run_type if run_type in RUN_TYPES else 'standard'
        risks = list(risks or [])
        if self.run_type in ('daily', 'weekly'):
            setup = challenge_setup(self.run_type)
            arena, risks, start_mode, tension = setup['arena'], setup['risks'], setup['start_mode'], setup['tension']
            self.seed = setup['seed']
            self.challenge_key = setup['key']
            random.seed(self.seed)
            self.director.rng = random.Random(self.seed)
        if self.run_type == 'training':
            risks, tension = [], 0
        self.arena = arena if arena in ARENAS else 'classic'
        self.tension = max(0, min(int(tension), self.profile.data['tension_unlocked']
                                  if self.run_type not in ('daily', 'weekly') else 10))
        self.risks = risks
        self.mods = self.profile.build_mods(self.run_type, self.settings, self.tension, risks)
        self.enemy_damage_mult = self.mods.enemy_damage_mult
        self.enemy_bullet_speed_mult = self.mods.enemy_bullet_speed_mult
        self.player = Player(CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2, self.mods, self.settings, start_mode)
        cos = self.profile.data['cosmetics']
        self.player.ship_shape = cos.get('ship_shape', 'circle')
        self.player.trail_style = cos.get('trail_style', 'mode')
        self.beat_tracker = BeatSyncTracker(self.mods.beat_window_add)
        self.update_refraction_window()
        self.music_system = MusicSystem(self.sound_manager, self.profile.data.get('archetype', 'balanced'))
        if self.settings.get('music', True):
            self.music_system.start()
        self.build_arena()
        self.in_run = True
        self.run_over = False
        self.is_training = self.run_type == 'training'
        if self.is_training:
            self.setup_training()
        self.tip('controls', 'WASD — движение, 1/2/3 или колесо — цвет, ПКМ/Пробел — рывок')
        self.tip('refraction', 'Смените цвет за мгновение до попадания пули — она отразится (Преломление)')
        self.ui.clear()

    def update_refraction_window(self) -> None:
        window = self.mods.refraction_window + self.adaptive_bonus
        self.chromatic_buffer.window = window
        self.parry_indicator = ParryIndicator(window)

    def build_arena(self) -> None:
        w, h = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        self.pillars = []
        if self.arena == 'pillars':
            for fx, fy in ((0.25, 0.3), (0.75, 0.3), (0.25, 0.7), (0.75, 0.7)):
                self.pillars.append(Pillar(w * fx, h * fy, 38))
        elif self.arena == 'prism':
            for i, m in enumerate(MODES):
                a = -math.pi / 2 + i * 2 * math.pi / 3
                self.resonances.append(ChromaticResonance(w / 2 + math.cos(a) * 260, h / 2 + math.sin(a) * 210,
                                                          m, 0.9, 0.0, static=True))

    def setup_training(self) -> None:
        w, h = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        for i in range(3):
            d = DummyEnemy(w * (0.3 + 0.2 * i), h * 0.25)
            self.enemies.append(d)
        self.enemies.append(TurretEnemy(w * 0.15, h * 0.8))
        self.enemies.append(TurretEnemy(w * 0.85, h * 0.8))
        self.director.state = 'training'
        self.announce('ТРЕНИРОВКА', 'Манекены показывают урон, турели — для Преломления. Esc — выход')

    def modal_open(self) -> bool:
        return self.ui.top() is not None

    def end_run(self, reason: str = 'death') -> None:
        """Финализирует забег: статистика, CP, профиль, экран итогов."""
        if not self.in_run or self.run_over:
            return
        self.run_over = True
        self.in_run = False
        self.music_system.stop()
        kills = self.stats['kills']
        lines = list(self.cp_lines)
        if kills >= 10:
            lines.append((f"Убийства ({kills})", (kills // 10) * CFG.CP_PER_10_KILLS))
        if self.stats['refractions']:
            lines.append((f"Преломления ({self.stats['refractions']})", self.stats['refractions'] * CFG.CP_PER_REFRACTION))
        if self.stats['groove_cp']:
            lines.append(('Грув-чип', self.stats['groove_cp']))
        run = dict(self.stats)
        run.update({'run_type': self.run_type, 'wave': self.director.wave if not self.is_training else 0,
                    'score': int(self.score), 'time': self.game_time, 'max_combo': self.max_combo,
                    'death_cause': self.player.last_damage_source if reason == 'death' else 'выход',
                    'tension': self.tension, 'risks': list(self.risks), 'arena': self.arena,
                    'cp_lines': lines, 'cp_mult': self.mods.cp_mult, 'wave_times': list(self.wave_times),
                    'challenge_key': self.challenge_key, 'artifacts_list': list(self.artifacts),
                    'wave_log': list(self.director.log), 'reason': reason})
        run['archetype'] = detect_archetype(run)
        result = self.profile.record_run(run)
        self.profile.save()
        self.settings.save()
        self.last_run = run
        for n in result.get('notices', []):
            self.toast(n)
        if result.get('notices'):
            self.sound_manager.play('achievement', 0.6)
        from .ui import ResultsScreen
        self.ui.clear()
        self.ui.push(ResultsScreen(self, run, result))

    # ------------------------------------------------------------------ события от сущностей
    def nearest_enemy(self, x: float, y: float, radius: float, exclude: Optional[List[int]] = None) -> Optional[Enemy]:
        best, best_d = None, radius
        for e in self.enemies:
            if not e.alive or (exclude and e.id in exclude) or e.kind in ('dummy', 'turret'):
                continue
            d = vec_distance(x, y, e.x, e.y)
            if d < best_d:
                best, best_d = e, d
        return best

    def blue_shockwave(self, x: float, y: float) -> None:
        self.particles.emit_burst(x, y, 30, mode_color('BLUE'), 420.0, 0.6, 4.0)
        self.screen_shake.trigger(6.0, 0.2)
        for e in list(self.enemies):
            if not e.alive:
                continue
            d = vec_distance(x, y, e.x, e.y)
            if d < 170:
                nx, ny = vec_normalize(e.x - x, e.y - y)
                e.vx += nx * 500
                e.vy += ny * 500
                e.take_damage(CFG.BULLET_DAMAGE * 0.8 * self.mods.damage_mult, self, 'BLUE', is_aoe=True)

    def on_player_dash(self, player: Player) -> None:
        self.stats['dashes'] += 1
        self.rail_hits = []
        if self.mods.green_afterimage:
            self.decoys.append(Decoy(player.x, player.y))
        if self.mods.red_dash_trail:
            self.dash_trail_timer = 0.0

    def on_player_shot(self, n: int) -> None:
        self.stats['shots'] += n

    def on_player_damaged(self, damage: float, source: str) -> None:
        self.stats['damage_taken'] += damage
        ds = self.stats['damage_sources']
        ds[source] = ds.get(source, 0) + damage
        self.director.on_player_damaged(damage)
        self.combo = 0
        self.music_system.conductor_damage()
        self.flash(CFG.COLOR_DANGER, 0.25)

    def player_died(self) -> None:
        if self.dying_timer >= 0:
            return
        self.dying_timer = 1.3
        self.particles.emit_burst(self.player.x, self.player.y, CFG.PLAYER_DEATH_PARTICLES, CFG.COLOR_PRIMARY, 400.0, 1.5, 5.0)
        self.screen_shake.trigger(15.0, 0.5)
        self.flash(CFG.COLOR_DANGER, 0.8)
        self.sound_manager.play('death', 0.8)
        self.music_system.stop()

    def on_kamikaze_exploded(self, enemy: Enemy) -> None:
        if enemy.counted:
            self.director.on_counted_kill()
        self.stats['codex']['kamikaze'] = self.stats['codex'].get('kamikaze', 0)

    def spawn_enemy(self, kind: str, x: float, y: float, elite: Optional[List[str]] = None,
                    shield: Optional[str] = None, tier: int = 1, counted: bool = True) -> Enemy:
        if kind == 'boss':
            enemy: Enemy = BossEnemy(x, y, tier)
        else:
            enemy = ENEMY_CLASSES[kind](x, y)
        hp_s, sp_s, dmg_s = self.director_scaling()
        enemy.apply_scaling(hp_s * self.mods.enemy_hp_mult, sp_s * self.mods.enemy_speed_mult, dmg_s)
        if self.director.special == 'haste':
            enemy.speed *= 1.3
        if elite:
            enemy.make_elite(elite, shield)
        enemy.counted = counted
        self.enemies.append(enemy)
        self.particles.emit_burst(x, y, 10, CFG.COLOR_DANGER if not elite else (255, 140, 220), 160.0, 0.4, 2.5)
        if kind == 'boss':
            self.tip('boss', 'Босс уязвим к цвету своей оболочки — следите за сменой цвета')
        return enemy

    def director_scaling(self) -> Tuple[float, float, float]:
        from .waves import wave_scaling
        return wave_scaling(max(1, self.director.wave))

    def on_enemy_killed(self, enemy: Enemy, mode: str, refraction_kill: bool = False) -> None:
        enemy.alive = False
        kind = enemy.kind
        st = self.stats
        if kind in ('dummy', 'turret'):
            return
        st['kills'] += 1
        st[f'kills_{mode}'] = st.get(f'kills_{mode}', 0) + 1
        st['codex'][kind] = st['codex'].get(kind, 0) + 1
        if enemy.elite:
            st['elites'] += 1
        if enemy.counted:
            self.director.on_counted_kill()
        self.combo += 1
        self.combo_timer = 3.0
        self.max_combo = max(self.max_combo, self.combo)
        mult = (1 + min(self.combo, 50) * 0.05) * self.mods.score_mult
        if self.director.overheat:
            mult *= 1.5
        base = KILL_SCORE.get(kind, 100) * (2 if enemy.elite else 1)
        on_beat = self.beat_tracker.is_on_beat(self.game_time)
        if on_beat:
            st['beat_kills'] += 1
            base *= 1.5
            self.floating_texts.append(FloatingText(enemy.x, enemy.y - 30, 'В ТАКТ', CFG.COLOR_ACCENT, 0.7, 16))
            self.sound_manager.play('beat_kill', 0.4)
            if self.mods.beat_groove and st['beat_kills'] % 5 == 0:
                st['groove_cp'] += 1
        if refraction_kill:
            base *= 2
        gained = int(base * mult)
        self.score += gained
        self.floating_texts.append(FloatingText(enemy.x, enemy.y, f"+{gained}", mode_color(mode), 0.8, 18))
        self.particles.emit_burst(enemy.x, enemy.y, CFG.ENEMY_DEATH_PARTICLES, mode_color(mode), 300.0, 0.7, 3.0)
        self._last_impact_x, self._last_impact_y = enemy.x, enemy.y
        self.juice_system.trigger_impact(3.0 if kind in ('dissonance', 'boss') else 1.0, mode_color(mode), self)
        self.sound_manager.play('enemy_death', 0.45)
        self.music_system.on_kill(mode)
        self.player.dash_cooldown = max(0.0, self.player.dash_cooldown - CFG.DASH_KILL_REDUCTION)
        # Резонанс и Импульс — независимые счётчики
        for m in MODES:
            if m != mode:
                self.kill_streak[m] = 0
                self.impulse_streak[m] = 0
        self.kill_streak[mode] += 1
        if self.kill_streak[mode] >= self.mods.resonance_threshold:
            self.kill_streak[mode] = 0
            self.resonances.append(ChromaticResonance(enemy.x, enemy.y, mode, self.mods.resonance_radius_mult,
                                                      self.mods.resonance_lifetime_add))
            st['resonances'] += 1
            self.tip('resonance', 'Резонанс: стойте в зоне своего цвета — быстрее, сильнее, чаще стреляете')
        self.impulse_streak[mode] += 1
        if self.impulse_streak[mode] >= self.mods.impulse_threshold:
            self.impulse_streak[mode] = 0
            self.player.impulse_active = True
            self.player.impulse_timer = CFG.IMPULSE_DURATION + self.mods.impulse_duration_add
            st['impulses'] += 1
            self.floating_texts.append(FloatingText(self.player.x, self.player.y - 50, 'ИМПУЛЬС!', mode_color(mode), 1.5, 28))
            self.sound_manager.play('combo', 0.6)
            self.tip('impulse', 'Импульс: серия убийств одним цветом даёт пробивающие пули')
        # Особые враги
        if 'splitting' in enemy.elite:
            for k in range(2):
                child = self.spawn_enemy('chaser', enemy.x + (k * 2 - 1) * 20, enemy.y, counted=False)
                child.hp = child.max_hp = child.max_hp * 0.4
                child.radius *= 0.75
        if kind == 'boss':
            st['bosses'] += 1
            self.cp_lines.append((f"Босс (волна {self.director.wave})", CFG.CP_PER_BOSS))
            self.flash(CFG.COLOR_ACCENT, 0.6)
            self.screen_shake.trigger(18.0, 0.6)
            self.sound_manager.play('achievement', 0.7)
            for e in self.enemies:
                if e.alive and not e.counted:
                    e.alive = False
        # Бонусы
        chance = CFG.POWERUP_SPAWN_CHANCE + self.mods.powerup_chance_add
        if self.random_roll() < chance:
            types = ['invuln', 'shield'] + ([] if self.mods.no_heal else ['heal', 'heal'])
            self.powerups.append(PowerUp(enemy.x, enemy.y, random.choice(types)))

    def random_roll(self) -> float:
        return random.random()

    def spawn_breather_choice(self) -> None:
        types = ['shield', 'invuln'] + ([] if self.mods.no_heal else ['heal'])
        picks = random.sample(types, 2)
        self.powerup_group += 1
        for i, t in enumerate(picks):
            p = PowerUp(CFG.SCREEN_WIDTH / 2 + (i * 2 - 1) * 140, CFG.SCREEN_HEIGHT / 2 + 120, t)
            p.group = self.powerup_group
            p.lifetime = 25.0
            self.powerups.append(p)

    def on_wave_cleared(self, summary: Dict[str, Any]) -> None:
        self.score += summary['score_bonus']
        self.cp_lines.append((f"Волна {summary['wave']}", summary['cp']))
        self.stats['waves_cleared'] += 1
        if summary['no_damage']:
            self.stats['no_damage_waves'] += 1
        self.wave_times.append(round(self.game_time, 2))
        ghost = self.profile.data['ghost'].get('wave_times', [])
        idx = summary['wave'] - 1
        if idx < len(ghost):
            delta = self.game_time - ghost[idx]
            col = CFG.COLOR_SUCCESS if delta <= 0 else CFG.COLOR_DANGER
            self.floating_texts.append(FloatingText(CFG.SCREEN_WIDTH / 2, 150, f"Призрак рекорда: {delta:+.1f} с", col, 2.0, 22))
        self.sound_manager.play('wave_clear', 0.6)
        self.wave_summary = [summary, 3.0]
        if (summary['wave'] % CFG.ARTIFACT_WAVE_INTERVAL == 0 and self.run_type not in ('pure', 'training')):
            from .ui import ArtifactScreen
            rng = self.director.rng if self.seed is not None else random
            choices = roll_artifacts(rng, self.profile.data.get('archetype', 'balanced'), self.artifacts)
            if choices:
                self.ui.push(ArtifactScreen(self, choices))

    def take_artifact(self, aid: str) -> None:
        shields_before, revives_before = self.mods.shield_charges, self.mods.revives
        ARTIFACTS[aid]['apply'](self.mods)
        self.player.shield_charges += max(0, self.mods.shield_charges - shields_before)
        self.player.revives += max(0, self.mods.revives - revives_before)
        self.artifacts.append(aid)
        self.stats['artifacts'] += 1
        self.refresh_player_from_mods()
        self.update_refraction_window()
        self.sound_manager.play('artifact', 0.7)
        self.toast(f"Артефакт: {ARTIFACTS[aid]['name']} — {ARTIFACTS[aid]['desc']}")

    def refresh_player_from_mods(self) -> None:
        p = self.player
        ratio = p.hp / max(1, p.max_hp)
        p.max_hp = max(10, int((CFG.PLAYER_MAX_HP + self.mods.max_hp_add) * self.mods.max_hp_mult))
        p.hp = max(1, int(round(p.max_hp * ratio)))
        p.dash_cooldown_max = CFG.DASH_COOLDOWN * self.mods.dash_cd_mult
        self.beat_tracker.beat_window = max(0.02, CFG.BEAT_WINDOW + self.mods.beat_window_add)
        self.enemy_damage_mult = self.mods.enemy_damage_mult

    def set_player_mode(self, mode: str) -> None:
        if mode == self.player.mode or mode not in MODES:
            return
        self.player.set_mode(mode, self)
        self.chromatic_buffer.record_change(self.game_time, mode)
        self.stats['switches'] += 1

    def cycle_mode(self, step: int) -> None:
        i = MODES.index(self.player.mode)
        self.set_player_mode(MODES[(i + step) % 3])

    # ------------------------------------------------------------------ Преломление
    def perfect_refraction(self, bullet: EnemyBullet) -> None:
        self.hitstop_timer = CFG.HITSTOP_DURATION
        dx, dy = -bullet.dx, -bullet.dy
        target = None
        for e in self.enemies:
            if isinstance(e, DissonanceEnemy) and e.alive and vec_distance(bullet.x, bullet.y, e.x, e.y) < 260:
                target = e
                break
        if target is None and self.mods.refraction_homing:
            target = self.nearest_enemy(bullet.x, bullet.y, 500)
        if target is not None:
            dx, dy = vec_normalize(target.x - bullet.x, target.y - bullet.y)
        self.screen_shake.trigger(8.0, 0.2, (dx, dy))
        ref = PlayerBullet(bullet.x, bullet.y, dx, dy, self.player.mode, self.mods.refraction_pierce)
        ref.speed = max(bullet.speed * 2, 500)
        ref.damage = max(bullet.damage, CFG.SHOOTER_BULLET_DAMAGE) * 3 * self.mods.damage_mult
        ref.is_refracted = True
        ref.ricochets = self.mods.refraction_ricochet
        ref.homing = self.mods.refraction_homing
        self.player_bullets.append(ref)
        self.particles.emit_burst(bullet.x, bullet.y, CFG.REFRACTION_PARTICLES, mode_color(self.player.mode), 400.0, 0.8, 4.0)
        self.sound_manager.play('refraction_perfect', 0.7)
        self.floating_texts.append(FloatingText(bullet.x, bullet.y - 20, 'ПРЕЛОМЛЕНИЕ!', CFG.COLOR_ACCENT, 1.0, 22))
        self.combo += 2
        self.max_combo = max(self.max_combo, self.combo)
        self.combo_timer = 3.0
        self.score += int(500 * self.mods.score_mult)
        self.stats['refractions'] += 1
        self.refraction_fail_streak = 0
        if self.adaptive_bonus > 0:
            self.adaptive_bonus = max(0.0, self.adaptive_bonus - 0.01)
            self.update_refraction_window()
        self.refraction_streak += 1
        if self.refraction_streak >= self.mods.echo_threshold:
            self.activate_echo_chamber()
        self.music_system.conductor_restore()

    def activate_echo_chamber(self) -> None:
        self.echo_chamber_active = True
        self.echo_chamber_timer = CFG.ECHO_DURATION + self.mods.echo_duration_add
        self.refraction_streak = 0
        self.stats['echoes'] += 1
        self.floating_texts.append(FloatingText(CFG.SCREEN_WIDTH / 2, CFG.SCREEN_HEIGHT / 2, 'ЭХО-КАМЕРА!', CFG.COLOR_ACCENT, 2.0, 36))
        self.particles.emit_spiral(self.player.x, self.player.y, 50, CFG.COLOR_ACCENT, 400.0)
        self.sound_manager.play('combo', 0.8)
        self.tip('echo', 'Эхо-камера: после серии Преломлений вражеские пули замедляются')

    def on_refraction_failed(self) -> None:
        self.stats['refraction_fails'] += 1
        self.refraction_streak = 0
        self.refraction_fail_streak += 1
        adaptive = (self.settings.get('adaptive_windows', True)
                    and self.run_type not in ('daily', 'weekly', 'pure'))
        if adaptive and self.refraction_fail_streak >= 4 and self.adaptive_bonus < 0.06:
            self.adaptive_bonus = min(0.06, self.adaptive_bonus + 0.02)
            self.refraction_fail_streak = 0
            self.update_refraction_window()

    def is_in_resonance(self, x: float, y: float, mode: str) -> bool:
        return any(r.color_mode == mode and vec_distance(x, y, r.x, r.y) < r.radius for r in self.resonances)

    # ------------------------------------------------------------------ обновление
    def handle_game_action(self, act: str) -> None:
        if act == 'pause':
            from .ui import PauseScreen
            self.ui.push(PauseScreen(self))
        elif act.startswith('mode_'):
            self.set_player_mode(act[5:].upper())
        elif act == 'cycle_next':
            self.cycle_mode(1)
        elif act == 'cycle_prev':
            self.cycle_mode(-1)
        elif act == 'dash' and self.dying_timer < 0:
            self.player.start_dash(self)
        elif act == 'fullscreen':
            self.toggle_fullscreen()
        elif act == 'fps':
            self.show_fps = not self.show_fps
        elif act == 'god' and CFG.DEBUG_MODE:
            self.god_mode = not self.god_mode
            self.toast(f"God mode: {'вкл' if self.god_mode else 'выкл'}")

    def update_playing(self, dt: float) -> None:
        self.game_time += dt
        self.bg_offset += dt * 20
        p = self.player
        if self.dying_timer >= 0:
            self.dying_timer -= dt
            self.particles.update(dt)
            self.screen_shake.update(dt)
            if self.dying_timer < 0:
                self.end_run('death')
            return
        self.stats[f'time_{p.mode}'] += dt
        move = self.input.move_vector()
        aim = self.input.aim_point(p, [e for e in self.enemies if e.alive])
        self.input.update_radial((p.x, p.y), aim)
        p.in_resonance = self.is_in_resonance(p.x, p.y, p.mode)
        p.update(dt, move, aim, self)
        for pl in self.pillars:
            pl.push_out(p)
        if self.input.fire_held() and not self.input.radial_open:
            if p.in_resonance:
                p.fire_cooldown = min(p.fire_cooldown, CFG.FIRE_COOLDOWN * CFG.RESONANCE_FIRE_RATE_MULT)
            p.shoot(self)
        # Рывок: огненный след и рельсотрон
        if p.is_dashing:
            if self.mods.red_dash_trail:
                self.dash_trail_timer -= dt
                if self.dash_trail_timer <= 0:
                    self.dash_trail_timer = 0.03
                    self.hazards.append(Hazard(p.x, p.y, 60.0 * self.mods.damage_mult))
            if self.mods.railgun_dash:
                for e in self.enemies:
                    if e.alive and e.id not in self.rail_hits and circle_collision(p.x, p.y, p.radius + 6, e.x, e.y, e.radius):
                        self.rail_hits.append(e.id)
                        e.take_damage(CFG.BULLET_DAMAGE * 2 * self.mods.damage_mult, self, 'RED')

        self.crystal.update(dt, p.x, p.y, p.mode, self.combo)
        beat = self.beat_tracker.update(dt, self.game_time)
        if beat:
            self.music_system.on_beat()
        self.music_system.update(dt)
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0
        if self.echo_chamber_active:
            self.echo_chamber_timer -= dt
            if self.echo_chamber_timer <= 0:
                self.echo_chamber_active = False
        if not self.is_training:
            self.director.update(dt, beat)

        bullet_cap = len(self.enemy_bullets) >= CFG.WAVE_MAX_ENEMY_BULLETS
        for e in list(self.enemies):
            if not e.alive:
                continue
            target: Any = p
            if self.decoys and isinstance(e, ChaserEnemy):
                d = min(self.decoys, key=lambda dc: vec_distance(e.x, e.y, dc.x, dc.y))
                if vec_distance(e.x, e.y, d.x, d.y) < 400:
                    target = d
            result = e.update(dt, target)
            if isinstance(result, EnemyBullet):
                if not bullet_cap or isinstance(e, TurretEnemy):
                    self.enemy_bullets.append(result)
            elif result == 'explode' and isinstance(e, KamikazeEnemy):
                e.explode(self)
            elif isinstance(result, list):
                for a in result:
                    if isinstance(a, EnemyBullet):
                        if len(self.enemy_bullets) < CFG.WAVE_MAX_ENEMY_BULLETS * 1.5:
                            self.enemy_bullets.append(a)
                    elif isinstance(a, tuple) and a[0] == 'summon':
                        for k in range(a[1]):
                            ang = random.uniform(0, math.pi * 2)
                            self.spawn_enemy('chaser', clamp(e.x + math.cos(ang) * 70, 30, CFG.SCREEN_WIDTH - 30),
                                             clamp(e.y + math.sin(ang) * 70, 30, CFG.SCREEN_HEIGHT - 30), counted=False)
                if isinstance(e, BossEnemy):
                    ph = e.phase
                    if ph != getattr(e, '_announced_phase', 1):
                        e._announced_phase = ph
                        self.announce(f"ФАЗА {ph}", 'Таран с предупреждением' if ph == 2 else 'Спираль и призыв')
                        self.sound_manager.play('boss_phase', 0.6)
            if self.pillars:
                for pl in self.pillars:
                    pl.push_out(e)
            if not isinstance(e, BossEnemy):
                e.x = clamp(e.x, -60, CFG.SCREEN_WIDTH + 60)
                e.y = clamp(e.y, -60, CFG.SCREEN_HEIGHT + 60)

        self.player_bullets = [b for b in self.player_bullets if b.update(dt, self)]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.update(dt, self)]
        if self.pillars:
            self.player_bullets = [b for b in self.player_bullets if not any(pl.blocks(b.x, b.y, b.radius) for pl in self.pillars)]
            self.enemy_bullets = [b for b in self.enemy_bullets if not any(pl.blocks(b.x, b.y, b.radius) for pl in self.pillars)]
        self.powerups = [pu for pu in self.powerups if pu.update(dt)]
        self.resonances = [r for r in self.resonances if r.update(dt)]
        self.hazards = [h for h in self.hazards if h.update(dt)]
        self.decoys = [d for d in self.decoys if d.update(dt)]
        self.particles.update(dt)
        self.floating_texts = [t for t in self.floating_texts if t.update(dt)]
        self.screen_shake.update(dt)
        self.parry_indicator.update(dt)
        self.juice_system.update(dt)
        if self.flash_alpha > 0:
            self.flash_alpha = max(0.0, self.flash_alpha - dt * 5)
        self.collisions()
        self.enemies = [e for e in self.enemies if e.alive]

    def collisions(self) -> None:
        p = self.player
        sh = self.spatial_hash
        sh.clear()
        for e in self.enemies:
            if e.alive:
                sh.insert(e)
        res_mult = 1.0 + CFG.RESONANCE_DAMAGE_BOOST if p.in_resonance else 1.0
        # 1. Пули игрока → враги
        keep: List[PlayerBullet] = []
        for b in self.player_bullets:
            consumed = False
            for e in sh.query(b.x, b.y, b.radius + 60):
                if not e.alive or e.id in b.hit_enemies:
                    continue
                if not circle_collision(b.x, b.y, b.radius, e.x, e.y, e.radius):
                    continue
                self.stats['hits'] += 1
                if isinstance(e, DissonanceEnemy) and b.is_refracted:
                    e.on_perfect_refraction_hit(self)
                else:
                    e.take_damage(b.damage * res_mult, self, b.mode)
                if b.is_refracted and b.ricochet(self, e):
                    continue
                if b.is_piercing:
                    b.hit_enemies.append(e.id)
                    continue
                consumed = True
                break
            if not consumed:
                keep.append(b)
        self.player_bullets = keep
        # 2. Пули врагов → игрок (Преломление)
        keep_e: List[EnemyBullet] = []
        for b in self.enemy_bullets:
            d = vec_distance(b.x, b.y, p.x, p.y)
            if d < CFG.PARRY_WARNING_RADIUS:
                self.parry_indicator.start_warning()
            if d < CFG.PARRY_INDICATOR_RADIUS and not self.parry_indicator.active:
                self.parry_indicator.trigger()
            if circle_collision(b.x, b.y, b.radius, p.x, p.y, p.radius):
                if self.chromatic_buffer.is_in_window(self.game_time):
                    self.perfect_refraction(b)
                    continue
                if p.can_be_damaged(self):
                    self.on_refraction_failed()
                if b.damage > 0:
                    p.take_damage(b.damage, self, b.x, b.y, b.source)
                continue
            keep_e.append(b)
        self.enemy_bullets = keep_e
        # 3. Контакт с врагами
        for e in sh.query(p.x, p.y, p.radius + 60):
            if not e.alive or not circle_collision(e.x, e.y, e.radius, p.x, p.y, p.radius):
                continue
            if isinstance(e, KamikazeEnemy):
                if not e.exploded:
                    e.explode(self)
            elif isinstance(e, ChaserEnemy):
                p.take_damage(CFG.CHASER_DAMAGE * e.damage_mult, self, e.x, e.y, e.name)
            elif isinstance(e, BossEnemy):
                p.take_damage(25 * e.damage_mult, self, e.x, e.y, e.name)
        # 4. Огненный след
        for h in self.hazards:
            if h.tick <= 0:
                h.tick = 0.2
                for e in sh.query(h.x, h.y, h.radius + 40):
                    if e.alive and circle_collision(h.x, h.y, h.radius, e.x, e.y, e.radius):
                        e.take_damage(h.dps * 0.2, self, 'RED', is_aoe=True)
        # 5. Бонусы (с магнитом)
        pick_r = p.radius * self.mods.pickup_radius_mult
        taken_groups = set()
        keep_p: List[PowerUp] = []
        for pu in self.powerups:
            d = vec_distance(pu.x, pu.y, p.x, p.y)
            if self.mods.pickup_radius_mult > 1.0 and d < 120 * self.mods.pickup_radius_mult:
                nx, ny = vec_normalize(p.x - pu.x, p.y - pu.y)
                pu.x += nx * 4
                pu.y += ny * 4
            if d < pu.radius + pick_r:
                if pu.type == 'heal' and self.mods.no_heal:
                    keep_p.append(pu)
                    continue
                pu.apply(self)
                if pu.group is not None:
                    taken_groups.add(pu.group)
                continue
            keep_p.append(pu)
        self.powerups = [pu for pu in keep_p if pu.group is None or pu.group not in taken_groups]

    # ------------------------------------------------------------------ главный цикл
    def update(self, dt: float) -> None:
        self.time += dt
        self.menu_time += dt
        for t in self.toasts:
            t[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]
        if self.announcement:
            self.announcement[2] -= dt
            if self.announcement[2] <= 0:
                self.announcement = None
        if getattr(self, 'wave_summary', None):
            self.wave_summary[1] -= dt
            if self.wave_summary[1] <= 0:
                self.wave_summary = None
        top = self.ui.top()
        if top is not None:
            top.update(dt)
        if self.in_run and top is None:
            if self.hitstop_timer > 0:
                self.hitstop_timer -= dt
                self.screen_shake.update(dt)
            else:
                self.update_playing(dt)
        elif not self.in_run:
            self.particles.update(dt)

    def handle_event(self, event: Any) -> None:
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type == CONDUCTOR_RESTORE_EVENT:
            if self.in_run and self.dying_timer < 0:
                self.music_system.conductor_restore()
            return
        if event.type == pygame.VIDEORESIZE and not self.headless:
            return
        top = self.ui.top()
        in_game = self.in_run and top is None
        acts = self.input.process_event(event, in_game)
        if event.type == pygame.MOUSEMOTION and top is not None:
            top.on_mouse(self.mouse_logical(), False)
        if in_game:
            for a in acts:
                self.handle_game_action(a)
        elif top is not None:
            for a in acts:
                if a == 'click':
                    top.on_mouse(self.mouse_logical(), True)
                elif a == 'fullscreen':
                    self.toggle_fullscreen()
                else:
                    top.on_action(a)

    def draw(self) -> None:
        surf = self.render_surface
        top = self.ui.top()
        if self.in_run or (top is not None and getattr(top, 'show_world', False)):
            from .ui import draw_world
            draw_world(self, surf)
            if self.in_run:
                self.hud.draw(surf)
        else:
            from .ui import draw_background
            draw_background(self, surf, menu=True)
        if top is not None:
            top.draw(surf)
        self.hud.draw_toasts(surf)
        if self.show_fps:
            from .utils import get_font
            surf.blit(get_font('consolas', 14).render(f"FPS {self.clock.get_fps():.0f}", True, CFG.COLOR_SUCCESS),
                      (CFG.SCREEN_WIDTH - 80, CFG.SCREEN_HEIGHT - 22))
        self.present()

    def present(self) -> None:
        ww, wh = self.window.get_size()
        sw, sh = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        scale = min(ww / sw, wh / sh)
        self.window.fill((0, 0, 0))
        ox, oy = int(self.screen_shake.offset_x), int(self.screen_shake.offset_y)
        if abs(scale - 1.0) < 1e-3:
            self.view_scale, self.view_offset = 1.0, ((ww - sw) // 2, (wh - sh) // 2)
            self.window.blit(self.render_surface, (self.view_offset[0] + ox, self.view_offset[1] + oy))
        else:
            tw, th = int(sw * scale), int(sh * scale)
            self.view_scale, self.view_offset = scale, ((ww - tw) // 2, (wh - th) // 2)
            scaled = pygame.transform.smoothscale(self.render_surface, (tw, th))
            self.window.blit(scaled, (self.view_offset[0] + int(ox * scale), self.view_offset[1] + int(oy * scale)))
        pygame.display.flip()

    def step(self, dt: float, events: Optional[List[Any]] = None) -> None:
        for event in (events if events is not None else pygame.event.get()):
            self.handle_event(event)
        self.update(min(dt, 0.05))

    def quit(self) -> None:
        if self.in_run:
            self.end_run('quit')
        self.settings.save()
        self.profile.save()
        self.running = False

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(CFG.TARGET_FPS) / 1000.0
            self.step(dt)
            if self.running:
                self.draw()
        pygame.quit()
        sys.exit(0)

"""Игровое ядро ChromaShift 0.7.0: цикл, забег, механики цвета, арены, тренировка,
чёткий рендер в физическом разрешении, новые враги/боссы, магазин, режимы и победа."""
import logging
import math
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

import pygame

from .audio import CONDUCTOR_RESTORE_EVENT, BeatSyncTracker, MusicSystem, SoundManager
from .config import ALL_MODES, CFG, GAME_VERSION, MODES
from .entities import (BossEnemy, ChaserEnemy, ChromaticBuffer, Decoy, DissonanceEnemy, DummyEnemy,
                       Enemy, EnemyBullet, Hazard, KamikazeEnemy, Pillar, Player, PlayerBullet, PowerUp,
                       ShooterEnemy, TurretEnemy)
from .enemies_ext import (EXT_ENEMIES, EXT_HINTS, EXT_NAMES, Beam, HydraBoss, HydraHead, Mine, PaintZone,
                          Portal, ShardEnemy, SpectrumBoss, WardenEnemy)
from .fx import (ChromaticResonance, FloatingText, JuiceSystem, ParryIndicator, ParticleManager,
                 PrismaticCrystal, ScreenShake)
from .hires import HiSurface, get_scale, set_scale
from .mechanics import ColorMechanics, GravityWell
from .progression import (ARTIFACT_SETS, ARTIFACTS, DAILY_RULES, Profile, apply_caps, apply_daily_rule,
                          challenge_setup, completed_sets, detect_archetype, roll_artifacts)
from .settings import InputManager, Settings
from .utils import clear_render_caches
from .utils import SpatialHash, circle_collision, clamp, mode_color, vec_distance, vec_normalize, visual
from .waves import WaveDirector

logger = logging.getLogger('ChromaShift')

ENEMY_CLASSES = {'chaser': ChaserEnemy, 'shooter': ShooterEnemy, 'kamikaze': KamikazeEnemy,
                 'dissonance': DissonanceEnemy, 'warden': WardenEnemy}
ENEMY_CLASSES.update(EXT_ENEMIES)
BOSS_CLASSES = {'boss': BossEnemy, 'hydra': HydraBoss, 'spectrum': SpectrumBoss}
KILL_SCORE = {'chaser': 100, 'shooter': 150, 'kamikaze': 120, 'dissonance': 400, 'boss': 5000,
              'swarm': 25, 'shard': 40, 'prism': 220, 'mirror': 200, 'chameleon': 180, 'shieldbearer': 260,
              'miner': 200, 'laser': 260, 'devourer': 260, 'summoner': 300, 'teleporter': 180, 'resonator': 240,
              'leader': 300, 'warden': 2000, 'hydra_head': 600}
ARENAS = {'classic': 'Классика', 'pillars': 'Колонны', 'prism': 'Призма', 'portals': 'Порталы'}
RUN_TYPES = {'standard': 'Стандарт', 'daily': 'Ежедневное испытание', 'weekly': 'Еженедельное испытание',
             'pure': 'Чистый режим', 'training': 'Тренировка', 'endless': 'Бесконечный',
             'bossrush': 'Босс-раш', 'blitz': 'Блиц (10 минут)', 'custom': 'Свои волны'}
RENDER_QUALITY = {'native': 'Чёткая (родное разрешение)', 'balanced': 'Сбалансированная', 'classic': 'Классическая (720p)'}


class TrialTarget(DummyEnemy):
    """Мишень испытания RED: разбивается и сразу появляется в новом месте."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y)
        self.hp = self.max_hp = 45.0
        self.radius = 16

    def take_damage(self, damage: float, game: Any, bullet_mode: str, is_aoe: bool = False) -> bool:
        super().take_damage(damage, game, bullet_mode, is_aoe)
        self.hp -= damage
        if self.hp <= 0:
            game.particles.emit_burst(self.x, self.y, 16, mode_color(bullet_mode), 240.0, 0.5, 3.0)
            tr = game.color_mech.trial
            if tr and tr['id'] == 'trial_red' and not tr['done']:
                tr['progress'] += 1
            self.hp = self.max_hp
            self.x = random.uniform(120, CFG.SCREEN_WIDTH - 120)
            self.y = random.uniform(100, CFG.SCREEN_HEIGHT * 0.6)
        return False


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
        self.render_surface: pygame.Surface = HiSurface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT))
        self.custom_waves: List[Dict[str, Any]] = []
        self.victory = False
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
        self.update_notice = ''
        if self.settings.get('check_updates', False) and not headless:
            from .updates import start_check
            start_check(self)
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

    def floating_texts_add(self, x: float, y: float, text: str, color: Tuple[int, int, int] = CFG.COLOR_ACCENT,
                           life: float = 0.9, size: int = 18) -> None:
        if len(self.floating_texts) < 80:
            self.floating_texts.append(FloatingText(x, y, text, color, life, size))

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
        self.paints: List[PaintZone] = []
        self.walls: List[Any] = []
        self.portals: List[Portal] = []
        self.mines: List[Mine] = []
        self.beams: List[Beam] = []
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
        self.color_mech = ColorMechanics(self)
        self.color_mech.ability = self.settings.get('ability', 'nova')
        self.daily_rule = 'none'
        self.trial_node: Optional[str] = None
        self.victory = False
        self.blitz_left = 0.0
        self.inversion_t = 0.0
        self.last_run_args: Dict[str, Any] = {}
        self.game_time = 0.0
        self.score = 0
        self.combo = 0
        self.combo_timer = 0.0
        self.max_combo = 0
        self.hitstop_timer = 0.0
        self.flash_alpha = 0.0
        self.flash_color = CFG.COLOR_PRIMARY
        self.kill_streak = {m: 0 for m in ALL_MODES}
        self.impulse_streak = {m: 0 for m in ALL_MODES}
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
                                      'damage_sources': {}, 'groove_cp': 0,
                                      'hydra_kills': 0, 'spectrum_kills': 0, 'vortexes': 0, 'touch_parries': 0,
                                      'chains': 0, 'precise_kills': 0, 'absorbed': 0, 'shop_buys': 0,
                                      'gambles_won': 0, 'damage_by_mode': {m: 0.0 for m in ALL_MODES},
                                      'damage_timeline': []}
        for m in ALL_MODES:
            self.stats[f'kills_{m}'] = 0
            self.stats[f'time_{m}'] = 0.0
        self.last_run: Optional[Dict[str, Any]] = None

    def start_run(self, run_type: str = 'standard', tension: int = 0, risks: Optional[List[str]] = None,
                  arena: str = 'classic', start_mode: str = 'RED', trial_node: Optional[str] = None,
                  trial: Optional[str] = None, custom_waves: Optional[List[Dict[str, Any]]] = None) -> None:
        args = {'run_type': run_type, 'tension': tension, 'risks': list(risks or []), 'arena': arena,
                'start_mode': start_mode, 'trial_node': trial_node, 'trial': trial, 'custom_waves': custom_waves}
        self.reset_run_state()
        self.last_run_args = args
        if custom_waves is not None:
            self.custom_waves = list(custom_waves)
        rule = 'none'
        self.run_type = run_type if run_type in RUN_TYPES else 'standard'
        risks = list(risks or [])
        if self.run_type in ('daily', 'weekly'):
            setup = challenge_setup(self.run_type)
            arena, risks, start_mode, tension = setup['arena'], setup['risks'], setup['start_mode'], setup['tension']
            self.seed = setup['seed']
            self.challenge_key = setup['key']
            rule = setup.get('rule', 'none') if self.run_type == 'daily' else 'none'
            random.seed(self.seed)
            self.director.rng = random.Random(self.seed)
        if self.run_type == 'training':
            risks, tension = [], 0
        self.arena = arena if arena in ARENAS else 'classic'
        self.tension = max(0, min(int(tension), self.profile.data['tension_unlocked']
                                  if self.run_type not in ('daily', 'weekly') else 10))
        self.risks = risks
        self.mods = self.profile.build_mods(self.run_type, self.settings, self.tension, risks, trial_node=trial_node)
        self.trial_node = trial_node
        self.daily_rule = rule
        if rule != 'none':
            apply_daily_rule(self.mods, rule)
            apply_caps(self.mods)
        if self.run_type == 'blitz':
            self.blitz_left = CFG.BLITZ_DURATION
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
            if trial:
                self.start_trial(trial)
        self.tip('controls', 'WASD — движение, 1/2/3 или колесо — цвет, ПКМ/Пробел — рывок, R — навык цвета, '
                             'F — способность')
        if self.mods.violet_unlocked:
            self.tip('violet', 'VIOLET (клавиша 4): быстрый и скользкий, пули пробивают врага и цветные щиты')
        if rule != 'none':
            self.toast(f"Правило дня: {DAILY_RULES[rule][0]} — {DAILY_RULES[rule][1]}", 6.0)
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
        elif self.arena == 'portals':
            pairs = (('RED', (0.12, 0.2), (0.88, 0.8)), ('BLUE', (0.88, 0.2), (0.12, 0.8)),
                     ('GREEN', (0.5, 0.12), (0.5, 0.88)))
            for col, a, b in pairs:
                pa, pb = Portal(w * a[0], h * a[1], col), Portal(w * b[0], h * b[1], col)
                pa.pair, pb.pair = pb, pa
                self.portals += [pa, pb]
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
        if self.victory:
            lines.append(('Победа', 60))
        run = dict(self.stats)
        run.update({'run_type': self.run_type, 'wave': self.director.wave if not self.is_training else 0,
                    'score': int(self.score), 'time': self.game_time, 'max_combo': self.max_combo,
                    'death_cause': self.player.last_damage_source if reason == 'death' else 'выход',
                    'tension': self.tension, 'risks': list(self.risks), 'arena': self.arena,
                    'cp_lines': lines, 'cp_mult': self.mods.cp_mult, 'wave_times': list(self.wave_times),
                    'challenge_key': self.challenge_key, 'artifacts_list': list(self.artifacts),
                    'wave_log': list(self.director.log), 'reason': reason, 'victory': self.victory,
                    'hull': self.profile.loadout.get('hull', 'prism'), 'shards_left': self.color_mech.shards,
                    'daily_rule': self.daily_rule})
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
                    shield: Optional[str] = None, tier: int = 1, counted: bool = True,
                    extra: Optional[Dict[str, Any]] = None) -> Enemy:
        if kind in BOSS_CLASSES:
            enemy: Enemy = BOSS_CLASSES[kind](x, y, tier)
        elif kind == 'warden':
            enemy = WardenEnemy(x, y, tier)
        elif kind == 'shard':
            enemy = ShardEnemy(x, y, (extra or {}).get('color'))
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
        if kind in BOSS_CLASSES:
            self.tip('boss', 'Босс уязвим к цвету своей оболочки — следите за сменой цвета')
        seen = self.profile.data.setdefault('codex_seen', [])
        if kind in EXT_HINTS and kind not in seen and not self.is_training:
            seen.append(kind)
            self.toast(f"Новый враг — {EXT_NAMES.get(kind, kind)}: {EXT_HINTS[kind]}", 6.0)
        return enemy

    def handle_enemy_result(self, e: Enemy, result: Any) -> None:
        """Обрабатывает всё, что вернул враг из update(): пули и действия-кортежи."""
        if result is None:
            return
        if isinstance(result, EnemyBullet):
            if len(self.enemy_bullets) < CFG.WAVE_MAX_ENEMY_BULLETS or isinstance(e, TurretEnemy):
                self.enemy_bullets.append(result)
            return
        if result == 'explode' and isinstance(e, KamikazeEnemy):
            e.explode(self)
            return
        if isinstance(result, tuple):
            result = [result]
        if not isinstance(result, list):
            return
        p = self.player
        for a in result:
            if isinstance(a, EnemyBullet):
                if len(self.enemy_bullets) < CFG.WAVE_MAX_ENEMY_BULLETS * 1.5:
                    self.enemy_bullets.append(a)
                continue
            if not isinstance(a, tuple) or not a:
                continue
            tag = a[0]
            if tag == 'summon':
                for k in range(a[1]):
                    ang = random.uniform(0, math.pi * 2)
                    self.spawn_enemy('chaser', clamp(e.x + math.cos(ang) * 70, 30, CFG.SCREEN_WIDTH - 30),
                                     clamp(e.y + math.sin(ang) * 70, 30, CFG.SCREEN_HEIGHT - 30), counted=False)
            elif tag == 'spawn':
                _, kind, x, y, counted = a
                if sum(1 for en in self.enemies if en.alive) < CFG.WAVE_MAX_ACTIVE_ENEMIES + 10:
                    self.spawn_enemy(kind, clamp(x, 20, CFG.SCREEN_WIDTH - 20), clamp(y, 20, CFG.SCREEN_HEIGHT - 20),
                                     counted=counted)
            elif tag == 'mine':
                if len(self.mines) < 14:
                    self.mines.append(Mine(a[1], a[2], a[3]))
            elif tag == 'beam':
                src = f"луч: {e.name}" if not isinstance(e, BossEnemy) else f"луч: {getattr(e, 'title', e.name)}"
                self.beams.append(Beam(a[1], a[2], a[3], a[4], a[5], source=src))
            elif tag == 'jam':
                if vec_distance(a[1], a[2], p.x, p.y) < a[3] + p.radius:
                    p.color_lock_t = max(p.color_lock_t, CFG.DISSONANCE_JAM_TIME)
                    self.floating_texts_add(p.x, p.y - 36, 'ГЛУШЕНИЕ', (170, 170, 190), 0.8, 16)
                    self.tip('jam', 'Диссонанс глушит цвет рядом с собой — отойдите от его кольца')
            elif tag == 'inversion':
                self.start_inversion(float(a[1]))
            elif tag == 'hydra_heads' and isinstance(e, HydraBoss):
                hp = 260 * a[1] * max(1.0, e.max_hp / (CFG.BOSS_HP * 1.15))
                e.heads = []
                for i, m in enumerate(MODES):
                    h = HydraHead(e.x, e.y, m, e, i, hp)
                    self.enemies.append(h)
                    e.heads.append(h)
                self.announce('ГОЛОВЫ ГИДРЫ', 'Каждая голова уязвима к своему цвету')
        if isinstance(e, BossEnemy):
            ph = e.phase
            if ph != getattr(e, '_announced_phase', 1):
                e._announced_phase = ph
                if isinstance(e, HydraBoss):
                    sub = 'Головы уничтожены — тело уязвимо!' if ph == 2 else 'Головы отросли!'
                elif isinstance(e, SpectrumBoss):
                    sub = 'Инверсия: физика цветов перемешана' if ph == 2 else 'Распад: зеркала и спираль'
                else:
                    sub = 'Таран с предупреждением' if ph == 2 else 'Спираль и призыв'
                self.announce(f"ФАЗА {ph}", sub)
                self.sound_manager.play('boss_phase', 0.6)

    def start_inversion(self, seconds: float) -> None:
        modes = list(MODES)
        shuffled = modes[1:] + modes[:1]
        self.player.physics_map = dict(zip(modes, shuffled))
        self.inversion_t = max(self.inversion_t, seconds)
        self.announce('ИНВЕРСИЯ', 'RED движется как BLUE, BLUE — как GREEN, GREEN — как RED')

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
        last_of_wave = False
        if enemy.counted:
            self.director.on_counted_kill()
            d = self.director
            last_of_wave = (d.state == 'active' and d.current_sub >= len(d.subwaves) - 1 and not d.telegraphs
                            and d.special != 'survive'
                            and not any(e.alive and e.counted and e is not enemy for e in self.enemies))
        precise = self.color_mech.on_kill(enemy, mode, last_of_wave)
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
        gained = int(base * mult * precise)
        self.score += gained
        if self.settings.get('damage_numbers', True) or gained >= 1000:
            self.floating_texts_add(enemy.x, enemy.y, f"+{gained}", mode_color(mode), 0.8, 18)
        self.particles.emit_burst(enemy.x, enemy.y, CFG.ENEMY_DEATH_PARTICLES, mode_color(mode), 300.0, 0.7, 3.0)
        self._last_impact_x, self._last_impact_y = enemy.x, enemy.y
        self.juice_system.trigger_impact(3.0 if kind in ('dissonance', 'boss', 'warden') else
                                         (0.4 if kind == 'swarm' else 1.0), mode_color(mode), self)
        self.sound_manager.play('enemy_death', 0.2 if kind == 'swarm' else 0.45)
        self.music_system.on_kill(mode)
        self.player.dash_cooldown = max(0.0, self.player.dash_cooldown - CFG.DASH_KILL_REDUCTION)
        # Резонанс и Импульс — независимые счётчики
        for m in ALL_MODES:
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
        # Призма раскалывается, вожак — отряд теряет строй, Пожиратель лопается
        if hasattr(enemy, 'death_spawns'):
            for k2, x2, y2, extra in enemy.death_spawns():
                self.spawn_enemy(k2, x2, y2, counted=False, extra=extra)
        if enemy.is_leader and enemy.squad_id is not None:
            for e2 in self.enemies:
                if e2.alive and e2.squad_id == enemy.squad_id:
                    e2.scatter_t = 6.0
            self.floating_texts_add(enemy.x, enemy.y - 40, 'ОТРЯД БЕЗ ВОЖАКА', CFG.COLOR_ACCENT, 1.2, 18)
        if hasattr(enemy, 'on_killed_burst'):
            for b in enemy.on_killed_burst():
                self.enemy_bullets.append(b)
        if kind == 'warden':
            self.cp_lines.append((f"Страж (волна {self.director.wave})", CFG.CP_PER_BOSS // 2))
            self.flash(CFG.COLOR_ACCENT, 0.4)
            self.screen_shake.trigger(12.0, 0.4)
            self.sound_manager.play('achievement', 0.6)
        if kind == 'boss':
            st['bosses'] += 1
            if isinstance(enemy, HydraBoss):
                st['hydra_kills'] += 1
            elif isinstance(enemy, SpectrumBoss):
                st['spectrum_kills'] += 1
            self.cp_lines.append((f"{getattr(enemy, 'title', 'Босс')} (волна {self.director.wave})", CFG.CP_PER_BOSS))
            self.flash(CFG.COLOR_ACCENT, 0.6)
            self.screen_shake.trigger(18.0, 0.6)
            self.sound_manager.play('achievement', 0.7)
            for e in self.enemies:
                if e.alive and not e.counted:
                    e.alive = False
        # Бонусы
        chance = CFG.POWERUP_SPAWN_CHANCE + self.mods.powerup_chance_add
        if kind == 'swarm':
            chance *= 0.15  # рой даёт мало бонусов, иначе их будет слишком много
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
        if (summary['wave'] % CFG.SHOP_WAVE_INTERVAL == 0 and self.run_type not in ('pure', 'training', 'blitz')
                and not summary.get('boss')):
            from .ui_ext import ShopScreen
            rng = self.director.rng if self.seed is not None else random
            self.ui.push(ShopScreen(self, self.color_mech.shop_offer(rng)))

    def take_artifact(self, aid: str) -> None:
        shields_before, revives_before = self.mods.shield_charges, self.mods.revives
        ARTIFACTS[aid]['apply'](self.mods)
        self.player.shield_charges += max(0, self.mods.shield_charges - shields_before)
        self.player.revives += max(0, self.mods.revives - revives_before)
        sets_before = set(completed_sets(self.artifacts))
        self.artifacts.append(aid)
        for sid in set(completed_sets(self.artifacts)) - sets_before:
            ARTIFACT_SETS[sid]['apply'](self.mods)
            self.toast(f"Набор «{ARTIFACT_SETS[sid]['name']}» собран: {ARTIFACT_SETS[sid]['desc']}", 6.0)
        apply_caps(self.mods)
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

    def available_modes(self) -> List[str]:
        return list(ALL_MODES) if self.mods.violet_unlocked else list(MODES)

    def set_player_mode(self, mode: str, forced: bool = False) -> bool:
        p = self.player
        if mode == p.mode or mode not in self.available_modes():
            return False
        if not forced and p.color_lock_t > 0:
            self.floating_texts_add(p.x, p.y - 30, 'ЦВЕТ ЗАБЛОКИРОВАН', (170, 170, 190), 0.5, 14)
            return False
        old = p.mode
        p.set_mode(mode, self)
        if p.mode != mode:
            return False
        self.chromatic_buffer.record_change(self.game_time, mode)
        self.stats['switches'] += 1
        if not forced:
            self.color_mech.on_switch(old, mode)
        return True

    def cycle_mode(self, step: int) -> None:
        modes = self.available_modes()
        i = modes.index(self.player.mode) if self.player.mode in modes else 0
        self.set_player_mode(modes[(i + step) % len(modes)])

    # ------------------------------------------------------------------ особые волны, победа
    def on_special_wave(self, special: str) -> None:
        p = self.player
        if special == 'onecolor':
            p.color_lock_t = 9999.0
        elif special == 'inversion':
            self.start_inversion(9999.0)
        elif special == 'gravity':
            w, h = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
            for fx, fy in ((0.3, 0.5), (0.7, 0.5)):
                self.color_mech.wells.append(GravityWell(w * fx, h * fy, 999.0, 230, 160, 'all'))

    def on_special_end(self, special: str) -> None:
        p = self.player
        if special == 'onecolor':
            p.color_lock_t = 0.0
        elif special == 'inversion':
            self.inversion_t = 0.0
            p.physics_map = {}
        elif special == 'gravity':
            self.color_mech.wells = [w for w in self.color_mech.wells if w.life < 900]

    def on_victory(self) -> None:
        self.victory = True
        self.flash(CFG.COLOR_ACCENT, 0.7)
        self.sound_manager.play('achievement', 0.8)
        if self.run_type in ('bossrush', 'custom'):
            self.announce('ПОБЕДА!', 'Все волны пройдены')
            self.end_run('victory')
            return
        from .ui_ext import VictoryScreen
        self.ui.push(VictoryScreen(self))

    def restart_run(self) -> None:
        args = dict(self.last_run_args or {})
        if not args:
            return
        if self.in_run and not self.is_training:
            self.end_run('quit')
        self.ui.clear()
        self.start_run(**args)

    def start_trial(self, tid: str) -> None:
        from .mechanics import TRIALS
        if tid not in TRIALS:
            return
        info = TRIALS[tid]
        if info['mode'] == 'VIOLET':
            self.mods.violet_unlocked = True
        self.set_player_mode(info['mode'], forced=True)
        self.color_mech.start_trial(tid)
        self.announce(info['name'].upper(), info['desc'])
        w, h = CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT
        if tid == 'trial_red':
            for i in range(4):
                self.enemies.append(TrialTarget(w * (0.2 + 0.2 * i), h * 0.45))
        elif tid == 'trial_violet':
            for i in range(3):  # пары манекенов на одной линии
                self.enemies.append(DummyEnemy(w * (0.3 + 0.2 * i), h * 0.45))
                self.enemies.append(DummyEnemy(w * (0.3 + 0.2 * i), h * 0.45 - 50))
        elif tid == 'trial_blue':
            for i in range(5):
                a = i * 2 * math.pi / 5
                self.enemies.append(DummyEnemy(w * 0.5 + math.cos(a) * 60, h * 0.5 + math.sin(a) * 60))

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
        elif act == 'skill':
            self.color_mech.color_skill()
        elif act == 'ability':
            self.color_mech.use_ability()
        elif act == 'gamble' and not self.is_training:
            self.toast(self.director.toggle_gamble(), 4.0)
        elif act == 'restart':
            self.restart_run()
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
        self.color_mech.update(dt)
        if self.inversion_t > 0 and self.inversion_t < 9000:
            self.inversion_t -= dt
            if self.inversion_t <= 0:
                p.physics_map = {}
        if self.director.special == 'onecolor' and self.director.state == 'active':
            p.color_lock_t = max(p.color_lock_t, 0.5)
        if self.run_type == 'blitz' and not self.is_training:
            self.blitz_left -= dt
            if self.blitz_left <= 0:
                self.announce('ВРЕМЯ!', 'Блиц окончен')
                self.end_run('blitz')
                return
        self.stats['damage_timeline'] = self.stats['damage_timeline'] or []
        if int(self.game_time) % 10 == 0 and (not self.stats['damage_timeline']
                                              or self.stats['damage_timeline'][-1][0] != int(self.game_time)):
            self.stats['damage_timeline'].append((int(self.game_time), int(self.stats['damage_taken'])))

        # Статусы и ауры (Щитоносец, Резонатор, элита-Ускоритель)
        alive = [e for e in self.enemies if e.alive]
        for e in alive:
            e.tick_status(dt)
        for src in alive:
            aura_r = getattr(src, 'AURA', 0.0)
            accel = 'accelerator' in src.elite
            if not aura_r and not accel:
                continue
            rr = aura_r or 120.0
            for e in alive:
                if e is src or vec_distance(src.x, src.y, e.x, e.y) > rr:
                    continue
                if src.kind == 'shieldbearer':
                    e.aura_shield = True
                else:
                    e.aura_speed = max(e.aura_speed, 1.3)
        ts = self.color_mech.enemy_time_scale()
        for e in list(self.enemies):
            if not e.alive:
                continue
            target: Any = p
            if self.decoys and isinstance(e, ChaserEnemy):
                d = min(self.decoys, key=lambda dc: vec_distance(e.x, e.y, dc.x, dc.y))
                if vec_distance(e.x, e.y, d.x, d.y) < 400:
                    target = d
            k = e.time_factor() * ts
            if k <= 0:
                if e.hit_flash > 0:
                    e.hit_flash -= dt
                e.x += e.vx * dt * 0.3
                e.y += e.vy * dt * 0.3
                e.vx *= 0.9
                e.vy *= 0.9
                continue
            result = e.update(dt * k, target)
            self.handle_enemy_result(e, result)
            if self.pillars:
                for pl in self.pillars:
                    pl.push_out(e)
            if not isinstance(e, BossEnemy):
                e.x = clamp(e.x, -60, CFG.SCREEN_WIDTH + 60)
                e.y = clamp(e.y, -60, CFG.SCREEN_HEIGHT + 60)

        self.player_bullets = [b for b in self.player_bullets if b.update(dt, self)]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.update(dt * ts, self)]
        self.mines = [m for m in self.mines if m.update(dt * ts, self)]
        self.beams = [bm for bm in self.beams if bm.update(dt, self)]
        self.paints = [z for z in self.paints if z.update(dt)]
        self.walls = [wl for wl in self.walls if wl.update(dt)]
        if self.walls:
            self.enemy_bullets = [b for b in self.enemy_bullets
                                  if not any(wl.blocks(b.x, b.y, b.radius) for wl in self.walls)]
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
                mode = self.color_mech.bullet_mode_vs(b, e)
                # Зеркало и элита с отражающей аурой возвращают пулю
                if not b.is_refracted and ((hasattr(e, 'reflects') and e.reflects(mode))
                                           or ('reflective' in e.elite and random.random() < 0.3)):
                    dx, dy = vec_normalize(p.x - b.x, p.y - b.y)
                    eb = EnemyBullet(b.x, b.y, dx, dy, 260, CFG.SHOOTER_BULLET_DAMAGE * 0.8 * e.damage_mult,
                                     f"отражение: {e.name}")
                    eb.color = getattr(e, 'color_tag', None) or mode
                    self.enemy_bullets.append(eb)
                    self.particles.emit_burst(b.x, b.y, 8, mode_color(mode), 180.0, 0.3, 2.0)
                    self.tip('mirror', 'Зеркало отражает пули ВАШЕГО текущего цвета — смените цвет')
                    consumed = True
                    break
                dmg = b.damage * res_mult
                if isinstance(e, BossEnemy) or getattr(e, 'boss_like', False):
                    dmg *= self.mods.boss_damage_mult
                if b.slow_hit:
                    e.slow_t = max(e.slow_t, 1.5)
                hp_before = e.hp
                if isinstance(e, DissonanceEnemy) and b.is_refracted:
                    e.on_perfect_refraction_hit(self)
                else:
                    e.take_damage(dmg, self, mode)
                dealt = max(0.0, hp_before - max(0.0, e.hp))
                dbm = self.stats['damage_by_mode']
                dbm[b.mode] = dbm.get(b.mode, 0.0) + dealt
                if b.crit and self.settings.get('damage_numbers', True):
                    self.floating_texts_add(e.x, e.y - 22, 'КРИТ', (255, 240, 150), 0.5, 14)
                if b.mix:
                    self.color_mech.consume_mix()
                if b.is_refracted and b.ricochet(self, e):
                    continue
                if b.is_piercing:
                    b.hit_enemies.append(e.id)
                    continue
                if b.pierce_left > 0:
                    b.pierce_left -= 1
                    b.hit_enemies.append(e.id)
                    if len(b.hit_enemies) >= 2 and e.kind == 'dummy':
                        self.color_mech.trial_event('pierce2')
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
                if self.color_mech.try_absorb(b):
                    continue
                if self.chromatic_buffer.is_in_window(self.game_time):
                    self.perfect_refraction(b)
                    self.color_mech.trial_event('refraction')
                    continue
                if p.phase_t > 0:
                    keep_e.append(b)
                    continue
                if p.can_be_damaged(self):
                    self.on_refraction_failed()
                if self.is_training and not p.dash_invuln:
                    self.color_mech.trial_event('hit')
                if b.damage > 0:
                    p.take_damage(b.damage, self, b.x, b.y, b.source)
                continue
            keep_e.append(b)
        self.enemy_bullets = keep_e
        # 3. Контакт с врагами
        for e in sh.query(p.x, p.y, p.radius + 60):
            if not e.alive or not circle_collision(e.x, e.y, e.radius, p.x, p.y, p.radius):
                continue
            if e.spawn_t > 0 or e.kind in ('dummy', 'turret') or p.phase_t > 0:
                continue
            if isinstance(e, KamikazeEnemy):
                if not e.exploded and not self.color_mech.touch_parry(e):
                    e.explode(self)
                continue
            if isinstance(e, BossEnemy):
                dmg = 25 * e.damage_mult
            elif e.contact_damage > 0:
                dmg = e.contact_damage * e.damage_mult
            elif isinstance(e, ChaserEnemy):
                dmg = CFG.CHASER_DAMAGE * e.damage_mult
            else:
                dmg = 10 * e.damage_mult if getattr(e, 'boss_like', False) else 0
            if dmg <= 0 or not p.can_be_damaged(self):
                continue
            if self.color_mech.touch_parry(e):
                continue
            if p.take_damage(dmg, self, e.x, e.y, e.name):
                e.retreat_t = 0.7
                if 'vampire' in e.elite:
                    e.hp = min(e.max_hp, e.hp + e.max_hp * 0.25)
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
            cm = self.color_mech
            if cm.slowmo_t > 0:  # замедление на последнем убийстве волны
                cm.slowmo_t -= dt
                dt *= 0.35
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

    # ------------------------------------------------------------------ рендер
    def render_scale_for(self, ww: int, wh: int) -> float:
        """Масштаб рендера: «Чёткая» — родное разрешение окна, «Сбалансированная» — не выше 1.5×,
        «Классическая» — 720p с растяжением (как до 0.7.0)."""
        fit = min(ww / CFG.SCREEN_WIDTH, wh / CFG.SCREEN_HEIGHT)
        q = self.settings.get('render_quality', 'native')
        if q == 'classic' or self.headless:
            return 1.0
        if q == 'balanced':
            return max(0.5, min(fit, 1.5))
        return max(0.5, min(fit, 4.0))

    def ensure_render_scale(self) -> None:
        ww, wh = self.window.get_size()
        target = round(self.render_scale_for(ww, wh), 3)
        cur = self.render_surface.s if isinstance(self.render_surface, HiSurface) else 1.0
        if abs(target - cur) > 1e-3 or abs(get_scale() - target) > 1e-3:
            set_scale(target)
            clear_render_caches()
            self.render_surface = HiSurface((CFG.SCREEN_WIDTH, CFG.SCREEN_HEIGHT), 0, target)
            self._dark_surf = None
            try:
                from . import ui
                ui.clear_ui_caches()
            except (ImportError, AttributeError):
                pass

    def draw(self) -> None:
        self.ensure_render_scale()
        surf = self.render_surface
        top = self.ui.top()
        if self.in_run or (top is not None and getattr(top, 'show_world', False)):
            from .ui import draw_world
            draw_world(self, surf)
            if self.in_run:
                from .ui import draw_minimap, draw_post_fx
                if self.settings.get('minimap', False):
                    draw_minimap(self, surf)
                if self.settings.get('post_fx', True):
                    draw_post_fx(self, surf)
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
        ox, oy = self.screen_shake.offset_x, self.screen_shake.offset_y
        tw, th = int(sw * scale), int(sh * scale)
        self.view_scale, self.view_offset = scale, ((ww - tw) // 2, (wh - th) // 2)
        src = self.render_surface
        pw, ph = pygame.Surface.get_size(src)
        pos = (self.view_offset[0] + int(ox * scale), self.view_offset[1] + int(oy * scale))
        if abs(pw - tw) <= 1 and abs(ph - th) <= 1:
            # Кадр уже в физическом разрешении — выводим 1:1, без размытия
            pygame.Surface.blit(self.window, src, pos)
        else:
            if self.settings.get('render_quality', 'native') == 'classic' and scale >= 2 and abs(scale - round(scale)) < 0.01:
                scaled = pygame.transform.scale(src, (tw, th))  # целый масштаб — чёткие пиксели
            else:
                scaled = pygame.transform.smoothscale(src, (tw, th))
            pygame.Surface.blit(self.window, scaled, pos)
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
            cap = int(self.settings.get('fps_cap', CFG.TARGET_FPS) or 0)
            dt = self.clock.tick(cap if cap > 0 else 0) / 1000.0
            self.step(dt)
            if self.running:
                self.draw()
        pygame.quit()
        sys.exit(0)

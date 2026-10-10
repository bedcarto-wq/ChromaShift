"""Звук: загрузка WAV-исходников, ретро-синтез как запасной вариант, ритм и музыка."""
import math
import os
from array import array
from typing import Any, Dict, List, Optional, Set

import pygame

from .config import CFG, BASE_DIR, logger, resource_path

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

SOUND_PACKS = {'studio': 'Студийный (WAV-файлы)', 'retro': 'Ретро (синтез)'}
USER_SOUND_DIR = os.path.join(BASE_DIR, 'assets', 'sounds')


def sound_dirs() -> List[str]:
    """Пользовательская папка важнее встроенной: можно подменить любой звук своим."""
    dirs = [USER_SOUND_DIR]
    bundled = resource_path('assets', 'sounds')
    if os.path.abspath(bundled) != os.path.abspath(USER_SOUND_DIR):
        dirs.append(bundled)
    return dirs


class SoundManager:
    """Звуки из файлов (assets/sounds/*.wav) с fallback на процедурный синтез."""

    def __init__(self, pack: str = 'studio', volume: float = 0.8):
        self.enabled = False
        self.sounds: Dict[str, Any] = {}
        self._failed_sounds: Set[str] = set()
        self.channels = 2
        self.pack = pack
        self.volume = volume
        self.loaded_from_files = 0
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            init_info = pygame.mixer.get_init()
            if init_info:
                self.channels = init_info[2]
            pygame.mixer.set_num_channels(24)
            self.enabled = True
        except Exception as e:  # микшер может отсутствовать (нет аудиоустройства)
            logger.warning(f"Sound init failed: {e}")
            self.enabled = False
        if self.enabled:
            self.load_pack(pack)

    # --- Загрузка ---
    def load_pack(self, pack: str) -> None:
        self.pack = pack if pack in SOUND_PACKS else 'studio'
        self.sounds.clear()
        self._failed_sounds.clear()
        self.loaded_from_files = 0
        if not self.enabled:
            return
        self._generate_sounds()  # ретро-набор всегда есть как основа
        if self.pack == 'studio':
            self._ensure_assets()
            self._load_files()

    def _ensure_assets(self) -> None:
        """При первом запуске из исходников создаёт WAV-файлы звукового дизайна."""
        if any(os.path.isdir(d) and any(f.endswith('.wav') for f in os.listdir(d)) for d in sound_dirs()):
            return
        try:
            from .sound_design import generate_all
            generate_all(USER_SOUND_DIR)
        except Exception as e:  # нет прав на запись/NumPy — останется ретро-синтез
            logger.warning(f"Sound asset generation skipped: {e}")

    def _load_files(self) -> None:
        for folder in reversed(sound_dirs()):
            if not os.path.isdir(folder):
                continue
            for fname in os.listdir(folder):
                name, ext = os.path.splitext(fname)
                if ext.lower() not in ('.wav', '.ogg'):
                    continue
                try:
                    self.sounds[name] = pygame.mixer.Sound(os.path.join(folder, fname))
                    self.loaded_from_files += 1
                except pygame.error as e:
                    logger.warning(f"Sound load failed '{fname}': {e}")

    def _make_sound(self, wave_16: Any) -> Any:
        if self.channels == 1:
            return pygame.sndarray.make_sound(wave_16.copy())
        frames = np.repeat(wave_16[:, None], self.channels, axis=1)
        return pygame.sndarray.make_sound(np.ascontiguousarray(frames))

    def _generate_sounds(self) -> None:
        s = self._synth
        self.sounds.update({
            'shoot_red': s(1200, 400, 60, 'sine', 0.25), 'shoot_blue': s(200, 80, 150, 'sine', 0.2),
            'shoot_green': s(800, 1200, 100, 'sine', 0.2), 'refraction': s(2000, 500, 80, 'sine', 0.35),
            'hit': s(150, 50, 200, 'sine', 0.3), 'death': s(300, 50, 400, 'saw', 0.4),
            'enemy_death': s(500, 100, 120, 'sine', 0.2),
            'pickup': self._synth_arpeggio([262, 330, 392], 60, 0.2),
            'wave': s(100, 400, 300, 'sine', 0.25), 'refraction_perfect': s(2500, 800, 100, 'sine', 0.4),
            'combo': s(600, 1200, 100, 'sine', 0.25), 'dash': s(400, 800, 80, 'sine', 0.3),
            'mode_red': s(600, 800, 50, 'sine', 0.2), 'mode_blue': s(300, 200, 80, 'sine', 0.2),
            'mode_green': s(500, 700, 60, 'sine', 0.2), 'beat_kill': s(800, 1200, 80, 'sine', 0.3),
            'error': s(150, 80, 150, 'square', 0.3), 'bass_note': s(80, 80, 200, 'sine', 0.3),
            'percussion_hit': s(2000, 1000, 50, 'noise', 0.2),
            'shield': s(900, 1800, 120, 'sine', 0.25), 'revive': self._synth_arpeggio([392, 523, 659, 784], 70, 0.25),
            'boss_phase': s(70, 50, 500, 'saw', 0.35), 'telegraph': s(1200, 1200, 40, 'sine', 0.12),
            'wave_clear': self._synth_arpeggio([523, 784, 1046], 70, 0.22),
            'artifact': self._synth_arpeggio([440, 554, 659, 880], 70, 0.22),
            'achievement': self._synth_arpeggio([784, 988, 1175], 80, 0.22),
            'ui_move': s(900, 900, 25, 'sine', 0.1), 'ui_select': s(660, 990, 60, 'sine', 0.15),
        })
        for name, f in (('melody_c', 262), ('melody_d', 294), ('melody_e', 330), ('melody_g', 392),
                        ('melody_a', 440), ('melody_eb', 311), ('melody_f', 349), ('melody_bb', 466)):
            self.sounds[name] = s(f, f, 150, 'sine', 0.25)

    def _synth(self, freq_start: float, freq_end: float, duration_ms: int,
               wave_type: str, volume: float) -> Optional[Any]:
        if not self.enabled:
            return None
        
        sample_rate = 44100
        n_samples = int(sample_rate * duration_ms / 1000)
        
        try:
            if NUMPY_AVAILABLE:
                t = np.linspace(0, duration_ms / 1000, n_samples, False)
                freq = np.linspace(freq_start, freq_end, n_samples)
                
                if wave_type == 'sine':
                    wave = np.sin(2 * np.pi * freq * t)
                elif wave_type == 'square':
                    wave = np.sign(np.sin(2 * np.pi * freq * t))
                elif wave_type == 'saw':
                    wave = 2 * (freq * t - np.floor(freq * t + 0.5))
                elif wave_type == 'noise':
                    wave = np.random.uniform(-1, 1, n_samples)
                else:
                    wave = np.sin(2 * np.pi * freq * t)
                
                attack = int(n_samples * 0.04)
                release = int(n_samples * 0.25)
                envelope = np.ones(n_samples)
                if attack > 0:
                    envelope[:attack] = np.linspace(0, 1, attack)
                if release > 0:
                    envelope[-release:] = np.linspace(1, 0, release)
                
                wave = wave * envelope * volume
                wave_16 = np.int16(wave * 32767)
                return self._make_sound(wave_16)
            else:
                # Fallback без NumPy: 16-битные знаковые сэмплы.
                # bytes() не принимает отрицательные значения, поэтому array('h').
                samples = array('h')
                attack_samples = int(n_samples * 0.04)
                release_start = int(n_samples * 0.75)
                
                for i in range(n_samples):
                    t = i / sample_rate
                    progress = i / n_samples
                    freq = freq_start + (freq_end - freq_start) * progress
                    value = math.sin(2 * math.pi * freq * t)
                    
                    if i < attack_samples:
                        env = i / attack_samples
                    elif i > release_start:
                        env = (n_samples - i) / (n_samples - release_start)
                    else:
                        env = 1.0
                    
                    value *= env * volume
                    val_int = int(value * 16384)
                    samples.extend([val_int] * self.channels)
                
                return pygame.mixer.Sound(buffer=samples.tobytes())
        except Exception as e:
            logger.warning(f"Sound synth failed: {e}")
            return None
    
    def _synth_arpeggio(self, freqs: List[float], note_ms: int, volume: float) -> Optional[Any]:
        if not self.enabled:
            return None
        
        sample_rate = 44100
        total_samples = int(sample_rate * note_ms / 1000 * len(freqs))
        
        try:
            if NUMPY_AVAILABLE:
                wave = np.zeros(total_samples)
                for i, freq in enumerate(freqs):
                    start = int(i * sample_rate * note_ms / 1000)
                    end = int((i + 1) * sample_rate * note_ms / 1000)
                    if end > total_samples:
                        end = total_samples
                    length = end - start
                    t = np.linspace(0, note_ms / 1000, length, False)
                    note = np.sin(2 * np.pi * freq * t)
                    release = int(length * 0.4)
                    env = np.ones(length)
                    env[-release:] = np.linspace(1, 0, release)
                    wave[start:end] = note * env * volume
                
                wave_16 = np.int16(wave * 32767)
                return self._make_sound(wave_16)
        except Exception as e:
            logger.warning(f"Arpeggio synth failed: {e}")
        return None
    
    def play(self, name: str, volume: float = 1.0) -> None:
        if not self.enabled or name in self._failed_sounds:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.set_volume(max(0.0, min(1.0, volume * self.volume)))
            sound.play()
        except pygame.error as e:
            logger.warning(f"Sound play failed '{name}': {e}")
            self._failed_sounds.add(name)


# === BEAT SYNC TRACKER ===
class BeatSyncTracker:
    """Ритмические часы игры (идут и без звука) и проверка убийств «в такт»."""

    def __init__(self, window_add: float = 0.0):
        self.beat_window = max(0.02, CFG.BEAT_WINDOW + window_add)
        self.last_beat_time = 0.0
        self.beat_kill_count = 0
        self.beat_index = 0
        self._beat_accum = 0.0

    def update(self, dt: float, game_time: float) -> bool:
        interval = CFG.BEAT_INTERVAL
        if interval <= 0:
            return False
        self._beat_accum += dt
        on_beat = False
        while self._beat_accum >= interval:
            self._beat_accum -= interval  # без накопления дрейфа
            on_beat = True
            self.beat_index += 1
        if on_beat:
            self.last_beat_time = game_time - self._beat_accum
        return on_beat

    def on_beat(self, game_time: float) -> None:
        self.last_beat_time = game_time

    def is_on_beat(self, game_time: float) -> bool:
        since = game_time - self.last_beat_time
        return since < self.beat_window or since > (CFG.BEAT_INTERVAL - self.beat_window)


# === MUSIC SYSTEM ===
CONDUCTOR_RESTORE_EVENT = pygame.USEREVENT + 1

# Персональная музыка: лад и плотность зависят от стиля игрока
MUSIC_STYLES = {
    'assault': {'notes': ['melody_c', 'melody_eb', 'melody_f', 'melody_g', 'melody_bb'], 'perc': 0.125},
    'control': {'notes': ['melody_c', 'melody_d', 'melody_e', 'melody_g', 'melody_a'], 'perc': 0.5},
    'dancer': {'notes': ['melody_d', 'melody_e', 'melody_g', 'melody_a', 'melody_c'], 'perc': 0.25},
    'parry': {'notes': ['melody_c', 'melody_e', 'melody_g'], 'perc': 0.25},
    'balanced': {'notes': ['melody_c', 'melody_e', 'melody_g'], 'perc': 0.25},
}


class MusicSystem:
    """Процедурная музыка: бас на долях, перкуссия по интенсивности волны, ноты за убийства."""

    def __init__(self, sound_manager: SoundManager, style: str = 'balanced'):
        self.enabled = sound_manager.enabled
        self.sound_manager = sound_manager
        self.active = False
        self.kill_count = 0
        self.style = style if style in MUSIC_STYLES else 'balanced'
        self.note_sequence = MUSIC_STYLES[self.style]['notes']
        self.current_note_index = 0
        self.percussion_timer = 0.0
        self.base_percussion = MUSIC_STYLES[self.style]['perc']
        self.intensity = 0.5  # 0..1, задаётся директором волн

    @property
    def percussion_interval(self) -> float:
        # Плотнее при высокой интенсивности (фазы волны)
        return self.base_percussion * (1.0 if self.intensity < 0.66 else 0.5)

    def start(self) -> None:
        if self.enabled:
            self.active = True

    def stop(self) -> None:
        self.active = False
        pygame.time.set_timer(CONDUCTOR_RESTORE_EVENT, 0)

    def on_kill(self, mode: str) -> None:
        if not self.active or not self.enabled:
            return
        self.kill_count += 1
        self.sound_manager.play(self.note_sequence[self.current_note_index], 0.4)
        self.current_note_index = (self.current_note_index + 1) % len(self.note_sequence)

    def on_beat(self) -> None:
        if self.active and self.enabled:
            self.sound_manager.play('bass_note', 0.3 + 0.15 * self.intensity)

    def update(self, dt: float) -> None:
        if not self.active or not self.enabled:
            return
        self.percussion_timer += dt
        while self.percussion_timer >= self.percussion_interval:
            self.percussion_timer -= self.percussion_interval
            self.sound_manager.play('percussion_hit', 0.15 + 0.1 * self.intensity)

    def conductor_damage(self) -> None:
        if not self.enabled:
            return
        self.active = False
        pygame.time.set_timer(CONDUCTOR_RESTORE_EVENT, 2000, 1)

    def conductor_restore(self) -> None:
        if self.enabled:
            self.active = True

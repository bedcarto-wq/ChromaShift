"""Офлайн-дизайн звуков ChromaShift → WAV-файлы (assets/sounds/*.wav).

Это «исходники» звуков: многослойный синтез (несколько осцилляторов, шум,
фильтры, огибающие ADSR, хорус, короткая реверберация), заметно богаче
старой процедурной генерации в реальном времени. Любой файл можно заменить
своим WAV с тем же именем — игра загрузит его вместо сгенерированного.

Запуск вручную:  python -m cshift.sound_design [папка]
"""
import os
import sys
import wave
from typing import Callable, Dict

try:
    import numpy as np
except ImportError:  # без NumPy генерация недоступна, игра использует ретро-синтез
    np = None

SR = 44100


def _t(dur: float):
    return np.arange(int(SR * dur)) / SR


def _env(n: int, a: float, d: float, s: float, r: float):
    """ADSR-огибающая в долях длительности."""
    env = np.full(n, s, dtype=np.float64)
    ia, idd, ir = int(n * a), int(n * d), int(n * r)
    if ia > 0:
        env[:ia] = np.linspace(0, 1, ia)
    if idd > 0:
        env[ia:ia + idd] = np.linspace(1, s, len(env[ia:ia + idd]))
    if ir > 0:
        env[n - ir:] = np.linspace(s, 0, ir)
    return env


def _sweep(f0: float, f1: float, dur: float, shape: str = 'sine', curve: float = 1.0):
    t = _t(dur)
    k = (t / dur) ** curve
    freq = f0 + (f1 - f0) * k
    phase = 2 * np.pi * np.cumsum(freq) / SR
    if shape == 'square':
        return np.tanh(np.sin(phase) * 4)
    if shape == 'saw':
        return 2 * ((phase / (2 * np.pi)) % 1.0) - 1
    if shape == 'tri':
        return 2 * np.abs(2 * ((phase / (2 * np.pi)) % 1.0) - 1) - 1
    return np.sin(phase)


def _noise(dur: float, seed: int = 0):
    return np.random.default_rng(seed).uniform(-1, 1, int(SR * dur))


def _lowpass(x, cutoff: float):
    """Однополюсный НЧ-фильтр (векторизован через рекурсию по блокам не нужен: звуки короткие)."""
    a = float(np.exp(-2 * np.pi * cutoff / SR))
    y = np.empty_like(x)
    acc = 0.0
    b = 1.0 - a
    for i, v in enumerate(x.tolist()):
        acc = b * v + a * acc
        y[i] = acc
    return y


def _highpass(x, cutoff: float):
    return x - _lowpass(x, cutoff)


def _chorus(x, depth_ms: float = 6.0, rate: float = 0.8, mix: float = 0.35):
    n = len(x)
    t = np.arange(n) / SR
    delay = (depth_ms / 1000 * SR) * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t))
    idx = np.clip(np.arange(n) - delay, 0, n - 1).astype(int)
    return x * (1 - mix) + x[idx] * mix


def _reverb(x, decay: float = 0.35, taps=(0.023, 0.041, 0.067, 0.089), tail: float = 0.25):
    out = np.concatenate([x, np.zeros(int(SR * tail))])
    for i, tap in enumerate(taps):
        d = int(SR * tap)
        out[d:d + len(x)] += x * (decay ** (i + 1))
    return out


def _mix(*parts):
    out = np.zeros(max(len(p) for p in parts))
    for p in parts:
        out[:len(p)] += p
    return out


def _norm(x, peak: float = 0.9):
    m = float(np.max(np.abs(x))) or 1.0
    return x / m * peak


def _e(d: float, a=0.0, dd=0.2, s=0.4, r=0.6):
    return _env(int(SR * d), a, dd, s, r)


# === Рецепты звуков ===
def shoot_red():
    d = 0.09
    body = _sweep(1400, 380, d, 'saw', 0.6) * _e(d, 0.01, 0.2, 0.4, 0.6)
    click = _highpass(_noise(0.02, 1), 3000) * _e(0.02, 0, 0.1, 0.3, 0.8)
    return _norm(_mix(_lowpass(body, 5000) * 0.8, click * 0.4), 0.55)


def shoot_blue():
    d = 0.18
    sub = _sweep(220, 70, d, 'sine', 0.5) * _e(d, 0.01, 0.3, 0.5, 0.6)
    thump = _lowpass(_noise(0.06, 2), 600) * _e(0.06, 0, 0.2, 0.2, 0.7)
    return _norm(_reverb(_mix(sub, thump * 0.6), 0.25), 0.6)


def shoot_green():
    d = 0.12
    x = (_sweep(700, 1300, d, 'tri', 0.8) + _sweep(705, 1310, d, 'sine', 0.8)) * 0.5 * _e(d, 0.05, 0.3, 0.5, 0.5)
    return _norm(_chorus(x), 0.5)


def refraction():
    d = 0.12
    x = _mix(_sweep(2200, 600, d, 'sine', 0.5), _sweep(3300, 900, d, 'tri', 0.5) * 0.4) * _e(d)
    return _norm(_reverb(x, 0.4), 0.7)


def refraction_perfect():
    d = 0.35
    bell = _mix(*[_sweep(f, f * 0.98, d, 'sine') * g for f, g in ((1320, 1), (1980, 0.5), (2640, 0.3), (3960, 0.15))])
    zap = _sweep(3000, 800, 0.08, 'saw', 0.4) * _e(0.08, 0, 0.2, 0.3, 0.7) * 0.3
    return _norm(_reverb(_mix(bell * _e(d, 0, 0.15, 0.35, 0.8), zap), 0.45, tail=0.4), 0.8)


def hit():
    d = 0.25
    x = _sweep(180, 45, d, 'sine', 0.4) * _e(d, 0, 0.3, 0.4, 0.6)
    crunch = _lowpass(_noise(0.12, 3), 1800) * _e(0.12, 0, 0.2, 0.3, 0.7)
    return _norm(_mix(x, crunch * 0.7), 0.8)


def death():
    d = 0.9
    x = _sweep(320, 40, d, 'saw', 0.6) * _e(d, 0, 0.2, 0.6, 0.6)
    rumble = _lowpass(_noise(d, 4), 400) * _e(d, 0, 0.1, 0.7, 0.8)
    return _norm(_reverb(_mix(_lowpass(x, 2000), rumble), 0.5, tail=0.5), 0.85)


def enemy_death():
    d = 0.16
    x = _sweep(600, 110, d, 'square', 0.5) * _e(d, 0, 0.2, 0.3, 0.6)
    pop = _highpass(_noise(0.05, 5), 1500) * _e(0.05, 0, 0.2, 0.2, 0.7)
    return _norm(_mix(_lowpass(x, 3500) * 0.7, pop * 0.4), 0.5)


def _arp(freqs, note: float, shape: str = 'tri', rev: float = 0.35):
    parts = []
    for i, f in enumerate(freqs):
        n = _sweep(f, f, note, shape) * _e(note, 0.02, 0.2, 0.5, 0.5)
        parts.append(np.concatenate([np.zeros(int(SR * note * i)), n]))
    return _norm(_reverb(_mix(*parts), rev), 0.6)


def pickup():
    return _arp([523, 659, 784, 1046], 0.06)


def wave_sound():
    d = 0.45
    x = _mix(_sweep(110, 440, d, 'saw', 1.5), _sweep(111, 445, d, 'saw', 1.5))
    return _norm(_reverb(_lowpass(x, 2500) * _e(d, 0.2, 0.3, 0.6, 0.4), 0.4), 0.55)


def combo():
    return _arp([660, 880, 1320], 0.05, 'sine')


def dash():
    d = 0.14
    whoosh = _lowpass(_highpass(_noise(d, 6), 400), 4000) * _e(d, 0.1, 0.3, 0.5, 0.5)
    tone = _sweep(400, 900, d, 'sine', 0.5) * _e(d, 0, 0.3, 0.3, 0.6) * 0.4
    return _norm(_mix(whoosh, tone), 0.55)


def mode_red():
    return _norm(_sweep(600, 820, 0.06, 'saw', 0.5) * _e(0.06, 0, 0.3, 0.4, 0.5), 0.4)


def mode_blue():
    return _norm(_sweep(320, 200, 0.09, 'sine', 0.5) * _e(0.09, 0, 0.3, 0.4, 0.5), 0.45)


def mode_green():
    return _norm(_chorus(_sweep(500, 720, 0.07, 'tri') * _e(0.07, 0.05, 0.3, 0.4, 0.5)), 0.4)


def beat_kill():
    return _arp([988, 1319], 0.05, 'sine', 0.3)


def error():
    return _norm(_sweep(160, 90, 0.16, 'square') * _e(0.16, 0, 0.2, 0.5, 0.4), 0.4)


def bass_note():
    d = 0.22
    x = _sweep(82, 80, d, 'sine') + 0.3 * _sweep(164, 160, d, 'tri')
    return _norm(_lowpass(x, 900) * _e(d, 0.01, 0.3, 0.4, 0.6), 0.6)


def percussion_hit():
    return _norm(_highpass(_noise(0.05, 7), 5000) * _e(0.05, 0, 0.2, 0.1, 0.8), 0.35)


def _note(f: float):
    def make():
        d = 0.22
        x = _mix(_sweep(f, f, d, 'tri'), _sweep(f * 2, f * 2, d, 'sine') * 0.25) * _e(d, 0.02, 0.2, 0.5, 0.6)
        return _norm(_reverb(_chorus(x), 0.3), 0.45)
    return make


def shield():
    return _norm(_reverb(_sweep(900, 1800, 0.15, 'sine') * _e(0.15, 0, 0.2, 0.5, 0.6), 0.4), 0.5)


def revive():
    return _arp([392, 523, 659, 784, 1046], 0.08, 'sine', 0.5)


def boss_phase():
    d = 0.8
    x = _mix(_sweep(60, 55, d, 'saw'), _sweep(90, 82, d, 'saw') * 0.6)
    return _norm(_reverb(_lowpass(x, 700) * _e(d, 0.05, 0.2, 0.7, 0.5), 0.5, tail=0.4), 0.8)


def telegraph():
    return _norm(_sweep(1200, 1200, 0.05, 'sine') * _e(0.05, 0, 0.3, 0.3, 0.6), 0.25)


def wave_clear():
    return _arp([523, 784, 1046, 1568], 0.07, 'tri', 0.45)


def artifact():
    return _arp([440, 554, 659, 880, 1108], 0.07, 'sine', 0.55)


def achievement():
    return _arp([784, 988, 1175, 1568], 0.08, 'tri', 0.5)


def ui_move():
    return _norm(_sweep(900, 900, 0.03, 'sine') * _e(0.03, 0, 0.3, 0.2, 0.6), 0.2)


def ui_select():
    return _arp([660, 990], 0.04, 'sine', 0.2)


RECIPES: Dict[str, Callable] = {
    'shoot_red': shoot_red, 'shoot_blue': shoot_blue, 'shoot_green': shoot_green,
    'refraction': refraction, 'refraction_perfect': refraction_perfect, 'hit': hit,
    'death': death, 'enemy_death': enemy_death, 'pickup': pickup, 'wave': wave_sound,
    'combo': combo, 'dash': dash, 'mode_red': mode_red, 'mode_blue': mode_blue,
    'mode_green': mode_green, 'beat_kill': beat_kill, 'error': error,
    'bass_note': bass_note, 'percussion_hit': percussion_hit,
    'shield': shield, 'revive': revive, 'boss_phase': boss_phase, 'telegraph': telegraph,
    'wave_clear': wave_clear, 'artifact': artifact, 'achievement': achievement,
    'ui_move': ui_move, 'ui_select': ui_select,
}
# Мелодия: ноты для мажорной и минорной пентатоники (персональная музыка)
NOTE_FREQS = {'melody_c': 262, 'melody_d': 294, 'melody_e': 330, 'melody_g': 392,
              'melody_a': 440, 'melody_eb': 311, 'melody_f': 349, 'melody_bb': 466}
for _name, _f in NOTE_FREQS.items():
    RECIPES[_name] = _note(_f)


def write_wav(path: str, data) -> None:
    pcm = (np.clip(data, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.column_stack([pcm, pcm]).ravel().tobytes())


def generate_all(folder: str, overwrite: bool = False) -> int:
    """Генерирует недостающие WAV. Возвращает число созданных файлов."""
    if np is None:
        return 0
    os.makedirs(folder, exist_ok=True)
    made = 0
    for name, recipe in RECIPES.items():
        path = os.path.join(folder, f"{name}.wav")
        if os.path.exists(path) and not overwrite:
            continue
        tmp = path + '.tmp'
        write_wav(tmp, recipe())
        os.replace(tmp, path)
        made += 1
    return made


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'sounds')
    print(f"Создано файлов: {generate_all(target, overwrite=True)} -> {target}")

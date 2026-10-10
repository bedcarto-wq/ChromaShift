# ChromaShift

Top-down twin-stick / rhythm-action шутер на Python + Pygame, где **каждый цвет меняет физику** движения: RED — импульс, BLUE — якорь, GREEN — текучесть. Смена цвета за мгновение до попадания пули отражает её (Преломление).

Текущая версия — **0.6.5** (см. `CHANGELOG.md`).

## Запуск
**Windows:** скачайте `ChromaShift-<версия>-windows.zip` со страницы Releases и запустите `ChromaShift.exe`.

**Из исходников:**
```bash
cd chromashift
pip install pygame numpy   # numpy нужен для студийных звуков, без него — ретро-синтез
python main.py
```

## Управление (по умолчанию, меняется в настройках)
WASD — движение · мышь — прицел · ЛКМ — огонь · ПКМ/Пробел — рывок · 1/2/3 — RED/BLUE/GREEN · Q/E и колесо — цикл цвета · Shift (удерж.) — радиальное меню · Esc — пауза · F11 — полный экран · F3 — FPS.
Геймпад: левый стик — движение, правый стик/RT — прицел и огонь, A — рывок, X/B/Y — цвета, LB/RB — цикл, Start — пауза.

## Структура
- `chromashift/main.py` — точка входа; `chromashift/cshift/` — код игры.
- `chromashift/saves/` — профили (`profile_N.json` + бэкапы) и `settings.json`. Сохранение v6 переносится автоматически.
- `chromashift/assets/sounds/` — WAV-звуки (создаются при первом запуске; можно заменить своими файлами с теми же именами).
- `chromashift/legacy/` — архив `67.py` (v6.1) и `Play.py`.
- `chromashift/chromashift_config.json` (необязательно) — переопределение параметров баланса.

## Тесты
```bash
cd chromashift
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover -s tests -v
```

## Релизы
Изменение файла `VERSION` на `main` запускает GitHub Actions: тесты → сборка exe → релиз с exe и исходниками.

> Папка `chromashift/venv/` закоммичена исторически и не нужна для игры — её стоит удалить из репозитория (`git rm -r --cached chromashift/venv`).

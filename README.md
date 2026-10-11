# ChromaShift

Top-down twin-stick / rhythm-action шутер на Python + Pygame, где **каждый цвет меняет физику** движения: RED — импульс, BLUE — якорь, GREEN — текучесть, VIOLET — фаза (открывается в дереве). Смена цвета за мгновение до попадания пули отражает её (Преломление).

Текущая версия — **0.7.0** (см. `CHANGELOG.md`).

## Запуск
**Windows:** скачайте `ChromaShift-<версия>-windows.zip` со страницы Releases и запустите `ChromaShift.exe`. Для Linux/macOS в релизе могут быть экспериментальные сборки `*.tar.gz`.

**Из исходников:**
```bash
cd chromashift
pip install pygame numpy   # numpy нужен для студийных звуков, без него — ретро-синтез
python main.py
```

## Управление (по умолчанию, меняется в настройках)
WASD — движение · мышь — прицел · ЛКМ — огонь · ПКМ/Пробел — рывок · 1/2/3/4 — RED/BLUE/GREEN/VIOLET · Q/E и колесо — цикл цвета · R — навык цвета · F — способность · B — ставка на волну · F5 — быстрый рестарт · Shift (удерж.) — радиальное меню · Esc — пауза · F11 — полный экран · F3 — FPS.
Геймпад: левый стик — движение, правый стик/RT — прицел и огонь, A — рывок, X/B/Y — цвета, LB/RB — цикл, Start — пауза.

## Структура
- `chromashift/main.py` — точка входа; `chromashift/cshift/` — код игры.
- `chromashift/saves/` — профили (`profile_N.json` + бэкапы) и `settings.json`. Сохранение v6 переносится автоматически.
- `chromashift/assets/sounds/` — WAV-звуки (создаются при первом запуске; можно заменить своими файлами с теми же именами).
- `chromashift/legacy/` — архив `67.py` (v6.1) и `Play.py`.
- `chromashift/chromashift_config.json` (необязательно) — переопределение параметров баланса.
- `chromashift/crash_*.txt` — отчёт о вылете (если игра упала); приложите его к issue.
- Код сборки дерева `CS7-…` сохраняется в `saves/build_code.txt`.

## Тесты
```bash
cd chromashift
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover -s tests -v
```

## Релизы
Изменение файла `VERSION` на `main` запускает GitHub Actions: тесты → сборка exe (и экспериментально Linux/macOS) → релиз.

Папка `chromashift/venv/` удаляется из репозитория разовым workflow `cleanup-venv.yml` и больше не коммитится (`.gitignore`).

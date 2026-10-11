"""Необязательная проверка обновлений (выключена по умолчанию, включается в настройках).

Один запрос к GitHub API в фоновом потоке, таймаут 4 с. Никаких данных о пользователе не отправляется.
"""
import json
import logging
import threading
import urllib.request
from typing import Any, Optional, Tuple

from .config import GAME_VERSION

LATEST_URL = 'https://api.github.com/repos/bedcarto-wq/ChromaShift/releases/latest'
RELEASES_PAGE = 'https://github.com/bedcarto-wq/ChromaShift/releases'
logger = logging.getLogger('ChromaShift')


def parse_version(v: str) -> Tuple[int, ...]:
    v = (v or '').strip().lstrip('vV')
    out = []
    for part in v.split('.'):
        num = ''.join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out + [0] * (3 - len(out)))[:3]


def is_newer(remote: str, local: str = GAME_VERSION) -> bool:
    return parse_version(remote) > parse_version(local)


def fetch_latest(timeout: float = 4.0) -> Optional[str]:
    req = urllib.request.Request(LATEST_URL, headers={'Accept': 'application/vnd.github+json',
                                                      'User-Agent': f'ChromaShift/{GAME_VERSION}'})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — фиксированный https-адрес
        data = json.loads(r.read().decode('utf-8'))
    return data.get('tag_name')


def start_check(game: Any) -> None:
    """Запускает фоновую проверку; результат кладётся в game.update_notice."""
    def worker() -> None:
        try:
            tag = fetch_latest()
            if tag and is_newer(tag):
                game.update_notice = f"Доступна версия {tag.lstrip('v')}: {RELEASES_PAGE}"
        except Exception as e:  # сеть недоступна — молча пропускаем
            logger.info(f"Update check skipped: {e}")
    threading.Thread(target=worker, daemon=True).start()

"""ChromaShift — точка входа. Запуск: python main.py"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    from cshift.config import BASE_DIR
    log_path = os.path.join(BASE_DIR, 'chromashift.log')
    handlers = [logging.StreamHandler()] if sys.stderr is not None else []  # в exe --windowed консоли нет
    try:
        handlers.append(logging.FileHandler(log_path, encoding='utf-8'))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=handlers)
    from cshift.game import Game
    try:
        Game().run()
    except SystemExit:
        raise
    except Exception:
        logging.getLogger('ChromaShift').exception('Критическая ошибка')
        path = write_crash_report(BASE_DIR)
        show_crash_message(path)
        raise


def write_crash_report(folder: str) -> str:
    """0.7.0: отчёт о вылете — версия, система, трассировка. Файл можно приложить к issue."""
    import datetime
    import platform
    import traceback
    try:
        from cshift.config import GAME_VERSION
    except Exception:
        GAME_VERSION = '?'
    name = 'crash_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.txt'
    path = os.path.join(folder, name)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"ChromaShift {GAME_VERSION}\n{platform.platform()}\nPython {sys.version}\n\n")
            f.write(traceback.format_exc())
        return path
    except OSError:
        return ''


def show_crash_message(path: str) -> None:
    msg = ('ChromaShift завершилась с ошибкой.\n' +
           (f'Отчёт сохранён: {path}\n' if path else '') +
           'Пришлите его разработчику: https://github.com/bedcarto-wq/ChromaShift/issues')
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, 'ChromaShift — ошибка', 0x10)
            return
        except Exception:
            pass
    if sys.stderr is not None:
        print(msg, file=sys.stderr)


if __name__ == '__main__':
    main()

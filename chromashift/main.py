"""ChromaShift — точка входа. Запуск: python main.py"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    from cshift.config import BASE_DIR
    log_path = os.path.join(BASE_DIR, 'chromashift.log')
    handlers = [logging.StreamHandler()]
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
        raise


if __name__ == '__main__':
    main()

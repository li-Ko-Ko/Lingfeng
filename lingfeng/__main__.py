"""Run the desktop application with ``python -m lingfeng``."""
from multiprocessing import freeze_support


if __name__ == '__main__':
    freeze_support()
    from lingfeng.cli import main
    raise SystemExit(main())

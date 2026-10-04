"""TurboPlay — entrypoint para o executável (GUI + fallback CLI).

Executar sem argumentos abre a janela. Flags CLI continuam disponíveis:
  TurboPlay.exe scan | apply | rollback | watch
"""
from __future__ import annotations

import sys

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def main() -> int:
    args = sys.argv[1:]
    if not args:
        try:
            from src.gui import main as gui_main
        except ImportError:  # rodando como script/onfile sem pacote
            import gui as _gui
            gui_main = _gui.main
        gui_main()
        return 0
    try:
        from src.turboplay import main as cli_main
    except ImportError:
        import turboplay as _cli
        cli_main = _cli.main
    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())

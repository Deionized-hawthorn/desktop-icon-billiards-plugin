"""Desktop Icon Billiards entry point.

One frozen executable serves two roles:

* the normal GUI application;
* ``--watchdog <journal> <session> <pid>`` launched by the GUI as an independent
  process that restores the Explorer icon layout if the GUI dies unexpectedly.

The watchdog role is dispatched before Tk is imported so the helper process
never creates a window.
"""
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == '--watchdog':
        from dib.watchdog import main as watchdog_main

        watchdog_main(sys.argv[2:])
        return
    from dib.ui import main as ui_main

    ui_main()


if __name__ == '__main__':
    main()

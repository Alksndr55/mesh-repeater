"""Process-local setup for non-interactive KiCad Python scripts.

Warnings remain visible on stderr.  This does not install fonts, suppress
diagnostics, change KiCad preferences or edit a board/schematic.

Use configure_headless() before pcbnew operations, or run:
  KiCad/bin/python.exe design/kicad_headless.py design/<script>.py [arguments]
"""
from pathlib import Path
import os
import runpy
import sys

_log_target = None


def configure_headless():
    """Select stderr instead of wx's default modal message-box log target."""
    global _log_target
    # Match the official installation's fontconfig setup, only in this process.
    font_config = Path(sys.executable).resolve().parent.parent / 'etc' / 'fonts'
    if font_config.joinpath('fonts.conf').is_file():
        os.environ.setdefault('FONTCONFIG_PATH', str(font_config))

    import wx
    if _log_target is None:
        _log_target = wx.LogStderr()
    wx.Log.SetActiveTarget(_log_target)
    return {'fontconfig_path': os.environ.get('FONTCONFIG_PATH'),
            'wx_log_target': type(_log_target).__name__,
            'font_installation': 'none', 'warning_policy': 'preserve on stderr'}


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: kicad_headless.py SCRIPT.py [arguments]')
    script = Path(sys.argv[1]).resolve()
    if not script.is_file():
        raise SystemExit(f'Script not found: {script}')
    configure_headless()
    # pcbnew initialisation may install its own target; select ours again.
    import pcbnew  # noqa: F401
    configure_headless()
    sys.argv = [str(script), *sys.argv[2:]]
    sys.path.insert(0, str(script.parent))
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    main()

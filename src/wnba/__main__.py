"""Allows `python -m wnba ...`, which the scheduled task uses via pythonw.exe."""

from wnba.cli import main

main()

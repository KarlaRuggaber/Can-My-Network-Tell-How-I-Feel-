import os
import sys

from .cli import main

# Own process group, so a hung browser close can end this run together with Playwright and
# Chromium without touching other runs in the same container (cli._kill_own_group).
try:
    os.setpgrp()
except OSError:
    pass

sys.exit(main())

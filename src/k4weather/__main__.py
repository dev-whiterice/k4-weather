"""Entry point for `python -m k4weather`."""

import sys

from .cli import main

sys.exit(main())

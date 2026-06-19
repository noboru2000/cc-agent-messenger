# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
"""cc_agent_messenger — Slack message-turn bridge (C0 loop).

Phase 3 implementation. This first increment covers the return path: the
host-side send API (Unix-socket egress chokepoint) and its CLI client, plus the
foundation modules (config, models, profile, authz, kill switch, audit). The
Slack ingress (Bolt + Socket Mode) is a later increment.

See ``docs/DETAILED_DESIGN.md`` for the contracts implemented here.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    # Single source of truth = pyproject `[project].version` (read from the
    # installed distribution's metadata). Never hard-code the version here.
    __version__ = _pkg_version("cc-agent-messenger")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+source"

__author__ = "Noboru Harada"
__email__ = "noboru@ieee.org"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2026 Noboru Harada"
PROTOCOL_VERSION = 1

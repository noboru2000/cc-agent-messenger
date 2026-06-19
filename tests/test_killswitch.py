from __future__ import annotations

import os
import tempfile
import unittest

import _helpers  # noqa: F401
from claude_messenger import killswitch


class KillSwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "sub", "KILL_SWITCH")

    def test_absent_then_engage_then_disengage(self) -> None:
        self.assertFalse(killswitch.is_engaged(self.path))
        killswitch.engage(self.path)
        self.assertTrue(killswitch.is_engaged(self.path))
        killswitch.engage(self.path)  # idempotent
        self.assertTrue(killswitch.is_engaged(self.path))
        killswitch.disengage(self.path)
        self.assertFalse(killswitch.is_engaged(self.path))
        killswitch.disengage(self.path)  # idempotent, no error


if __name__ == "__main__":
    unittest.main()

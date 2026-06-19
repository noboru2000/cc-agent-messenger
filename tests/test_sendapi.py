# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Noboru Harada
from __future__ import annotations

import json
import os
import socket
import stat
import tempfile
import threading
import unittest

import _helpers
from cc_agent_messenger import sendapi


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.ctx = _helpers.make_ctx(_helpers.make_config(self.dir))

    def test_dispatch_ping(self) -> None:
        self.assertEqual(sendapi.dispatch({"op": "ping"}, self.ctx)["status"], "alive")

    def test_dispatch_send(self) -> None:
        out = sendapi.dispatch({"op": "send", "text": "hi", "mention_owner": False}, self.ctx)
        self.assertEqual(out["status"], "posted")

    def test_dispatch_missing_text(self) -> None:
        self.assertEqual(sendapi.dispatch({"op": "send"}, self.ctx)["status"], "failed")

    def test_dispatch_unknown_op(self) -> None:
        self.assertEqual(sendapi.dispatch({"op": "nope"}, self.ctx)["status"], "failed")

    def test_handle_bad_json(self) -> None:
        out = json.loads(sendapi.handle_request_bytes(b"not json", self.ctx))
        self.assertEqual(out["status"], "failed")


class SocketRoundTripTests(unittest.TestCase):
    def test_serve_ping_round_trip(self) -> None:
        ctx = _helpers.make_ctx(_helpers.make_config(tempfile.mkdtemp()))
        stop, ready = threading.Event(), threading.Event()
        thread = threading.Thread(target=sendapi.serve, args=(ctx, stop, ready), daemon=True)
        thread.start()
        try:
            self.assertTrue(ready.wait(3))
            # socket created 0o600
            mode = stat.S_IMODE(os.stat(ctx.cfg.send_api_endpoint).st_mode)
            self.assertEqual(mode, 0o600)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(ctx.cfg.send_api_endpoint)
                client.sendall(b'{"op": "ping"}\n')
                client.shutdown(socket.SHUT_WR)
                data = client.recv(4096)
            self.assertEqual(json.loads(data.decode())["status"], "alive")
        finally:
            stop.set()
            thread.join(3)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Example-mirror tests for queuelink.link().

Each test corresponds to a specific code block in the public documentation.
If a doc example breaks, the matching test here should fail.

Doc sources:
  - README.rst  "Quick start with link()" and pattern examples
  - docs/link_guide.rst  "Getting Started", "Common Patterns", "Fan-out"

Style: focused example tests (style 2 per AGENTS.md). No parameterized
matrix — link() abstracts queue-type and start-method complexity.
"""
import os
import queue
import tempfile
import time
import unittest

from subprocess import Popen, PIPE

from tests.tests import context  # noqa: F401  — configures sys.path and logging
from queuelink import link

TIMEOUT = 10


class ReadmeExamplesTest(unittest.TestCase):
    """Mirrors the code blocks in README.rst."""

    def test_quick_start_queue_to_queue(self):
        """README: Quick start with link() — basic queue→queue."""
        import queue
        from queuelink import link

        src = queue.Queue()
        dst = queue.Queue()

        result = link(src, dst)

        src.put("hello")
        self.assertEqual("hello", dst.get(timeout=TIMEOUT))

        result.stop()

    def test_fan_out_two_queues(self):
        """README: link(src, [dst1, dst2]) — fan-out to two queues."""
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()

        result = link(src, [dst1, dst2])

        src.put("broadcast")
        self.assertEqual("broadcast", dst1.get(timeout=TIMEOUT))
        self.assertEqual("broadcast", dst2.get(timeout=TIMEOUT))

        result.stop()

    def test_subprocess_pipe_to_queue(self):
        """README: Reading from a subprocess pipe into a queue."""
        dest_q = queue.Queue()
        proc = Popen(['echo', '-n', 'hello'], stdout=PIPE, universal_newlines=True)

        result = link(proc.stdout, dest_q)

        line = dest_q.get(timeout=TIMEOUT)
        proc.wait()
        result.stop()

        self.assertEqual("hello", line)

    def test_queue_to_open_file_handle(self):
        """README: Writing from a queue to an open file handle."""
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False) as f:
            fname = f.name

        try:
            src_q = queue.Queue()

            with open(fname, "w") as f:
                result = link(src_q, f)
                src_q.put("hello\n")

                deadline = time.monotonic() + TIMEOUT
                while time.monotonic() < deadline:
                    if os.path.getsize(fname) > 0:
                        break
                    time.sleep(0.05)

                result.stop()

            with open(fname) as fh:
                content = fh.read()

            self.assertEqual("hello\n", content)
        finally:
            os.unlink(fname)


class LinkGuideExamplesTest(unittest.TestCase):
    """Mirrors the code blocks in docs/link_guide.rst."""

    def test_getting_started_queue_to_queue(self):
        """link_guide: Getting Started — basic queue→queue."""
        import queue
        from queuelink import link

        src = queue.Queue()
        dst = queue.Queue()

        result = link(src, dst)

        src.put("hello")
        self.assertEqual("hello", dst.get(timeout=TIMEOUT))

        result.stop()

    def test_subprocess_pipe_to_queue(self):
        """link_guide: Common Patterns — subprocess pipe to queue."""
        dest_q = queue.Queue()
        proc = Popen(['echo', '-n', 'hello'], stdout=PIPE, universal_newlines=True)

        result = link(proc.stdout, dest_q)

        line = dest_q.get(timeout=TIMEOUT)
        proc.wait()
        result.stop()

        self.assertEqual("hello", line)

    def test_queue_to_open_file_handle(self):
        """link_guide: Common Patterns — queue to file (open handle)."""
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False) as f:
            fname = f.name

        try:
            src_q = queue.Queue()

            with open(fname, "w") as f:
                result = link(src_q, f)
                src_q.put("line one\n")

                deadline = time.monotonic() + TIMEOUT
                while time.monotonic() < deadline:
                    if os.path.getsize(fname) > 0:
                        break
                    time.sleep(0.05)

                result.stop()

            with open(fname) as fh:
                content = fh.read()

            self.assertEqual("line one\n", content)
        finally:
            os.unlink(fname)

    def test_file_path_to_queue(self):
        """link_guide: Common Patterns — file path to queue."""
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False) as f:
            f.write("hello")
            fname = f.name

        try:
            dest_q = queue.Queue()
            result = link(fname, dest_q)

            out = dest_q.get(timeout=TIMEOUT)
            result.stop()

            self.assertEqual("hello", out)
        finally:
            os.unlink(fname)

    def test_fan_out_queue_to_two_queues(self):
        """link_guide: Fan-out — queue to two queues."""
        src = queue.Queue()
        dst1 = queue.Queue()
        dst2 = queue.Queue()

        result = link(src, [dst1, dst2])

        src.put("broadcast")
        self.assertEqual("broadcast", dst1.get(timeout=TIMEOUT))
        self.assertEqual("broadcast", dst2.get(timeout=TIMEOUT))

        result.stop()

    def test_fan_out_queue_to_queue_and_file(self):
        """link_guide: Fan-out — mixed destinations (queue + file path)."""
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False) as f:
            fname = f.name

        try:
            src = queue.Queue()
            dst_queue = queue.Queue()

            result = link(src, [dst_queue, fname])

            src.put("broadcast")

            out = dst_queue.get(timeout=TIMEOUT)
            self.assertEqual("broadcast", out)

            deadline = time.monotonic() + TIMEOUT
            while time.monotonic() < deadline:
                if os.path.getsize(fname) > 0:
                    break
                time.sleep(0.05)

            result.stop()

            with open(fname) as fh:
                content = fh.read()

            self.assertEqual("broadcast", content)
        finally:
            os.unlink(fname)


if __name__ == "__main__":
    unittest.main(verbosity=2)

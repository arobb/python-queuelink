# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import codecs
import tempfile
import unittest

from queuelink import writeout

class QueueLinkWriteoutTestCase(unittest.TestCase):
    def test_queuelink_writeout_same_values(self):
        targetPipe = tempfile.TemporaryFile()
        targetPipeReader = codecs.getreader("utf-8")(targetPipe)

        prefix = "test> "
        inputText = "Hello! 😂"
        validationText = "{}{}".format(prefix, inputText)
        writeoutFunction = writeout(pipe=targetPipe, output_prefix=prefix)

        # Execute the function
        writeoutFunction(inputText)

        targetPipe.seek(0)
        outputText = targetPipeReader.read()

        self.assertEqual(validationText,
                         outputText,
                         "writeOut is not providing identical inputs/outputs: In '{}', Out '{}'".format(validationText, outputText))

        targetPipe.close()


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkWriteoutTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)

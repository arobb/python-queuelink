# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import math
import pickle
import unittest

from pickle import PickleError, UnpicklingError
from kitchen.text.converters import to_bytes
from queuelink.contentwrapper import ContentWrapper
from queuelink.contentwrapper import TYPES

'''
'''
class QueueLinkContentWrapperTestCase(unittest.TestCase):
    def setUp(self):
        def ofBytesLength(subject, length):
            """
            Calculates the length of a string in bytes, then generates a longer string that comes in at
            or under "length"
            """
            subjectByteCount = len(to_bytes(subject))

            # If the length is less than the byte count of the subject (say length 2 but the byte count is 4)
            # return the subject unmodified
            if length < subjectByteCount:
                return subject

            subjectArray = [subject] * int(math.floor(int(length) / subjectByteCount))
            return "".join(subjectArray)

        self.contentUnderThreshold = ofBytesLength("😂", (ContentWrapper.THRESHOLD - 1))
        self.contentOverThreshold = ofBytesLength("😂", ContentWrapper.THRESHOLD)
        self.content1m   = ofBytesLength("😂", 2**20)  #  1,048,576
        self.content8m   = ofBytesLength("😂", 2**23)  #  8,388,608
        self.content16m  = ofBytesLength("😂", 2**24)  # 16,777,216

    def test_queuelink_contentwrapper_explicit_file(self):
        content = self.contentUnderThreshold
        cw = ContentWrapper(content, type=TYPES.FILE)
        expectedType = TYPES.FILE
        actualType = cw.type

        self.assertEqual(expectedType,
                         actualType,
                         "ContentWrapper type isn't what is expected: expected {}, actual {}"
                         .format(expectedType, actualType))

    def test_queuelink_contentwrapper_value_under_threshold(self):
        content = self.contentUnderThreshold
        cw = ContentWrapper(content)

        self.assertEqual(content,
                         cw,
                         "ContentWrapper is not returning the right value")

    def test_queuelink_contentwrapper_length_under_threshold(self):
        content = self.contentUnderThreshold
        cw = ContentWrapper(content)

        self.assertEqual(len(content),
                         len(cw),
                         "ContentWrapper is not returning the right length: original {}, returned {}".format(len(content), len(cw)))

    def test_queuelink_contentwrapper_type_under_threshold(self):
        content = self.contentUnderThreshold
        cw = ContentWrapper(content)
        expectedType = "DIRECT"
        actualType = TYPES(cw.type).name

        self.assertEqual(expectedType,
                         actualType,
                         "ContentWrapper type isn't what is expected: expected {}, actual {}".format(expectedType, actualType))

    def test_queuelink_contentwrapper_double_read_under_threshold(self):
        content = self.contentUnderThreshold
        cw = ContentWrapper(content)

        read1 = cw.value
        read2 = cw.value

        self.assertEqual(content,
                         read2,
                         "ContentWrapper is not returning the right value on second read")

    def test_queuelink_contentwrapper_value_over_threshold(self):
        content = self.contentOverThreshold
        cw = ContentWrapper(content)

        self.assertEqual(content,
                         cw,
                         "ContentWrapper is not returning the right value")

    def test_queuelink_contentwrapper_length_over_threshold(self):
        content = self.contentOverThreshold
        cw = ContentWrapper(content)

        self.assertEqual(len(content),
                         len(cw),
                         "ContentWrapper is not returning the right length: original {}, returned {}".format(len(content),
                                                                                                             len(cw)))

    def test_queuelink_contentwrapper_type_over_threshold(self):
        content = self.contentOverThreshold
        cw = ContentWrapper(content)
        expectedType = "FILE"
        actualType = TYPES(cw.type).name

        self.assertEqual(expectedType,
                         actualType,
                         "ContentWrapper type isn't what is expected: expected {}, actual {}".format(expectedType, actualType))

    def test_queuelink_contentwrapper_value_empty_over_threshold(self):
        content = self.contentOverThreshold
        cw = ContentWrapper(content)

        self.assertRaises(AttributeError,
                          getattr,
                          [cw, 'value'],
                          "ContentWrapper value attribute intact")

    def test_queuelink_contentwrapper_value_empty_over_threshold_second_write(self):
        small_content = self.contentUnderThreshold
        big_content = self.contentOverThreshold
        cw = ContentWrapper(small_content)
        cw.value = big_content

        self.assertRaises(AttributeError,
                          getattr,
                          [cw, 'value'],
                          "ContentWrapper value attribute intact")

    def test_queuelink_contentwrapper_no_file_under_threshold_second_write(self):
        small_content = self.contentUnderThreshold
        big_content = self.contentOverThreshold
        cw = ContentWrapper(big_content)
        cw.value = small_content

        expectedValue = None
        actualValue = cw.location_handle

        self.assertEqual(expectedValue,
                         actualValue,
                         "ContentWrapper file intact after smaller value set")

    def test_queuelink_contentwrapper_double_read_over_threshold(self):
        content = self.contentOverThreshold
        cw = ContentWrapper(content)

        read1 = cw.value
        read2 = cw.value

        self.assertEqual(content,
                         read2,
                         "ContentWrapper is not returning the right value on second read")

    def test_queuelink_contentwrapper_value_1m(self):
        content = self.content1m
        cw = ContentWrapper(content)

        self.assertEqual(content,
                         cw,
                         "ContentWrapper is not returning the right value")

    def test_queuelink_contentwrapper_length_1m(self):
        content = self.content1m
        cw = ContentWrapper(content)

        self.assertEqual(len(content),
                         len(cw),
                         "ContentWrapper is not returning the right length: original {}, returned {}".format(len(content),
                                                                                                             len(cw)))

    def test_queuelink_contentwrapper_double_read_1m(self):
        content = self.content1m
        cw = ContentWrapper(content)

        read1 = cw.value
        read2 = cw.value

        self.assertEqual(content,
                         read2,
                         "ContentWrapper is not returning the right value on second read")

    def test_queuelink_contentwrapper_value_8m(self):
        content = self.content8m
        cw = ContentWrapper(content)

        self.assertEqual(content,
                         cw,
                         "ContentWrapper is not returning the right value")

    def test_queuelink_contentwrapper_length_8m(self):
        content = self.content8m
        cw = ContentWrapper(content)

        self.assertEqual(len(content),
                         len(cw),
                         "ContentWrapper is not returning the right length: original {}, returned {}".format(len(content),
                                                                                                             len(cw)))

    def test_queuelink_contentwrapper_double_read_8m(self):
        content = self.content8m
        cw = ContentWrapper(content)

        read1 = cw.value
        read2 = cw.value

        self.assertEqual(content,
                         read2,
                         "ContentWrapper is not returning the right value on second read")

    def test_queuelink_contentwrapper_value_16m(self):
        content = self.content16m
        cw = ContentWrapper(content)

        self.assertEqual(content,
                         cw,
                         "ContentWrapper is not returning the right value")

    def test_queuelink_contentwrapper_length_16m(self):
        content = self.content16m
        cw = ContentWrapper(content)

        self.assertEqual(len(content),
                         len(cw),
                         "ContentWrapper is not returning the right length: original {}, returned {}".format(len(content),
                                                                                                             len(cw)))

    def test_queuelink_contentwrapper_double_read_16m(self):
        content = self.content16m
        cw = ContentWrapper(content)

        read1 = cw.value
        read2 = cw.value

        self.assertEqual(content,
                         read2,
                         "ContentWrapper is not returning the right value on second read")

    def test_queuelink_contentwrapper_pickle_under_threshold(self):
        content = self.contentUnderThreshold
        cw = ContentWrapper(content)

        pickled = pickle.dumps(cw)
        unpickled = pickle.loads(pickled)

        self.assertEqual(cw,
                         unpickled,
                         "ContentWrapper not equivalent after pickling/unpickling")

    def test_queuelink_contentwrapper_pickle_over_threshold(self):
        content = self.contentOverThreshold
        cw = ContentWrapper(content)

        pickled = pickle.dumps(cw)
        unpickled = pickle.loads(pickled)

        self.assertEqual(cw,
                         unpickled,
                         "ContentWrapper not equivalent after pickling/unpickling")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(QueueLinkContentWrapperTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)

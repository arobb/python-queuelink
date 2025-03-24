# -*- coding: utf-8 -*-
"""
Representation of content for a queue where the values may exceed the native
pipe size.
"""
import math
import os
import tempfile

from codecs import getreader
from enum import Enum, auto
from io import IOBase as file
from typing import Union

from kitchen.text.converters import to_bytes
from kitchenpatch import getwriter

from .classtemplate import ClassTemplate
from .timer import Timer


def get_len(obj: any) -> int:
    """Calculate the byte length of a given object.

    Args:
        obj: The object to calculate the byte length for.

    Returns:
        The byte length of the given object.
    """
    if isinstance(obj, str):
        subject_byte_count = len(obj.encode('utf8'))
    else:
        subject_byte_count = len(to_bytes(obj))

    return subject_byte_count


def of_bytes_length(subject: str, length: int, round_func_name='floor') -> str:
    """Generate an object of the given length out of the subject.

    Calculates the length of "subject" in bytes, then generates a longer string as multiples
    of ``subject`` that comes in at or under ``length``. See next note for "at or above".

    Set ``round_func_name`` to ``ceil`` to generate a longer string that comes in at or above
    ``length``.

    Args:
        subject: The baseline object to multiply to create the output object
        length: The length to generate.
        round_func_name: The name of the function used to round the length.

    Returns:
        An extended string based on the ``subject``.
    """
    subject_byte_count = get_len(subject)

    # If the length is less than the byte count of the subject (say length 2 but the byte
    # count is 4) return the subject unmodified
    if length < subject_byte_count:
        return subject

    # Rounding function
    round_func = getattr(math, round_func_name)

    # subject_byte_count = 4
    # length = 22
    # math.floor(int(length=22) / subject_byte_count=4) = math.floor(5.5) = 5
    # joined length = 20
    subject_array = [subject] * int(round_func(int(length) / subject_byte_count))
    return "".join(subject_array)


class TYPES(Enum):
    """Enum indicating whether a wrapped item is in memory or a file"""
    DIRECT = 0
    FILE = 1


class WRAP_WHEN(Enum):  # pylint: disable=invalid-name
    """Enum for deciding when to use ContentWrapper
    Not used directly inside ContentWrapper

    AUTO: Use a ContentWrapper only when content is over ContentWrapper.THRESHOLD (or local size)
    ALWAYS: All content is wrapped
    NEVER: No content is wrapped
    """
    AUTO = auto()
    ALWAYS = auto()
    NEVER = auto()


class ContentWrapper(ClassTemplate):
    """
    Representation of content for a queue where the values may exceed the
    native pipe size.

    Store data with
        cw = ContentWrapper("My text data")
        cw.value = "Updated text data"

    Access data with
        print("My data: {cw.value}")
        print("My data: {cw}")
    """

    # Need to figure out a way to do this automatically
    THRESHOLD = 2**14  # 2**14 = 16,384

    def __getattr__(self, attr):
        """When necessary pull the 'value' from a buffer file"""
        log = object.__getattribute__(self, "_log")

        # pylint: disable=no-else-return
        # The 'else' can be hit, so it is not superfluous
        if attr == "value" \
                and object.__getattribute__(self, "storage_type") == TYPES.FILE:
            log.debug("Pulling value from buffer file")
            return self._get_value_from_file()
        else:
            log.debug("Pulling value from memory")
            return object.__getattribute__(self, attr)

    def __setattr__(self, attr, val):
        """When necessary, save the 'value' to a buffer file"""
        if attr == "value":
            # Within the threshold size limit or not forced to use a file
            if get_len(val) < self.threshold and not self._is_explicit_file():
                self._log.debug("Storing value to memory")
                object.__setattr__(self, attr, val)

                # Delete temp file if we had previously used a file
                self._delete_temp_file()

            # Larger than what a queue value can hold
            # due to pipe limits, store value in a temp file
            else:
                # Clear existing in-memory value
                if hasattr(object, 'value'):
                    del self.value

                # Set the type
                object.__setattr__(self, "storage_type", TYPES.FILE)

                # pylint: disable=consider-using-with
                # We explicitly do not want to close the tempfile automatically
                if not self.location_handle:
                    object.__setattr__(self, "location_handle",
                                       tempfile.NamedTemporaryFile(delete=False))
                handle = object.__getattribute__(self, "location_handle")
                object.__setattr__(self, "location_name", handle.name)
                writer = getwriter("utf-8")(handle)

                self._log.info("Writing value into buffer file %s",
                               handle.name)
                stopwatch = Timer()
                writer.write(val)
                writer.flush()
                lap = stopwatch.lap()
                self._log.info("Finished writing value into buffer file in "
                               "%.1f seconds", lap)

        # Not assigning to self.value
        else:
            object.__setattr__(self, attr, val)

    def __getstate__(self):
        """Being Pickled"""
        self._log.debug("Being pickled")

        # Close the buffer file if needed
        if isinstance(self.location_handle, file):
            self.location_handle.close()

        state = self.__dict__.copy()
        del state['location_handle']
        del state['_log']  # Delete the logger instance

        # Prevent __del__ from deleting the buffer file
        # Needs to come after we've created the state copy so
        # this doesn't persist after un-pickling
        self.being_serialized = True

        return state

    def __setstate__(self, state):
        """Being un-Pickled, need to restore state"""

        self.__dict__.update(state)
        self.location_handle = None

        # Reestablish the logger
        self._initialize_logging(__name__)
        self._log.debug("Being un-pickled")

        if self.location_name is not None:
            # pylint: disable=consider-using-with
            # We explicitly do not want to close the file automatically
            self.location_handle = open(self.location_name, "r+b")

    def __del__(self):
        """When used, close any open file handles on object destruction"""
        self._log.debug("Object being deleted")
        self._delete_temp_file()

    def __len__(self):
        return len(self.value)

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.value}')"

    def __str__(self):
        if isinstance(self.value, str):
            return self.value

        if isinstance(self.value, bytes):
            return self.value.decode('utf8')

        return str(self.value)

    def __bytes__(self):
        if isinstance(self.value, str):
            return self.value.encode('utf8')

        if isinstance(self.value, bytes):
            return self.value

        return bytes(self.value)

    def __eq__(self, other):
        return self.value == other

    def __init__(self, val, threshold: int = None, storage_type: TYPES = None):
        self._log = None
        self._initialize_logging(__name__)

        self.threshold = self.THRESHOLD if threshold is None else threshold

        # Set the type
        if storage_type:
            if isinstance(storage_type, TYPES):
                self.storage_type = storage_type
                self.type_explicit = True
            else:
                raise TypeError(f'Given type "{storage_type}" is not from TYPES')
        else:
            self.storage_type = TYPES.DIRECT
            self.type_explicit = False

        # Used only if this is stored in a file
        self.location_handle: file = None
        self.location_name: str = None
        self.being_serialized: bool = False

        # Store the initial value
        self.value = val

    def _create_buffer(self):
        pass

    def _is_explicit_file(self):
        if self.type_explicit and self.storage_type == TYPES.FILE:
            return True

        return False

    def _get_value_from_file(self):
        handle = object.__getattribute__(self, "location_handle")
        reader = getreader("utf-8")(handle)
        handle.seek(0)

        stopwatch = Timer()
        content = reader.read()
        lap = stopwatch.lap()
        self._log.info("Finished reading value into buffer file in %.1f "
                       "seconds", lap)

        return content

    def _delete_temp_file(self):
        """Delete the temp file if set"""
        if isinstance(self.location_handle, file):
            self._log.debug('Closing temp file')
            self.location_handle.close()

        # Delete any files on disk
        if self.location_name and not self.being_serialized:
            self._log.debug('Deleting temp file')
            os.remove(self.location_name)
            self.location_handle = None
            self.location_name = None


def conditional_wrap(content: any,
                     wrap_when: WRAP_WHEN=WRAP_WHEN.AUTO,
                     wrap_threshold: int=ContentWrapper.THRESHOLD) -> Union[any, ContentWrapper]:
    """Method to wrap content only if it meets the given conditions.

    Typically to keep values that would be stored in memory from being wrapped.

    Passes wrap_threshold as the file threshold into the ContentWrapper instance.

    Args:
        content: Object to be conditionally wrapped.
        wrap_when: Condition when the wrapping should occur.
        wrap_threshold: Size threshold over which the wrapping should occur.

    Returns:
        The wrapped content.
    """

    # Never wrap
    if wrap_when == WRAP_WHEN.NEVER:
        return content

    # Always wrap
    if wrap_when == WRAP_WHEN.ALWAYS:
        return ContentWrapper(content, threshold=wrap_threshold)

    # Wrap only over certain thresholds
    if wrap_when == WRAP_WHEN.AUTO \
            and get_len(content) > wrap_threshold:
        return ContentWrapper(content, threshold=wrap_threshold)

    return content

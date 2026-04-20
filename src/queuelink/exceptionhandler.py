# -*- coding: utf-8 -*-
"""
Exception management classes
"""
from __future__ import unicode_literals

import logging
import sys
import traceback


# pylint: disable=super-init-not-called
# User-defined exceptions don't call their super initializer


class SIGINTException(Exception):
    """Represents a ctrl-c interrupt"""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class ProcessNotStarted(Exception):
    """Raise if a publishing QueueLink hasn't been started, but a method has been
    called that depends on the target process running.
    """
    def __init__(self, value=""):
        """Arguments must be option to prevent triggering
        https://bugs.python.org/issue15440 when raised in _Command"""
        self.errno = 4
        self.value = value

    def __str__(self):
        return repr(self.value)


class HandleAlreadySet(Exception):
    """Raise if a pipe adapter has already been configured with a pipe handle"""
    def __init__(self, value=""):
        """Arguments must be option to prevent triggering
        https://bugs.python.org/issue15440 when raised in _Command"""
        self.errno = 5
        self.value = value

    def __str__(self):
        return repr(self.value)


class HandleNotSet(Exception):
    """Raise if a pipe adapter has not been configured with a pipe handle, but
    a call requires one have been set
    """
    def __init__(self, value=""):
        """Arguments must be option to prevent triggering
        https://bugs.python.org/issue15440 when raised in _Command"""
        self.errno = 6
        self.value = value

    def __str__(self):
        return repr(self.value)


def log_exception(error, message=None):
    """Log an exception with optional context message, error type/text, and traceback.

    Prefer this function over ``ExceptionHandler`` for new code.  It performs
    the same structured logging without raising or wrapping the exception, so
    callers retain full control over how (and whether) the original exception
    is propagated.

    Args:
        error (Exception): The caught exception to log.
        message (str, optional): An additional context message to log before
            the exception details.
    """
    _exc_type, _exc_obj, exc_tb = sys.exc_info()
    err_type = type(error).__name__
    error_text = str(error)

    log = logging.getLogger(__name__)
    log.addHandler(logging.NullHandler())

    if message is not None:
        log.error(message)

    template = "An exception of type {0} occurred. Error message:\n{1}"
    errmsg = template.format(err_type, error_text)
    errmsg += "\n"
    log.error(errmsg)

    errargmsg = f"{err_type} {type(error).__name__} arguments:\n{error.args:2!r}"
    errargmsg += "\n"
    log.error(errargmsg)

    tbmsg = err_type + " traceback (most recent call last):"
    log.error(tbmsg)
    log.error("".join(traceback.format_tb(exc_tb)))


class ExceptionHandler(Exception):
    """Legacy exception wrapper that also logs on construction.

    .. deprecated::
        This class inherits from ``Exception`` but its primary purpose is
        structured logging, which makes it misleading as an exception type.
        Prefer :func:`log_exception` for new code.  If you need to surface an
        error to the caller, use ``log_exception(exc, msg); raise exc`` so the
        original exception type is preserved.
    """
    def __repr__(self):
        return self.errmsg

    def __str__(self):
        return self.errmsg

    def __init__(self, error, message=None):
        self.exc_type, self.exc_obj, self.exc_tb = sys.exc_info()
        # fname = os.path.split(self.exc_tb.tb_frame.f_code.co_filename)[1]
        self.err_type = type(error).__name__
        self.error_text = str(error)

        log = logging.getLogger(__name__)
        log.addHandler(logging.NullHandler())

        if message is not None:
            log.error(message)

        template = "An exception of type {0} occurred. Error message:\n{1}"
        self.errmsg = template.format(self.err_type, self.error_text)
        self.errmsg += "\n"
        log.error(self.errmsg)

        errargmsg = f"{self.err_type} {type(error).__name__} arguments:\n{error.args:2!r}"
        errargmsg += "\n"
        log.error(errargmsg)

        tbmsg = self.err_type+" traceback (most recent call last):"
        log.error(tbmsg)
        log.error("".join(traceback.format_tb(self.exc_tb)))

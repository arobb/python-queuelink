# -*- coding: utf-8 -*-
"""Wrapper to make async writing to a pipe more reliable across processes"""
from __future__ import unicode_literals

from ._encoding import to_bytes, getwriter
from .exceptionhandler import log_exception


def writeout(pipe, output_prefix):
    """Easily write to your favorite pipe or handle with current content

    Args:
        pipe (pipe): A system pipe/file handle to write output to
        output_prefix (string): A string to prepend to each line

    Returns:
        function
    """
    # TODO Validate the pipe somehow

    def func(line):
        # Uses errors='replace' so unencodable characters produce the replacement
        # character rather than raising. The TypeError fallback handles pipes
        # that reject the encoded form.
        pipe_writer = getwriter("utf-8")(pipe)
        output = f'{output_prefix}{line}'

        try:
            pipe_writer.write(output)

        except TypeError:
            # Shenanigans with unicode
            try:
                pipe_writer.write(to_bytes(output))
            except TypeError:
                pipe.write(str(output))
            except Exception as exc:
                log_exception(exc, f'Crazy pipe writer stuff: {exc}')
                raise exc

        except ValueError as exc:
            log_exception(exc, f'writeout caught odd error: {exc}')
            raise exc

        finally:
            pipe_writer.flush()
            pipe.flush()

    return func

# -*- coding: utf-8 -*-
"""Stdlib-only encoding utilities.

Replaces the ``kitchen`` and ``kitchenpatch`` (``processrunner-kitchenpatch``)
runtime dependencies with equivalents built on Python 3 builtins.

Public surface (mirrors the old import paths used in this package):

  ``to_bytes(obj)``
      Convert any object to UTF-8 bytes, replacing unencodable characters
      (including lone surrogates) with ``?`` (``errors='replace'`` on
      encoding).  Byte strings are returned unchanged.

  ``getwriter(encoding)``
      Return a writer class whose constructor takes a binary-mode stream and
      returns an object with a ``.write()`` method that encodes text before
      writing.  Mirrors the ``codecs.getwriter()`` / kitchenpatch API:
      bytes are written through unchanged; strings are encoded with
      ``errors='replace'`` so that unencodable characters produce ``?``
      rather than raising ``UnicodeEncodeError``.
"""


def to_bytes(obj, encoding='utf-8', errors='replace'):
    """Convert an object to bytes.

    Mirrors ``kitchen.text.converters.to_bytes`` using only stdlib.

    Args:
        obj: Object to convert.  ``bytes`` instances are returned unchanged.
            ``str`` instances are encoded using ``encoding``.  Any other type
            is first converted via ``str()`` then encoded.
        encoding: Text encoding to use (default ``'utf-8'``).
        errors: Error-handling strategy (default ``'replace'``, which
            substitutes unencodable characters with ``?`` on encoding rather
            than raising).

    Returns:
        bytes
    """
    if isinstance(obj, bytes):
        return obj

    if not isinstance(obj, str):
        obj = str(obj)

    return obj.encode(encoding, errors=errors)


def getwriter(encoding):
    """Return a writer class that encodes text and writes bytes to a binary stream.

    Mirrors the ``kitchenpatch.getwriter()`` API using only stdlib:

    * Takes a binary-mode stream in the constructor.
    * ``.write()`` accepts both ``str`` (encoded to bytes) and ``bytes``
      (written through unchanged) — same as kitchenpatch's StreamWriter.
    * Uses ``errors='replace'`` so that unencodable characters produce the
      replacement character rather than raising ``UnicodeEncodeError``.
    * Exposes ``.flush()`` and ``.fileno()`` directly; all other attributes
      are delegated to the underlying stream via ``__getattr__``.

    Usage::

        writer = getwriter('utf-8')(binary_stream)
        writer.write('hello 😂')
        writer.flush()

    Args:
        encoding: Text encoding to use (e.g. ``'utf-8'``).

    Returns:
        A class whose constructor accepts a binary-mode stream and returns a
        writer that encodes text on each ``.write()`` call.
    """
    class _Writer:
        """Text-to-bytes writer wrapping a binary stream."""

        def __init__(self, stream, errors='replace'):
            self._stream = stream
            self._errors = errors

        def write(self, text):
            """Encode *text* and write the resulting bytes to the stream.

            Args:
                text: ``str`` to encode and write, or ``bytes`` to write
                    directly without re-encoding.
            """
            if isinstance(text, str):
                self._stream.write(text.encode(encoding, errors=self._errors))
            else:
                self._stream.write(text)

        def flush(self):
            """Flush the underlying stream."""
            self._stream.flush()

        def fileno(self):
            """Return the file descriptor of the underlying stream."""
            return self._stream.fileno()

        def __getattr__(self, name):
            return getattr(self._stream, name)

    return _Writer

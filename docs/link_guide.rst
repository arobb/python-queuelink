Using ``link()``
================

``link()`` is the recommended entry point for most QueueLink use cases. It
inspects the types of your source and destination and wires up the correct
combination of :class:`QueueLink`, :class:`QueueHandleAdapterReader`, and/or
:class:`QueueHandleAdapterWriter` automatically.

.. code-block:: python

    from queuelink import link

    result = link(source, destination)
    # ... use your queues ...
    result.stop()


Getting Started
---------------

The simplest case: route messages from one queue to another.

.. code-block:: python

    import queue
    from queuelink import link

    src = queue.Queue()
    dst = queue.Queue()

    result = link(src, dst)

    src.put("hello")
    print(dst.get())   # "hello"

    result.stop()

``link()`` detects whether your queues are thread-based or process-based and
creates the appropriate publisher (thread or process) automatically.


Supported Endpoint Types
------------------------

**Sources** — anything you want to read from:

* Any queue: ``queue.Queue``, ``queue.LifoQueue``, ``queue.PriorityQueue``,
  ``queue.SimpleQueue``, ``multiprocessing.Queue``, ``multiprocessing.JoinableQueue``,
  ``multiprocessing.SimpleQueue``, or a ``multiprocessing.Manager`` queue
* Open file handles with ``readline()`` (subprocess pipes, ``open()``, etc.)
* File paths (``str`` or ``os.PathLike``) — opened automatically
* ``multiprocessing.connection.Connection`` (to queue destinations only)

**Destinations** — anything you want to write to:

* Any queue (same types as above)
* Open file handles with ``write()``
* File paths (``str`` or ``os.PathLike``) — opened automatically
* A ``list`` of any of the above for fan-out


Common Patterns
---------------

Queue to queue
~~~~~~~~~~~~~~

.. code-block:: python

    import queue
    from queuelink import link

    src = queue.Queue()
    dst = queue.Queue()
    result = link(src, dst)

Subprocess pipe to queue
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import queue
    from subprocess import Popen, PIPE
    from queuelink import link

    dest_q = queue.Queue()
    proc = Popen(['myprogram'], stdout=PIPE, universal_newlines=True)

    result = link(proc.stdout, dest_q)

    line = dest_q.get()
    result.stop()

Queue to file
~~~~~~~~~~~~~

.. code-block:: python

    import queue
    from queuelink import link

    src_q = queue.Queue()

    with open("output.txt", "w") as f:
        result = link(src_q, f)
        src_q.put("line one\n")
        result.stop()

File path to queue
~~~~~~~~~~~~~~~~~~

Pass a path string directly — ``link()`` opens the file for you:

.. code-block:: python

    import queue
    from queuelink import link

    dest_q = queue.Queue()
    result = link("input.txt", dest_q)


Fan-out
-------

Pass a list as the destination to broadcast each message to multiple endpoints:

.. code-block:: python

    import queue
    from queuelink import link

    src = queue.Queue()
    dst1 = queue.Queue()
    dst2 = queue.Queue()

    result = link(src, [dst1, dst2])

    src.put("broadcast")
    print(dst1.get())   # "broadcast"
    print(dst2.get())   # "broadcast"

    result.stop()

Mixed fan-out (queues and files) is also supported:

.. code-block:: python

    result = link(src, [dst_queue, "log.txt"])

Destinations must be in a ``list``. Tuples and sets are rejected — use a list
to keep behaviour explicit.


Result Interface
----------------

``link()`` returns a result object with the following interface:

``stop()``
    Shut down all managed components in the correct order: reader first, then
    wait for internal queues to drain, then publishers, then writers.

``close()``
    Alias for ``stop()``, consistent with adapter usage patterns.

``is_alive()``
    Returns ``True`` if any managed worker thread or process is still running.

``queue_link``
    For queue-to-queue links, direct access to the underlying
    :class:`QueueLink` instance. Useful for metrics, drain checking, or
    runtime queue registration. ``None`` for adapter-only paths.

``reader``
    The :class:`QueueHandleAdapterReader` instance, if one was created.

``writers``
    List of :class:`QueueHandleAdapterWriter` instances, if any were created.


Advanced Parameters
-------------------

``start_method``
    Multiprocessing start method: ``'fork'``, ``'forkserver'``, or
    ``'spawn'``. Defaults to the system preference.

    .. code-block:: python

        result = link(src, dst, start_method='spawn')

``thread_only``
    Force threading instead of spawning separate processes, regardless of
    queue types.

    .. code-block:: python

        result = link(src, dst, thread_only=True)

``name``
    Optional name passed to created components for log identification.

    .. code-block:: python

        result = link(src, dst, name="pipeline-stage-1")

``wrap_when``
    When to wrap large messages in a :class:`ContentWrapper` for disk
    buffering (avoids pipe size limits). Only applies when a reader adapter
    is created. See :class:`WRAP_WHEN` for values.

    .. code-block:: python

        from queuelink import WRAP_WHEN
        result = link("large_input.txt", dest_q, wrap_when=WRAP_WHEN.AUTO)

``wrap_threshold``
    Byte size above which wrapping is triggered, when ``wrap_when`` is
    ``WRAP_WHEN.AUTO``.

``link_timeout``
    Queue ``get()`` timeout (seconds) for internal publishers. Default
    ``0.01``. Increase under heavy load to reduce thrashing; note that higher
    values slow response to ``stop()``.

``trusted``
    For ``Connection`` sources — if ``True``, use ``.recv()``/``.send()``;
    if ``False`` (default), use ``.recv_bytes()``.


Error Handling
--------------

``link()`` raises ``TypeError`` for unsupported or incompatible inputs:

.. code-block:: python

    import multiprocessing
    from queuelink import link

    conn_recv, conn_send = multiprocessing.Pipe()

    # TypeError: Connection as destination is not supported
    result = link(src, conn_recv)

    # TypeError: tuples/sets are not accepted — use a list
    result = link(src, (dst1, dst2))

    # TypeError: QueueLink instances cannot be passed as endpoints
    from queuelink import QueueLink
    ql = QueueLink(source=src, destination=dst)
    result = link(ql, dst2)

``ValueError`` is raised for empty or duplicate destination lists:

.. code-block:: python

    # ValueError: empty destination list
    result = link(src, [])

    # ValueError: duplicate destination object
    result = link(src, [dst, dst])


When to Use ``link()`` vs Direct Classes
-----------------------------------------

``link()`` covers the majority of use cases. Use the lower-level classes
directly when you need capabilities that ``link()`` does not expose:

Use :class:`QueueLink` directly when you need:

* Dynamic queue registration or unregistration at runtime (``read()`` /
  ``write()`` / ``unregister_queue()``)
* Access to per-queue metrics (``get_metrics()``)
* Drain checking (``is_drained()``, ``is_empty()``)
* Destructive audit (``destructive_audit()``)

Use :class:`QueueHandleAdapterReader` or :class:`QueueHandleAdapterWriter`
directly when you need:

* Custom error handling during read or write
* Non-standard content wrapping configuration

``QueueLink`` is not deprecated. ``link()`` is an additive convenience layer
on top of the same underlying classes.

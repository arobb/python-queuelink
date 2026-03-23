---------
QueueLink
---------


.. image:: https://github.com/arobb/python-queuelink/actions/workflows/ci.yaml/badge.svg
   :target: https://github.com/arobb/python-queuelink/actions/workflows/ci.yaml
   :alt: CI

.. image:: https://img.shields.io/pypi/v/queuelink.svg
   :target: https://pypi.org/project/queuelink/
   :alt: PyPI

.. image:: https://img.shields.io/pypi/pyversions/queuelink.svg
   :target: https://pypi.org/project/queuelink/
   :alt: Python versions

.. image:: https://readthedocs.org/projects/queuelink/badge/?version=latest
   :target: https://queuelink.readthedocs.io/en/latest/
   :alt: Documentation

Route messages between any combination of Python queues — fan-out, fan-in,
or many-to-many — without the boilerplate.

Why?
====
Connecting ``queue.Queue``, ``multiprocessing.Queue``, and
``multiprocessing.Manager().Queue`` by hand means writing your own publisher
loops, handling thread-vs-process selection, and dealing with edge cases like
pipe size limits and clean shutdown. QueueLink handles all of that:

* **Automatic thread/process selection** — detects whether your queues are thread-based or process-based and creates the right kind of link.
* **Fan-out and fan-in** — one source to many destinations, many sources to one destination, or any combination.
* **Handle adapters** — bridge subprocess pipes, file handles, and multiprocessing connections directly into your queue graph.
* **Large-message spill-to-disk** — transparently buffers oversized objects to disk to avoid pipe size limits.
* **Tested across fork, forkserver, and spawn** — CI runs a 25-job matrix across Linux, macOS, and Python 3.9–3.13.

Install
=======

::

    pip install queuelink


Use
===

Quick start with ``link()``
---------------------------

The ``link()`` factory function inspects your source and destination and wires everything
up automatically — no need to choose between ``QueueLink``, ``QueueHandleAdapterReader``,
or ``QueueHandleAdapterWriter`` by hand:

.. code-block:: python

    import queue
    from queuelink import link

    src = queue.Queue()
    dst = queue.Queue()

    # link() returns a result with stop(), close(), and is_alive()
    result = link(src, dst)

    src.put("hello")
    print(dst.get())   # "hello"

    result.stop()

``link()`` accepts queues, file handles, file paths, and
``multiprocessing.connection.Connection`` as source or destination. Pass a list for fan-out:

.. code-block:: python

    result = link(src, [dst1, dst2])   # fan-out to two queues

Use ``QueueLink`` directly when you need fine-grained control (registering/unregistering
queues at runtime, accessing metrics).

With ``QueueLink`` directly
---------------------------
A QueueLink is a one-way process that connects queues together. When two or more queues are linked, a sub-process is started to read from the "source" queue and write into the "destination" queue.

Circular references are not allowed.

Users create each queue from the Queue or Multiprocessing libraries. Those queues can then be added to a QueueLink instance as either the source or destination.

With standard queues
--------------------

.. code-block:: python

    from queue import Queue
    from queuelink import QueueLink

    # Source and destination queues
    source_q = Queue()
    dest_q = Queue()

    # Create the QueueLink
    queue_link = QueueLink(name="my link")

    # Connect queues to the QueueLink
    source_id = queue_link.read(q=source_q)
    dest_id = queue_link.write(q=dest_q)

    # Text to send
    text_in = "a😂" * 10

    # Add text to the source queue
    source_q.put(text_in)

    # Retrieve the text from the destination queue!
    text_out = dest_q.get()
    print(text_out)


With a process manager
----------------------

.. code-block:: python

    from multiprocessing import Manager
    from queuelink import QueueLink

    # Create the multiprocessing.Manager
    manager = Manager()

    # Source and destination queues
    source_q = manager.JoinableQueue()
    dest_q = manager.JoinableQueue()

    # Create the QueueLink
    queue_link = QueueLink(name="my link")

    # Connect queues to the QueueLink
    source_id = queue_link.read(q=source_q)
    dest_id = queue_link.write(q=dest_q)

    # Text to send
    text_in = "a😂" * 10

    # Add text to the source queue
    source_q.put(text_in)

    # Retrieve the text from the destination queue!
    text_out = dest_q.get()
    print(text_out)

Methods
=======

Primary methods
---------------------
These methods are used most common use cases.

* ``register_queue(q: UNION_SUPPORTED_QUEUES, direction: str, start_method: str=None) -> client id: str``
* ``stop``

Secondary methods
-----------------
These methods are less common.

* ``destructive_audit(direction: str)``
* ``get_queue(queue_id: [str, int])``
* ``is_alive``
* ``is_drained``
* ``is_empty(queue_id:str =None)``
* ``unregister_queue(queue_id: str, direction: str, start_method: str=None)``

Queue Compatibility
===================
QueueLink is tested against multiple native Queue implementations. When a source or destination queue is thread-based, the link will be created as a Thread instance. When all involved queues are process-based, the link will also be a Process instance.

Note that in thread-based situations throughput might be limited by the `Python GIL <https://wiki.python.org/moin/GlobalInterpreterLock>`_.

Two thread-based queues in different processes cannot be bridged directly. They would require an intermediate multiprocessing queue that can be accessed across processes.

Tested against the following queue implementations:

* SyncManager.Queue (multiprocessing.Manager)
* SyncManager.JoinableQueue (multiprocessing.Manager)
* multiprocessing.Queue
* multiprocessing.JoinableQueue
* multiprocessing.SimpleQueue
* queue.Queue
* queue.LifoQueue
* queue.PriorityQueue
* queue.SimpleQueue

Implementation
==============
QueueLink creates a new thread or process for each source queue, regardless of the number of downstream queues. The linking thread/process gets each element of the source queue and iterates over and puts to the set of destination queues.

Multiprocessing
---------------
Start Method: QueueLink is tested against fork, forkserver, and spawn start methods. It defaults to the system preference, but can be overridden by passing the preferred start method name to the class "start_method" parameter.

Linking with other channels
===========================
QueueLink includes two "adapters" to link queues with inbound and outbound connections.

Inbound Connections
-------------------
To quickly link a pipe or handle with a queue, use ``QueueHandleAdapterReader``. The Reader Adapter is tested against Multiprocessing Connections and Subprocess pipes. It calls ``flush`` and ``readline`` to consume from handles, so it should work against any object implementing those methods, with ``readline`` returning a string or byte array. For Multiprocessing Connections, the adapter injects a no-op ``flush`` method and a custom ``readline`` method.

::

    # Text to send
    text_in = "a😂" * 10

    # Destination queue
    dest_q = multiprocessing.Queue()  # Process-based

    # Subprocess, simple example sending some text to stdout
    # from subprocess import Popen, PIPE
    proc = Popen(['echo', '-n', text_in],  # -n prevents echo from adding a newline character
                 stdout=PIPE,
                 universal_newlines=True,
                 close_fds=True)

    # Connect the reader
    # from queuelink import QueueHandleAdapterReader
    read_adapter = QueueHandleAdapterReader(queue=dest_q,
                                            handle=proc.stdout)

    # Get the text from the queue
    text_out = dest_q.get()
    print(text_out)

Other Notes
===========

Tuning link_timeout
-------------------
Under heavily loaded conditions the "publisher" process/thread can thrash when trying to retrieve records from the source queue. Tuning link_timeout higher (default 0.1 seconds) can improve responsiveness. Higher values might be less responsive to stop requests and throw warnings during shutdown.
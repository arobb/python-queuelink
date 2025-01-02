---------
QueueLink
---------
The QueueLink library simplifies several queue patterns including linking queues together with one-to-many or many-to-one relationships, and supports reading and writing to text-based files.

Use
===
A QueueLink is a one-way process that connects queues together. When two or more queues are linked, a sub-process is started to read from the "source" queue and write into the "destination" queue.

Circular references are not allowed, making QueueLink a 'directed acyclic graph', or DAG.

Users create each queue from the Queue or Multiprocessing libraries. Those queues can then be added to a QueueLink instance as either the source or destination.

With standard queues
--------------------

::

    from queue import Queue
    from queuelink import QueueLink

    # Source and destination queues
    source_q = Queue()
    dest_q = Queue()

    # Create the QueueLink
    queue_link = QueueLink(name="my link")

    # Connect queues to the QueueLink
    source_id = queue_link.register_queue(queue_proxy=source_q,
                                          direction="source")
    dest_id = queue_link.register_queue(queue_proxy=dest_q,
                                        direction="destination")

    # Text to send
    text_in = "a😂" * 10

    # Add text to the source queue
    source_q.put(text_in)

    # Retrieve the text from the destination queue!
    text_out = dest_q.get()
    print(text_out)


With a process manager
----------------------

::

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
    source_id = queue_link.register_queue(queue_proxy=source_q,
                                          direction="source")
    dest_id = queue_link.register_queue(queue_proxy=dest_q,
                                        direction="destination")

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

* ``register_queue(queue_proxy, direction: str, start_method: str=None) -> client id: str``
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
=============
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
QueueLink creates a new process for each source queue, regardless of the number of downstream queues. The linking thread/process gets each element on the source queue and iterates over and puts to the set of destination queues.

Multiprocessing
---------------
Start Method: QueueLink is tested against fork, forkserver, and spawn start methods. It defaults to the system preference, but can be overridden by passing the preferred start method name to the class "start_method" parameter.

Other Notes
===========

Tuning link_timeout
-------------------
Under heavily loaded conditions the "publisher" process/thread can thrash when trying to retrieve records from the source queue. Tuning link_timeout higher (default 0.1 seconds) can improve responsiveness. Higher values might be less responsive to stop requests and throw warnings during shutdown.
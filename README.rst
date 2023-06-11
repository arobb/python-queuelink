---------
QueueLink
---------
The QueueLink library simplifies several queue patterns including linking queues together with one-to-many or many-to-one relationships, and supports reading and writing to text-based files.

Interaction Pattern
===================
A QueueLink is a one-way process that connects queues together. When two or more queues are linked, a sub-process is started to read from the "source" queue and write into the "destination" queue.

Circular references are not allowed, making QueueLink a 'directed acyclic graph', or DAG.

Users create each queue, which must be instances of ``multiprocessing.Manager.JoinableQueue``. Those queues can then be added to a QueueLink instance as either the source or destination.

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
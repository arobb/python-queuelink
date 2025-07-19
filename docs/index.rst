Welcome to QueueLink's documentation!
=====================================

.. image:: https://badge.fury.io/py/queuelink.svg
   :target: https://pypi.org/project/queuelink
   :alt: Pypi Version
.. image:: https://readthedocs.org/projects/queuelink/badge/?version=latest
   :target: http://queuelink.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

This documentation includes an introduction to the purpose of QueueLink,
example uses, and API docs.

The project source is available on `Github <https://github.com/arobb/python-queuelink>`_.

.. toctree::
   :maxdepth: 1
   :caption: Contents

   api

Introduction and Background
===========================
The QueueLink library simplifies linking queues together with one-to-many or many-to-one relationships. "Adapters" support reading files handles and pipes into queues, and writing from queues into file handles and pipes.

A QueueLink instance is a one-way process that connects queues together. When two or more queues are linked, a separate process (or thread) is started to read from each "source" queue and write into the "destination" queues. (One process per source queue.)

Circular references are not allowed.

Users create each queue from the Queue or Multiprocessing libraries. Those queues can then be added to a QueueLink instance as either the source or destination.

Adapters permit this type of linkage between handles and pipes and queues.

Examples
========
Some implementations of QueueLink connecting queues together.

These examples are validated during testing in `this test file <https://github.com/arobb/python-queuelink/blob/main/tests/tests/queuelink_examples_test.py>`_.

Basic use
---------
One-to-one, the "hello world".

These examples both use the threaded Queue library for both queues (first example) or one of the queues (second example). Because of that, the link itself lives in the main code process and might be more likely to experience Global Interpreter Lock contention than if both queues were from the multiprocessing library. However, inter-process communication is quite slow, so you'll need to determine which works better for your use case.

If both queues are created from the multiprocessing library the link will be a separate process. If you don't need to set the start method directly, you can simply ``from multiprocessing import Queue`` and replace ``q = multiprocessing.get_context(start_method).Queue()`` with ``q = Queue()``.

.. code-block:: python

    # Threading only
    from queue import Queue
    from queuelink import QueueLink

    def test_example_threaded(self):
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
        text_out = dest_q.get(timeout=1)
        # self.assertEqual(text_in, text_out, 'Text is inconsistent')  # Pytest

.. code-block:: python

    # Multiprocessing
    import multiprocessing

    from queue import Queue
    from queuelink import QueueLink

    # Selecting a start method for this example
    start_method = "spawn"  # macOS default

    def test_cross_thread_multiprocess(self):
        # Source and destination
        source_q = Queue()  # Thread-based
        dest_q = multiprocessing.get_context(start_method).Queue()  # Process-based

        # Create the QueueLink
        queue_link = QueueLink(name="my link", start_method=self.start_method)

        # Connect queues to the QueueLink
        source_id = queue_link.read(q=source_q)
        dest_id = queue_link.write(q=dest_q)

        # Text to send
        text_in = "a😂" * 10

        # Add text to the source queue
        source_q.put(text_in)

        # Retrieve the text from the destination queue!
        text_out = dest_q.get(timeout=1)
        # self.assertEqual(text_in, text_out, 'Text is inconsistent')  # Pytest

Reading from an open subprocess PIPE
------------------------------------
This illustrates how to use a QueueLink adapter to read directly from a subprocess pipe into a queue. The pipe reader adapter only accepts one queue to write into, so if you need to read the pipe output from multiple processes/threads, you need to use a QueueLink to copy the pipe output into a set of additional queues.

.. code-block:: python

    # Multiprocessing
    import multiprocessing

    from queue import Queue
    from queuelink import QueueLink, QueueHandleAdapterReader
    from subprocess import Popen, PIPE

    # Selecting a start method for this example
    start_method = "spawn"  # macOS default

    def test_reader(self):
        # Text to send
        text_in = "a😂" * 10

        # Destination queue
        dest_q = multiprocessing.get_context(start_method).Queue()  # Process-based

        # Subprocess, simple example sending some text to stdout
        # from subprocess import Popen, PIPE
        proc = Popen(['echo', '-n', text_in],  # -n prevents echo from adding a newline character
                     stdout=PIPE,
                     universal_newlines=True)

        # Connect the reader
        read_adapter = QueueHandleAdapterReader(queue=dest_q,
                                                handle=proc.stdout,
                                                start_method=self.start_method)

        # Get the text from the queue
        text_out = dest_q.get()
        self.assertEqual(text_in, text_out, 'Text is inconsistent')

Start Method
============
The "start method" is how a separate process is started by Python, applicable only to "multiprocessing", not multi-threading. You can read more about this in the `Python documentation <https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods>`_. It is passed as a string to the QueueLink(start_method=) parameter, where it is sent unmodified to the multiprocessing.get_context() method.

This is helpful to set if you need to specify the start method because you or a downstream user may chose one other than the default.

Indices and tables
==================
* :ref:`genindex`
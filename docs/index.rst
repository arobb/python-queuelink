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

.. toctree::
   :maxdepth: 1
   :caption: Contents

   api

Introduction and Background
===========================
The QueueLink library simplifies linking queues together with one-to-many or many-to-one relationships. "Adapters" support reading files handles and pipes into queues, and writing from queues into file handles and pipes.

A QueueLink instance is a one-way process that connects queues together. When two or more queues are linked, a separate process (or thread) is started to read from each "source" queue and write into the "destination" queues. (One process per source queue.)

Circular references are not allowed, making QueueLink a 'directed acyclic graph', or DAG.

Users create each queue from the Queue or Multiprocessing libraries. Those queues can then be added to a QueueLink instance as either the source or destination.

Adapters permit this type of linkage between handles and pipes and queues.


Indices and tables
==================
* :ref:`genindex`
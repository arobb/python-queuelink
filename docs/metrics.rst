Metrics
=======

``QueueLink`` tracks two kinds of data for each active link automatically —
message latency (how long each message took to move from source to destination)
and message count (how many messages have been forwarded).  No configuration is
required; collection starts as soon as the first publisher starts and stops when
``stop()`` is called.

Metrics are available through ``QueueLink.get_metrics()``.  The ``link()``
factory exposes the underlying ``QueueLink`` instance via ``result.queue_link``
for queue-to-queue links:

.. code-block:: python

    import queue
    from queuelink import link

    src = queue.Queue()
    dst = queue.Queue()
    result = link(src, dst)

    src.put("hello")
    dst.get()
    result.stop()

    metrics = result.queue_link.get_metrics()


Calling ``get_metrics()``
--------------------------

``get_metrics()`` returns a snapshot of all data emitted up to that point.
It can be called at any time — before, during, or after a ``stop()`` — but
calling it after ``stop()`` guarantees all in-flight data has been flushed:

.. code-block:: python

    ql = QueueLink(source=src, destination=dst)

    # ... move messages ...

    ql.stop()
    metrics = ql.get_metrics()   # complete snapshot

**Return value** — a ``dict`` keyed by element ID (an opaque string).  Each
value is a ``dict`` describing one tracked element:

.. code-block:: text

    {
        "<element_id>": {
            "name":             str or None,
            "data_point_count": int,        # number of latency samples
            "mean":             float,      # mean latency in seconds
            "median":           float,      # median latency in seconds
            "stddev":           float,      # population std dev in seconds
        },
        "<element_id>": {
            "name":             str or None,
            "count":            int,        # total messages forwarded
        },
        ...
    }

The element IDs are stable for the lifetime of the ``QueueLink`` instance but
are not meaningful outside of it.  To tell the two element types apart, check
for the ``"mean"`` key (timing) or ``"count"`` key (counting):

.. code-block:: python

    for eid, data in metrics.items():
        if "mean" in data:
            print(f"Latency — mean: {data['mean']:.4f}s  "
                  f"median: {data['median']:.4f}s  "
                  f"stddev: {data['stddev']:.4f}s  "
                  f"samples: {data['data_point_count']}")
        elif "count" in data:
            print(f"Messages forwarded: {data['count']}")


Timing metric details
---------------------

The timing element records the elapsed time between when each message was
placed on the source queue and when it was forwarded to every destination queue.
Latency values are in **seconds** (float).

Rolling window
~~~~~~~~~~~~~~

Only the most recent 100 samples are kept in memory at any time.  The mean,
median, and standard deviation are recalculated over that window on every new
sample, so the statistics always reflect recent behaviour.

``data_point_count`` reflects how many samples are in the current window
(up to 100), not the total number of messages ever forwarded.  Use the
counting element for the lifetime total.

Standard deviation
~~~~~~~~~~~~~~~~~~

``stddev`` is the **population** standard deviation (``statistics.pstdev``),
not the sample standard deviation.  It is zero when only one sample has been
collected.


Counting metric details
-----------------------

The counting element increments once for every message forwarded.  Unlike the
timing window, the count is cumulative for the entire lifetime of the publisher.

When ``get_metrics()`` returns multiple elements with a ``"count"`` key (which
can happen if the publisher was restarted), sum them to get the overall total.


Periodic vs. final emission
----------------------------

Metrics snapshots are emitted internally at two points:

* **Periodically** — every 100 messages forwarded.
* **On stop** — once when the publisher shuts down, capturing any remaining
  data.

``get_metrics()`` drains the internal snapshot queue and merges the results,
so it always returns the most recent available snapshot per element, not a
running total of all snapshots.  For most use cases, calling ``get_metrics()``
once after ``stop()`` is sufficient.


Limitations
-----------

* Metrics are per-``QueueLink`` instance.  If you create multiple links in a
  pipeline, call ``get_metrics()`` on each one separately.
* Latency measurement begins when the publisher reads from the source queue,
  not when the caller puts a message onto it.  Network or IPC overhead between
  the caller and the publisher is not included.
* ``link()`` only exposes metrics when the result includes a ``QueueLink``
  component.  Adapter-only paths (e.g. file-to-file) have no ``queue_link``
  attribute and no metrics.

Contributing to QueueLink
=========================

Contributions are welcome!

Development setup
-----------------

.. code-block:: bash

    git clone https://github.com/arobb/python-queuelink.git
    cd python-queuelink
    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[test]"

Running tests
-------------

.. code-block:: bash

    # Run all environments (full matrix + lint)
    tox

    # Run tests for a single Python version
    tox -e py313

    # Recreate the virtualenvs
    tox --recreate

    # Run a specific test file
    tox -e py313 -- tests/tests/queuelink_test.py

    # Run a specific test by keyword
    tox -e py313 -- -k "test_queuelink_source_destination"

    # Disable parallel execution
    tox -- -n 0

    # Show detailed test output in sequential mode
    tox -- -n 0 --verbose

Tests run in two phases per tox environment:

1. Fork-context tests run in parallel via pytest-xdist (``-n auto``).
2. Forkserver/spawn tests run serially to avoid SemLock conflicts with
   xdist's forked workers.

Linting
-------

.. code-block:: bash

    tox -e pylint
    tox -e bandit

Submitting changes
------------------

1. Fork the repo and create a branch from ``main``.
2. Add tests for any new functionality.
3. Ensure ``tox`` passes locally.
4. Open a pull request against ``main``.

All PRs require CI to pass before merge. Squash or rebase merges only
(linear history required).

For maintainer release instructions, see `docs/publishing.rst <docs/publishing.rst>`_.
Publishing QueueLink
====================
Information on contributing may get added later.

Upcoming Changes
----------------
#. Add better test coverage
#. Move features from future to queuelink folders
#. Update documentation for the additional features
#. Add examples
#. Add proper documentation for readthedocs

Testing
-------
Some test commands

.. code-block::

    # Basic
    tox

    # Recreate the virtualenvs
    tox --recreate

    # Run just one environment
    tox -e py313

    # Run just one test file
    tox -e py313 -- tests/tests/queuelink_examples_test.py

    # Disable parallel execution
    tox -- -n 0

    # Show the detailed list of tests while running (in sequential mode)
    tox -- -n 0 --verbose

Publishing
----------
Configure Twine and the PyPi RC file at `~/.pypirc` . Entries with tokens scoped for an entire account can be used for multiple projects.

.. code-block:: ini

    [distutils]
    index-servers=
        test-create
        production-create

    # Use twine upload --repository test-create dist/*
    [test-create]
    repository = https://test.pypi.org/legacy/
    username = __token__
    password = <your token>

    # Use twine upload --repository production-create dist/*
    [production-create]
    repository = https://upload.pypi.org/legacy/
    username = __token__
    password = <your token>

1. Make sure you're at the project root

2. Ensure all commits are made, pushed, and the Git environment clear

.. code-block:: bash

    git stash

3. Set the new version in the pyproject.toml file

4. Tag the current version

.. code-block:: bash

    git tag -a x.y.z -m "Version release message"

5. Build the release package. The resulting files will be in `./dist/`.

.. code-block:: bash

    ./make-dist.sh

6. Check that the distribution has no errors

.. code-block:: bash

    twine check dist/*

7. Push to PyPi's test environment first and ensure everything looks good on
the web site.

.. code-block:: bash

    python -m twine upload --repository test-create dist/*

8. Then push to PyPi's official repo.

.. code-block:: bash

    python -m twine upload --repository production-create dist/*

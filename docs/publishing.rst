Publishing QueueLink
====================

This page documents the release process for maintainers.

Releases are published to PyPI via OIDC trusted publishing, triggered
automatically when a version tag is pushed. Manual Twine uploads are
a fallback only.

Release steps
-------------

1. Ensure all commits are pushed and the working tree is clean.

2. Tag the release:

   .. code-block:: bash

       git tag -a x.y.z -m "Version x.y.z"
       git push origin x.y.z

   The CI publish workflow triggers on version tags and uploads to PyPI
   automatically via OIDC trusted publishing.

Manual publishing (fallback)
-----------------------------

If you need to publish manually, configure ``~/.pypirc``:

.. code-block:: ini

    [distutils]
    index-servers=
        test-create
        production-create

    [test-create]
    repository = https://test.pypi.org/legacy/
    username = __token__
    password = <your token>

    [production-create]
    repository = https://upload.pypi.org/legacy/
    username = __token__
    password = <your token>

Then build and upload:

.. code-block:: bash

    # Build
    ./make-dist.sh

    # Verify
    twine check dist/*

    # Upload to TestPyPI first
    python -m twine upload --repository test-create dist/*

    # Upload to PyPI
    python -m twine upload --repository production-create dist/*
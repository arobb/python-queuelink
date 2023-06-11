#!/usr/bin/env bash
# Use rst2html-2.7.py README.rst /dev/null to validate the formatting of README
DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

# Run in a virtual environment
if [ ! -d "./build" ]; then
  virtualenv -p python3 "./build"
fi

# Activate the virtual environment
source ./build/bin/activate

# Make sure we have the build command
pip install build

rm -rf "$DIR/src/queuelink.egg-info"
python -m build --sdist

# Sign the distribution
if [ "$?" = "0" ]; then
  gpg --detach-sign -a "$DIR"/dist/*.tar.gz
fi

# Stop the virtual environment
deactivate
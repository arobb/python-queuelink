# -*- coding: utf-8 -*-
# Provide benchmark modules an easy way to import project stuff

import os
import sys

# Configure the package search path to include the benchmarks directory itself
# (so intra-benchmark imports like `from throughput_results import ...` resolve)
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

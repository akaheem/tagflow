"""Pytest configuration for TagFlow.

Its presence at the repo root makes that root the pytest ``rootdir``, which is
inserted onto ``sys.path`` under the default *prepend* import mode. That lets
both ``import tagflow`` and ``from tests.fakes import ...`` resolve when running
``pytest`` from anywhere in the tree — no editable install required.
"""

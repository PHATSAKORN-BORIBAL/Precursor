"""Precursor: a flight-data recorder for small machines.

It keeps a rolling buffer of multi-channel sensor data, detects incidents,
seals the seconds *before* each incident into a tamper-evident bundle and ranks
which channel moved first.
"""

__version__ = "0.1.0"

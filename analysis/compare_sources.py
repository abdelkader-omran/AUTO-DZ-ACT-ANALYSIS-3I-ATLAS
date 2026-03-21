"""
Source comparison tool for analysis layer.

Reads normalized observation data and compares it with MPC availability
and raw source status for a given date.
"""

from scripts.compare_sources import compare_sources

if __name__ == "__main__":
    compare_sources("2026-03-21")

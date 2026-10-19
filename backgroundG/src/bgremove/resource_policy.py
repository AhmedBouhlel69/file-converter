"""Resource defaults shared by inference, batch jobs and model diagnostics.

These thresholds are conservative application checks, not measured peak memory
requirements or a guarantee that inference will complete.
"""

LARGE_MODEL_BYTES = 500_000_000
MIN_LARGE_CPU_FREE_BYTES = 8 * 1024**3
DEFAULT_CPU_THREADS = 2

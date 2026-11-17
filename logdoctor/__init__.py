"""Universal Log Doctor analysis engine.

Pure Python, no web code and no storage: give it log text, get back a
structured analysis. The website, the API and the command-line tool all
use this same engine.
"""

from logdoctor.analyze import analyze
from logdoctor.models import Analysis, ErrorGroup, LogEntry, Summary, Timeline

__version__ = "0.1.0"

__all__ = [
    "analyze",
    "Analysis",
    "ErrorGroup",
    "LogEntry",
    "Summary",
    "Timeline",
]

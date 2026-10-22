"""Safety fixture: importing this module writes a marker file.

Graphora must never import analyzed code; tests assert the marker never appears.
"""

from pathlib import Path

Path(__file__).with_name("IMPORTED_MARKER").write_text("imported\n")

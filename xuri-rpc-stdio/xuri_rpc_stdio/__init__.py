"""
xuri-rpc-stdio — Stdio-based sender for xuri-rpc.
"""

from .stdio_sender import (
    createServer,
    createMain,
)

__all__ = [
    'createServer',
    'createMain',
]

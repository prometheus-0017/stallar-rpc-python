"""
xuri-rpc-websocket — WebSocket sender for xuri-rpc.
"""

from .websocket_sender import (
    WebSocketBinarySender,
    createServer,
    createMain,
)

__all__ = [
    'WebSocketBinarySender',
    'createServer',
    'createMain',
]

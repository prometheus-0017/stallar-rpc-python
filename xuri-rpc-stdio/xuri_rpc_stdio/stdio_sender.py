"""
Stdio-based RPC transport using CBOR binary encoding (cross-platform).

Supports both:
- Raw ``BinaryIO`` streams (``sys.stdin.buffer`` / ``sys.stdout.buffer``)
- ``asyncio.StreamReader`` / ``asyncio.StreamWriter`` (from ``create_subprocess_exec``)

Usage — parent process launches a child::

    # child.py (server)
    async def main():
        serve = await createServer('childHost')
        await serve(MyService())  # blocks until connection closes

    # parent.py (client)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'child.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    client, main_proxy = await createMain('parentHost', proc.stdin, proc.stdout)
    result = await main_proxy.add(1, 2)  # → 3
"""
import asyncio
import sys
from typing import Any, Callable, Optional, Tuple, Union, BinaryIO

import cbor2

from xuri_rpc import Client, MessageReceiver, RpcMessage, ISender

# Type alias for stream parameters
StreamType = Union[BinaryIO, asyncio.StreamReader, asyncio.StreamWriter]


# ---------------------------------------------------------------------------
# Low-level helpers (supports both asyncio streams and raw BinaryIO)
# ---------------------------------------------------------------------------

def _is_async_stream(stream: StreamType) -> bool:
    """Check if *stream* is an asyncio StreamReader or StreamWriter."""
    return hasattr(stream, 'drain') or hasattr(stream, 'readexactly')


async def _read_exactly(stream: StreamType, n: int) -> Optional[bytes]:
    """Read exactly *n* bytes from a stream (async or blocking)."""
    if _is_async_stream(stream):
        try:
            return await stream.readexactly(n)
        except asyncio.IncompleteReadError:
            return None
    else:
        loop = asyncio.get_event_loop()
        buf = b''
        while len(buf) < n:
            chunk = await loop.run_in_executor(None, stream.read, n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf


async def _read_message(stream: StreamType) -> Optional[RpcMessage]:
    """Read one length-prefixed CBOR message."""
    header = await _read_exactly(stream, 4)
    if header is None:
        return None
    length = int.from_bytes(header, 'big')
    data = await _read_exactly(stream, length)
    if data is None:
        return None
    return cbor2.loads(data)


class _StdioSender(ISender):
    """Sends RPC messages as CBOR binary to a stream."""

    def __init__(self, stream: StreamType) -> None:
        self._stream: StreamType = stream
        self._lock: asyncio.Lock = asyncio.Lock()
        self._is_async: bool = _is_async_stream(stream)

    async def send(self, message: RpcMessage) -> None:
        data = cbor2.dumps(message)
        header = len(data).to_bytes(4, 'big')
        payload = header + data
        async with self._lock:
            if self._is_async:
                self._stream.write(payload)
                await self._stream.drain()
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._stream.write, payload)
                self._stream.flush()


async def _runLoop(
    in_stream: StreamType,
    out_stream: StreamType,
    messageReceiver: MessageReceiver,
    client: Client,
) -> None:
    """Continuously read CBOR messages and dispatch them."""
    sender = _StdioSender(out_stream)
    if client.useSender() is None:
        client.setSender(lambda: sender)
    try:
        while True:
            msg = await _read_message(in_stream)
            if msg is None:
                break
            await messageReceiver.onReceiveMessage(msg, client)
    except (EOFError, OSError, asyncio.IncompleteReadError):
        pass


# ---------------------------------------------------------------------------
# Server side
# ---------------------------------------------------------------------------

async def createServer(
    hostId: str,
    in_stream: Optional[StreamType] = None,
    out_stream: Optional[StreamType] = None,
) -> Callable[[Any], Any]:
    """Create a stdio-based RPC server.

    If *in_stream*/*out_stream* are not given, ``sys.stdin.buffer`` /
    ``sys.stdout.buffer`` are used.

    Returns a callable ``serve(mainObject)`` that registers the main object
    and starts the I/O loop.  ``serve`` is an async function that blocks
    (awaits) until the connection is closed.  Returns ``(messageReceiver, serve)``.
    """
    in_stream = in_stream or sys.stdin.buffer
    out_stream = out_stream or sys.stdout.buffer

    messageReceiver: MessageReceiver = MessageReceiver(hostId)
    client: Client = Client(hostId)
    sender: _StdioSender = _StdioSender(out_stream)
    client.setSender(lambda: sender)

    async def serve(mainObject: Any) -> Tuple[MessageReceiver, Callable[[Any], Any]]:
        messageReceiver.setMain(mainObject)
        await _runLoop(in_stream, out_stream, messageReceiver, client)
        return (messageReceiver, serve)

    return serve


# ---------------------------------------------------------------------------
# Client side
# ---------------------------------------------------------------------------

async def createMain(
    hostId: str,
    out_stream: Optional[StreamType] = None,
    in_stream: Optional[StreamType] = None,
) -> Tuple[Client, Any]:
    """Create a stdio-based RPC client.

    *out_stream* is the stream that goes to the server's stdin.
    *in_stream* is the stream that receives the server's stdout.

    Returns ``(client, mainProxy)``.
    """
    out_stream = out_stream or sys.stdout.buffer
    in_stream = in_stream or sys.stdin.buffer

    client: Client = Client(hostId)
    messageReceiver: MessageReceiver = MessageReceiver(hostId)
    sender: _StdioSender = _StdioSender(out_stream)
    client.setSender(lambda: sender)

    asyncio.ensure_future(_runLoop(in_stream, out_stream, messageReceiver, client))

    main: Any = await client.getMain()
    return (client, main)

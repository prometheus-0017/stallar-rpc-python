"""
TCP sender and connection helpers using CBOR binary format with length-prefix framing.
"""
import asyncio
import logging
import struct
import uuid
from typing import Any, Awaitable, Callable, Optional, Tuple, Dict, Union

import cbor2
from xuri_rpc.rpc import debugFlag

from xuri_rpc import Client, MessageReceiver, RpcMessage, ISender

logger = logging.getLogger(__name__)

# Length prefix format: 4-byte unsigned big-endian
_HEADER_FMT = "!I"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------

class TcpBinarySender(ISender):
    """Sends RPC messages as length-prefixed CBOR-encoded binary over TCP.

    *session_id* may be a plain string **or** a zero-argument callable that
    returns the current session id (useful on the client side where the id is
    learned lazily from the server's responses).

    Reconnection
    ------------
    The sender transparently reconnects when the connection is lost.
    Reconnection is triggered from two places:

    * :meth:`send` — catches connection errors and reconnects before retry.
    * :func:`listen` — catches connection errors and reconnects, then
      continues the receive loop.

    Both paths go through :meth:`ensure_connected` which uses an internal lock
    so that only one reconnection happens at a time.
    """

    def __init__(
        self,
        stream: Optional[Tuple[asyncio.StreamReader, asyncio.StreamWriter]] = None,
        session_id: Optional[Union[str, Callable[[], Optional[str]]]] = None,
    ) -> None:
        self.stream: Optional[Tuple[asyncio.StreamReader, asyncio.StreamWriter]] = stream
        self._session_id: Optional[Union[str, Callable[[], Optional[str]]]] = session_id
        # sessionId → sender mapping for server-side multi-connection routing
        self.session_sender_map: Dict[str, 'TcpBinarySender'] = {}

        # reconnection config (set by createMain)
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._max_retries: int = 0
        self._retry_delay: float = 1.0
        self._retry_backoff: float = 2.0
        self._on_reconnect: Optional[Callable[[], Awaitable[Any]]] = None
        self._reconnect_lock: Optional[asyncio.Lock] = None
        self._client: Optional[Client] = None

    # -- session id ---------------------------------------------------------

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @session_id.setter
    def session_id(self, value: Optional[str]) -> None:
        self._session_id = value

    # -- low-level I/O ------------------------------------------------------

    @staticmethod
    async def _write_frame(
        writer: asyncio.StreamWriter, payload: bytes
    ) -> None:
        """Write a length-prefixed frame to the TCP stream."""
        header = struct.pack(_HEADER_FMT, len(payload))
        writer.write(header + payload)
        await writer.drain()

    @staticmethod
    async def _read_frame(
        reader: asyncio.StreamReader,
    ) -> Optional[bytes]:
        """Read one length-prefixed frame. Returns None on clean EOF."""
        raw_header = await reader.readexactly(_HEADER_SIZE)
        (length,) = struct.unpack(_HEADER_FMT, raw_header)
        if length == 0:
            return b""
        return await reader.readexactly(length)

    # -- reconnection -------------------------------------------------------

    def _configure_reconnect(
        self,
        host: str,
        port: int,
        client: Client,
        *,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        on_reconnect: Optional[Callable[[Client, Optional[Any]], Any]] = None,
    ) -> None:
        """Store reconnection parameters (called by :func:`createMain`)."""
        self._host = host
        self._port = port
        self._client = client
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff
        self._on_reconnect = on_reconnect
        self._reconnect_lock = asyncio.Lock()

    def _is_connected(self) -> bool:
        if self.stream is None:
            return False
        _, writer = self.stream
        return not writer.is_closing()

    async def ensure_connected(self) -> None:
        """Ensure the underlying TCP connection is alive; reconnect if needed.

        Safe to call from both :meth:`send` and the listen loop concurrently —
        only one actual reconnection will take place; the other callers wait
        and return once the connection is restored.
        """
        if self._is_connected():
            return

        if self._reconnect_lock is None:
            if debugFlag:
                logger.warning("TCP disconnected and no reconnect configured")
            return

        async with self._reconnect_lock:
            # double-check after acquiring the lock
            if self._is_connected():
                return

            delay = self._retry_delay
            attempts = 0

            while True:
                attempts += 1
                if 0 < self._max_retries < attempts:
                    logger.warning(
                        "Gave up reconnecting to %s:%d after %d attempts",
                        self._host, self._port, attempts - 1,
                    )
                    raise ConnectionError(
                        f"Failed to reconnect after {attempts - 1} attempts"
                    )

                logger.info(
                    "Reconnecting to %s:%d in %.1fs (attempt %d)",
                    self._host, self._port, delay, attempts,
                )
                await asyncio.sleep(delay)

                try:
                    reader, writer = await asyncio.open_connection(
                        self._host, self._port
                    )
                    self.stream = (reader, writer)
                    local_addr = writer.get_extra_info("sockname")
                    remote_addr = writer.get_extra_info("peername")
                    print(
                        f"[TCP] Reconnected: local port {local_addr[1]}, "
                        f"remote port {remote_addr[1]}"
                    )

                    if self._on_reconnect is not None:
                        try:
                            await self._on_reconnect(self._client, None)
                        except Exception:
                            logger.exception("on_reconnect callback raised")
                    return
                except OSError as exc:
                    print(
                        f"[TCP] Reconnect to {self._host}:{self._port} "
                        f"failed (attempt {attempts}): {exc}"
                    )
                    logger.warning(
                        "Reconnect to %s:%d failed (attempt %d): %s",
                        self._host, self._port, attempts, exc,
                    )
                    delay = min(delay * self._retry_backoff, 60.0)

    # -- send ---------------------------------------------------------------

    async def send(self, message: RpcMessage) -> None:
        sid = self.session_id
        if sid and "sessionId" not in message.get("meta", {}):
            message.setdefault("meta", {})["sessionId"] = sid

        broken = False
        try:
            await self.ensure_connected()
            _, writer = self.stream
            payload = cbor2.dumps(message)
            await self._write_frame(writer, payload)
        except (ConnectionError, OSError) as exc:
            if self.stream is not None:
                _, writer = self.stream
                local_addr = writer.get_extra_info("sockname")
                remote_addr = writer.get_extra_info("peername")
                print(
                    f"[TCP] broken connection: local port {local_addr[1]}, "
                    f"remote port {remote_addr[1]}, error={exc}"
                )
            broken = True

        if broken:
            raise Exception("failed to send message, TCP connection broken")


# ---------------------------------------------------------------------------
# Server side
# ---------------------------------------------------------------------------

async def createServer(
    hostId: str,
    host: str = "localhost",
    port: int = 8765,
    path: str = "/",
) -> Tuple[Callable[[Any], Any], asyncio.AbstractServer]:
    """Create a TCP-based RPC server with length-prefix framing.

    Returns ``(serve, tcp_server)`` where ``serve`` is an async function that
    registers the main object and blocks until the server is closed.
    ``tcp_server`` is the underlying asyncio server for lifecycle management.

    Usage::

        serve, tcp_server = await createServer('myServer', 'localhost', 8765)
        await serve(MyService())  # blocks until tcp_server is closed
    """
    serverReceiver: MessageReceiver = MessageReceiver(hostId)

    async def _onTcpConnected(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single TCP client connection."""
        local_addr = writer.get_extra_info("sockname")
        remote_addr = writer.get_extra_info("peername")
        print(
            f"[TCP] Server connection handled: local port {local_addr[1]}, "
            f"remote port {remote_addr[1]}, writer_id={id(writer)}"
        )

        session_id: str = str(uuid.uuid4())
        conn_sender: TcpBinarySender = TcpBinarySender(
            (reader, writer), session_id
        )
        # Register sender in session map at connection time
        conn_client: Client = Client(hostId)
        conn_client.getSessionData()[session_id] = conn_sender
        conn_client.setSender(lambda: conn_client.getSessionData()[session_id])
        connReceiver: MessageReceiver = MessageReceiver(hostId)

        try:
            while True:
                raw = await TcpBinarySender._read_frame(reader)
                if raw is None:
                    break  # clean EOF
                data = cbor2.loads(raw)
                await connReceiver.onReceiveMessage(data, conn_client)
        except asyncio.IncompleteReadError:
            # Peer disconnected without sending full frame
            pass
        except (ConnectionError, OSError) as e:
            import traceback
            traceback.print_exc()
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    tcp_server: asyncio.AbstractServer = await asyncio.start_server(
        _onTcpConnected, host, port
    )

    async def serve(mainObject: Any) -> Tuple[MessageReceiver, Callable[[Any], Any]]:
        serverReceiver.setMain(mainObject)
        async with tcp_server:
            await tcp_server.serve_forever()
        return (serverReceiver, serve)

    return (serve, tcp_server)


# ---------------------------------------------------------------------------
# Client side (with auto-reconnect)
# ---------------------------------------------------------------------------

async def createMain(
    hostId: str,
    host: str = "localhost",
    port: int = 8765,
    path: str = "/",
    *,
    max_retries: int = 0,
    retry_delay: float = 1.0,
    retry_backoff: float = 2.0,
    on_reconnect: Optional[Callable[[Client, Optional[Any]], Any]] = None,
) -> Tuple[Client, Any]:
    """Connect to a TCP-based RPC server and return the main proxy.

    Returns ``(client, main_proxy)``.

    If the connection drops later, reconnection is handled transparently:

    * When :meth:`send <TcpBinarySender.send>` detects a closed
      connection, it reconnects and retries.
    * When the background listen loop detects a closed connection, it
      reconnects and continues receiving.

    Reconnection parameters
    -----------------------
    max_retries : int
        Maximum consecutive reconnection attempts.  ``0`` (default) means
        **reconnect forever**.
    retry_delay : float
        Initial delay in seconds between reconnection attempts.
    retry_backoff : float
        Multiplier applied to *retry_delay* after each failed attempt
        (capped at 60 s).
    on_reconnect : callable, optional
        ``fn(client, main)`` or ``async def fn(client, main)`` called after
        every successful *re*connection.  Useful for re-subscribing or
        re-registering state.

    Usage::

        client, main = await createMain('myClient', 'localhost', 8765)
        result = await main.hello('world')
    """
    client: Client = Client(hostId)
    messageReceiver: MessageReceiver = MessageReceiver(hostId)
    sender: TcpBinarySender = TcpBinarySender(None)  # stream set below
    client.setSender(lambda: sender)

    # Configure reconnection parameters on the sender
    sender._configure_reconnect(
        host, port, client,
        max_retries=max_retries,
        retry_delay=retry_delay,
        retry_backoff=retry_backoff,
        on_reconnect=on_reconnect,
    )

    # Initial connection
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError as exc:
        print(f"[TCP] Initial connection to {host}:{port} failed: {exc}")
        raise
    sender.stream = (reader, writer)
    local_addr = writer.get_extra_info("sockname")
    remote_addr = writer.get_extra_info("peername")
    print(
        f"[TCP] Connected: local port {local_addr[1]}, "
        f"remote port {remote_addr[1]}"
    )

    # Start background listen — reconnect is triggered from inside
    asyncio.ensure_future(_listen(sender, messageReceiver, client))

    main: Any = await client.getMain()
    return (client, main)


async def _listen(
    sender: TcpBinarySender,
    messageReceiver: MessageReceiver,
    client: Client,
) -> None:
    """Read messages from the sender's TCP stream; reconnect on drop."""
    while True:
        try:
            if sender.stream is None:
                raise ConnectionError("No active TCP stream")
            reader, _ = sender.stream
            while True:
                raw = await TcpBinarySender._read_frame(reader)
                if raw is None:
                    raise ConnectionError("Clean EOF from server")
                data = cbor2.loads(raw)
                # Extract sessionId from meta and update sender
                meta = data.get("meta") or {}
                if meta.get("sessionId"):
                    sender.session_id = meta["sessionId"]
                await messageReceiver.onReceiveMessage(data, client)
        except (
            ConnectionError,
            OSError,
            asyncio.IncompleteReadError,
        ):
            pass

        # Connection lost — reconnect via sender (shared with send path)
        try:
            await sender.ensure_connected()
        except ConnectionError:
            logger.warning("Reconnect gave up, listen loop exiting")
            return
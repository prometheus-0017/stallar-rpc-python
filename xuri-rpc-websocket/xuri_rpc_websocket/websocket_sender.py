"""
WebSocket sender and connection helpers using CBOR binary format.
Requires: pip install websockets cbor2
"""
import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional, Tuple, Dict, Union

import cbor2
from xuri_rpc.rpc import debugFlag
import websockets
from websockets.exceptions import ConnectionClosed
from websockets.legacy.protocol import WebSocketCommonProtocol
from websockets.legacy.server import WebSocketServerProtocol, WebSocketServer
from websockets.legacy.client import WebSocketClientProtocol

from xuri_rpc import Client, MessageReceiver, RpcMessage, ISender

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sender
# ---------------------------------------------------------------------------

class WebSocketBinarySender(ISender):
    """Sends RPC messages as CBOR-encoded binary over a WebSocket connection.

    *session_id* may be a plain string **or** a zero-argument callable that
    returns the current session id (useful on the client side where the id is
    learned lazily from the server's responses).

    Reconnection
    ------------
    The sender transparently reconnects when the connection is lost.
    Reconnection is triggered from two places:

    * :meth:`send` — catches ``ConnectionClosed`` and reconnects before retry.
    * :func:`listen` — catches ``ConnectionClosed`` and reconnects, then
      continues the receive loop.

    Both paths go through :meth:`ensure_connected` which uses an internal lock
    so that only one reconnection happens at a time.
    """

    def __init__(self, ws: Optional[WebSocketCommonProtocol], session_id: Optional[Union[str, Callable[[], Optional[str]]]] = None) -> None:
        self.ws: Optional[WebSocketCommonProtocol] = ws
        self._session_id: Optional[Union[str, Callable[[], Optional[str]]]] = session_id
        # sessionId → sender mapping for server-side multi-connection routing
        self.session_sender_map: Dict[str, 'WebSocketBinarySender'] = {}

        # reconnection config (set by createMain)
        self._uri: Optional[str] = None
        self._max_retries: int = 0
        self._retry_delay: float = 1.0
        self._retry_backoff: float = 2.0
        self._on_reconnect: Optional[Callable[[],Awaitable[Any]]] = None
        self._reconnect_lock: Optional[asyncio.Lock] = None
        self._client: Optional[Client] = None

    # -- session id ---------------------------------------------------------

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @session_id.setter
    def session_id(self, value: Optional[str])->None:
        self._session_id = value

    # -- reconnection -------------------------------------------------------

    def _configure_reconnect(
        self,
        uri: str,
        client: Client,
        *,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        on_reconnect: Optional[Callable[[Client, Optional[Any]], Any]] = None,
    ) -> None:
        """Store reconnection parameters (called by :func:`createMain`)."""
        self._uri = uri
        self._client = client
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff
        self._on_reconnect = on_reconnect
        self._reconnect_lock = asyncio.Lock()

    async def ensure_connected(self) -> None:
        """Ensure the underlying WebSocket is connected; reconnect if needed.

        Safe to call from both :meth:`send` and the listen loop concurrently —
        only one actual reconnection will take place; the other callers wait
        and return once the connection is restored.
        """
        if self.ws is not None and self.ws.close_code is None:
            return

        if self._reconnect_lock is None:
            if(debugFlag):
                logger.warning("ws disconnected and no reconnect configured")
            return

        async with self._reconnect_lock:
            # double-check after acquiring the lock
            if self.ws is not None and self.ws.close_code is None:
                return

            delay = self._retry_delay
            attempts = 0

            while True:
                attempts += 1
                if 0 < self._max_retries < attempts:
                    logger.warning(
                        "Gave up reconnecting to %s after %d attempts",
                        self._uri, attempts - 1,
                    )
                    raise ConnectionError(
                        f"Failed to reconnect after {attempts - 1} attempts"
                    )

                logger.info(
                    "Reconnecting to %s in %.1fs (attempt %d)",
                    self._uri, delay, attempts,
                )
                await asyncio.sleep(delay)

                try:
                    self.ws = await websockets.connect(self._uri)
                    local_addr = self.ws.local_address
                    remote_addr = self.ws.remote_address
                    print(f"[WebSocket] Reconnected: local port {local_addr[1]}, remote port {remote_addr[1]}")

                    if self._on_reconnect is not None:
                        try:
                            await self._on_reconnect(self._client, None)
                        except Exception:
                            logger.exception("on_reconnect callback raised")
                    return
                except (OSError, websockets.WebSocketException) as exc:
                    print(f"[WebSocket] Reconnect to {self._uri} failed (attempt {attempts}): {exc}")
                    logger.warning(
                        "Reconnect to %s failed (attempt %d): %s",
                        self._uri, attempts, exc,
                    )
                    delay = min(delay * self._retry_backoff, 60.0)

    # -- send ---------------------------------------------------------------

    async def send(self, message: RpcMessage) -> None:
        sid = self.session_id
        if sid and 'sessionId' not in message.get('meta', {}):
            message.setdefault('meta', {})['sessionId'] = sid
        broken=False
        
        try:
            await self.ensure_connected()
            await self.ws.send(cbor2.dumps(message))
        except ConnectionClosed:
            local_addr = self.ws.local_address
            remote_addr = self.ws.remote_address
            print(f"[WebSocket] broken Reconnected: local port {local_addr[1]}, remote port {remote_addr[1]}")
            broken=True
        if broken:
            raise Exception('failed to send message,ws broken')


# ---------------------------------------------------------------------------
# Server side
# ---------------------------------------------------------------------------

async def createServer(
    hostId: str,
    host: str = "localhost",
    port: int = 8765,
    path: str = "/",
) -> Tuple[Callable[[Any], Any], Any,MessageReceiver]:
    """Create a WebSocket-based RPC server.

    Returns ``(serve, ws_server)`` where ``serve`` is an async function that
    registers the main object and blocks until the server is closed.
    ``ws_server`` is the underlying WebSocket server for lifecycle management.

    Usage::

        serve, ws_server = await createServer('myServer', 'localhost', 8765)
        await serve(MyService())  # blocks until ws_server is closed
    """
    serverReceiver: MessageReceiver = MessageReceiver(hostId)

    async def _onWsConnected(ws: WebSocketServerProtocol, path: Optional[str] = None) -> None:
        """Handle a single WebSocket client connection."""
        local_addr = ws.local_address
        remote_addr = ws.remote_address
        print(f'[WebSocket] Server connection handled: local port {local_addr[1]}, remote port {remote_addr[1]}, ws_id={id(ws)}')

        session_id: str = str(uuid.uuid4())
        conn_sender: WebSocketBinarySender = WebSocketBinarySender(ws, session_id)
        # Register sender in session map at connection time
        conn_client: Client = Client(hostId)
        conn_client.getSessionData()[session_id]=conn_sender
        conn_client.setSender(lambda: conn_client.getSessionData()[session_id])
        connReceiver: MessageReceiver = serverReceiver

        try:
            async for raw in ws:
                data = cbor2.loads(raw)
                await connReceiver.onReceiveMessage(data, conn_client)
        except ConnectionClosed as e:
            import traceback
            traceback.print_exc()
            pass

    ws_server: WebSocketServer = await websockets.serve(_onWsConnected, host, port)

    async def serve(mainObject: Any) -> Tuple[MessageReceiver, Callable[[Any], Any]]:
        serverReceiver.setMain(mainObject)
        await ws_server.wait_closed()
        return (serverReceiver, serve)

    return (serve, ws_server,serverReceiver)


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
    """Connect to a WebSocket-based RPC server and return the main proxy.

    Returns ``(client, main_proxy)``.

    If the connection drops later, reconnection is handled transparently:

    * When :meth:`send <WebSocketBinarySender.send>` detects a closed
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
    uri = f"ws://{host}:{port}{path}"

    client: Client = Client(hostId)
    messageReceiver: MessageReceiver = MessageReceiver(hostId)
    sender: WebSocketBinarySender = WebSocketBinarySender(None)  # ws set below
    client.setSender(lambda: sender)

    # Configure reconnection parameters on the sender
    sender._configure_reconnect(
        uri, client,
        max_retries=max_retries,
        retry_delay=retry_delay,
        retry_backoff=retry_backoff,
        on_reconnect=on_reconnect,
    )

    # Initial connection
    try:
        ws: WebSocketClientProtocol = await websockets.connect(uri)
    except (OSError, websockets.WebSocketException) as exc:
        print(f"[WebSocket] Initial connection to {uri} failed: {exc}")
        raise
    sender.ws = ws
    local_addr = ws.local_address
    remote_addr = ws.remote_address
    print(f"[WebSocket] Connected: local port {local_addr[1]}, remote port {remote_addr[1]}")

    # Start background listen — reconnect is triggered from inside
    asyncio.ensure_future(_listen(sender, messageReceiver, client))

    main: Any = await client.getMain()
    return (client, main)


async def _listen(
    sender: WebSocketBinarySender,
    messageReceiver: MessageReceiver,
    client: Client,
) -> None:
    """Read messages from the sender's ws; reconnect and continue on drop."""
    while True:
        try:
            async for raw in sender.ws:
                data = cbor2.loads(raw)
                # Extract sessionId from meta and update sender
                meta = data.get('meta') or {}
                if meta.get('sessionId'):
                    sender.session_id = meta['sessionId']
                await messageReceiver.onReceiveMessage(data, client)
        except ConnectionClosed:
            pass

        # Connection lost — reconnect via sender (shared with send path)
        try:
            await sender.ensure_connected()
        except ConnectionError:
            logger.warning("Reconnect gave up, listen loop exiting")
            return

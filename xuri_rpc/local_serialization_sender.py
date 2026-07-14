"""
Local serialisation sender using CBOR for in-process RPC testing.
Requires: pip install cbor2
"""
import asyncio
from typing import Any, Optional, Tuple, Callable, Dict

from .rpc import Client, MessageReceiver, RpcMessage, ISender


class LocalSerializationSender(ISender):
    """Sends RPC messages via a DumpChannel using CBOR encoding."""

    def __init__(self, channel: 'DumpChannel', direction: str) -> None:
        self.channel: 'DumpChannel' = channel
        self.direction: str = direction

    async def send(self, message: RpcMessage) -> None:
        import cbor2

        dumped = cbor2.dumps(message)
        if self.direction == 'toServer':
            self.channel.sendToServer(dumped)
        else:
            self.channel.sendToClient(dumped)


class DumpChannel:
    """In-process bidirectional channel connecting a server and client side."""

    def __init__(self) -> None:
        self.serverSideReceiver: Optional[MessageReceiver] = None
        self.clientSideReceiver: Optional[MessageReceiver] = None
        self.serverSideClient: Optional[Client] = None
        self.clientSideClient: Optional[Client] = None

    def setServerSide(self, receiver: MessageReceiver, client: Client) -> None:
        self.serverSideReceiver = receiver
        self.serverSideClient = client

    def setClientSide(self, receiver: MessageReceiver, client: Client) -> None:
        self.clientSideReceiver = receiver
        self.clientSideClient = client

    def sendToServer(self, message: bytes) -> None:
        import cbor2

        decoded = cbor2.loads(message)
        asyncio.ensure_future(
            self.serverSideReceiver.onReceiveMessage(
                decoded, self.serverSideClient
            )
        )

    def sendToClient(self, message: bytes) -> None:
        import cbor2

        decoded = cbor2.loads(message)
        asyncio.ensure_future(
            self.clientSideReceiver.onReceiveMessage(
                decoded, self.clientSideClient
            )
        )


async def createServer(
    hostId: str, channel: DumpChannel
) -> Callable[[Any], Tuple[MessageReceiver, Callable[[Any], Tuple[MessageReceiver, ...]]]]:
    """Create a server-side handler bound to the given DumpChannel.

    Returns a callable ``serve(mainObject)`` that registers the main object
    and returns ``(messageReceiver, serve)``.
    """
    messageReceiver: MessageReceiver = MessageReceiver(hostId)
    client: Client = Client(hostId)
    _sender: LocalSerializationSender = LocalSerializationSender(channel, 'toClient')
    client.setSender(lambda: _sender)
    channel.setServerSide(messageReceiver, client)

    def serve(mainObject: Any) -> Tuple[MessageReceiver, Callable[[Any], Tuple[MessageReceiver, ...]]]:
        messageReceiver.setMain(mainObject)
        return (messageReceiver, serve)

    return serve


async def createMain(
    hostId: str, channel: DumpChannel
) -> Tuple[Client, Any]:
    """Create a client-side connection to the server via DumpChannel.

    Returns ``(client, mainProxy)``.
    """
    client: Client = Client(hostId)
    messageReceiver: MessageReceiver = MessageReceiver(hostId)
    channel.setClientSide(messageReceiver, client)
    _sender: LocalSerializationSender = LocalSerializationSender(channel, 'toServer')
    client.setSender(lambda: _sender)
    main: Any = await client.getMain()
    return (client, main)

"""
Test helpers mirroring __tests__/base.ts.
"""
import asyncio
from typing import Any, Callable, Optional

from xuri_rpc.rpc import Client, MessageReceiver, setHostId
from xuri_rpc.local_serialization_sender import DumpChannel, createServer, createMain

_id_counter = 0


async def mainFunc(
    mainObject: Any,
    testProcess: Callable,
    customHostIds: Optional[dict] = None,
):
    """
    Set up an in-process RPC server/client pair via DumpChannel and run
    ``testProcess(client, main, server_id)``.
    """
    global _id_counter
    idx = _id_counter
    _id_counter += 1

    server_id = (customHostIds or {}).get('serverId') or f'server{idx}'
    client_id = (customHostIds or {}).get('clientId') or f'client{idx}'

    channel = DumpChannel()
    serve = await createServer(server_id, channel)
    _recv, _serve = serve(mainObject)
    client, main = await createMain(client_id, channel)
    await testProcess(client, main, server_id)


def assert_true(condition: bool, text: Optional[str] = None):
    """Assert helper mirroring TS ``assert``."""
    if not condition:
        raise AssertionError(text or 'assertion failed')

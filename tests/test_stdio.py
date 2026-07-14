"""test_stdio.py — stdio 二进制通信端到端测试"""
import asyncio
import sys
import os
import pytest

from xuri_rpc_stdio import createServer, createMain


# ---------------------------------------------------------------------------
# Helper: create a subprocess that runs as the server
# ---------------------------------------------------------------------------

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), '_stdio_server.py')


def _write_server_script():
    """Write a helper script that acts as the stdio server."""
    script = '''\
import asyncio
import sys
sys.path.insert(0, r"{pkg_dir}")
from xuri_rpc_stdio import createServer

class ChildService:
    def add(self, a, b):
        return a + b
    def greet(self, name):
        return f'hello {name}'
    def echo(self, x):
        return x
    def merge(self, d):
        return {**d, 'extra': True}
    def boom(self):
        raise ValueError('child boom')

async def main():
    serve = await createServer('childHost')
    await serve(ChildService())

asyncio.run(main())
'''.format(pkg_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    with open(SERVER_SCRIPT, 'w', encoding='utf-8') as f:
        f.write(script)


@pytest.fixture(scope='module', autouse=True)
def _setup_server_script():
    _write_server_script()


@pytest.mark.asyncio
async def test_stdio_basic_call():
    """Call a remote function over stdio."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await createMain('parentHost', proc.stdin, proc.stdout)
        result = await main.add(10, 20)
        assert result == 30
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_string_return():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await createMain('parentHost', proc.stdin, proc.stdout)
        result = await main.greet('world')
        assert result == 'hello world'
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_none_handling():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await createMain('parentHost', proc.stdin, proc.stdout)
        result = await main.echo(None)
        assert result is None
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_dict_argument_and_return():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await createMain('parentHost', proc.stdin, proc.stdout)
        result = await main.merge({'a': 1, 'b': 2})
        assert result == {'a': 1, 'b': 2, 'extra': True}
    finally:
        proc.terminate()
        await proc.wait()


@pytest.mark.asyncio
async def test_stdio_exception_propagation():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, SERVER_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        client, main = await createMain('parentHost', proc.stdin, proc.stdout)
        with pytest.raises(Exception) as exc_info:
            await main.boom()
        assert 'child boom' in str(exc_info.value)
    finally:
        proc.terminate()
        await proc.wait()

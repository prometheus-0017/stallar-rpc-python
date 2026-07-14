"""test_byte.py — 字节传输测试 (mirrors byte.test.ts)"""
import struct
import pytest
from .base_test import mainFunc, assert_true


def int2bytes(value: int) -> bytes:
    """Convert a 32-bit int to 4 bytes (big-endian)."""
    return struct.pack('>i', value)


def byteconcat(a: bytes, b: bytes) -> bytes:
    """Concatenate two byte strings."""
    return a + b


def byte2int(data: bytes, offset: int = 0) -> int:
    """Read a 32-bit int from bytes at offset (big-endian)."""
    return struct.unpack('>i', data[offset:offset + 4])[0]


class ByteService:
    def add(self, a, b):
        return byteconcat(a, b)


@pytest.mark.asyncio
async def test_byte_transmit_and_concat():
    await mainFunc(
        ByteService(),
        lambda _client, main, sid: _check(main),
    )


async def _check(main):
    v = await main.add(int2bytes(1), int2bytes(2))
    a = byte2int(v)
    b = byte2int(v, 4)
    assert_true(a + b == 3, 'byte concat failed')

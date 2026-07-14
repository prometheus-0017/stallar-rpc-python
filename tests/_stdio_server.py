import asyncio
import sys
sys.path.insert(0, r"C:\Users\lzy\Desktop\xuri-rpc\python")
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

import asyncio
import json
import websockets
from xuri_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
setHostId('backend')
from xuri_rpc import setDebugFlag
setDebugFlag(True)


# define a sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        # message is an object can be jsonified
        await self.ws.send(json.dumps(message))

async def main():
    setHostId('frontend')
    client = Client()

    ws = await websockets.connect('ws://localhost:18081')

    async def on_message(data):
        await getMessageReceiver().onReceiveMessage(json.loads(data), client)
        print(f'收到服务器消息: {data}')

    # Run message reception in the background
    async def listen():
        async for message in ws:
            asyncio.ensure_future(on_message(message))

    # Start listening in the background
    asyncio.ensure_future(listen())

    client.setSender(Sender(ws))

    main_proxy = await client.getMain()
    def callback(result):
        # breakpoint()
        print('from callback', result)
    result = await main_proxy.plus(1, 2, asProxy(callback))
    print('from rpc', result)

    try:
        result=await main_proxy.plus(1,2,None)
        raise Exception('should not reach here')
    except:
        print('right')
    from xuri_rpc import setDebugFlag
    setDebugFlag(True)
    from datetime import datetime
    result=await main_proxy.plus(datetime.now(),2,None)
                              

asyncio.run(main())
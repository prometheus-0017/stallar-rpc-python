import asyncio
import json
import websockets
from xuri_rpc import PlainProxyManager, RunnableProxyManager, MessageReceiver, Client, asProxy, getMessageReceiver, setHostId
from xuri_rpc import setDebugFlag
setDebugFlag(True)
# 设置hostName
setHostId('backend')

# 创建一个Sender
class Sender:
    def __init__(self, ws):
        self.ws = ws

    async def send(self, message):
        await self.ws.send(json.dumps(message))

# 设置用于提供起始方法的main对象
from xuri_rpc import dict2obj
async def plus(a,b,callback):
    if(callback==None):
        raise Exception('callback is null')
    else:
        return None
getMessageReceiver().setMain(dict2obj({
    'plus': plus
}))

async def handle_connection(ws, path):
    # 创建一个client用于发送返回信息
    client = Client()
    client.setSender(Sender(ws))

    try:
        async for data in ws:
            # 处理接收到的信息
            message = json.loads(data)
            asyncio.ensure_future(getMessageReceiver().onReceiveMessage(message, client))
    except Exception as error:
        print('客户端连接错误:', error)

start_server = websockets.serve(handle_connection, "", 18081)

try:
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
except Exception as error:
    print('服务器错误:', error)
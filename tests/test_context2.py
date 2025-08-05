# 假设这些类和函数已由某个模块提供
from stallar_rpc import  Message,MessageReceiverOptions,RunnableProxyManager,PlainProxyManager,setHostId,Client,ISender,asProxy,getMessageReceiver,MessageReceiver 
from stallar_rpc import dict2obj

import asyncio


async def main():
    setHostId('frontJs')

    hostId = 'backendJs'

    messageReceiverBackend = MessageReceiver(hostId)

    class DirectSender(ISender):
        def __init__(self, clientCallback: Client, msgReceiverTo: MessageReceiver):
            self.clientCallback = clientCallback
            self.msgReceiver = msgReceiverTo

        async def send(self, message):
            await self.msgReceiver.onReceiveMessage(message, self.clientCallback)
            print('send', message)

    objectTest = dict2obj({
        'say': lambda name: print('hello ', name)
    })

    messageReceiverBackend.setMain(dict2obj({
        # 'hello': lambda a, b, onResult: (async lambda: await onResult(a + b))(),
        'getObject': lambda: asProxy(objectTest, hostId)
    }))

    messageReceiverBackend.setObject('contextTest',dict2obj( {
        'hello': lambda context: f"hello {context.get('a')} and {context.get('b')}"
    }), True)

    messageReceiverBackend.setResultAutoWrapper(lambda x: x)

    async def interceptor1(ctx, msg, clt, next_func):
        ctx['a'] = 'mike'
        await next_func()
        del ctx['a']

    async def interceptor2(ctx, msg, clt, next_func):
        ctx['b'] = 'jack'
        await next_func()
        del ctx['b']

    messageReceiverBackend.addInterceptor(interceptor1)
    messageReceiverBackend.addInterceptor(interceptor2)

    client = Client()
    clientOnBackend = Client(hostId)
    sender = DirectSender(clientOnBackend, messageReceiverBackend)
    backSender = DirectSender(client, getMessageReceiver())

    client.sender = sender
    clientOnBackend.sender = backSender

    client.setArgsAutoWrapper(lambda x: x)

    # 获取远程对象
    rpc = await client.getObject('contextTest')
    result = await rpc.hello()
    
    # 断言结果
    assert result == 'hello mike and jack', f"Expected 'hello mike and jack', got {result}"


# def test_funca():
#     """模拟 describe('funca', ...) 中的 it(...) 测试"""
#     asyncio.run(main())

# 如果直接运行此脚本，可取消下面注释
# asyncio.run(main())
import asyncio
def test_main():
    if __name__ == "__main__":
        try:
            main_proxy = asyncio.run(main())
            print(main_proxy)
        except Exception as e:
            import traceback
            traceback.print_exc()
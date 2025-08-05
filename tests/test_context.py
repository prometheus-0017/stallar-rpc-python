# 假设以下导入的类和函数已在某处定义并可用
from stallar_rpc import  Message,MessageReceiverOptions,RunnableProxyManager,PlainProxyManager,setHostId,Client,ISender,asProxy,getMessageReceiver,MessageReceiver 

import asyncio

from stallar_rpc import dict2obj
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

    objectTest = {
        'say': lambda name: print('hello ', name)
    }

    # 设置主对象（模拟 RPC 接口）
    messageReceiverBackend.setMain(dict2obj({
        'hello': lambda a, b, onResult: (asyncio.create_task(onResult(a + b)), a + b)[1],
        'getObject': lambda: asProxy(objectTest, hostId)
    }))

    # 注册名为 'contextTest' 的对象
    messageReceiverBackend.setObject('contextTest', dict2obj({
        'hello': lambda context: 'hello'
    }), True)

    # 设置结果自动包装器（无操作）
    messageReceiverBackend.setResultAutoWrapper(lambda x: x)

    # 创建客户端实例
    client = Client()
    clientOnBackend = Client(hostId)

    # 创建双向发送器
    sender = DirectSender(clientOnBackend, messageReceiverBackend)
    backSender = DirectSender(client, getMessageReceiver())

    # 绑定发送器
    client.sender = sender
    clientOnBackend.sender = backSender

    # 设置参数自动包装（无操作）
    client.setArgsAutoWrapper(lambda x: x)

    # 获取远程代理对象
    rpc = await client.getObject('contextTest')

    # 调用远程方法
    result = await rpc.hello()

    # 断言结果（使用 Python 的 unittest 或 pytest 风格）
    assert result == 'hello', f"Expected 'hello', but got {result}"


# 测试用例包装（模拟 describe/it）
# import pytest


# @pytest.mark.asyncio
# async def test_funca():
#     """Simulates the describe/it block"""
#     await main()


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
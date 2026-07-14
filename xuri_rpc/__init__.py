"""
xuri-rpc — A Python RPC framework with remote callback support.
"""

from .rpc import (
    # Types
    RpcMessage,
    ArgObjType,
    # Abstract interfaces
    ISender,
    ICustomTranslator,
    # Flags & configuration
    setDebugFlag,
    setHostId,
    # Core data wrapper
    PreArgObj,
    # Proxy managers
    ObjectOfProxyManager as PlainProxyManager,
    RemoteProxyManager as RunnableProxyManager,
    RemoteProxy,
    # Client & receiver
    Client,
    MessageReceiver,
    getMessageReceiver,
    # Utilities
    asProxy,
    generateErrorReply,
    # Proxy deletion helpers
    _deleteProxy,
    _deleteProxyById,
    # Maintenance
    removeOutdatedProxyObject,
    getProxyHoldingInfo,
    autoReRegister,
    autoCheck,
    RpcRemoteError,
)

__all__ = [
    # Types
    'RpcMessage',
    'ArgObjType',
    # Abstract interfaces
    'ISender',
    'ICustomTranslator',
    # Flags & configuration
    'setDebugFlag',
    'setHostId',
    # Core data wrapper
    'PreArgObj',
    # Proxy managers
    'PlainProxyManager',
    'RunnableProxyManager',
    'RemoteProxy',
    # Client & receiver
    'Client',
    'MessageReceiver',
    'getMessageReceiver',
    # Utilities
    'asProxy',
    'generateErrorReply',
    # Proxy deletion helpers
    '_deleteProxy',
    '_deleteProxyById',
    # Maintenance
    'removeOutdatedProxyObject',
    'getProxyHoldingInfo',
    'autoReRegister',
    'autoCheck',
    'RpcRemoteError',
]

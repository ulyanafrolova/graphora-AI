"""In-process MCP client calls for tests (specs/006-mcp-server research § R13)."""

import json

import anyio
from mcp import Client


def _run(server, use):
    async def go():
        async with Client(server) as client:
            return await use(client)

    return anyio.run(go)


def list_tools(server):
    async def use(client):
        return (await client.list_tools()).tools

    return _run(server, use)


def call(server, tool, /, **args):
    async def use(client):
        return await client.call_tool(tool, args)

    return _run(server, use)


def calls(server, *named):
    """Several `(name, args)` calls on one connection, in order."""

    async def use(client):
        return [await client.call_tool(name, args) for name, args in named]

    return _run(server, use)


def instructions(server):
    async def use(client):
        return client.instructions

    return _run(server, use)


def text(result):
    (block,) = result.content
    return block.text


def canonical(structured):
    return (json.dumps(structured, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

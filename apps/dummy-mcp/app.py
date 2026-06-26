import sys
import json


def handle_request(msg):
    req_id = msg.get('id')
    method = msg.get('method', '')

    if method == 'initialize':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "serverInfo": {
                    "name": "dummy-mcp",
                    "version": "1.0.0"
                }
            }
        }

    elif method == 'notifications/initialized':
        return None

    elif method == 'tools/list':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo back the input message",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string"}
                            },
                            "required": ["message"]
                        }
                    },
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "number"},
                                "b": {"type": "number"}
                            },
                            "required": ["a", "b"]
                        }
                    }
                ]
            }
        }

    elif method == 'resources/list':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "resources": [
                    {
                        "uri": "dummy://data/config",
                        "name": "Dummy Config",
                        "description": "A sample configuration resource",
                        "mimeType": "application/json"
                    }
                ]
            }
        }

    elif method == 'prompts/list':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "prompts": [
                    {
                        "name": "greet",
                        "description": "Generate a greeting message",
                        "arguments": [
                            {
                                "name": "name",
                                "description": "Name to greet",
                                "required": True
                            }
                        ]
                    }
                ]
            }
        }

    elif method == 'tools/call':
        params = msg.get('params', {})
        tool_name = params.get('name', '')
        tool_args = params.get('arguments', {})

        if tool_name == 'echo':
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": tool_args.get('message', '')
                        }
                    ]
                }
            }
        elif tool_name == 'add':
            a = tool_args.get('a', 0)
            b = tool_args.get('b', 0)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": str(a + b)
                        }
                    ]
                }
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool not found: {tool_name}"
                }
            }

    elif method == 'shutdown':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": None
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


def main():
    sys.stderr.write("dummy-mcp: server starting (stdio)\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"dummy-mcp: invalid JSON: {e}\n")
            sys.stderr.flush()
            continue

        response = handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + '\n')
            sys.stdout.flush()

            if msg.get('method') == 'shutdown':
                break

    sys.stderr.write("dummy-mcp: server stopped\n")
    sys.stderr.flush()


if __name__ == '__main__':
    main()

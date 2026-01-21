import sys
import json
import logging
from daraja_client import DarajaClient, TOOLS_METADATA

logger = logging.getLogger('daraja_server')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('m_pesa_debug.log', encoding='utf-8')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


def send_response(req_id, result=None, error=None):
    resp = {"id": req_id}
    if error:
        resp["error"] = str(error)
    else:
        resp["result"] = result
    json_str = json.dumps(resp, ensure_ascii=False)
    sys.stdout.write(json_str + "\n")
    sys.stdout.flush()


def main():
    client = DarajaClient()
    # Expose the tools with hyper-explicit signatures and descriptions
    tools = {
        name: {"func": getattr(client, name), "description": meta["description"], "args": meta.get("args", {})}
        for name, meta in TOOLS_METADATA.items()
    }

    logger.info("MCP server started, waiting for STDIO messages")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as e:
            logger.exception("Failed to parse JSON from stdin: %s", e)
            continue

        req_id = msg.get("id")
        tool = msg.get("tool")
        args = msg.get("args", {})

        logger.debug("Received request id=%s tool=%s args=%s", req_id, tool, args)

        if tool == "list_tools":
            send_response(req_id, {k: {"description": v["description"], "args": v["args"]} for k, v in tools.items()})
            continue

        if tool not in tools:
            send_response(req_id, error=f"Unknown tool: {tool}. Call `list_tools` to see available tools.")
            continue

        func = tools[tool]["func"]
        try:
            result = func(**args) if args else func()
            send_response(req_id, result=result)
            logger.info("Tool %s executed for id=%s", tool, req_id)
        except Exception as e:
            logger.exception("Tool execution error: %s", e)
            send_response(req_id, error=str(e))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server interrupted and shutting down")

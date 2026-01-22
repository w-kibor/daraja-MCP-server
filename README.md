# Lipa Na M-Pesa (Daraja) DevTools MCP Server

Small MCP server exposing Daraja Sandbox tools over STDIO so Copilot Agent (MCP) can trigger and monitor M-Pesa transactions from the IDE.

Quick start

```powershell
pip install -r requirements.txt
```

3. Run the MCP server locally (Copilot Agent will use STDIO):

```powershell
python -u server.py
```

Protocol (stdin/stdout JSON)

- Send a JSON line: `{ "id": "unique-id", "tool": "simulate_stk_push", "args": { "phone_number": "2547...", "amount": 1, "description": "test" } }`
- Server responds with JSON line: `{ "id": "unique-id", "result": { ... } }` or `{ "id": "unique-id", "error": "..." }`

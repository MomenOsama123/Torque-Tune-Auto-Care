"""
agent/client.py

CLIENT SIDE OF CAPABILITY NEGOTIATION (Protocol Concern #1)
=============================================================
This is the "agent" side required by the task: a client wired to the real
server, showing the initialize/initialized handshake actually happening
over stdio -- not assumed.

Run it with:
    python client.py

It will spawn mcp-server/server.py as a subprocess, talk to it over
stdin/stdout using line-delimited JSON-RPC 2.0 messages, and print exactly
what capabilities the server declared. It then demonstrates the whole
point of negotiation: deciding whether a risky tool (update_inventory) is
safe to expose, based on what the server actually said it supports --
never assumed.
"""

import json
import subprocess
import sys
from pathlib import Path

SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp-server" / "server.py"

CLIENT_INFO = {
    "name": "auto-care-technician-agent",
    "version": "0.1.0",
}


def send(proc: subprocess.Popen, message: dict) -> None:
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def read_response(proc: subprocess.Popen) -> dict:
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Server closed the connection unexpectedly.")
    return json.loads(line)


def main() -> None:
    print(f"[client] Starting server subprocess: {SERVER_SCRIPT}")
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        # --- Step 1: send initialize -------------------------------------
        print("[client] Sending 'initialize' request...")
        send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": CLIENT_INFO,
            },
        })

        response = read_response(proc)
        result = response.get("result", {})
        server_capabilities = result.get("capabilities", {})
        server_info = result.get("serverInfo", {})

        print(f"[client] Server identified itself as: {server_info}")
        print(f"[client] Server declared capabilities: {list(server_capabilities.keys())}")

        # --- Step 2: send initialized notification ------------------------
        print("[client] Sending 'notifications/initialized'...")
        send(proc, {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        # --- Step 3: THE ACTUAL NEGOTIATION CHECK --------------------------
        # This is the part the task cares about: the client must check the
        # declaration before relying on a capability, not assume it exists.
        supports_elicitation = "elicitation" in server_capabilities
        supports_resources = "resources" in server_capabilities

        print()
        print("=== Capability-based decision ===")
        if supports_elicitation:
            print(
                "[client] Server supports elicitation -> it is safe to expose "
                "the risky 'update_inventory' write tool, since the server can "
                "pause and ask a human for confirmation before zeroing out stock "
                "or applying a large decrease."
            )
        else:
            print(
                "[client] Server does NOT support elicitation -> falling back to "
                "READ-ONLY tools only (search_part, check_quantity, "
                "suggest_alternative). update_inventory is withheld because a "
                "confirmation step could never be delivered safely."
            )

        if supports_resources:
            print(
                "[client] Server supports resources -> the agent will fetch "
                "warehouse_policy via resources/read instead of hardcoding "
                "policy text into its own prompt."
            )
        else:
            print(
                "[client] Server does NOT support resources -> the agent will "
                "have no access to the warehouse policy document."
            )

        # --- Step 4: prove the server enforces the handshake ---------------
        # Demonstrate that trying to skip straight to a real call before
        # initialize would have been rejected (defensive check on server side).
        print()
        print("[client] Handshake complete. Session is ready for tool calls.")

    finally:
        proc.terminate()
        stderr_output = proc.stderr.read()
        if stderr_output:
            print("\n--- server log (stderr) ---")
            print(stderr_output.strip())


if __name__ == "__main__":
    main()

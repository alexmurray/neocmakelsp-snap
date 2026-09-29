#!/usr/bin/env python3
# Minimal LSP client: starts `neocmakelsp stdio`, initializes it, asks it to
# format the given file and checks the result, then shuts it down.
import json
import os
import subprocess
import sys

path = os.path.abspath(sys.argv[1])
root = "file://" + os.path.dirname(path)
uri = "file://" + path

server = subprocess.Popen(
    ["neocmakelsp", "stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
)


def send(msg):
    body = json.dumps(dict(jsonrpc="2.0", **msg)).encode()
    server.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    server.stdin.flush()


def recv(want_id):
    """Return the response to request want_id, skipping everything else."""
    while True:
        length = None
        while True:
            line = server.stdout.readline()
            if not line:
                sys.exit("server closed stdout before responding to %d" % want_id)
            if line == b"\r\n":
                break
            name, _, value = line.decode().partition(":")
            if name.strip().lower() == "content-length":
                length = int(value)
        msg = json.loads(server.stdout.read(length))
        if "method" in msg:
            # reply to server->client requests (e.g. client/registerCapability)
            # so the server doesn't sit waiting on us
            if "id" in msg:
                send({"id": msg["id"], "result": None})
            continue
        if msg.get("id") == want_id:
            if "error" in msg:
                sys.exit("request %d failed: %s" % (want_id, msg["error"]))
            return msg["result"]


send({"id": 1, "method": "initialize",
      "params": {"processId": os.getpid(), "rootUri": root, "capabilities": {}}})
result = recv(1)
print("initialize:", json.dumps(result))
assert result["serverInfo"]["name"] == "neocmakelsp", result
assert result["capabilities"]["documentFormattingProvider"], result
send({"method": "initialized", "params": {}})

with open(path) as f:
    text = f.read()
send({"method": "textDocument/didOpen",
      "params": {"textDocument": {"uri": uri, "languageId": "cmake",
                                  "version": 1, "text": text}}})
send({"id": 2, "method": "textDocument/formatting",
      "params": {"textDocument": {"uri": uri},
                 "options": {"tabSize": 2, "insertSpaces": True}}})
edits = recv(2)
print("formatting:", json.dumps(edits))
assert any('\n  message(STATUS "greeting enabled")\n' in e["newText"]
           for e in edits), edits

# neocmakelsp exits as soon as it gets shutdown, without replying to it
send({"id": 3, "method": "shutdown"})
rc = server.wait(timeout=10)
assert rc == 0, "server exited with %d" % rc

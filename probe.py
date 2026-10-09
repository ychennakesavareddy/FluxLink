import asyncio, json, sys, uuid, httpx, websockets

BASE, WS = "http://127.0.0.1:8001", "ws://127.0.0.1:8001"

async def main(n):
    code = "".join(uuid.uuid4().hex[:1] for _ in range(1)) and uuid.uuid4().hex[:6].upper()
    a = {"email": "a@x.com", "name": "A", "device_id": "A-1", "device_name": "A", "session_code": code}
    b = {"email": "b@x.com", "name": "B", "device_id": "B-1", "device_name": "B", "session_code": code}
    async with httpx.AsyncClient() as c:
        print("create", (await c.post(f"{BASE}/api/sessions/create", json=a)).status_code)
        print("join", (await c.post(f"{BASE}/api/sessions/join", json=b)).status_code)
    content = ("def f():\n\treturn 'é🙂'\n" * (n // 20 + 1))[:n]
    async with websockets.connect(f"{WS}/ws/{code}/A-1", max_size=None) as wa, \
               websockets.connect(f"{WS}/ws/{code}/B-1", max_size=None) as wb:
        await wa.send(json.dumps({"type": "code_file", "message_id": str(uuid.uuid4()),
            "sender_device_id": "A-1", "file_name": "t.py", "language": "python", "content": content}))
        for _ in range(5):
            try:
                m = json.loads(await asyncio.wait_for(wb.recv(), 5))
            except asyncio.TimeoutError:
                print("B received nothing"); return
            if m.get("type") == "code_file":
                print("sent", len(content), "received", len(m["content"]), "identical:", m["content"] == content)
                return
            print("B got", m.get("type"))

asyncio.run(main(int(sys.argv[1])))

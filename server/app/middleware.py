from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    """Bound actual incoming bytes, including chunked or misleading length headers."""

    def __init__(self, app, max_bytes=5_000_000):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
            if declared < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({'detail': 'Некорректный Content-Length'}, 400)(scope, receive, send)
        if declared > self.max_bytes:
            return await self.too_large(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > self.max_bytes:
                return await self.too_large(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body = b''.join(chunks)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)

    async def too_large(self, scope, receive, send):
        return await JSONResponse({'detail': 'Максимальный размер запроса — 5 МБ'}, 413)(scope, receive, send)

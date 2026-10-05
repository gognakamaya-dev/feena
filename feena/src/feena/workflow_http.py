"""Authenticated workflow endpoints. Called only after workspace bearer verification."""
import json

from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, Response


async def handle(workflow, scope, receive, headers):
    request = Request(scope, receive)
    parts = scope['path'].strip('/').split('/')[1:]
    method = scope['method']
    try:
        data = {}
        if method == 'POST':
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse({'error': 'Request exceeds 64 KB'}, 413, headers=headers)
            data = json.loads(body or b'{}')
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
        if parts == ['readiness'] and method == 'GET':
            result = await workflow.readiness()
        elif parts == ['journeys'] and method == 'GET':
            result = workflow.list()
        elif len(parts) == 2 and parts[0] == 'journeys' and method == 'GET':
            result = workflow.get(parts[1])
        elif len(parts) == 3 and parts[0] == 'journeys':
            if parts[2] == 'approve' and method == 'POST':
                result = workflow.approve(parts[1], data.get('version'), data.get('reviewed') is True)
            elif parts[2] == 'run' and method == 'POST':
                result = await workflow.start(parts[1], data.get('version'), data.get('request_id'))
            elif parts[2] == 'export' and method == 'GET':
                return Response(workflow.export(parts[1]), media_type='application/yaml',
                                headers={**headers, 'Content-Disposition': 'attachment; filename="feena-approved.yaml"'})
            else:
                raise ValueError('Unknown operation')
        elif len(parts) == 2 and parts[0] == 'runs' and method == 'GET':
            result = workflow.run(parts[1])
        elif len(parts) == 3 and parts[0] == 'runs' and method == 'POST':
            original = workflow.run(parts[1])
            if parts[2] == 'rerun':
                result = await workflow.start(original['journey_id'], original['version'], data.get('request_id'), rerun_of=parts[1])
            elif parts[2] == 'cancel':
                await workflow.campaigns.cancel(parts[1])
                result = workflow.run(parts[1])
            else:
                raise ValueError('Unknown operation')
        elif len(parts) == 6 and parts[0] == 'runs' and parts[2] == 'jobs' and parts[4] == 'artifacts' and method == 'GET':
            path = workflow.artifact(parts[1], parts[3], parts[5])
            return FileResponse(path, filename=path.name, headers=headers)
        else:
            return JSONResponse({'error': 'Not found'}, 404, headers=headers)
        return JSONResponse(result, headers=headers)
    except (ValueError, KeyError, TypeError):
        # Validation may contain proposed input values; keep raw exception details private.
        return JSONResponse({'error': 'Request could not be completed. Refresh and check approval, IDs, version, and run status.'}, 400, headers=headers)

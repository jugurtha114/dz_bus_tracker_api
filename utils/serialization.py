from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser

try:
    import orjson
    import ormsgpack
    ORJSON_AVAILABLE = True
    ORMSGPACK_AVAILABLE = True
except ImportError:
    ORJSON_AVAILABLE = False
    ORMSGPACK_AVAILABLE = False


def orjson_dumps(data, **kwargs):
    if ORJSON_AVAILABLE:
        # Return the raw bytes without decoding to UTF-8.
        return orjson.dumps(data)
    import json
    # Encode the JSON string to UTF-8 bytes.
    return json.dumps(data, **kwargs).encode('utf-8')


def orjson_loads(data, **kwargs):
    if ORJSON_AVAILABLE:
        # orjson.loads expects a bytes-like object.
        return orjson.loads(data)
    import json
    return json.loads(data, **kwargs)


def ormsgpack_dumps(data, **kwargs):
    if ORMSGPACK_AVAILABLE:
        return ormsgpack.packb(data)
    return orjson_dumps(data, **kwargs)


def ormsgpack_loads(data, **kwargs):
    if ORMSGPACK_AVAILABLE:
        return ormsgpack.unpackb(data)
    return orjson_loads(data, **kwargs)



class ORJSONRenderer(JSONRenderer):
    media_type = 'application/json'
    
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b''
            
        renderer_context = renderer_context or {}
        response = renderer_context.get('response')
        
        if response and response.status_code == 204:
            return b''
            
        return orjson_dumps(data)


class ORJSONParser(JSONParser):
    media_type = 'application/json'
    
    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        encoding = parser_context.get('encoding', 'utf-8')
        
        try:
            data = stream.read().decode(encoding)
            return orjson_loads(data)
        except ValueError as exc:
            from rest_framework.exceptions import ParseError
            raise ParseError(f'JSON parse error - {str(exc)}')


class ORMsgPackRenderer(JSONRenderer):
    media_type = 'application/x-msgpack'
    
    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b''
            
        renderer_context = renderer_context or {}
        response = renderer_context.get('response')
        
        if response and response.status_code == 204:
            return b''
            
        return ormsgpack_dumps(data)


class ORMsgPackParser(JSONParser):
    media_type = 'application/x-msgpack'
    
    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        
        try:
            data = stream.read()
            return ormsgpack_loads(data)
        except ValueError as exc:
            from rest_framework.exceptions import ParseError
            raise ParseError(f'MsgPack parse error - {str(exc)}')

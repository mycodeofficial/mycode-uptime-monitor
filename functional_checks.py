"""Comprobaciones de solo lectura; nunca envían formularios válidos ni datos de clientes."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

SITES = {'MyCode': 'https://mycodeoficial.com', 'Daroka': 'https://daroka.mycodeoficial.com'}


def checks(name):
    if name == 'Daroka':
        return [('/', 'daroka', None), ('/carta', 'carta', None), ('/api/health', 'database', None)]
    return [('/', 'mycodeoficial', None), ('/api/contact', 'contact-validation', b'{}')]


def check(name, base):
    for path, expected, body in checks(name):
        url = base + path + '?monitor=' + str(time.time_ns())
        request = urllib.request.Request(url, data=body, headers={
            'User-Agent': 'MyCode-Monitor/2.0', 'Cache-Control': 'no-cache',
            'Content-Type': 'application/json', 'Accept': 'application/json' if expected in ('database', 'contact-validation') else 'text/html'})
        code = None
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                code, content = response.status, response.read(2_000_000).decode('utf-8', errors='replace')
        except urllib.error.HTTPError as error:
            code, content = error.code, error.read(16384).decode('utf-8', errors='replace')
        except Exception:
            return {'ok': False, 'error': 'No se pudo abrir una conexión segura con la web', 'path': path, 'url': base + path, 'expected': expected}
        if code in (401, 403, 429):
            return {'ok': None, 'code': code, 'error': 'Comprobación bloqueada o limitada; caída no confirmada', 'path': path, 'url': base + path, 'expected': expected}
        if expected == 'contact-validation':
            try:
                valid = code == 400 and json.loads(content).get('ok') is False
            except (ValueError, AttributeError):
                valid = False
        elif expected == 'database':
            try:
                payload = json.loads(content)
                valid = code == 200 and payload.get('ok') is True and payload.get('checks', {}).get('database') is True
            except (ValueError, AttributeError):
                valid = False
        else:
            valid = code == 200 and '<html' in content.lower() and expected in content.lower()
        if not valid:
            return {'ok': False, 'code': code, 'error': {'database': 'Daroka no puede leer los datos de su carta', 'contact-validation': 'La comprobación del formulario de contacto no responde como se esperaba', 'daroka': 'La portada de Daroka no se carga correctamente', 'carta': 'La carta de Daroka no se carga correctamente', 'mycodeoficial': 'La portada de MyCode no se carga correctamente'}[expected],
                    'path': path, 'url': base + path, 'expected': expected}
    return {'ok': True, 'code': 200, 'checks': len(checks(name)), 'url': base}

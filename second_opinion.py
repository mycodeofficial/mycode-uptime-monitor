"""Confirmación desde países distintos mediante Globalping, sin credenciales.
Contrato: https://github.com/jsdelivr/globalping/blob/master/public/v1/spec.yaml
"""
import json
import time
import urllib.parse
import urllib.request

API = 'https://api.globalping.io/v1/measurements'


def request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'MyCode-Monitor/2.0'})
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.load(response)


def verdict(results, expected=None):
    evidence = []
    countries = set()
    for row in results:
        probe, result = row.get('probe', {}), row.get('result', {})
        country = probe.get('country')
        if result.get('status') not in ('finished', 'failed') or not country:
            continue
        code = result.get('statusCode')
        if code in (401, 403, 404, 429):
            continue
        if code and 200 <= code < 400:
            if expected == 'database':
                try:
                    body = json.loads(result.get('rawBody') or '')
                    if body.get('ok') is True and body.get('checks', {}).get('database') is True:
                        return {'ok': True, 'detail': country + ': la aplicación y su base de datos responden.'}
                except (ValueError, AttributeError):
                    continue
            elif expected and expected != 'contact-validation':
                body = result.get('rawBody')
                if body is None:
                    continue
                if expected in body.lower():
                    return {'ok': True, 'detail': country + ': contenido esperado disponible.'}
                # El cuerpo se limita a 10 KB: una marca ausente no demuestra un fallo.
                continue
            else:
                return {'ok': True, 'detail': country + ': la web responde; caída no confirmada.'}
        if code is None and result.get('status') != 'failed':
            continue
        if country not in countries:
            countries.add(country)
            evidence.append({'DE': 'Alemania', 'US': 'Estados Unidos'}.get(country, country) + (': la web devuelve un error' if code else ': no se consigue conectar'))
    if len(evidence) >= 2:
        return {'ok': False, 'detail': '; '.join(evidence)}
    return {'ok': None, 'detail': 'No hay dos países con resultados concluyentes.'}


def corroborate(url, expected=None):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError()
        payload = {'type': 'http', 'target': parsed.hostname,
                   'locations': [{'country': 'DE', 'limit': 1}, {'country': 'US', 'limit': 1}],
                   'measurementOptions': {'protocol': 'HTTPS', 'request': {
                       'method': 'GET', 'path': parsed.path or '/', 'query': 'monitor=' + str(time.time_ns()),
                       'headers': {'Cache-Control': 'no-cache'}}}}
        created = request(API, payload)
        deadline = time.monotonic() + 35
        for _ in range(8):
            if time.monotonic() >= deadline:
                break
            time.sleep(3)
            measurement = request(API + '/' + urllib.parse.quote(created['id'], safe=''))
            result = verdict(measurement.get('results', []), expected)
            if result['ok'] is not None or measurement.get('status') == 'finished':
                return result
    except Exception:
        pass
    return {'ok': None, 'detail': 'La segunda comprobación externa no está disponible; caída no confirmada.'}

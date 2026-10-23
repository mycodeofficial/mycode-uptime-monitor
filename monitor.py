#!/usr/bin/env python3
"""Vigilante ejecutado en GitHub, independiente del servidor de las webs."""
import base64
import concurrent.futures
import copy
import datetime
import json
import os
import time
import urllib.error
import urllib.request

SITES = {'MyCode': 'https://mycodeoficial.com', 'Daroka': 'https://daroka.mycodeoficial.com'}
STATE_FILE = '.monitor-state.json'


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def probe(item):
    name, url = item
    for attempt in range(2):
        try:
            request = urllib.request.Request(url + '/?monitor=' + str(time.time_ns()), headers={
                'User-Agent': 'MyCode-External-Monitor/1.0', 'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=12) as response:
                if 200 <= response.status < 400:
                    return name, {'ok': True, 'code': response.status}
                result = {'ok': False, 'code': response.status}
        except urllib.error.HTTPError as error:
            result = {'ok': False, 'code': error.code}
        except Exception:
            result = {'ok': False, 'error': 'No se pudo conectar o validar HTTPS'}
        if attempt == 0:
            time.sleep(2)
    return name, result


def transition(previous, readings, now):
    """Sin red: cambios con cola persistente y duración de las caídas."""
    state = copy.deepcopy(previous)
    state.setdefault('services', {})
    state.setdefault('pending', [])
    state.setdefault('next_id', 1)
    checked = now.isoformat()
    changes = False
    for name, reading in readings.items():
        old = state['services'].get(name)
        if old is None or old['ok'] != reading['ok']:
            changes = True
            if not reading['ok']:
                message = '🔴 Vigilante externo · ' + name + ' no está disponible tras dos intentos.'
                message += '\n' + SITES[name]
                if 'code' in reading:
                    message += '\nHTTP ' + str(reading['code'])
            elif old and not old['ok']:
                started = datetime.datetime.fromisoformat(old['since'])
                minutes = max(0, int((now - started).total_seconds() // 60))
                message = '✅ Vigilante externo · ' + name + ' vuelve a responder.' + f'\nDuración aproximada: {minutes} min.'
            else:
                message = None
            if message:
                state['pending'].append({'id': state['next_id'], 'text': message, 'delivered': []})
                state['next_id'] += 1
            state['services'][name] = {**reading, 'since': checked}
    if readings and all(not row['ok'] for row in readings.values()):
        if not previous.get('server_unreachable', False):
            state['pending'].append({'id': state['next_id'], 'text':
                '⚠️ Vigilante externo · Las dos webs están inaccesibles. Puede haberse apagado el servidor o perdido su conexión a Internet. Este aviso se envía desde GitHub.', 'delivered': []})
            state['next_id'] += 1
            changes = True
        state['server_unreachable'] = True
    else:
        if previous.get('server_unreachable', False):
            state['pending'].append({'id': state['next_id'], 'text':
                '✅ Vigilante externo · El servidor vuelve a responder desde Internet; al menos una de las webs está disponible.', 'delivered': []})
            state['next_id'] += 1
            changes = True
        state['server_unreachable'] = False
    # Una actividad diaria evita la suspensión del cron por inactividad del repositorio.
    if previous.get('last_checked', '')[:10] != checked[:10]:
        changes = True
    if changes:
        state['last_checked'] = checked
    return state, changes


class GitHubState:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.token = os.environ['GH_TOKEN']
        self.sha = None

    def request(self, method='GET', data=None):
        url = 'https://api.github.com/repos/' + self.repo + '/contents/' + STATE_FILE
        request = urllib.request.Request(url, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'User-Agent': 'MyCode-External-Monitor/1.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)

    def load(self):
        try:
            result = self.request()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {}
            raise RuntimeError('No se pudo leer el estado del vigilante.') from None
        self.sha = result['sha']
        return json.loads(base64.b64decode(result['content']))

    def save(self, state):
        data = {'message': 'Actualizar estado del vigilante externo',
                'content': base64.b64encode((json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode()).decode()}
        if self.sha:
            data['sha'] = self.sha
        result = self.request('PUT', data)
        self.sha = result['content']['sha']


def send(text, target):
    token = os.environ['TELEGRAM_BOT_TOKEN']
    data = {'chat_id': target['chat_id'], 'text': text, 'link_preview_options': {'is_disabled': True}}
    if target.get('thread_id'):
        data['message_thread_id'] = target['thread_id']
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
        data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if not json.load(response).get('ok'):
                raise ValueError()
    except Exception:
        raise RuntimeError('Telegram no confirmó el aviso; se reintentará sin mostrar secretos.') from None


def main():
    storage = GitHubState()
    previous = storage.load()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        readings = dict(pool.map(probe, SITES.items()))
    state, changed = transition(previous, readings, utcnow())
    if changed:
        storage.save(state)
    targets = json.loads(os.environ['TELEGRAM_TARGETS_JSON'])
    if not targets:
        raise RuntimeError('No hay destinatarios configurados.')
    failures = 0
    dirty = False
    for notice in state['pending']:
        for index, target in enumerate(targets):
            if index in notice['delivered']:
                continue
            try:
                send(notice['text'], target)
            except RuntimeError:
                failures += 1
                continue
            notice['delivered'].append(index)
            dirty = True
            storage.save(state)
    pending = [notice for notice in state['pending'] if len(notice['delivered']) < len(targets)]
    if pending != state['pending']:
        state['pending'] = pending
        dirty = True
    if dirty:
        storage.save(state)
    print('Comprobación externa finalizada:', sum(row['ok'] for row in readings.values()), '/', len(readings), 'webs disponibles.')
    if failures:
        raise SystemExit('Quedan avisos pendientes; se reintentarán en la próxima ejecución.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Falló el vigilante externo. Revisar conectividad o configuración; no se muestran credenciales.') from None

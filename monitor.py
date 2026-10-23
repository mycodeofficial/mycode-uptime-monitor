#!/usr/bin/env python3
"""Vigilante ejecutado en GitHub, independiente del servidor de las webs."""
import base64
import concurrent.futures
import copy
import datetime
import json
import os
from zoneinfo import ZoneInfo
import time
import urllib.error
import urllib.request
from functional_checks import SITES, check
from second_opinion import corroborate

STATE_FILE = '.monitor-state.json'


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def probe(item):
    name, url = item
    for attempt in range(3):
        result = check(name, url)
        if result['ok'] is True:
            return name, result
        if attempt < 2:
            time.sleep(10)
    if result['ok'] is False:
        opinion = corroborate(result.get('url', url), result.get('expected'))
        result['evidence'] = opinion['detail']
        if opinion['ok'] is not False:
            result['ok'] = None
    return name, result


def transition(previous, readings, now):
    """Una alerta por web tras dos ejecuciones fallidas, tres intentos por ejecución."""
    state = copy.deepcopy(previous)
    state.setdefault('services', {})
    state.setdefault('pending', [])
    state.setdefault('next_id', 1)
    state.setdefault('candidates', {})
    state.setdefault('candidate_since', {})
    state.setdefault('last_failure_check', {})
    for name, reading in readings.items():
        old = state['services'].get(name)
        if reading['ok'] is None:
            state['candidates'][name] = 0
            state['candidate_since'].pop(name, None)
            state['last_failure_check'].pop(name, None)
            continue
        last = state['last_failure_check'].get(name)
        consecutive = last and 60 <= (now - datetime.datetime.fromisoformat(last)).total_seconds() <= 1800
        count = 0 if reading['ok'] else min(2, (state['candidates'].get(name, 0) if consecutive else 0) + 1)
        if not reading['ok']:
            if not consecutive:
                state['candidate_since'][name] = now.isoformat()
            state['last_failure_check'][name] = now.isoformat()
        else:
            state['last_failure_check'].pop(name, None)
            state['candidate_since'].pop(name, None)
        state['candidates'][name] = count
        unseen_down = any(n.get('service') == name and n.get('kind') == 'down' and not n.get('delivered') for n in state['pending'])
        # Cancelar avisos de caída pendientes si la web ya responde.
        if reading['ok']:
            state['pending'] = [n for n in state['pending']
                                if not (n.get('service') == name and n.get('kind') == 'down')]
        if not reading['ok'] and count < 2:
            continue
        if old is None or old['ok'] != reading['ok']:
            message = None
            if not reading['ok']:
                started = state['candidate_since'].get(name, now.isoformat())
                message = ('🔴 La web ' + name + ' está fallando.\n'
                           + reading.get('error', 'No se puede acceder correctamente a la web.')
                           + '\nLo observo desde: ' + datetime.datetime.fromisoformat(started).astimezone(ZoneInfo('Europe/Madrid')).strftime('%d/%m %H:%M')
                           + '\nHe repetido las pruebas y también falla desde: '
                           + reading.get('evidence', 'otras dos ubicaciones')
                           + '\n' + SITES[name])
            elif old and not old['ok'] and not unseen_down:
                minutes = max(0, int((now - datetime.datetime.fromisoformat(old['since'])).total_seconds() // 60))
                message = '✅ La web ' + name + ' vuelve a funcionar.\nDuración observada: ' + str(minutes) + ' min.'
            if message:
                state['pending'].append({'id': state['next_id'], 'text': message,
                                         'service': name, 'kind': 'up' if reading['ok'] else 'down', 'delivered': []})
                state['next_id'] += 1
            state['services'][name] = {**reading, 'since': state['candidate_since'].get(name, now.isoformat()) if not reading['ok'] else now.isoformat()}
    # Una fecha antigua describe el monitor, nunca una caída del servidor.
    state['server_unreachable'] = False
    if previous.get('last_checked', '')[:10] != now.isoformat()[:10]:
        state['last_checked'] = now.isoformat()
    return state, state != previous


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
    for name, reading in readings.items():
        label = 'disponible' if reading['ok'] is True else 'fallo observado' if reading['ok'] is False else 'resultado sin confirmar'
        print(name + ': ' + label + (' · ' + reading.get('evidence', reading.get('error', '')) if reading['ok'] is not True else ''))
    print('Comprobación externa finalizada:', sum(row['ok'] is True for row in readings.values()), '/', len(readings), 'webs disponibles.')
    if failures:
        raise SystemExit('Quedan avisos pendientes; se reintentarán en la próxima ejecución.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Falló el vigilante externo. Revisar conectividad o configuración; no se muestran credenciales.') from None

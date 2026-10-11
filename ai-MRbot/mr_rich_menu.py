"""Install the approved four-button MR menu using the server's LINE token."""
import base64
import logging
import os
from pathlib import Path
import threading
import requests

NAME = 'MR four buttons 2026-10-11 v1'
LABELS = ['生活助理', '官方網站', '查資料', '電子名片模板參考']
STATUS = {'installed': False, 'state': 'pending', 'buttons': LABELS}
_STARTED = False


def menu_payload():
    actions = [
        {'type': 'message', 'label': LABELS[0], 'text': '生活助理'},
        {'type': 'uri', 'label': LABELS[1], 'uri': 'https://mrbusinesslab.github.io/official/index.html'},
        {'type': 'message', 'label': LABELS[2], 'text': '查資料'},
        {'type': 'message', 'label': LABELS[3], 'text': '展示'},
    ]
    return {'size': {'width': 1200, 'height': 810}, 'selected': True,
            'name': NAME, 'chatBarText': '功能選單', 'areas': [
                {'bounds': {'x': i % 2 * 600, 'y': i // 2 * 405,
                            'width': 600, 'height': 405}, 'action': action}
                for i, action in enumerate(actions)]}


def install():
    token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '')
    if not token:
        raise RuntimeError('LINE configuration missing')
    headers = {'Authorization': 'Bearer ' + token}
    base = 'https://api.line.me/v2/bot'
    def api(method, path, **kwargs):
        response = requests.request(method, base + path, headers=headers,
                                    timeout=(3, 10), **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
    payload = menu_payload()
    menus = api('GET', '/richmenu/list').get('richmenus', [])
    menu = next((m for m in menus if m.get('name') == NAME), None)
    created = menu is None
    if menu is None:
        api('POST', '/richmenu/validate', json=payload)
        menu = api('POST', '/richmenu', json=payload)
    mid = menu['richMenuId']
    data = base64.b64decode((Path(__file__).parent / 'data/mr_four_menu.b64').read_text())
    if not created:
        content = requests.get('https://api-data.line.me/v2/bot/richmenu/' + mid + '/content',
                               headers=headers, timeout=(3, 10))
        if content.status_code == 404: created = True
        else: content.raise_for_status()
    if created:
        upload = requests.post('https://api-data.line.me/v2/bot/richmenu/' + mid + '/content',
                               headers={**headers, 'Content-Type': 'image/png'}, data=data,
                               timeout=(3, 10))
        upload.raise_for_status()
    # Update the default and existing MR/Ruru overrides, which otherwise hide it.
    api('POST', '/user/all/richmenu/' + mid)
    members = {os.getenv('LIFEOS_GOOGLE_USER_ID', ''),
               'U6ae8eac2d8623b7b2ca26d443345e5f6'} - {''}
    for uid in members:
        api('POST', '/user/' + uid + '/richmenu/' + mid)
        if api('GET', '/user/' + uid + '/richmenu').get('richMenuId') != mid:
            raise RuntimeError('Personal menu verification failed')
    if api('GET', '/user/all/richmenu').get('richMenuId') != mid:
        raise RuntimeError('Default menu verification failed')
    saved = api('GET', '/richmenu/' + mid)
    if saved.get('areas') != payload['areas']:
        raise RuntimeError('Menu actions verification failed')
    STATUS.update(installed=True, state='verified', personal_menus_verified=len(members))
    logging.getLogger(__name__).warning('MR four-button rich menu installed and verified')


def start(app):
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    app.add_url_rule('/mr/menu-status', 'mr_menu_status', lambda: dict(STATUS))
    def run():
        try:
            install()
        except Exception as exc:
            STATUS.update(state='failed')
            # Do not log access tokens or response/request bodies.
            logging.getLogger(__name__).error('MR menu installation failed: %s', type(exc).__name__)
    thread = threading.Thread(target=run, daemon=True, name='mr-menu-setup')
    thread.start()

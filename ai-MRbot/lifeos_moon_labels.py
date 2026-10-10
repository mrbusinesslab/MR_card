"""One-time named labels for the user-approved October MOON import."""
import threading
from urllib.parse import quote

CALENDAR = 'ca1f00e31ae893419db55626596e7ce9a27fb9f6893547d4d03b9ccf6514333f@group.calendar.google.com'
TARGETS = [{"id":"8tvocpa2hk7aruqimlnduu2kn8","title":"許鳳珊F","label":"美容美體"},{"id":"c5bhn5eif2u8nqgb06fcptjj8c","title":"許鳳珊F","label":"美容美體"},{"id":"ol1tkei9p62hbtj6ovff4r62lc","title":"講座","label":"講座"},{"id":"fejf76rc6s64cv96f6esfj6dko","title":"🏠吳佳蓉B","label":"美容美體"},{"id":"gulpdofmkvmva79mratr6c4s50","title":"👨🏻Yumi老公B","label":"新客"},{"id":"oncldvg4t6mtlku9c2td08qbb0","title":"🏠陳婉文F","label":"美容美體"},{"id":"n048rf6jpiihvi7m5afigup0us","title":"潘順如F","label":"美容美體"},{"id":"k1lofh6a135sf93k4207uke15k","title":"楊雪嵐B","label":"美容美體"},{"id":"jtdsdgn64dqn0frge52b1p2qv0","title":"美儀 B","label":"美容美體"},{"id":"fdklqv213lhnc0s0pduh55fpok","title":"🏠小孟","label":"美容美體"}]
TARGETS += [{"id":"ncmfrcdfe1mluee29jmqjjeons","title":"均均休假","label":"均均休假"},{"id":"rgk5ikvdt6e7g2v4go8hivq9fg","title":"均均休假","label":"均均休假"},{"id":"pocilppksvh33bjt7d10b4g6o0","title":"均均休假","label":"均均休假"},{"id":"0jmfr4ldnush8pogp9qghsl1eo","title":"均均休假","label":"均均休假"},{"id":"ks58m5uti6uamjtm4ki3tsc50c","title":"均均休假","label":"均均休假"},{"id":"ufc597lepmn42avfh2sa0ksfg8","title":"均均休假","label":"均均休假"},{"id":"ap9l0ha46ig9gdceegaf8144n8","title":"均均休假","label":"均均休假"},{"id":"1ki3mm50efocdrsprvl98sf6mo","title":"均均休假","label":"均均休假"},{"id":"e33906k1lrhs1rtuq3usru5s50","title":"均均休假","label":"均均休假"}]
MARKER = 'moon_202610_labels_v1'

def run(c, logger):
    _, cal, owner = c.config()
    if cal != CALENDAR or not owner: return
    labels = {x.get('name'):x['id'] for x in c.event_labels() if x.get('name')}
    for target in TARGETS:
        try:
            event = c.call('GET','/'+quote(target['id'],safe=''),params={'eventLabelVersion':1})
            if event.get('status') == 'cancelled': continue
            private = event.get('extendedProperties',{}).get('private',{})
            if not private.get(MARKER):
                if event.get('summary') != target['title'] or 'TimeTree UID' not in event.get('description',''): continue
                label = labels.get(target['label'])
                if not label or not event.get('etag'): continue
                extended = c.actor_metadata(event,owner)
                extended['private'][MARKER] = 'done'
                extended['private']['lifeos_category'] = {'新客':'新客','美容美體':'美容','講座':'講座','均均休假':'其他'}[target['label']]
                c.call('PATCH','/'+quote(target['id'],safe=''),body={'eventLabelId':label,'extendedProperties':extended},params={'sendUpdates':'none'},etag=event['etag'])
                verified=c.call('GET','/'+quote(target['id'],safe=''),params={'eventLabelVersion':1})
                if verified.get('eventLabelId') != label: raise RuntimeError('label verification failed')
            # Register imports for existing Life OS edit/cancel authorization.
            c.l.gateway('calendar_save',owner,calendar_id=cal,event_id=target['id'],title=event.get('summary',target['title']))
            logger.info('MOON import label/index verified: %s',target['id'])
        except Exception:
            logger.exception('MOON import label/index migration failed: %s',target['id'])

def start(c,logger):
    threading.Thread(target=run,args=(c,logger),daemon=True,name='moon-label-import').start()

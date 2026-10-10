"""Private, signed weekly calendar snapshots for LINE image messages."""
import hashlib
import hmac
import io
import os
import re
import secrets
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

FONT_URL='https://raw.githubusercontent.com/google/fonts/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf'
ROOT=Path(tempfile.gettempdir())/'lifeos-week-images'

def font(size):
    path=Path(tempfile.gettempdir())/'lifeos-noto.ttf'
    if not path.exists():
        response=requests.get(FONT_URL,timeout=20)
        response.raise_for_status()
        if len(response.content)>20000000: raise ValueError('font_too_large')
        temporary=path.with_name('lifeos-font-'+secrets.token_hex(8))
        temporary.write_bytes(response.content)
        os.replace(temporary,path)
    result=ImageFont.truetype(str(path),size)
    result.set_variation_by_axes([400])
    return result

def week_events(start,end):
    import lifeos_calendar as c
    params={'timeMin':start.isoformat(),'timeMax':end.isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':250,'eventLabelVersion':1}
    events=[]
    for _ in range(10):
        result=c.call('GET',params=params)
        events.extend(e for e in result.get('items',[]) if e.get('status')!='cancelled')
        token=result.get('nextPageToken')
        if not token: return events
        params={**params,'pageToken':token}
    raise c.CalendarError('incomplete_week')

def event_days(event,start,end):
    import lifeos as l
    import lifeos_calendar as c
    from datetime import datetime
    a=event.get('start',{}); b=event.get('end',{})
    if a.get('dateTime'):
        left=c.instant(a['dateTime']).astimezone(l.TZ)
        right=c.instant(b['dateTime']).astimezone(l.TZ)
        stamp=left.strftime('%H:%M')+'～'+right.strftime('%H:%M')
    elif a.get('date'):
        left=datetime.fromisoformat(a['date']).replace(tzinfo=l.TZ)
        right=datetime.fromisoformat(b['date']).replace(tzinfo=l.TZ)
        stamp='全天'
    else: return []
    result=[]
    for index in range(7):
        day=start+timedelta(days=index)
        if left<day+timedelta(days=1) and right>day:
            result.append((index,stamp if left.date()==day.date() or stamp=='全天' else '跨日行程'))
    return result

def render_week(events,start,now,label_colors=None):
    import lifeos as l
    label_colors=label_colors or {}
    body_font=font(27); small_font=font(23); heading_font=font(32)
    measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
    columns=[[] for _ in range(7)]
    for event in events:
        title=event.get('summary') or '未命名行程'
        wrapped=[]; line=''
        for character in title:
            if character=='\n' or measure.textlength(line+character,font=body_font)>244:
                if line: wrapped.append(line)
                line='' if character=='\n' else character
            else: line+=character
        if line: wrapped.append(line)
        group=event.get('extendedProperties',{}).get('private',{}).get('lifeos_category')
        color=label_colors.get(event.get('eventLabelId')) or l.category_ink(title,group)
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}',color): color='#345C58'
        for index,stamp in event_days(event,start,start+timedelta(days=7)):
            columns[index].append((stamp,wrapped or ['未命名行程'],color))
    heights=[sum(44+len(lines)*39+22 for _,lines,_ in column) for column in columns]
    width=2100; height=max(570,230+max(heights,default=0))
    if height>10000: raise ValueError('weekly_image_too_tall')
    canvas=Image.new('RGB',(width,height),'white'); draw=ImageDraw.Draw(canvas)
    draw.text((30,20),'本週行程  '+start.strftime('%m/%d')+'－'+(start+timedelta(days=6)).strftime('%m/%d'),font=heading_font,fill='#172B2A')
    draw.text((30,70),'更新時間 '+now.strftime('%Y/%m/%d %H:%M')+'｜台北時間',font=small_font,fill='#64748B')
    for index,column in enumerate(columns):
        x=index*300; day=start+timedelta(days=index)
        if day.date()==now.date(): draw.rectangle((x,118,x+299,height-1),fill='#F3F8FB')
        draw.line((x,118,x,height),fill='#DCE3EB',width=2)
        draw.text((x+95,130),'週'+'一二三四五六日'[index],font=heading_font,fill='#172B2A')
        draw.text((x+110,180),day.strftime('%m/%d'),font=small_font,fill='#64748B')
        y=244
        if not column: draw.text((x+82,y),'沒有行程',font=small_font,fill='#94A3B8')
        for stamp,lines,color in column:
            draw.ellipse((x+18,y+9,x+30,y+21),fill=color)
            draw.text((x+40,y),stamp,font=small_font,fill='#475569'); y+=40
            for line in lines:
                draw.text((x+40,y),line,font=body_font,fill='#172B2A'); y+=39
            y+=26
    draw.line((0,225,width,225),fill='#DCE3EB',width=2)
    output=io.BytesIO(); canvas.save(output,format='PNG',optimize=True)
    return output.getvalue()

def signature(key,expires):
    secret=os.getenv('LIFEOS_CRON_KEY','')
    if not secret: raise ValueError('image_signing_not_configured')
    return hmac.new(secret.encode(),(key+':'+str(expires)).encode(),hashlib.sha256).hexdigest()

def weekly_message(user_id,now,period='week'):
    import lifeos as l
    import lifeos_calendar as c
    from linebot.v3.messaging import ImageMessage
    _,cal,approved=c.config()
    if not cal or not c.calendar_access(user_id): return None
    start,end=l.period_bounds(now,period)
    events=c.visible_events(user_id,week_events(start,end))
    try: colors={x['id']:x.get('backgroundColor') for x in c.event_labels()}
    except c.CalendarError: colors={}
    if period=='month':
        from lifeos_month_image import render_month
        data=render_month(events,start,now,colors)
    else: data=render_week(events,start,now,colors)
    ROOT.mkdir(mode=0o700,exist_ok=True)
    for old in ROOT.glob('*.png'):
        try:
            if old.stat().st_mtime<time.time()-7*86400: old.unlink()
        except OSError: pass
    key=secrets.token_hex(24); expires=int(time.time())+7*86400
    sig=signature(key,expires)
    (ROOT/(key+'.png')).write_bytes(data)
    base=os.getenv('LIFEOS_PUBLIC_BASE_URL','https://mr-6c1r.onrender.com').rstrip('/')
    url=base+'/lifeos/week-image/'+key+'.png?expires='+str(expires)+'&signature='+sig
    return ImageMessage(original_content_url=url,preview_image_url=url)

def install_routes(app):
    from flask import request,Response
    @app.get('/lifeos/week-image/<key>.png')
    def week_image(key):
        if not re.fullmatch(r'[0-9a-f]{48}',key): return '',404
        try:
            expires=int(request.args.get('expires','0'))
            if not time.time()<expires<=time.time()+7*86400+60: return '',404
            if not hmac.compare_digest(request.args.get('signature',''),signature(key,expires)): return '',404
            data=(ROOT/(key+'.png')).read_bytes()
        except (ValueError,OSError): return '',404
        return Response(data,mimetype='image/png',headers={'Cache-Control':'private, max-age=3600','X-Content-Type-Options':'nosniff'})

"""Monday-first monthly calendar image, preserving named Google label colors."""
import calendar
import io
import re
from datetime import timedelta
from PIL import Image,ImageDraw
import lifeos_week_image as w

def render_month(events,start,now,label_colors=None):
    import lifeos as l
    colors=label_colors or {}
    weeks=calendar.Calendar(firstweekday=0).monthdatescalendar(start.year,start.month)
    body=w.font(27);small=w.font(23);heading=w.font(36)
    measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
    rows=[]
    for dates in weeks:
        row=[[] for _ in range(7)]
        week=start.replace(day=1)+timedelta(days=(dates[0]-start.date()).days)
        for event in events:
            title=re.sub(r'[\U0001F300-\U0001FAFF\ufe0f\u200d]','',event.get('summary') or '').strip() or '未命名行程';wrapped=[];line=''
            for ch in title:
                if ch=='\n' or measure.textlength(line+ch,font=body)>245:
                    if line:wrapped.append(line)
                    line='' if ch=='\n' else ch
                else:line+=ch
            if line:wrapped.append(line)
            group=event.get('extendedProperties',{}).get('private',{}).get('lifeos_category')
            color=colors.get(event.get('eventLabelId')) or l.category_ink(title,group)
            if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):color='#345C58'
            for idx,stamp in w.event_days(event,week,week+timedelta(days=7)):
                if dates[idx].month==start.month:row[idx].append((stamp,wrapped or ['未命名行程'],color))
        height=max(280,75+max((sum(38+len(lines)*38+22 for _,lines,_ in cell) for cell in row),default=0))
        rows.append((dates,row,height))
    height=165+sum(x[2] for x in rows)
    if height>10000:raise ValueError('monthly_image_too_tall')
    image=Image.new('RGB',(2100,height),'white');draw=ImageDraw.Draw(image)
    draw.text((30,18),f'本月行程  {start.year}年{start.month}月',font=heading,fill='#172B2A')
    draw.text((30,73),'更新時間 '+now.strftime('%Y/%m/%d %H:%M')+'｜台北時間',font=small,fill='#64748B')
    for idx in range(7):draw.text((idx*300+106,119),'週'+'一二三四五六日'[idx],font=body,fill='#172B2A')
    y=165
    for dates,row,h in rows:
        for idx,day in enumerate(dates):
            x=idx*300
            if day.month!=start.month:draw.rectangle((x,y,x+299,y+h-1),fill='#F7F8FA')
            elif day==now.date():draw.rectangle((x,y,x+299,y+h-1),fill='#EEF7FE')
            draw.rectangle((x,y,x+299,y+h),outline='#DCE3EB',width=2)
            draw.text((x+18,y+12),str(day.day),font=body,fill='#172B2A' if day.month==start.month else '#ADB5C0')
            pos=y+62
            for stamp,lines,color in row[idx]:
                draw.ellipse((x+16,pos+8,x+28,pos+20),fill=color)
                draw.text((x+38,pos),stamp,font=small,fill='#475569');pos+=38
                for line in lines:draw.text((x+38,pos),line,font=body,fill='#172B2A');pos+=38
                pos+=22
        y+=h
    output=io.BytesIO();image.save(output,format='PNG',optimize=True);return output.getvalue()

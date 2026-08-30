import os
import json
from difflib import SequenceMatcher
from datetime import date
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

configuration = Configuration(access_token=os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

CASE_LIST = [
    {"case":"case1_小如如","num":1,"keyword":"小如如","alt":"小如如｜MR.主理人","name_keywords":["小如如","潘昱如","潘 昱如"],"industry_keywords":["顧問","建築組","個人服務","美容美體","如妍美學","MN13"]},
    {"case":"case2_鍾師富","num":2,"keyword":"鍾師富","alt":"鍾師富｜詠順工程行老闆","name_keywords":["鍾師富","鍾一德","鍾 一德"],"industry_keywords":["建築組","防水","防風雨","抓漏","詠順工程行"]},
    {"case":"case3_emma","num":3,"keyword":"emma","alt":"Emma｜大象木地板","name_keywords":["emma","Emma","吳玫勳","吳 玫勳","大象木地板"],"industry_keywords":["建築組","地板","大象木地板","廣德地板企業有限公司"]},
    {"case":"case4_傑哥","num":4,"keyword":"傑哥","alt":"蘇祺傑｜傑出油漆工程行","name_keywords":["傑哥","蘇祺傑","蘇 祺傑"],"industry_keywords":["建築組","油漆","粉刷師","裝飾師","傑出油漆"]},
    {"case":"case5_一昌","num":5,"keyword":"一昌","alt":"蔡一昌｜平衡之道-財務規劃師","name_keywords":["一昌","蔡一昌","蔡 一昌"],"industry_keywords":["房地產服務","房地產投資","財務規劃","金融","富屋"]},
    {"case":"case6_寧寧","num":6,"keyword":"寧寧","alt":"寧寧｜雅如詩品牌經營人","name_keywords":["寧寧","吳芷寧","吳 芷寧"],"industry_keywords":["個人服務","頭皮理療","SPA","雅如詩","森莫"]},
    {"case":"case7_雙雙","num":7,"keyword":"雙雙","alt":"品雙｜葡眾健康顧問","name_keywords":["雙雙","高品雙","高 品雙"],"industry_keywords":["健康","保健","保健品","葡眾企業股份有限公司"]},
    {"case":"case8_林威","num":8,"keyword":"林威","alt":"林威｜amomris業務經理","name_keywords":["林威"],"industry_keywords":["健康","保健食品","amomris","Amomris"]},
    {"case":"case9_昺諺","num":9,"keyword":"昺諺","alt":"賴昺諺｜兆朋工程","name_keywords":["昺諺","賴昺諺","賴 昺諺"],"industry_keywords":["建築組","裝修","改造","清運","兆朋工程股份有限公司"]},
    {"case":"case10_竹勝","num":10,"keyword":"竹勝","alt":"周竹勝｜Paradiso爬樓梯創辦人","name_keywords":["竹勝","周竹勝","周 竹勝"],"industry_keywords":["食品&飲料","餐飲服務","爬樓梯","必昇有限公司"]},
    {"case":"case11_耀宗","num":11,"keyword":"耀宗","alt":"王耀宗｜健康管理顧問","name_keywords":["耀宗","王耀宗","王 耀宗"],"industry_keywords":["健康","保健品","蘆薈汁","永久產品公司"]},
    {"case":"case12_凱程","num":12,"keyword":"凱程","alt":"阮凱程｜耕家實業公司經理","name_keywords":["凱程","阮凱程","阮 凱程"],"industry_keywords":["建築組","裝修","改造","裝潢","耕家"]},
    {"case":"case13_致為","num":13,"keyword":"致為","alt":"黃致為｜蒔旭科技","name_keywords":["致為","小捲","黃致為","黃 致為"],"industry_keywords":["電腦&程式設計","資訊科技顧問","蒔旭有限公司"]},
    {"case":"case14_一晉","num":14,"keyword":"一晉","alt":"邱一晉｜尚晉通信","name_keywords":["一晉","邱一晉","邱 一晉"],"industry_keywords":["建築組","電工","電工-商業","尚晉通科技企業社"]},
    {"case":"case16_齊齊","num":16,"keyword":"齊齊","alt":"游宛齊｜馬鹿整合廣告","name_keywords":["齊齊","游宛齊","游 宛齊"],"industry_keywords":["廣告&行銷","廣告招牌輸出","馬鹿整合廣告股份有限公司"]},
    {"case":"case17_重凱","num":17,"keyword":"重凱","alt":"王重凱｜鉅沅管理顧問","name_keywords":["重凱","王重凱","王 重凱"],"industry_keywords":["金融&保險","金融投資","金融","鉅沅管理顧問有限公司"]},
]

DEMO_KEYWORDS=["小如如","寧寧","鍾師富","傑哥","林威","竹勝"]
RECENTLY_ADDED_COUNT=2
CATEGORY_QUICK_REPLIES=[("建築組","建築組"),("健康","健康"),("美業","個人服務"),("食品飲料","食品&飲料"),("金融","金融")]
CASE_BY_KEYWORD={c["keyword"]:c for c in CASE_LIST}
PENDING_SEARCH_USERS=set()
RECENT_VIEWS={}
RECENT_VIEWS_LIMIT=8

def record_view(user_id,case_item):
    items=RECENT_VIEWS.setdefault(user_id,[]); kw=case_item["keyword"]
    if kw in items: items.remove(kw)
    items.insert(0,kw); del items[RECENT_VIEWS_LIMIT:]

def load_flex(filepath):
    base_dir=os.path.dirname(os.path.abspath(__file__)); full_path=os.path.join(base_dir,"templates",filepath)
    if not os.path.exists(full_path): return None
    with open(full_path,"r",encoding="utf-8") as f: content=f.read()
    today=date.today().strftime("%Y%m%d"); content=content.replace("?raw=true",f"?raw=true&v={today}")
    return json.loads(content)

def load_liff(filepath):
    base_dir=os.path.dirname(os.path.abspath(__file__)); full_path=os.path.join(base_dir,"templates",filepath)
    with open(full_path,"r",encoding="utf-8") as f: content=f.read()
    today=date.today().strftime("%Y%m%d"); return content.replace("?raw=true",f"?raw=true&v={today}")

def build_card_message(case_item):
    filepath=f"{case_item['case']}/card_{case_item['case'].split('_',1)[1]}.json"; flex_data=load_flex(filepath)
    if flex_data: return FlexMessage(alt_text=case_item["alt"],contents=FlexContainer.from_dict(flex_data))
    return TextMessage(text="抱歉，名片檔案讀取失敗")

def search_cases(query):
    query=query.strip(); matched=[]
    if not query:return []
    for c in CASE_LIST:
        all_keywords=c["name_keywords"]+c["industry_keywords"]
        if any((query in kw) or (kw in query) for kw in all_keywords):matched.append(c)
    return matched

def normalize_name(text): return "".join(text.split()).lower()
def fuzzy_search_cases(query,threshold=0.5,limit=3):
    q=normalize_name(query)
    if not q:return []
    scored=[]
    for c in CASE_LIST:
        kws=[c["keyword"]]+c["name_keywords"]
        best=max([SequenceMatcher(None,q,normalize_name(k)).ratio() for k in kws if normalize_name(k)] or [0])
        if best>=threshold:scored.append((best,c))
    scored.sort(key=lambda x:(-x[0],x[1]["num"])); return [c for _,c in scored[:limit]]

def get_demo_cases(): return [CASE_BY_KEYWORD[k] for k in DEMO_KEYWORDS if k in CASE_BY_KEYWORD]
def build_list_flex(alt_text,header_text,matched_cases):
    rows=[]
    for c in matched_cases:
        rows.append({"type":"box","layout":"horizontal","spacing":"md","action":{"type":"message","label":c["alt"][:20],"text":c["keyword"]},"contents":[{"type":"box","layout":"vertical","width":"36px","height":"36px","cornerRadius":"18px","backgroundColor":"#473C38","justifyContent":"center","alignItems":"center","contents":[{"type":"text","text":str(c["num"]),"color":"#F8EED2","size":"sm","weight":"bold","align":"center"}]},{"type":"box","layout":"vertical","flex":1,"contents":[{"type":"text","text":c["alt"],"size":"sm","weight":"bold","color":"#473C38","wrap":True},{"type":"text","text":"・".join(c["industry_keywords"][:3]),"size":"xs","color":"#888888","wrap":True}]}]}); rows.append({"type":"separator","margin":"md"})
    if rows:rows.pop()
    bubble={"type":"bubble","size":"mega","body":{"type":"box","layout":"vertical","backgroundColor":"#FFFFFF","paddingAll":"16px","spacing":"md","contents":[{"type":"text","text":header_text,"size":"xs","color":"#888888"},{"type":"box","layout":"vertical","spacing":"md","contents":rows}]}}
    return FlexMessage(alt_text=alt_text,contents=FlexContainer.from_dict(bubble))
def build_search_result_flex(query,matched_cases):return build_list_flex(f"{query} 搜尋結果",f"「{query}」搜尋結果，共 {len(matched_cases)} 筆",matched_cases)
def build_suggestion_flex(query,suggested_cases):return build_list_flex("你可能想找的電子名片",f"找不到「{query}」，你是不是想找：",suggested_cases)
def build_demo_flex():
    d=get_demo_cases(); return build_list_flex("案例展示清單",f"案例展示清單，共 {len(d)} 筆",d)
def get_recently_added_cases():return sorted(CASE_LIST,key=lambda c:c["num"],reverse=True)[:RECENTLY_ADDED_COUNT]
def build_recent_flex(user_id):
    kws=RECENT_VIEWS.get(user_id,[]); cases=[CASE_BY_KEYWORD[k] for k in kws if k in CASE_BY_KEYWORD]
    for c in get_recently_added_cases():
        if c not in cases:cases.append(c)
    cases=cases[:RECENT_VIEWS_LIMIT]; return build_list_flex("最近查看的名片",f"最近查看的名片，共 {len(cases)} 筆",cases)

@app.route("/cases")
def cases(): return "MR Bot",200
@app.route("/callback",methods=["POST"])
def callback():
    signature=request.headers.get('X-Line-Signature'); body=request.get_data(as_text=True)
    try:handler.handle(body,signature)
    except InvalidSignatureError:abort(400)
    return 'OK'

@app.route("/liff/case1/小如如")
def liff_小如如():return load_liff("case1_小如如/liff_小如如.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case2/鍾師富")
def liff_鍾師富():return load_liff("case2_鍾師富/liff_鍾師富.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case3/emma")
def liff_emma():return load_liff("case3_emma/liff_emma.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case4/傑哥")
def liff_傑哥():return load_liff("case4_傑哥/liff_傑哥.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case5/一昌")
def liff_一昌():return load_liff("case5_一昌/liff_一昌.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case6/寧寧")
def liff_寧寧():return load_liff("case6_寧寧/liff_寧寧.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case7/雙雙")
def liff_雙雙():return load_liff("case7_雙雙/liff_雙雙.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case8/林威")
def liff_林威():return load_liff("case8_林威/liff_林威.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case9/昺諺")
def liff_昺諺():return load_liff("case9_昺諺/liff_昺諺.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case10/竹勝")
def liff_竹勝():return load_liff("case10_竹勝/liff_竹勝.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case11/耀宗")
def liff_耀宗():return load_liff("case11_耀宗/liff_耀宗.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case12/凱程")
def liff_凱程():return load_liff("case12_凱程/liff_凱程.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case13/致為")
def liff_致為():return load_liff("case13_致為/liff_致為.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case14/一晉")
def liff_一晉():return load_liff("case14_一晉/liff_一晉.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case16/齊齊")
def liff_齊齊():return load_liff("case16_齊齊/liff_齊齊.html"),200,{"Content-Type":"text/html; charset=utf-8"}
@app.route("/liff/case17/重凱")
def liff_重凱():return load_liff("case17_重凱/liff_重凱.html"),200,{"Content-Type":"text/html; charset=utf-8"}

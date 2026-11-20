import json,re
def pages(path):
    t=open(path,encoding='utf-8').read(); dec=json.JSONDecoder(); out={}
    for m in re.finditer(r'WH\.setPageData\("([^"]+)",',t):
        obj,_=dec.raw_decode(t,m.end()); out[m.group(1)]=obj
    return out

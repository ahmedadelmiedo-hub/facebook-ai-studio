import json, os, pathlib, urllib.request

ROOT = pathlib.Path(__file__).parent
CONFIG = json.loads((ROOT / 'channel.json').read_text(encoding='utf-8'))
QUEUE = json.loads((ROOT / 'queue.json').read_text(encoding='utf-8'))
API_KEY = os.environ.get('GROQ_API_KEY', '').strip()
if not API_KEY:
    raise SystemExit('Missing GROQ_API_KEY GitHub Actions secret')
episode = next((x for x in QUEUE['episodes'] if x['status'] == 'queued'), None)
if not episode:
    raise SystemExit('No queued episode found')
prompt = f'''اكتب سيناريو وثائقيًا عربيًا أصليًا لقناة {CONFIG['channel_name']}.
الموضوع: {episode['topic']}. العنوان: {episode['title']}.
الأسلوب: مزيج من الوثائقي المشوق والسرد القصصي، بصوت راوٍ رجالي.
اكتب افتتاحية قوية، ثم 6 إلى 8 مشاهد متسلسلة، وخاتمة. اجعل المعلومات العلمية دقيقة، ولا تختلق حقائق أو أرقامًا أو اقتباسات. ضع [بحاجة إلى تحقق] بجوار أي معلومة غير مؤكدة. أضف وصفًا بصريًا لكل مشهد، ونصوصًا قصيرة على الشاشة، وثلاث أفكار Shorts في النهاية. اللغة عربية واضحة مناسبة للتعليق الصوتي.'''
payload = json.dumps({'model':'openai/gpt-oss-120b','messages':[{'role':'user','content':prompt}],'temperature':0.6,'max_completion_tokens':7000},ensure_ascii=False).encode()
req = urllib.request.Request('https://api.groq.com/openai/v1/chat/completions',data=payload,headers={'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json','Accept':'application/json','User-Agent':'secrets-of-the-wilderness/1.0'},method='POST')
try:
    with urllib.request.urlopen(req, timeout=240) as response:
        data = json.loads(response.read().decode())
except urllib.error.HTTPError as exc:
    details = exc.read().decode('utf-8', errors='replace')
    raise SystemExit(f'Groq API returned HTTP {exc.code}: {details}') from None
script=data['choices'][0]['message']['content'].strip()
out=ROOT/'output'
out.mkdir(exist_ok=True)
(out/'episode-001-script.md').write_text('# '+episode['title']+'\n\n'+script+'\n',encoding='utf-8')
(out/'episode-001-metadata.json').write_text(json.dumps({'channel':CONFIG['channel_name'],'episode':episode,'generated_by':'Groq','review_required':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Created episode script and metadata in channels/secrets-of-the-wilderness/output')

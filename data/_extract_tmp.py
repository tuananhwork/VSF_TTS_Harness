import json

files = [
    'adoring-loving-dirac__9590c9ea-019.jsonl',
    'ecstatic-elegant-ramanujan__c740302f-169.jsonl',
    'busy-hopeful-knuth__902a32c7-7c3.jsonl',
]
base = 'C:/Users/chuba/Workspace/VSF/Pattern/data/sessions_2026-06-15_runAt_20260615-173114/'
for fn in files:
    print('=' * 20, fn, '=' * 20)
    for line in open(base + fn, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        role = o.get('role') or o.get('type') or ''
        c = o.get('content')
        texts = []
        if isinstance(c, str):
            texts.append(c)
        elif isinstance(c, list):
            for b in c:
                if not isinstance(b, dict):
                    continue
                t = b.get('type')
                if t == 'text':
                    texts.append(b.get('text', ''))
                elif t == 'tool_use':
                    texts.append('[USE ' + str(b.get('name')) + ' ' + json.dumps(b.get('input', {}), ensure_ascii=False)[:160] + ']')
                elif t == 'tool_result':
                    rc = b.get('content')
                    s = rc if isinstance(rc, str) else json.dumps(rc, ensure_ascii=False)
                    texts.append('[RES ' + str(s)[:140] + ']')
        blob = ' | '.join(x for x in texts if x).replace('\n', ' ')
        if blob.strip():
            print(role[:9].ljust(9), blob[:380])

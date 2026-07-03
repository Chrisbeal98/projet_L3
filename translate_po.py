"""
Traduction automatique rapide avec 3 sources en cascade + rate limiting.
"""
import os, sys, time, io, requests, json, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import write_mo

TRANS = r'C:\wamp\www\projet_L3\app\translations'
STATE_FILE = os.path.join(TRANS, '_traduction_state.json')
LANG_MAP = {'zh': 'zh-CN', 'epo': 'eo', 'he': 'iw', 'jw': 'jv', 'tl': 'fil'}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
]


def _headers():
    return {'User-Agent': random.choice(USER_AGENTS)}


def _try_translate(orig, target, retries=2):
    gt = LANG_MAP.get(target, target)
    # 1: Google Translate
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                'https://translate.googleapis.com/translate_a/single',
                params={'client': 'gtx', 'sl': 'fr', 'tl': gt, 'dt': 't', 'q': orig},
                headers=_headers(), timeout=15
            )
            if resp.ok:
                data = resp.json()
                if data and data[0] and data[0][0] and data[0][0][0]:
                    t = data[0][0][0]
                    if t.lower() != orig.lower():
                        return t
            if resp.status_code == 429:
                time.sleep((2 ** attempt) * random.uniform(0.5, 1.5))
                continue
        except:
            pass
        break
    time.sleep(0.3)
    # 2: MyMemory
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                'https://api.mymemory.translated.net/get',
                params={'q': orig, 'langpair': f'fr|{gt}'},
                headers=_headers(), timeout=15
            )
            if resp.ok:
                data = resp.json()
                t = data.get('responseData', {}).get('translatedText', '')
                if t and t.lower() != orig.lower():
                    return t
            if resp.status_code == 429:
                time.sleep((2 ** attempt) * random.uniform(0.5, 1.5))
                continue
        except:
            pass
        break
    time.sleep(0.3)
    # 3: LibreTranslate
    for url in ('https://libretranslate.com', 'https://translate.argosopentech.com'):
        for attempt in range(retries + 1):
            try:
                resp = requests.post(f'{url}/translate',
                    json={'q': orig, 'source': 'fr', 'target': gt},
                    headers={'Content-Type': 'application/json'}, timeout=15)
                if resp.ok:
                    t = resp.json().get('translatedText', '')
                    if t and t.lower() != orig.lower():
                        return t
                if resp.status_code == 429:
                    time.sleep((2 ** attempt) * random.uniform(0.5, 1.5))
                    continue
            except:
                pass
            break
        time.sleep(0.2)
    return ''


def translate_texts(texts, target):
    if not texts:
        return {}
    results = {}
    # Process in smaller batches with delay between batches
    batch_size = 20
    with ThreadPoolExecutor(max_workers=5) as pool:
        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start:batch_start + batch_size]
            fut_map = {pool.submit(_try_translate, t, target): t for t in batch}
            for f in as_completed(fut_map):
                orig = fut_map[f]
                t = f.result()
                if t:
                    results[orig] = t
            time.sleep(random.uniform(0.15, 0.4))  # delay between batches
    return results


def process_language(lang):
    po_path = os.path.join(TRANS, lang, 'LC_MESSAGES', 'messages.po')
    if not os.path.exists(po_path):
        return None
    with open(po_path, 'rb') as f:
        cat = read_po(f)
    to_translate, msg_map = [], {}
    for m in cat:
        if m.id and not m.pluralizable:
            mid, mstr = m.id, m.string
            if isinstance(mid, str) and isinstance(mstr, str) and mstr == mid:
                to_translate.append(mid)
                msg_map[mid] = m
    if not to_translate:
        return 0
    translations = translate_texts(to_translate, lang)
    if not translations:
        return -1
    for msgid, trans in translations.items():
        if msgid in msg_map:
            msg_map[msgid].string = trans
    buf = io.BytesIO()
    write_po(buf, cat)
    with open(po_path, 'wb') as f:
        f.write(buf.getvalue())
    mo_path = po_path.replace('.po', '.mo')
    with open(po_path, 'rb') as f:
        new_cat = read_po(f)
    with open(mo_path, 'wb') as f:
        write_mo(f, new_cat)
    return len(translations)


def compile_mo_only(po_path):
    try:
        mo_path = po_path.replace('.po', '.mo')
        with open(po_path, 'rb') as f:
            cat = read_po(f)
        with open(mo_path, 'wb') as f:
            write_mo(f, cat)
        return True
    except:
        return False


def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'done': [], 'fr_only': [], 'failed': []}


def can_translate(lang):
    gt = LANG_MAP.get(lang, lang)
    try:
        resp = requests.get(
            'https://translate.googleapis.com/translate_a/single',
            params={'client': 'gtx', 'sl': 'fr', 'tl': gt, 'dt': 't', 'q': 'test'},
            timeout=10
        )
        if resp.ok:
            return True
    except:
        pass
    try:
        resp = requests.get(
            'https://api.mymemory.translated.net/get',
            params={'q': 'test', 'langpair': f'fr|{gt}'},
            headers=HEADERS, timeout=10
        )
        if resp.ok:
            return True
    except:
        pass
    for url in ('https://libretranslate.com', 'https://translate.argosopentech.com'):
        try:
            resp = requests.post(f'{url}/translate',
                json={'q': 'test', 'source': 'fr', 'target': gt},
                headers={'Content-Type': 'application/json'}, timeout=10)
            if resp.ok:
                return True
        except:
            pass
    return False


def main():
    print("=== Traduction (Google + MyMemory + LibreTranslate) ===\n", flush=True)

    lang_dirs = sorted([
        d for d in os.listdir(TRANS)
        if os.path.isdir(os.path.join(TRANS, d)) and d not in ('fr',)
    ])

    state = load_state()
    done_set = set(state['done'] + state['fr_only'])
    remaining = [l for l in lang_dirs if l not in done_set]
    remaining.sort()

    if not remaining:
        print("Toutes les langues deja traitees !", flush=True)
        s = state
        print(f"  Traduites: {len(s['done'])}, FR only: {len(s['fr_only'])}, Echecs: {len(s['failed'])}", flush=True)
        return

    print(f"  Restantes: {len(remaining)}/{len(lang_dirs)} langues\n", flush=True)
    print("Phase 1: Test des langues...\n", flush=True)

    supported, unsupported = [], []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(can_translate, lang): lang for lang in remaining}
        for i, f in enumerate(as_completed(futures), 1):
            lang = futures[f]
            ok = f.result()
            (supported if ok else unsupported).append(lang)
            print(f"  [{i}/{len(remaining)}] {lang}... {'OK' if ok else 'NON'}", flush=True)

    supported.sort()
    unsupported.sort()
    all_langs = supported + unsupported
    print(f"\n  Traduisibles: {len(supported)}, FR only: {len(unsupported)}\n", flush=True)

    print("Phase 2: Traduction...\n", flush=True)

    for i, lang in enumerate(all_langs):
        print(f"  [{i+1}/{len(all_langs)}] {lang}...", end=' ', flush=True)

        if lang in unsupported:
            po_path = os.path.join(TRANS, lang, 'LC_MESSAGES', 'messages.po')
            if not os.path.exists(po_path):
                print("pas de fichier", flush=True)
            elif compile_mo_only(po_path):
                print("OK (FR)", flush=True)
                state['fr_only'].append(lang)
            else:
                print("ECHEC", flush=True)
                state['failed'].append(lang)
        else:
            result = process_language(lang)
            if result is None:
                print("pas de fichier", flush=True)
            elif result == 0:
                print("deja traduit", flush=True)
            elif result == -1:
                print("ECHEC", flush=True)
                state['failed'].append(lang)
            else:
                print(f"{result} OK", flush=True)
                state['done'].append(lang)

        save_state(state)

    s = state
    print(f"\n=== Termine! {len(s['done'])} traduites, {len(s['fr_only'])} FR only, {len(s['failed'])} echecs ===", flush=True)
    if s['failed']:
        print(f"  Echecs: {', '.join(s['failed'])}", flush=True)


if __name__ == '__main__':
    main()

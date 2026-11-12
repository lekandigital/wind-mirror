"""Parse CMU mocap listing pages (mocap.cs.cmu.edu/search.php..., saved as HTML) into a JSON index.

Usage: python cmu_index.py <out index.json> <page.html> [more pages.html ...]
Pages are merged; a later page only fills trials missing from earlier ones.
Output: {"subjects": {"<n>": {"desc": str, "trials": {"<t>": {"desc": str, "fps": int|null}}}}}
"""
import sys, re, json, html


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def parse(text, subjects):
    for m in re.finditer(r'Subject #(\d+)\s*\((.*?)\)\s*<A HREF', text, re.S):
        sd = subjects.setdefault(m.group(1), dict(desc='', trials={}))
        if not sd['desc']:
            sd['desc'] = clean(m.group(2))
    for row in re.finditer(r'<TR[^>]*>(.*?)</TR>', text, re.S | re.I):
        r = row.group(1)
        b = re.search(r'badtrial\.php\?subjectnumber=(\d+)&(?:amp;)?motion=(\d+)', r)
        if not b:
            continue
        sn, tn = str(int(b.group(1))), str(int(b.group(2)))
        cells = [clean(c) for c in re.findall(r'<TD[^>]*>(.*?)</TD>', r, re.S | re.I)]
        # cells: image, trial #, description, tvd, c3d, amc, mpg, avi, framerate, feedback
        desc = cells[2] if len(cells) > 2 else ''
        fps = None
        for c in cells[3:]:
            if re.fullmatch(r'\d+', c):
                fps = int(c)
        sd = subjects.setdefault(sn, dict(desc='', trials={}))
        if tn not in sd['trials']:
            sd['trials'][tn] = dict(desc=desc, fps=fps)
    return subjects


if __name__ == '__main__':
    subj = {}
    for p in sys.argv[2:]:
        parse(open(p, encoding='latin-1').read(), subj)
    subj = {k: subj[k] for k in sorted(subj, key=int)}
    json.dump(dict(subjects=subj), open(sys.argv[1], 'w'), indent=1)
    nt = sum(len(s['trials']) for s in subj.values())
    fps = {}
    for s in subj.values():
        for t in s['trials'].values():
            fps[t['fps']] = fps.get(t['fps'], 0) + 1
    print(f'{len(subj)} subjects, {nt} trials, fps counts {fps}')

"""Coarse motion categories from CMU trial descriptions, by keyword.

Each trial gets ONE primary category: the first rule below whose pattern matches its trial description (CamelCase is
split and text lower-cased first). If no rule matches the trial description (or it is 'unknown'), the same rules are
applied to the subject-level text ('cat'); if still nothing matches, 'other'.
`all_categories` returns every rule that matches (multi-label), with the same fallback.
"""
import re

RULES = [
    ('cartwheel/acrobatics', r'cartwheel|flip|\bflp\b|handstand|hand stand|\bacrobat|somersault|\btumbl|gymnast'),
    ('interaction', r'2 subjects|two subjects|subject [ab]\b|human interaction|synchronized|high five|shak(e|ing) hands|quarrel|conversation'),
    ('climb', r'\bclimb|ladder|\bstairs?\b'),
    ('crawl/floor', r'crawl|\broll(s|ing)?\b|\bfloor\b|\bground\b|\blay(ing)?\b|\blying\b|\blie\b|push ?ups?|sit ?ups?|get(ting)? up|prone|scramble|creeping'),
    ('dance', r'danc|salsa|charleston|charelston|\bjete\b|pirouette|arabesque|ballet|waltz|tourant|attitude|derriere|lambada|tango'),
    ('sports', r'basketball|soccer|football|golf|\bputt|\btee\b|baseball|boxing|punch|kick|karate|martial|tai chi|yoga|stretch|'
               r'jumping jacks|\bjacks\b|squat|swim|stroke|skateboard|sword|dribble|shoot|shot|throw|catch|lunge|blocks|fishing|'
               r'bowling|tennis|swing|frisbee|pitch|\btoss|\bempi\b|bassai|gedanbarai|heian|mawashigeri|oiduki|syutouuke|yokogeri'),
    ('jump', r'jump|\bhop|leap|\bbound|\bskip'),
    ('sit', r'\bsit|\bseat|chair|\bstool\b|sitting'),
    ('run', r'\brun|\bjog|sprint'),
    ('walk', r'walk|march|\bstep|sidestep|stride|sneak|tiptoe|limp|stroll|wander|navigate'),
]
CATEGORIES = [r[0] for r in RULES] + ['other']
_RX = [(n, re.compile(p)) for n, p in RULES]


def _norm(text):
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', text or '').replace('_', ' ').lower()


def _match(text):
    s = _norm(text)
    return [n for n, rx in _RX if rx.search(s)]


def all_categories(desc, cat=''):
    m = [] if (desc or '').strip().lower() in ('', 'unknown') else _match(desc)
    if not m:
        m = _match(cat)
    return m or ['other']


def primary_category(desc, cat=''):
    return all_categories(desc, cat)[0]

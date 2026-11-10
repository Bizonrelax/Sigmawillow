#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СУБ v.3 converter + surname replacement for restruct phase 5."""
import re, sys

SUBS = [
    # surname replacements (step 4)
    ("Лемма Пустошилова", "Лемма о сохранении массы"),
    ("Леммы Пустошилова", "Леммы о сохранении массы"),
    ("Лемме Пустошилова", "Лемме о сохранении массы"),
    ("Лемму Пустошилова", "Лемму о сохранении массы"),
    ("Волны Пустошилова", "Квазипериодические колебания"),
    ("Волн Пустошилова", "Квазипериодических колебаний"),
    ("Волнами Пустошилова", "Квазипериодическими колебаниями"),
    ("Волна Пустошилова", "Квазипериодическое колебание"),
    ("Волне Пустошилова", "Квазипериодическому колебанию"),
    ("Pustoshilov Lemma", "Mass Conservation Lemma"),
    ("Pustoshilov Waves", "Quasiperiodic Oscillations"),
    ("Pustoshilov Phase Non-Coincidence Lemma", "Phase Non-Coincidence Lemma"),
    # unicode math symbols
    ("\\leqslant", "≤"), ("\\geqslant", "≥"), ("\\le", "≤"), ("\\ge", "≥"),
    ("\\neq", "≠"), ("\\ne", "≠"), ("\\equiv", "≡"), ("\\approx", "≈"),
    ("\\infty", "∞"), ("\\cdot", "·"), ("\\times", "×"), ("\\div", "÷"),
    ("\\pm", "±"), ("\\to", "→"), ("\\rightarrow", "→"), ("\\Rightarrow", "⇒"),
    ("\\Leftrightarrow", "⇔"), ("\\in", "∈"), ("\\notin", "∉"),
    ("\\subset", "⊂"), ("\\cup", "∪"), ("\\cap", "∩"),
    ("\\forall", "∀"), ("\\exists", "∃"),
    ("\\mathbb{N}", "ℕ"), ("\\mathbb{Z}", "ℤ"), ("\\mathbb{R}", "ℝ"), ("\\mathbb{Q}", "ℚ"),
    ("\\alpha", "α"), ("\\beta", "β"), ("\\gamma", "γ"), ("\\delta", "δ"),
    ("\\epsilon", "ε"), ("\\theta", "θ"), ("\\lambda", "λ"), ("\\mu", "μ"),
    ("\\pi", "π"), ("\\sigma", "σ"), ("\\phi", "φ"), ("\\omega", "ω"),
    ("\\Delta", "Δ"), ("\\Sigma", "Σ"), ("\\Omega", "Ω"),
    ("\\blacksquare", "■"), ("\\quad", " "), ("\\,", " "), ("\\;", " "), ("\\ ", " "),
]

SUBSCRIPT = {'0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉',
             'a':'ₐ','e':'ₑ','h':'ₕ','i':'ᵢ','j':'ⱼ','k':'ₖ','l':'ₗ','m':'ₘ','n':'ₙ','o':'ₒ',
             'p':'ₚ','r':'ᵣ','s':'ₛ','t':'ₜ','u':'ᵤ','v':'ᵥ','x':'ₓ'}
SUPERSC = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹',
           'n':'ⁿ','k':'ᵏ','i':'ⁱ'}

GREEK = [('leqslant','≤'),('geqslant','≥'),('le','≤'),('ge','≥'),('neq','≠'),('ne','≠'),
         ('equiv','≡'),('approx','≈'),('infty','∞'),('cdot','·'),('times','×'),('div','÷'),
         ('pm','±'),('rightarrow','→'),('to','→'),('Rightarrow','⇒'),('Leftrightarrow','⇔'),
         ('notin','∉'),('in','∈'),('subset','⊂'),('cup','∪'),('cap','∩'),('forall','∀'),
         ('exists','∃'),('alpha','α'),('beta','β'),('gamma','γ'),('delta','δ'),('epsilon','ε'),
         ('theta','θ'),('lambda','λ'),('mu','μ'),('pi','π'),('sigma','σ'),('phi','φ'),('omega','ω'),
         ('Delta','Δ'),('Sigma','Σ'),('Omega','Ω'),('blacksquare','■'),('dots','…'),('ldots','…'),
         ('sum','Σ'),('int','∫')]

SURNAME_PHRASES = [
    ("Лемма Пустошилова о сохранении массы числовой строки", "Лемма о сохранении массы числовой строки"),
    ("Лемма Пустошилова о сохранении массы", "Лемма о сохранении массы"),
    ("Теорема о разрядной пульсации векторов ПУС / Волны Пустошилова", "Теорема о квазипериодической модуляции"),
    ("Волны Пустошилова", "Квазипериодические колебания"),
    ("Волн Пустошилова", "Квазипериодических колебаний"),
    ("Волнами Пустошилова", "Квазипериодическими колебаниями"),
    ("Волна Пустошилова", "Квазипериодическое колебание"),
    ("Волне Пустошилова", "Квазипериодическому колебанию"),
    ("Волну Пустошилова", "Квазипериодическое колебание"),
    ("Леммы Пустошилова", "Леммы о сохранении массы"),
    ("Лемме Пустошилова", "Лемме о сохранении массы"),
    ("Лемму Пустошилова", "Лемму о сохранении массы"),
    ("Лемм Пустошилова", "Лемм о сохранении массы"),
    ("Pustoshilov Lemma", "Mass Conservation Lemma"),
    ("Pustoshilov Waves", "Quasiperiodic Oscillations"),
    ("Pustoshilov Phase Non-Coincidence Lemma", "Phase Non-Coincidence Lemma"),
    ("Pustoshilov", ""),
]

def apply_surname(text):
    for a, b in sorted(SURNAME_PHRASES, key=lambda p: -len(p[0])):
        text = text.replace(a, b)
    # tidy double spaces produced by removals
    text = re.sub(r' {2,}', ' ', text)
    return text

def conv_math(text):
    """Convert a latex math fragment to plain unicode text."""
    t = text
    # surname / phrase replacements (longest first)
    for a, b in sorted(SUBS, key=lambda p: -len(p[0])):
        t = t.replace(a, b)
    # greek/operator macros with word boundary (case-sensitive, longest first)
    for name, sym in sorted(GREEK, key=lambda p: -len(p[0])):
        t = re.sub(r'\\' + name + r'(?![A-Za-z])', sym, t)
    t = re.sub(r'\\(?:quad|,|;| )', ' ', t)
    # \frac{A}{B} -> (A / B)
    def frac(m):
        return "(" + conv_math(m.group(1)) + " / " + conv_math(m.group(2)) + ")"
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}', frac, t)
    # \sqrt{X} -> √X
    def sqrt(m):
        inner = conv_math(m.group(1))
        if len(inner) > 1 and not re.fullmatch(r'[\w√∞π]+', inner):
            inner = "(" + inner + ")"
        return "√" + inner
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r'\\sqrt\{([^{}]*)\}', sqrt, t)
    t = re.sub(r'\\(?:left|right|text|mathrm|mathbf|operatorname|displaystyle|limits)\b', '', t)
    t = re.sub(r'\\begin\{[^}]*\}', '', t)
    t = re.sub(r'\\end\{[^}]*\}', '', t)
    t = t.replace('\\{', '{').replace('\\}', '}').replace('\\%', '%').replace('\\&', '&')
    # superscripts then subscripts
    def sup(m):
        body = m.group(1)
        out = ''.join(SUPERSC.get(ch, '^'+ch) for ch in body)
        return out
    def sub(m):
        body = m.group(1)
        parts, cur = [], ''
        for ch in body:
            if ch in SUBSCRIPT:
                cur += ch
            else:
                if cur:
                    parts.append(''.join(SUBSCRIPT[c] for c in cur)); cur = ''
                parts.append('_' + ch)
        if cur:
            parts.append(''.join(SUBSCRIPT[c] for c in cur))
        return ''.join(parts)
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r'\^\{([^{}]*)\}', sup, t)
        t = re.sub(r'_\{([^{}]*)\}', sub, t)
    t = re.sub(r'\^([0-9a-zA-Z])', lambda m: SUPERSC.get(m.group(1), '^'+m.group(1)), t)
    t = re.sub(r'_([0-9a-zA-Z])', lambda m: SUBSCRIPT.get(m.group(1), '_'+m.group(1)), t)
    t = t.replace('$', '')
    t = t.replace('{', '').replace('}', '')
    t = t.replace('\\', '')
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def has_index(s):
    return bool(re.search(r'[₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ]', s)) or '<sub>' in s

def convert(text):
    # 0. surname replacements across whole text (step 4)
    text = apply_surname(text)
    # 1. protect <sub>/<sup> content, escape < > inside
    def esc_tag(m):
        tag, inner = m.group(1), m.group(2)
        inner = inner.replace('<', '&lt;').replace('>', '&gt;')
        return f"<{tag}>{inner}</{tag}>"
    protected = []
    def prot(m):
        protected.append(esc_tag(m))
        return f"\x00{len(protected)-1}\x00"
    text = re.sub(r'<(sub|sup)>(.*?)</\1>', prot, text, flags=re.S)

    # 2. display math $$...$$
    text = re.sub(r'\$\$(.+?)\$\$', lambda m: ' \x01' + conv_math(m.group(1)) + '\x02 ', text, flags=re.S)
    # inline \(...\)
    text = re.sub(r'\\\((.+?)\\\)', lambda m: conv_math(m.group(1)), text, flags=re.S)
    # $...$
    text = re.sub(r'\$([^$\n]+?)\$', lambda m: conv_math(m.group(1)), text)

    lines = text.split('\n')
    out = []
    for ln in lines:
        stripped = ln.strip()
        indent = len(ln) - len(ln.lstrip())
        # heading depth clamp
        hm = re.match(r'^(#{4,})\s', stripped)
        if hm:
            stripped = '###' + stripped[len(hm.group(1)):]
            indent = 0
            ln = stripped
        # display-math-only line -> indented block if no indices
        if '\x01' in ln:
            core = ln.replace('\x01', '').replace('\x02', '').strip()
            if re.match(r'^\x01.*\x02$', ln.strip()):
                if not has_index(core):
                    out.append('    ' + ln.strip().replace('\x01','').replace('\x02',''))
                else:
                    out.append(ln.strip().replace('\x01','').replace('\x02',''))
                continue
        # standalone formula lines (plain text heuristics)
        if stripped and indent == 0 and looks_formula(stripped) and not has_index(stripped):
            out.append('    ' + stripped)
            continue
        if stripped.startswith('>'):
            out.append(stripped.lstrip('> ').rstrip() if False else ln.strip().lstrip('>').lstrip())
            continue
        out.append(ln.rstrip())
    text = '\n'.join(out)
    # restore protected tags
    def unprot(m):
        return protected[int(m.group(1))]
    text = re.sub(r'\x00(\d+)\x00', unprot, text)
    text = text.replace('\x01', '').replace('\x02', '')
    # collapse >2 blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

FORMULA_CHARS = set('=+-*/()[]{}<≥≤≠≡∞Σ∫·×±→⇒√^_₀₁₂₃₄₅₆₇₈₉')
def looks_formula(s):
    if len(s) > 140:
        return False
    if '=' not in s:
        return False
    if any(ord(c) in range(0x400, 0x4FF) for c in s):  # cyrillic -> prose
        return False
    toks = s.replace('(', ' ').replace(')', ' ').split()
    if not toks:
        return False
    ok = all(all(ch in FORMULA_CHARS or ch.isascii() and (ch.isalnum() or ch in ':,.') for ch in t) for t in toks)
    return ok and any(t for t in toks if any(ch in '=+*/√^_' for ch in t))

META_PAT = re.compile(r'^(Вот |Нет, |Да, |Отличный выбор|Полный объединенный|Твой взгляд|Для расчёта и построения|read and wonder)')
def strip_meta(text):
    lines = text.split('\n')
    i = 0
    while i < len(lines) and (not lines[i].strip() or META_PAT.match(lines[i].strip())):
        i += 1
    return '\n'.join(lines[i:])

if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding='utf-8') as f:
        data = f.read()
    res = convert(strip_meta(data))
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(res)
    print(f"converted {src} -> {dst}")

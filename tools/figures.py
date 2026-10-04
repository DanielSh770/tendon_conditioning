#!/usr/bin/env python3
"""Рисует картинки к упражнениям и вписывает их в index.html между метками FIG:BEGIN и FIG:END.

Фигуры собираются из отрезков: позу задают углы сегментов или точки, куда тянется
рука или нога (суставы считаются сами). Цвета берутся из CSS-переменных страницы,
поэтому картинки сами подстраиваются под светлую и тёмную тему.

Запуск из корня репозитория:
  python3 tools/figures.py              # обновить index.html
  python3 tools/figures.py preview.html # ещё и сохранить страницу со всеми картинками
"""
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VIEW_W, VIEW_H, GROUND = 200, 140, 130

# Длины и толщины сегментов в единицах viewBox.
LEN = dict(torso=38, neck=15, head=7.5, upper=22, fore=19, hand=6, thigh=30, shin=29, foot=10)
WID = dict(torso=13, upper=7.5, fore=6.5, hand=5, thigh=10, shin=8, foot=5.5)


def at(p, deg, length):
    a = math.radians(deg)
    return (p[0] + length * math.cos(a), p[1] + length * math.sin(a))


def angle(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def ik(base, target, l1, l2, bend):
    """Двухзвенник от base к target; bend=+1 или -1 выбирает, в какую сторону сгибается сустав."""
    d = min(max(dist(base, target), abs(l1 - l2) + 1e-6), l1 + l2 - 1e-6)
    c = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    a1 = angle(base, target) + bend * math.degrees(math.acos(max(-1.0, min(1.0, c))))
    mid = at(base, a1, l1)
    return a1, angle(mid, target)


def n(v):
    s = ('%.1f' % v).rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def pts(*ps):
    return ' '.join('%s %s' % (n(x), n(y)) for x, y in ps)


class Fig:
    def __init__(self):
        self.back, self.body, self.front = [], [], []

    # ---------- примитивы ----------
    def line(self, layer, a, b, w, cls):
        layer.append('<path class="%s" stroke-width="%s" d="M%sL%s"/>' % (cls, n(w), pts(a), pts(b)))

    def seg(self, a, b, w, cls, hi=None):
        self.line(self.body, a, b, w, cls)
        if hi is not None:
            # Подсветка рабочей мышцы: полоса вдоль сегмента, со сдвигом к нужной стороне.
            if hi == 0:
                self.line(self.body, a, b, w, 'fx-hi')
            else:
                dx, dy = b[0] - a[0], b[1] - a[1]
                k = hi * w / 4 / (math.hypot(dx, dy) or 1)
                o = (dy * k, -dx * k)
                self.line(self.body, (a[0] + o[0], a[1] + o[1]), (b[0] + o[0], b[1] + o[1]), w / 2 + .5, 'fx-hi')

    def floor(self, x1=8, x2=192, y=GROUND):
        self.back.append('<path class="fx-pl" d="M%sL%s"/>' % (pts((x1, y + 1)), pts((x2, y + 1))))

    def rect(self, x, y, w, h, layer='back', r=1.5):
        getattr(self, layer).append('<rect class="fx-pf" x="%s" y="%s" width="%s" height="%s" rx="%s"/>' % (n(x), n(y), n(w), n(h), n(r)))

    def wall(self, x, side, y1=6, y2=GROUND):
        """Стена: линия по x, заливка уходит в сторону side (+1 вправо, -1 влево)."""
        self.rect(x if side > 0 else x - 7, y1, 7, y2 - y1 + 2, r=0)
        self.back.append('<path class="fx-pl" d="M%sL%s"/>' % (pts((x, y1)), pts((x, y2 + 2))))

    def ball(self, c, r):
        self.front.append('<circle class="fx-pf fx-ps" cx="%s" cy="%s" r="%s"/>' % (n(c[0]), n(c[1]), n(r)))

    def strap(self, *ps):
        self.front.append('<path class="fx-st" d="M%s"/>' % ' L'.join(pts(p) for p in ps))

    def arrow(self, a, b):
        """Направление усилия: стрелка из a в b."""
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        h, s = 6.5, 4.2
        base = (b[0] - h * math.cos(ang), b[1] - h * math.sin(ang))
        l = (base[0] + s * math.sin(ang), base[1] - s * math.cos(ang))
        r = (base[0] - s * math.sin(ang), base[1] + s * math.cos(ang))
        self.front.append('<path class="fx-ar" d="M%sL%s"/><path class="fx-ah" d="M%sL%sL%sZ"/>' % (pts(a), pts(base), pts(b), pts(l), pts(r)))

    def measure(self, a, b, label_at, anchor='middle', label='см', tick=5):
        """Размерная линия для тестов: отрезок с засечками и подписью в точке label_at."""
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        t = (tick * math.sin(ang), -tick * math.cos(ang))
        out = '<path class="fx-ms" d="M%sL%sM%sL%sM%sL%s"/>' % (
            pts(a), pts(b), pts((a[0] - t[0], a[1] - t[1])), pts((a[0] + t[0], a[1] + t[1])),
            pts((b[0] - t[0], b[1] - t[1])), pts((b[0] + t[0], b[1] + t[1])))
        out += '<text class="fx-tx" x="%s" y="%s" text-anchor="%s">%s</text>' % (n(label_at[0]), n(label_at[1]), anchor, label)
        self.front.append(out)

    # ---------- человек сбоку ----------
    def side(self, hip, torso, head=None, armN=None, armF=None, legN=None, legF=None, hi=None):
        """Фигура в профиль. N — ближние к зрителю конечности, F — дальние (светлее).

        Конечность задаётся кортежем:
          ('to', (x, y), bend[, end_angle]) — тянется к точке, сустав считается сам;
          ('ang', a1, a2[, end_angle])      — абсолютные углы сегментов (0 вправо, 90 вниз).
        end_angle — угол стопы или кисти. hi = {'torso': 1, 'thighN': -1, ...} подсвечивает сегменты:
        для рук и ног +1 — передняя сторона, -1 — задняя; для корпуса +1 — спина, -1 — грудь и живот; 0 — целиком.
        """
        hi = hi or {}
        sh = at(hip, torso, LEN['torso'])
        hd = at(sh, torso if head is None else head, LEN['neck'])
        j = dict(hip=hip, sh=sh, head=hd)

        def limb(spec, base, l1, l2):
            a1, a2 = ik(base, spec[1], l1, l2, spec[2]) if spec[0] == 'to' else spec[1:3]
            m = at(base, a1, l1)
            return m, at(m, a2, l2), (spec[3] if len(spec) > 3 else a2)

        def leg(spec, tag, cls):
            if not spec:
                return
            k, a, fa = limb(spec, hip, LEN['thigh'], LEN['shin'])
            t = at(a, fa, LEN['foot'])
            j.update({'k' + tag: k, 'a' + tag: a, 't' + tag: t})
            self.seg(hip, k, WID['thigh'], cls, hi.get('thigh' + tag))
            self.seg(k, a, WID['shin'], cls, hi.get('shin' + tag))
            self.seg(a, t, WID['foot'], cls)

        def arm(spec, tag, cls):
            if not spec:
                return
            e, w, ha = limb(spec, sh, LEN['upper'], LEN['fore'])
            h = at(w, ha, LEN['hand'])
            j.update({'e' + tag: e, 'w' + tag: w, 'h' + tag: h})
            self.seg(sh, e, WID['upper'], cls, hi.get('upper' + tag))
            self.seg(e, w, WID['fore'], cls, hi.get('fore' + tag))
            self.seg(w, h, WID['hand'], cls)

        leg(legF, 'F', 'fx-f')
        arm(armF, 'F', 'fx-f')
        self.seg(hip, sh, WID['torso'], 'fx-n', hi.get('torso'))
        self.body.append('<circle class="fx-hd" cx="%s" cy="%s" r="%s"/>' % (n(hd[0]), n(hd[1]), n(LEN['head'])))
        leg(legN, 'N', 'fx-n')
        arm(armN, 'N', 'fx-n')
        return j

    # ---------- человек анфас ----------
    def front_view(self, cx, hip_y, arms, hi_arms=None, legs=True):
        """Фигура анфас: arms = (левая, правая), каждая ('to', (x, y), bend[, угол кисти])
        или ('pts', локоть, запястье[, угол кисти]), когда рука идёт к зрителю и в проекции короче."""
        sh_y = hip_y - LEN['torso']
        self.body.append('<path class="fx-tf" d="M%sL%sL%sL%sZ"/>' % (
            pts((cx - 11, sh_y)), pts((cx + 11, sh_y)), pts((cx + 7.5, hip_y)), pts((cx - 7.5, hip_y))))
        self.body.append('<circle class="fx-hd" cx="%s" cy="%s" r="%s"/>' % (n(cx), n(sh_y - LEN['neck'] + 1), n(LEN['head'])))
        j = {}
        if legs:
            for side in (-1, 1):
                hip = (cx + side * 5.5, hip_y + 2)
                ank = (cx + side * 9, GROUND - 2.5)
                self.seg(hip, ank, WID['thigh'] - 1, 'fx-n')
                self.seg(ank, (ank[0] + side * 4, GROUND - 2.5), WID['foot'], 'fx-n')
        for side, spec in zip((-1, 1), arms):
            sh = (cx + side * 12, sh_y + 3)
            if spec[0] == 'pts':
                e, w = spec[1], spec[2]
                a2 = angle(e, w)
            else:
                a1, a2 = ik(sh, spec[1], LEN['upper'], LEN['fore'], spec[2])
                e = at(sh, a1, LEN['upper'])
                w = at(e, a2, LEN['fore'])
            h = at(w, spec[3] if len(spec) > 3 else a2, LEN['hand'])
            hs = (hi_arms or {})
            self.seg(sh, e, WID['upper'], 'fx-n', hs.get('upper'))
            self.seg(e, w, WID['fore'], 'fx-n', hs.get('fore'))
            self.seg(w, h, WID['hand'], 'fx-n')
            j['w' + ('L' if side < 0 else 'R')] = w
            j['h' + ('L' if side < 0 else 'R')] = h
            j['e' + ('L' if side < 0 else 'R')] = e
        j['sh_y'] = sh_y
        return j

    def svg(self, zoom=None):
        vb = '0 0 %d %d' % (VIEW_W, VIEW_H) if zoom is None else ' '.join(n(v) for v in zoom)
        return '<svg viewBox="%s" aria-hidden="true">%s</svg>' % (vb, ''.join(self.back + self.body + self.front))


ON_FLOOR = GROUND - 2.75      # высота голеностопа, когда стопа стоит на полу
LYING = GROUND - WID['torso'] / 2


def calf_iso():
    f = Fig(); f.floor(); f.wall(150, 1)
    j = f.side(hip=(98, 64), torso=-86,
               legN=('ang', 90, 90, 52), legF=('ang', 91, 91, 52),
               armN=('to', (146, 46), 1), armF=('to', (146, 49), 1),
               hi={'shinN': -1})
    heel = j['aN']
    f.arrow((heel[0] - 9, heel[1] + 7), (heel[0] - 9, heel[1] - 11))
    return f


def calf_str():
    f = Fig(); f.floor(); f.wall(162, 1)
    f.side(hip=(104, 70), torso=-62,
           legN=('to', (62, ON_FLOOR), -1, 0), legF=('to', (128, ON_FLOOR), -1, 0),
           armN=('to', (158, 40), 1), armF=('to', (158, 44), 1),
           hi={'shinN': -1})
    return f


def knee_iso():
    f = Fig(); f.floor(); f.wall(58, -1)
    hip = (65 + WID['torso'] / 2 - 6, ON_FLOOR - LEN['shin'] - 2)
    f.side(hip=hip, torso=-90,
           legN=('ang', 0, 90, 0), legF=('ang', 0, 90, 0),
           armN=('ang', 2, 0), armF=('ang', 4, 2),
           hi={'thighN': 1})
    return f


def knee_str():
    f = Fig(); f.floor()
    hip = (100, ON_FLOOR - LEN['thigh'] - LEN['shin'] + 1)
    f.side(hip=hip, torso=-84, legF=('ang', 90, 90, 0),
           legN=('ang', 97, -122, -165),
           armF=('ang', -14, -8),
           armN=('to', (hip[0] - 17, hip[1] + 1), 1, 120),
           hi={'thighN': 1})
    return f


def ham_iso():
    f = Fig(); f.floor()
    hip = (82, LYING)
    j = f.side(hip=hip, torso=180, head=180,
               legF=('ang', 0, 0, -80),
               legN=('to', (hip[0] + 54, GROUND - 3.5), -1, -70),
               armF=('ang', 3, 0), armN=('ang', 3, 0),
               hi={'thighN': -1})
    a = j['aN']
    f.arrow((a[0] - 4, a[1] - 25), (a[0] - 4, a[1] - 8))
    return f


def ham_str():
    f = Fig(); f.floor(); f.rect(124, 92, 36, 6); f.rect(128, 98, 4, 32, r=0); f.rect(152, 98, 4, 32, r=0)
    hip = (82, ON_FLOOR - LEN['thigh'] - LEN['shin'] + 1)
    f.side(hip=hip, torso=-38,
           legF=('ang', 90, 90, 0),
           legN=('to', (140, 89), -1, -70),
           armN=('to', (112, 80), 1), armF=('to', (108, 78), 1),
           hi={'thighN': -1})
    return f


def hipflex_iso():
    f = Fig(); f.floor()
    hip = (92, LYING)
    feet = (hip[0] + 44, ON_FLOOR)
    j = f.side(hip=hip, torso=180, head=180,
               legF=('to', (feet[0] + 2, feet[1]), -1, 0), legN=('to', feet, -1, 0),
               armF=('ang', 3, 0), armN=('ang', 3, 0), hi={'thighN': 1})
    k = j['kN']
    f.ball((k[0] - 1, k[1] + 2), 7.5)
    f.arrow((k[0] - 21, k[1] - 13), (k[0] - 10, k[1] - 5))
    f.arrow((k[0] + 19, k[1] - 13), (k[0] + 8, k[1] - 5))
    return f


def hipflex_str():
    f = Fig(); f.floor()
    knee = (82, GROUND - WID['shin'] / 2)
    hip = at(knee, -72, LEN['thigh'])
    f.side(hip=hip, torso=-92,
           legN=('ang', 108, 180, 180),
           legF=('to', (hip[0] + 32, ON_FLOOR), -1, 0),
           armN=('to', (hip[0] + 6, hip[1] - 2), 1), armF=('to', (hip[0] + 8, hip[1] - 3), 1),
           hi={'thighN': 1})
    return f


def core_iso():
    f = Fig(); f.floor()
    sh = (130, GROUND - WID['fore'] / 2 - LEN['upper'])
    tilt = -7.5
    hip = at(sh, tilt + 180, LEN['torso'])
    f.side(hip=hip, torso=tilt,
           legN=('ang', tilt + 180, tilt + 180, 98), legF=('ang', tilt + 180, tilt + 180, 98),
           armN=('ang', 90, 0), armF=('ang', 90, 0),
           hi={'torso': -1})
    return f


def core_str():
    f = Fig(); f.floor()
    knee = (84, GROUND - WID['shin'] / 2)
    hip = at(knee, 214, LEN['thigh'])
    f.side(hip=hip, torso=12, head=20,
           legN=('ang', 34, 180, 180), legF=('ang', 34, 180, 180),
           armN=('to', (150, GROUND - 3.5), 1, 0), armF=('to', (148, GROUND - 3.5), 1, 0),
           hi={'torso': 1})
    return f


def shoulder_iso():
    f = Fig(); f.floor()
    for x in (33, 159):
        f.rect(x, 14, 8, GROUND - 14 + 2, r=0)
    f.rect(33, 8, 134, 8, r=0)
    cx, hip_y = 100, ON_FLOOR - 56
    y = hip_y - 35
    f.front_view(cx, hip_y, arms=(('to', (20, y), 1, 180), ('to', (180, y), -1, 0)),
                 hi_arms={'upper': 0})
    f.arrow((62, y - 13), (44, y - 13))
    f.arrow((138, y - 13), (156, y - 13))
    return f


def shoulder_str():
    f = Fig(); f.floor(); f.rect(52, 8, 8, GROUND - 8 + 2, r=0)
    hip = (90, ON_FLOOR - 57)
    f.side(hip=hip, torso=-84,
           legN=('to', (70, ON_FLOOR), -1, 0), legF=('to', (114, ON_FLOOR), -1, 0),
           armN=('to', (62, hip[1] - 52), -1, -90),
           armF=('ang', 100, 70),
           hi={'torso': -1})
    return f


def back_iso():
    f = Fig(); f.floor()
    hip = (66, LYING)
    j = f.side(hip=hip, torso=-96,
               legN=('ang', 0, 0, -90), legF=('ang', 0, 0, -90),
               armN=('to', (hip[0] + 16, hip[1] - 16), 1, 0), armF=('to', (hip[0] + 18, hip[1] - 17), 1, 0),
               hi={'torso': 1, 'upperN': 1})
    sole = (j['tN'][0] + 4, j['tN'][1] + 3)
    f.strap(j['hN'], sole, (j['aN'][0] + 4, j['aN'][1] + 3), j['hN'])
    w = j['wN']
    f.arrow((w[0] + 2, w[1] - 12), (w[0] - 16, w[1] - 12))
    return f


def back_str():
    f = Fig(); f.floor(); f.rect(150, 62, 34, 6); f.rect(176, 68, 5, 62, r=0)
    hip = (82, ON_FLOOR - LEN['thigh'] - LEN['shin'] + 1)
    f.side(hip=hip, torso=-4, head=12,
           legN=('ang', 92, 90, 0), legF=('ang', 92, 90, 0),
           armN=('to', (164, 58), 1, 0), armF=('to', (160, 59), 1, 0),
           hi={'torso': 1, 'upperN': -1})
    return f


def wrist_iso():
    f = Fig()
    cx, hip_y = 100, 112
    sh_y = hip_y - LEN['torso']
    f.front_view(cx, hip_y, legs=False,
                 arms=(('pts', (cx - 31, sh_y + 21), (cx - 3, sh_y + 13), -90),
                       ('pts', (cx + 31, sh_y + 21), (cx + 3, sh_y + 13), -90)),
                 hi_arms={'fore': 0})
    y = sh_y + 3
    f.arrow((cx - 30, y), (cx - 10, y))
    f.arrow((cx + 30, y), (cx + 10, y))
    return f, (cx - 55, sh_y - 32, 110, 77)


def wrist_str():
    f = Fig()
    hip = (64, 116)
    j = f.side(hip=hip, torso=-90,
               armN=('ang', 0, 0, -88),
               armF=('to', (112, 82), -1, -115),
               hi={'foreN': 0})
    h = j['hN']
    f.arrow((h[0] + 10, h[1] - 9), (h[0] - 8, h[1] - 9))
    return f, (36, 30, 120, 84)


def test_bend():
    f = Fig(); f.floor()
    hip = (84, ON_FLOOR - LEN['thigh'] - LEN['shin'] + 1)
    j = f.side(hip=hip, torso=8, head=96,
               legN=('ang', 92, 90, 0), legF=('ang', 92, 90, 0),
               armN=('ang', 88, 90, 90), armF=('ang', 86, 90, 90),
               hi={'thighN': -1})
    tip = j['hN']
    x = tip[0] + 12
    f.measure((x, tip[1] + 2.5), (x, GROUND), (x + 7, (tip[1] + GROUND) / 2 + 4), 'start')
    return f


def test_knee_wall():
    f = Fig(); f.floor(); f.wall(150, 1)
    ankle = (124, ON_FLOOR)
    knee = (148, ankle[1] - math.sqrt(LEN['shin'] ** 2 - 24 ** 2))
    hip = at(knee, 196, LEN['thigh'])
    # Задняя нога стоит коленом на полу, голень лежит на полу.
    dy = GROUND - WID['shin'] / 2 - hip[1]
    back = math.degrees(math.atan2(dy, -math.sqrt(LEN['thigh'] ** 2 - dy * dy)))
    j = f.side(hip=hip, torso=-82,
               legN=('to', ankle, -1, 0), legF=('ang', back, 180, 180),
               armN=('to', (146, hip[1] - 32), 1), armF=('to', (146, hip[1] - 28), 1),
               hi={'shinN': -1})
    x0 = j['tN'][0] + 3
    f.measure((x0, GROUND + 5.5), (150, GROUND + 5.5), (x0 - 4, GROUND + 9.5), 'end', tick=3.5)
    return f


FIGS = {
    'calf-iso': calf_iso, 'calf-str': calf_str,
    'knee-iso': knee_iso, 'knee-str': knee_str,
    'ham-iso': ham_iso, 'ham-str': ham_str,
    'hipflex-iso': hipflex_iso, 'hipflex-str': hipflex_str,
    'core-iso': core_iso, 'core-str': core_str,
    'shoulder-iso': shoulder_iso, 'shoulder-str': shoulder_str,
    'back-iso': back_iso, 'back-str': back_str,
    'wrist-iso': wrist_iso, 'wrist-str': wrist_str,
    'test-bend': test_bend, 'test-knee': test_knee_wall,
}


def render_all():
    out = {}
    for key, fn in FIGS.items():
        r = fn()
        f, zoom = r if isinstance(r, tuple) else (r, None)
        out[key] = f.svg(zoom)
    return out


def inject(figs):
    path = ROOT / 'index.html'
    src = path.read_text(encoding='utf-8')
    body = json.dumps(figs, ensure_ascii=False, indent=0).replace('</', '<\\/')
    new, count = re.subn(r'(// FIG:BEGIN[^\n]*\n).*?(\n\s*// FIG:END)',
                         lambda m: m.group(1) + '  var FIG = ' + body.replace('\n', '\n  ') + ';' + m.group(2),
                         src, flags=re.S)
    if count != 1:
        sys.exit('index.html: не найдены метки FIG:BEGIN / FIG:END')
    path.write_text(new, encoding='utf-8')


if __name__ == '__main__':
    figs = render_all()
    inject(figs)
    print('картинок: %d, %d КБ' % (len(figs), sum(len(v) for v in figs.values()) // 1024))
    if len(sys.argv) > 1:
        style = re.search(r'<style>.*?</style>', (ROOT / 'index.html').read_text(encoding='utf-8'), re.S).group(0)
        cards = ''.join('<figure class="ex"><div class="fig">%s</div><figcaption>%s</figcaption></figure>' % (v, k)
                        for k, v in figs.items())
        pathlib.Path(sys.argv[1]).write_text(
            '<!doctype html><meta charset="utf-8">%s<body><main><div class="exg" style="grid-template-columns:repeat(4,1fr)">%s</div></main>' % (style, cards),
            encoding='utf-8')

#!/usr/bin/env python3
"""Рисует картинки к упражнениям и вписывает их в index.html между метками FIG:BEGIN и FIG:END.

Человек собирается как манекен с пропорциями взрослого: у каждого сегмента (бедро,
голень, плечо, корпус...) есть профиль толщины спереди и сзади, поэтому видны икры,
ягодицы, грудь. Позу задают углы сегментов или точки, куда тянется рука или нога,
суставы считаются сами. Работающая или растягиваемая мышца закрашивается акцентным
цветом. Цвета берутся из CSS-переменных страницы, так что картинки сами подстраиваются
под светлую и тёмную тему.

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
GROUND = 130          # уровень пола
MAT = 2.5             # толщина коврика
ASPECT = 10 / 7       # обычные пропорции кадра

# Длины костей (рост около 121 единицы ≈ 175 см).
LEN = dict(torso=36, neck=13, thigh=30, shin=29, upper=22, fore=18, hand=12)

# Профили: (доля длины, толщина к передней стороне, толщина к задней).
PROF = {
    'thigh': [(0, 6.0, 6.6), (.25, 6.3, 6.2), (.6, 5.4, 5.0), (.85, 4.5, 4.2), (1, 4.0, 3.8)],
    'shin': [(0, 3.7, 3.9), (.12, 3.3, 4.7), (.32, 3.0, 5.3), (.55, 2.7, 4.2), (.8, 2.2, 2.8), (1, 2.1, 2.3)],
    'upper': [(0, 4.4, 4.6), (.18, 4.2, 4.1), (.5, 3.8, 3.4), (.8, 3.0, 2.8), (1, 2.7, 2.6)],
    'fore': [(0, 2.7, 2.9), (.22, 3.1, 3.2), (.6, 2.4, 2.5), (1, 1.8, 1.8)],
    'hand': [(0, 1.7, 1.7), (.3, 2.3, 1.9), (.7, 2.0, 1.5), (1, 1.1, .9)],
    'torso': [(-.16, 2.4, 4.6), (-.06, 5.0, 7.6), (.06, 6.0, 8.0), (.2, 5.8, 6.6), (.34, 5.8, 5.1), (.5, 6.6, 5.1),
              (.68, 7.8, 5.9), (.84, 7.4, 6.4), (.97, 5.6, 6.0), (1.07, 2.8, 3.6)],
    'neck': [(0, 3.3, 3.5), (1, 2.9, 2.7)],
}
# Голова в профиль: x вперёд (к лицу), y вниз; центр примерно на уровне уха.
HEAD = [(-1.5, -8.6), (3.0, -8.0), (6.2, -5.6), (7.3, -2.6), (7.4, -1.2), (9.0, 1.4), (7.6, 2.3), (7.7, 3.6),
        (7.1, 4.6), (7.0, 5.6), (5.6, 7.6), (2.6, 8.2), (.6, 6.6), (-1.8, 5.6), (-6.0, 4.8), (-7.9, 1.0),
        (-7.6, -3.6), (-5.4, -7.2)]
HAIR = [(-1.5, -9.0), (3.2, -8.4), (6.5, -5.9), (6.7, -4.3), (3.6, -5.5), (-.4, -4.9), (-2.8, -2.2),
        (-3.6, 1.4), (-5.6, 4.4), (-8.2, 1.0), (-8.0, -3.8), (-5.7, -7.6)]
# Стопа: x к носку, y к подошве; начало координат в голеностопе.
FOOT = [(-2.0, -2.4), (-3.6, .6), (-3.4, 3.0), (-1.8, 4.2), (4, 4.2), (10.5, 3.5), (14.2, 2.9), (15.3, 1.8),
        (14.4, .5), (10.5, -.4), (5, -1.6), (2, -2.8)]
SOLE = 4.2            # высота голеностопа над подошвой


# ---------- геометрия ----------
def add(a, b): return (a[0] + b[0], a[1] + b[1])
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def mul(a, k): return (a[0] * k, a[1] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1]
def dist(a, b): return math.hypot(b[0] - a[0], b[1] - a[1])
def unit(a):
    d = math.hypot(*a) or 1
    return (a[0] / d, a[1] / d)
def cw(a): return (-a[1], a[0])          # поворот на 90° по часовой (экранные координаты)
def ccw(a): return (a[1], -a[0])
def vec(deg): return (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
def at(p, deg, length): return add(p, mul(vec(deg), length))
def angle(a, b): return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def ik(base, target, l1, l2, bend):
    """Двухзвенник от base к target; bend=+1 или -1 выбирает, в какую сторону сгибается сустав."""
    d = min(max(dist(base, target), abs(l1 - l2) + 1e-6), l1 + l2 - 1e-6)
    c = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    a1 = angle(base, target) + bend * math.degrees(math.acos(max(-1.0, min(1.0, c))))
    return a1, angle(at(base, a1, l1), target)


def n(v):
    s = ('%.1f' % v).rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def nums(*vs):
    """Числа для атрибута d: без ведущих нулей, пробел только там, где нет минуса."""
    out = ''
    for v in vs:
        t = n(v).replace('0.', '.', 1) if abs(v) < 1 else n(v)
        out += (' ' if out and not t.startswith('-') else '') + t
    return out


def r1(p): return (round(p[0], 1), round(p[1], 1))


def smooth(ps):
    """Замкнутый сглаженный контур через точки (Catmull-Rom → кривые Безье).
    Смещения считаются от уже округлённой точки, поэтому ошибка не копится."""
    k = len(ps)
    cur = r1(ps[0])
    d = 'M' + nums(*cur)
    for i in range(k):
        p0, p1, p2, p3 = ps[i - 1], ps[i], ps[(i + 1) % k], ps[(i + 2) % k]
        c1 = r1(add(p1, mul(sub(p2, p0), 1 / 6)))
        c2 = r1(sub(p2, mul(sub(p3, p1), 1 / 6)))
        end = r1(p2)
        d += 'c' + nums(*sub(c1, cur), *sub(c2, cur), *sub(end, cur))
        cur = end
    return d + 'z'


def interp(prof, t):
    for (t0, f0, b0), (t1, f1, b1) in zip(prof, prof[1:]):
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0)
            return f0 + (f1 - f0) * k, b0 + (b1 - b0) * k
    r = prof[0] if t < prof[0][0] else prof[-1]
    return r[1], r[2]


def outline(a, b, prof, nf, t_from=None):
    """Контур сегмента от a до b; nf — нормаль к передней стороне."""
    d, L = unit(sub(b, a)), dist(a, b)
    rows = prof if t_from is None else [(t_from,) + interp(prof, t_from)] + [r for r in prof if r[0] > t_from]
    bone = lambda t: add(a, mul(d, t * L))
    front = [add(bone(t), mul(nf, wf)) for t, wf, wb in rows]
    back = [add(bone(t), mul(nf, -wb)) for t, wf, wb in rows]
    (t0, f0, b0), (t1, f1, b1) = rows[0], rows[-1]
    end = add(add(bone(t1), mul(d, (f1 + b1) * .42)), mul(nf, (f1 - b1) / 2))
    start = add(add(bone(t0), mul(d, -(f0 + b0) * .42)), mul(nf, (f0 - b0) / 2))
    return front + [end] + back[::-1] + [start]


def muscle(a, b, prof, nf, side, t0, t1):
    """Мышца внутри сегмента: side +1 спереди, -1 сзади, 0 по всей толщине."""
    d, L = unit(sub(b, a)), dist(a, b)
    outer, inner = [], []
    for i in range(7):
        t = t0 + (t1 - t0) * i / 6
        f = math.sin(math.pi * i / 6) ** .55
        wf, wb = interp(prof, t)
        c = add(a, mul(d, t * L))
        if side == 0:
            g = .2 + .8 * f
            outer.append(add(c, mul(nf, (wf - .9) * g)))
            inner.append(add(c, mul(nf, -(wb - .9) * g)))
        else:
            ws, wo = (wf, wb) if side > 0 else (wb, wf)
            o = ws - .9
            outer.append(add(c, mul(nf, side * o)))
            inner.append(add(c, mul(nf, side * (o - f * (o + .3 * wo)))))
    return outer + inner[::-1]


class Fig:
    def __init__(self, mat=None):
        self.layers = []
        self.box = []                   # точки, которые должны попасть в кадр
        self.ground = GROUND - (MAT if mat else 0)
        self.prop('<rect class="fx-fl" x="-400" y="%s" width="1000" height="80"/>' % GROUND)
        self.prop('<path class="fx-pl" d="M-400 %sH600"/>' % n(GROUND))
        if mat:
            self.prop('<rect class="fx-mt" x="%s" y="%s" width="%s" height="%s" rx="1.2"/>'
                      % (n(mat[0]), n(GROUND - MAT), n(mat[1] - mat[0]), n(MAT + .6)))
            self.box += [(mat[0], GROUND), (mat[1], GROUND)]

    def prop(self, svg, *pts):
        self.layers.append(svg)
        self.box += list(pts)

    def path(self, cls, ps):
        self.layers.append('<path class="%s" d="%s"/>' % (cls, smooth(ps)))
        self.box += ps

    def group(self, cls, shapes, outlined, muscles=()):
        """Сначала светлая обводка всех частей (отделяет от того, что позади), потом заливка и мышцы."""
        if outlined:
            for ps in outlined:
                self.layers.append('<path class="fx-o" d="%s"/>' % smooth(ps))
        for ps in shapes:
            self.path(cls, ps)
        for ps in muscles:
            self.layers.append('<path class="fx-hi" d="%s"/>' % smooth(ps))

    # ---------- предметы ----------
    def wall(self, x, side, top=-300):
        """Стена: лицевая грань по x, толща уходит в сторону side (+1 вправо, -1 влево)."""
        x0 = x if side > 0 else x - 10
        self.prop('<rect class="fx-pf" x="%s" y="%s" width="10" height="%s"/>' % (n(x0), top, n(GROUND - top)), (x, GROUND - 60))
        self.prop('<rect class="fx-pe" x="%s" y="%s" width="10" height="5"/>' % (n(x0), n(GROUND - 5)))
        self.prop('<path class="fx-pl" d="M%s %sV%s"/>' % (n(x), top, n(GROUND)))

    def block(self, x, y, w, h, cls='fx-pf', fit=True):
        self.prop('<rect class="%s" x="%s" y="%s" width="%s" height="%s" rx="1"/>' % (cls, n(x), n(y), n(w), n(h)),
                  *([(x, y), (x + w, y + h)] if fit else []))

    def stool(self, x, w, top):
        self.block(x, top, w, 5, 'fx-pe')
        self.block(x + 3, top + 5, 3.5, GROUND - top - 5)
        self.block(x + w - 6.5, top + 5, 3.5, GROUND - top - 5)

    def ball(self, c, r):
        self.layers.append('<circle class="fx-o" cx="%s" cy="%s" r="%s"/><circle class="fx-bl" cx="%s" cy="%s" r="%s"/>'
                           '<path class="fx-bs" d="M%s %sQ%s %s %s %s"/>' % (
                               n(c[0]), n(c[1]), n(r), n(c[0]), n(c[1]), n(r),
                               n(c[0] - r * .7), n(c[1] - r * .7), n(c[0] + r * .1), n(c[1]), n(c[0] - r * .2), n(c[1] + r * .97)))
        self.box += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]

    def strap(self, *ps):
        self.layers.append('<path class="fx-st" d="M%s"/>' % 'L'.join('%s %s' % (n(x), n(y)) for x, y in ps))

    def arrow(self, a, b):
        """Направление усилия: стрелка из a в b."""
        d = unit(sub(b, a))
        base = sub(b, mul(d, 6.5))
        l, r = add(base, mul(ccw(d), 4.2)), add(base, mul(cw(d), 4.2))
        self.layers.append('<path class="fx-ar" d="M%s %sL%s %s"/><path class="fx-ah" d="M%s %sL%s %sL%s %sZ"/>' % (
            n(a[0]), n(a[1]), n(base[0]), n(base[1]), n(b[0]), n(b[1]), n(l[0]), n(l[1]), n(r[0]), n(r[1])))
        self.box += [a, b]

    def measure(self, a, b, label_at, anchor='middle', label='см', tick=4):
        """Размерная линия для тестов: отрезок с засечками и подписью в точке label_at."""
        t = mul(cw(unit(sub(b, a))), tick)
        self.layers.append('<path class="fx-ms" d="M%s %sL%s %sM%s %sL%s %sM%s %sL%s %s"/>' % tuple(n(v) for v in (
            *a, *b, *sub(a, t), *add(a, t), *sub(b, t), *add(b, t))) +
            '<text class="fx-tx" x="%s" y="%s" text-anchor="%s">%s</text>' % (n(label_at[0]), n(label_at[1]), anchor, label))
        self.box += [a, b, label_at]

    # ---------- человек в профиль ----------
    def person(self, hip, torso, head=None, legN=None, legF=None, armN=None, armF=None, hi=()):
        """Человек в профиль, лицом в сторону по часовой стрелке от направления корпуса
        (стоя — вправо, лёжа на спине головой влево — вверх).

        Конечность: ('to', (x, y), bend, end) — тянется к точке, сустав считается сам;
        ('ang', a1, a2, end) — углы сегментов (0 вправо, 90 вниз). end — угол стопы или кисти.
        Для ног пятым элементом можно задать подошву: 'up' или 'down', если она не очевидна.
        N — ближние к зрителю конечности, F — дальние (светлее).
        hi — мышцы: (сегмент, сторона, t0, t1), сегменты torso, thighN, shinN, upperN, foreN;
        сторона +1 спереди, -1 сзади, 0 целиком.
        """
        sh = at(hip, torso, LEN['torso'])
        hdir = vec(torso if head is None else head)
        hc = add(add(sh, mul(hdir, LEN['neck'])), mul(cw(hdir), 1.5))
        j = dict(hip=hip, sh=sh, head=hc)
        segs = {}

        def limb(spec, base, l1, l2):
            a1, a2 = ik(base, spec[1], l1, l2, spec[2]) if spec[0] == 'to' else spec[1:3]
            m = at(base, a1, l1)
            return m, at(m, a2, l2), (spec[3] if len(spec) > 3 else a2), (spec[4] if len(spec) > 4 else None)

        def foot(ank, knee, fa, sole):
            f = vec(fa)
            s = cw(f)
            if sole == 'up':
                s = s if s[1] < 0 else mul(s, -1)
            elif sole == 'down':
                s = s if s[1] > 0 else mul(s, -1)
            elif dot(s, sub(knee, ank)) > 0:
                s = mul(s, -1)
            return [add(add(ank, mul(f, x)), mul(s, y)) for x, y in FOOT]

        def leg(spec, tag):
            k, a, fa, sole = limb(spec, hip, LEN['thigh'], LEN['shin'])
            ft = foot(a, k, fa, sole)
            j.update({'k' + tag: k, 'a' + tag: a, 'toe' + tag: ft[7], 'heel' + tag: ft[2], 'ball' + tag: ft[5]})
            nt, ns = ccw(unit(sub(k, hip))), ccw(unit(sub(a, k)))
            segs['thigh' + tag] = (hip, k, PROF['thigh'], nt)
            segs['shin' + tag] = (k, a, PROF['shin'], ns)
            shapes = [outline(hip, k, PROF['thigh'], nt), outline(k, a, PROF['shin'], ns), ft]
            # Обводка бедра начинается ниже тазобедренного сустава, чтобы нога не отрезалась от таза.
            outl = [outline(hip, k, PROF['thigh'], nt, .3), shapes[1], ft]
            return shapes, outl

        def arm(spec, tag):
            e, w, ha, _ = limb(spec, sh, LEN['upper'], LEN['fore'])
            h = at(w, ha, LEN['hand'])
            j.update({'e' + tag: e, 'w' + tag: w, 'h' + tag: h})
            nu, nf = ccw(unit(sub(e, sh))), ccw(unit(sub(w, e)))
            nh = ccw(unit(sub(h, w)))
            segs['upper' + tag] = (sh, e, PROF['upper'], nu)
            segs['fore' + tag] = (e, w, PROF['fore'], nf)
            shapes = [outline(sh, e, PROF['upper'], nu), outline(e, w, PROF['fore'], nf), outline(w, h, PROF['hand'], nh)]
            return shapes, shapes

        def muscles(names):
            return [muscle(*segs[s][:4], side, t0, t1) for s, side, t0, t1 in hi if s in names]

        for spec, fn in ((legF, leg), (armF, arm)):
            if spec:
                shapes, _ = fn(spec, 'F')
                self.group('fx-f', shapes, None)

        nt = cw(unit(sub(sh, hip)))
        segs['torso'] = (hip, sh, PROF['torso'], nt)
        neck = outline(add(sh, mul(hdir, 1)), sub(hc, mul(hdir, 1)), PROF['neck'], cw(hdir))
        body = [outline(hip, sh, PROF['torso'], nt), neck]
        headp = [add(add(hc, mul(cw(hdir), x)), mul(hdir, -y)) for x, y in HEAD]
        hair = [add(add(hc, mul(cw(hdir), x)), mul(hdir, -y)) for x, y in HAIR]
        self.group('fx-b', body + [headp], body + [headp], muscles({'torso'}))
        self.path('fx-hr', hair)

        if legN:
            shapes, outl = leg(legN, 'N')
            self.group('fx-b', shapes, outl, muscles({'thighN', 'shinN'}))
        if armN:
            shapes, outl = arm(armN, 'N')
            self.group('fx-b', shapes, outl, muscles({'upperN', 'foreN'}))
        return j

    # ---------- человек анфас ----------
    def front(self, cx, hip_y, arms, hi=(), legs=True):
        """Человек анфас. arms = (левая, правая): ('to', (x, y), bend, угол кисти)
        или ('pts', локоть, запястье, угол кисти), когда рука идёт к зрителю и в проекции короче.
        hi — мышцы рук: ('upper' | 'fore', t0, t1)."""
        sh_y = hip_y - LEN['torso']
        if legs:
            for s in (-1, 1):
                hp, k, a = (cx + s * 6.2, hip_y + 2), (cx + s * 7, hip_y + 32), (cx + s * 7.6, GROUND - SOLE)
                th = outline(hp, k, [(0, 6.4, 5.6), (.5, 5.2, 4.6), (1, 4.0, 3.6)], mul(ccw(unit(sub(k, hp))), -s))
                sn = outline(k, a, [(0, 3.9, 3.7), (.3, 4.6, 4.0), (.7, 3.2, 2.9), (1, 2.4, 2.3)], mul(ccw(unit(sub(a, k))), -s))
                ft = [add(a, p) for p in [(-2.6 * s, -1.5), (3.2 * s, -1), (5.2 * s, 3.1), (3.6 * s, 4.2), (-2.8 * s, 4.2), (-3.4 * s, 2.0)]]
                self.group('fx-b', [th, sn, ft], None)
        torso = [(-3, -6), (-9, -3.2), (-13.6, 1.5), (-12.6, 10), (-10, 22), (-11.6, 32), (-10.8, 40), (-2, 43),
                 (2, 43), (10.8, 40), (11.6, 32), (10, 22), (12.6, 10), (13.6, 1.5), (9, -3.2), (3, -6)]
        torso = [(cx + x, sh_y + y) for x, y in torso]
        hc = (cx, sh_y - 13)
        neck = [(cx - 3, sh_y - 2), (cx - 3, hc[1] + 4), (cx + 3, hc[1] + 4), (cx + 3, sh_y - 2)]
        headp = [(hc[0] + 6.6 * math.cos(t * math.pi / 8), hc[1] + 8.3 * math.sin(t * math.pi / 8)) for t in range(16)]
        hair = [(hc[0] + 7 * math.cos(t * math.pi / 10), hc[1] - 1 + 8.6 * math.sin(t * math.pi / 10)) for t in range(10, 21)]
        hair += [(cx + 5.2, hc[1] - 3.5), (cx + 1, hc[1] - 5.2), (cx - 3.5, hc[1] - 4.8), (cx - 5.4, hc[1] - 2.5)]
        self.group('fx-b', [torso, neck, headp], [torso])
        self.path('fx-hr', hair)
        j = {}
        for s, spec in zip((-1, 1), arms):
            sh = (cx + s * 12, sh_y + 3)
            if spec[0] == 'pts':
                e, w = spec[1], spec[2]
            else:
                a1, a2 = ik(sh, spec[1], LEN['upper'], LEN['fore'], spec[2])
                e = at(sh, a1, LEN['upper'])
                w = at(e, a2, LEN['fore'])
            h = at(w, spec[3], LEN['hand'])
            nu, nf, nh = (mul(ccw(unit(sub(q, p))), -s) for p, q in ((sh, e), (e, w), (w, h)))
            up = [(0, 4.6, 4.4), (.25, 4.3, 3.9), (.6, 3.6, 3.3), (1, 2.8, 2.6)]
            fo = [(0, 2.8, 2.8), (.25, 3.3, 3.1), (1, 2.0, 2.0)]
            hd = [(0, 2.0, 2.0), (.35, 3.1, 2.7), (.75, 2.8, 2.3), (1, 1.4, 1.2)]
            shapes = [outline(sh, e, up, nu), outline(e, w, fo, nf), outline(w, h, hd, nh)]
            ms = [muscle(*({'upper': (sh, e, up, nu), 'fore': (e, w, fo, nf)}[seg]), 0, t0, t1) for seg, t0, t1 in hi]
            self.group('fx-b', shapes, shapes, ms)
            j.update({('w', s): w, ('h', s): h, ('e', s): e})
        j['sh_y'] = sh_y
        return j

    def svg(self, view=None, min_w=150):
        if view is None:
            xs, ys = [p[0] for p in self.box], [p[1] for p in self.box]
            x0, x1, y0 = min(xs) - 8, max(xs) + 8, min(ys) - 8
            y1 = max(GROUND + 7, max(ys) + 4)
            w, h = x1 - x0, y1 - y0
            # Лёжа фигура длинная и низкая: кадр шире, чтобы над ней не оставалось пустоты.
            aspect = min(max(w / h, ASPECT), 2.1)
            if w < h * aspect:
                w = h * aspect
            w = max(w, min_w)
            h = w / aspect
            cx = (min(xs) + max(xs)) / 2
            view = (cx - w / 2, y1 - h, w, h)
        return '<svg viewBox="%s" aria-hidden="true">%s</svg>' % (' '.join(n(v) for v in view), ''.join(self.layers))


ON_FLOOR = GROUND - SOLE              # голеностоп стоящего человека
ON_MAT = GROUND - MAT - SOLE
MAT_TOP = GROUND - MAT
STAND = ON_FLOOR - LEN['shin'] - LEN['thigh']   # таз стоящего человека


# ---------- упражнения ----------
def calf_iso():
    f = Fig(); f.wall(150, 1)
    ank = 117.6                       # на носках: голеностоп приподнят
    hip = (102, ank - 59)
    j = f.person(hip, -86, legN=('ang', 89, 91, 52), legF=('ang', 90, 92, 52),
                 armN=('to', (147.5, hip[1] - 39), 1, -76), armF=('to', (147.5, hip[1] - 36), 1, -74),
                 hi=[('shinN', -1, .04, .66)])
    h = j['heelN']
    f.arrow((h[0] - 7, h[1] + 9), (h[0] - 7, h[1] - 9))
    return f


def calf_str():
    f = Fig(); f.wall(166, 1)
    back = (62, ON_FLOOR)
    hip = at(back, -55, 58.6)
    j = f.person(hip, -60, legN=('to', back, -1, 0), legF=('to', (128, ON_FLOOR), -1, 0),
                 armN=('to', (163.5, hip[1] - 36), 1, -70), armF=('to', (163.5, hip[1] - 33), 1, -70),
                 hi=[('shinN', -1, .04, .66)])
    return f


def knee_iso():
    f = Fig(); f.wall(60, -1)
    hip = (68.5, ON_FLOOR - LEN['shin'])
    f.person(hip, -90, legN=('ang', 0, 90, 0), legF=('ang', -1, 91, 0),
             armN=('ang', 4, 0, 0), armF=('ang', 6, 2, 2),
             hi=[('thighN', 1, .05, .92)])
    return f


def knee_str():
    f = Fig(); f.wall(150, 1)
    hip = (98, STAND)
    j = f.person(hip, -86, legF=('ang', 90, 90, 0),
                 legN=('ang', 94, -112, -150, 'up'),
                 armF=('to', (147.5, hip[1] - 32), 1, -76),
                 armN=('to', (84, hip[1] - 3), 1, 160),
                 hi=[('thighN', 1, .05, .92)])
    return f


def ham_iso():
    f = Fig(mat=(30, 170))
    hip = (84, MAT_TOP - 7.6)
    j = f.person(hip, 180.5, legF=('ang', .5, 1, -82),
                 legN=('to', (hip[0] + 56, MAT_TOP - 3.6), -1, -66),
                 armF=('ang', 4, 0, 0), armN=('ang', 3, 0, 0),
                 hi=[('thighN', -1, .08, .92)])
    a = j['heelN']
    f.arrow((a[0], a[1] - 26), (a[0], a[1] - 9))
    return f


def ham_str():
    f = Fig(); f.stool(124, 36, 92)
    hip = (78, STAND)
    f.person(hip, -38, legF=('ang', 90, 90, 0),
             legN=('to', (139, 88), -1, -72),
             armN=('to', (115, 77), 1, 20), armF=('to', (111, 75), 1, 20),
             hi=[('thighN', -1, .08, .92)])
    return f


def hipflex_iso():
    f = Fig(mat=(26, 160))
    hip = (84, MAT_TOP - 7.6)
    feet = (hip[0] + 42, ON_MAT)
    j = f.person(hip, 180.5, legF=('to', (feet[0] + 1.5, feet[1]), -1, 0), legN=('to', feet, -1, 0),
                 armF=('ang', 4, 0, 0), armN=('ang', 3, 0, 0),
                 hi=[('thighN', 0, .02, .6)])
    k = j['kN']
    f.ball((k[0] - 2, k[1] + 3), 7)
    f.arrow((k[0] - 22, k[1] - 12), (k[0] - 10, k[1] - 4))
    f.arrow((k[0] + 18, k[1] - 12), (k[0] + 7, k[1] - 4))
    return f


def hipflex_str():
    f = Fig(mat=(30, 170))
    knee = (80, MAT_TOP - 3.7)
    hip = at(knee, -70, LEN['thigh'])
    f.person(hip, -93, legN=('ang', 110, 180, 180, 'up'),
             legF=('to', (hip[0] + 33, ON_MAT), -1, 0),
             armN=('to', (hip[0] + 24, hip[1] - 4), 1, 10), armF=('to', (hip[0] + 26, hip[1] - 6), 1, 10),
             hi=[('thighN', 1, 0, .55), ('torso', -1, -.1, .3)])
    return f


def core_iso():
    f = Fig(mat=(30, 175))
    sh = (138, MAT_TOP - 2.7 - LEN['upper'])
    tilt = -8.2
    hip = at(sh, tilt + 180, LEN['torso'])
    f.person(hip, tilt, head=tilt - 4,
             legN=('ang', tilt + 180, tilt + 180, 100), legF=('ang', tilt + 180, tilt + 180, 100),
             armN=('ang', 90, -1, 0), armF=('ang', 90, -1, 0),
             hi=[('torso', -1, .1, .8)])
    return f


def core_str():
    f = Fig(mat=(30, 180))
    knee = (90, MAT_TOP - 3.7)
    hip = at(knee, 207, LEN['thigh'])
    f.person(hip, 8, head=12,
             legN=('ang', 27, 180, 180, 'up'), legF=('ang', 27, 181, 180, 'up'),
             armN=('to', (139, MAT_TOP - 2), 1, 2), armF=('to', (137, MAT_TOP - 2), 1, 2),
             hi=[('torso', 1, .05, 1)])
    return f


def shoulder_iso():
    f = Fig()
    cx, hip_y = 100, STAND
    y = hip_y - LEN['torso'] + 3
    for x in (37, 155):
        f.block(x, -300, 8, GROUND + 300, 'fx-pf', fit=False)
        f.block(x + (6 if x < 100 else 0), -300, 2, GROUND + 300, 'fx-pe', fit=False)
    f.block(37, hip_y - 74, 126, 9, 'fx-pf')
    f.front(cx, hip_y, arms=(('to', (40, y), 1, -90), ('to', (160, y), -1, -90)), hi=[('upper', 0, .32)])
    f.arrow((60, y - 20), (44, y - 20))
    f.arrow((140, y - 20), (156, y - 20))
    return f


def shoulder_str():
    f = Fig()
    hip = (98, ON_FLOOR - 57.5)
    sh = at(hip, -82, LEN['torso'])
    jamb = sh[0] - LEN['upper'] - 2.8       # предплечье прижато к косяку
    f.block(jamb - 12, -300, 12, GROUND + 300, 'fx-pf', fit=False)
    f.block(jamb - 2, -300, 2, GROUND + 300, 'fx-pe', fit=False)
    f.box.append((jamb - 12, GROUND))
    f.person(hip, -82, legN=('to', (80, ON_FLOOR), -1, 0), legF=('to', (122, ON_FLOOR), -1, 0),
             armN=('ang', 181, -90, -90), armF=('ang', 96, 64, 64),
             hi=[('torso', -1, .55, .96), ('upperN', 1, 0, .5)])
    return f


def back_iso():
    f = Fig(mat=(40, 175))
    hip = (70, MAT_TOP - 7.4)
    j = f.person(hip, -97, legN=('to', (hip[0] + 62, ON_MAT + .4), 1, -80), legF=('to', (hip[0] + 62, ON_MAT), 1, -80),
                 armN=('to', (hip[0] + 21, hip[1] - 14), 1, 0), armF=('to', (hip[0] + 23, hip[1] - 15), 1, 0),
                 hi=[('torso', 1, .3, .95), ('upperN', 1, .12, .9)])
    ball, top = j['ballN'], j['toeN']
    f.strap(j['hN'], (ball[0] + 2, ball[1] + 1.5), (top[0] - 2, top[1] - 4), j['hN'])
    w = j['wN']
    f.arrow((w[0] + 4, w[1] - 13), (w[0] - 16, w[1] - 13))
    return f


def back_str():
    f = Fig(); f.block(150, 63, 36, 5, 'fx-pe'); f.block(178, 68, 5, GROUND - 68)
    hip = (84, STAND + 1)
    f.person(hip, -2, head=14,
             legN=('ang', 93, 88, 0), legF=('ang', 93, 88, 0),
             armN=('to', (160, 60), 1, 0), armF=('to', (157, 61), 1, 0),
             hi=[('torso', 1, .35, 1.02), ('upperN', -1, .05, .8)])
    return f


def wrist_iso():
    f = Fig()
    cx, hip_y = 100, STAND
    sh_y = hip_y - LEN['torso']
    f.front(cx, hip_y, legs=False,
            arms=(('pts', (cx - 30, sh_y + 22), (cx - 3, sh_y + 14), -90),
                  ('pts', (cx + 30, sh_y + 22), (cx + 3, sh_y + 14), -90)),
            hi=[('fore', .05, .95)])
    y = sh_y + 4
    f.arrow((cx - 32, y), (cx - 12, y))
    f.arrow((cx + 32, y), (cx + 12, y))
    return f, (cx - 52, sh_y - 30, 104, 104 / ASPECT)


def wrist_str():
    f = Fig()
    hip = (62, STAND)
    j = f.person(hip, -90, armN=('ang', 0, 0, -84),
                 armF=('to', (106, hip[1] - 33), -1, -105),
                 hi=[('foreN', 0, .05, .95)])
    h = j['hN']
    f.arrow((h[0] + 12, h[1] - 6), (h[0] - 6, h[1] - 6))
    return f, (40, hip[1] - 62, 104, 104 / ASPECT)


def test_bend():
    f = Fig()
    hip = (84, STAND)
    j = f.person(hip, 12, head=95, legN=('ang', 91, 90, 0), legF=('ang', 91, 90, 0),
                 armN=('ang', 92, 92, 92), armF=('ang', 90, 91, 91),
                 hi=[('thighN', -1, .08, .92)])
    tip = j['hN']
    x = tip[0] + 12
    f.measure((x, tip[1] + 1.5), (x, GROUND), (x + 6, (tip[1] + GROUND) / 2 + 4), 'start')
    return f


def test_knee():
    f = Fig(mat=(40, 156)); f.wall(156, 1)
    ankle = (128, ON_MAT)
    knee = (152, ankle[1] - math.sqrt(LEN['shin'] ** 2 - 24 ** 2))
    hip = at(knee, 196, LEN['thigh'])
    # Задняя нога стоит коленом на коврике, голень лежит на нём.
    dy = MAT_TOP - 3.7 - hip[1]
    back = math.degrees(math.atan2(dy, -math.sqrt(LEN['thigh'] ** 2 - dy * dy)))
    j = f.person(hip, -84, legN=('to', ankle, -1, 0), legF=('ang', back, 180, 180, 'up'),
                 armN=('to', (153.5, hip[1] - 36), 1, -78), armF=('to', (153.5, hip[1] - 33), 1, -78),
                 hi=[('shinN', -1, .04, .66)])
    x0 = j['toeN'][0] + 2
    f.measure((x0, GROUND + 4.5), (156, GROUND + 4.5), (x0 - 3, GROUND + 9), 'end', tick=3)
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
    'test-bend': test_bend, 'test-knee': test_knee,
}


def render_all():
    out = {}
    for key, fn in FIGS.items():
        r = fn()
        f, view = r if isinstance(r, tuple) else (r, None)
        out[key] = f.svg(view)
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

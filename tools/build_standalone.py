#!/usr/bin/env python3
"""Собирает standalone/index.html: index.html с иконками и манифестом внутри, без внешних файлов.

Запуск из корня репозитория: python3 tools/build_standalone.py
"""
import base64
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def data_uri(name, mime):
    return 'data:%s;base64,%s' % (mime, base64.b64encode((ROOT / 'icons' / name).read_bytes()).decode())


def build(src):
    links = (
        '<link rel="manifest" href="manifest.webmanifest">\n'
        '<link rel="icon" href="icons/icon.svg" type="image/svg+xml">\n'
        '<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">\n'
    )
    if links not in src:
        sys.exit('index.html: не найдены ссылки на манифест и иконки')
    inline = (
        '<link rel="icon" href="%s" type="image/svg+xml">\n'
        '<link rel="apple-touch-icon" href="%s">\n'
    ) % (data_uri('icon.svg', 'image/svg+xml'), data_uri('apple-touch-icon.png', 'image/png'))
    src = src.replace(links, inline, 1)

    # Манифест собирается в браузере: в отдельном файле ему не на что сослаться.
    title = '<title>'
    manifest = """<script>
(function () {
  try {
    var base = location.href.split('#')[0].split('?')[0];
    var m = {
      name: 'Сильные сухожилия и гибкость', short_name: 'Сухожилия', lang: 'ru',
      start_url: base, scope: base.replace(/[^\\/]*$/, ''), display: 'standalone', orientation: 'portrait',
      background_color: '#0f2a33', theme_color: '#0f2a33',
      icons: [
        { src: '%s', sizes: '192x192', type: 'image/png', purpose: 'any' },
        { src: '%s', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: '%s', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
      ]
    };
    var l = document.createElement('link'); l.rel = 'manifest';
    l.href = URL.createObjectURL(new Blob([JSON.stringify(m)], { type: 'application/manifest+json' }));
    document.head.appendChild(l);
  } catch (e) {}
})();
</script>
""" % (data_uri('icon-192.png', 'image/png'), data_uri('icon-512.png', 'image/png'),
       data_uri('icon-maskable-512.png', 'image/png'))
    return src.replace(title, manifest + title, 1)


if __name__ == '__main__':
    src = (ROOT / 'index.html').read_text(encoding='utf-8')
    out = ROOT / 'standalone' / 'index.html'
    out.parent.mkdir(exist_ok=True)
    out.write_text(build(src), encoding='utf-8')
    print('standalone/index.html: %d КБ' % (out.stat().st_size // 1024))

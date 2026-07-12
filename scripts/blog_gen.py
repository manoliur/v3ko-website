#!/usr/bin/env python3
"""
Генератор SEO-статей для блога v3ko.ru.

Пишет статью через LLM (DeepSeek, те же ключи, что у контент-завода),
рендерит её в шаблон сайта и обновляет blog/index.html + sitemap.xml.

Использование:
  python3 scripts/blog_gen.py "Тема статьи"        # статья на заданную тему
  python3 scripts/blog_gen.py --auto                # LLM сам предложит тему
  python3 scripts/blog_gen.py --auto --dry-run      # показать без записи

Ключи: AI_API_KEY / AI_API_URL / AI_MODEL из окружения,
иначе подтягиваются из .env тест-копии завода (бренд V3Ko).
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "blog"
SITEMAP = ROOT / "sitemap.xml"
FACTORY_ENV = Path("/root/projects/bamwall-factory-test/.env")

MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

SITE_CONTEXT = """
Сайт v3ko.ru — платформа AI-продуктов и автоматизации для бизнеса (бренд V3Ko).
Продукты (используй для внутренних ссылок, где уместно):
- /n8n/ — каталог 9 580 готовых n8n-шаблонов автоматизации (100 ⭐ Telegram Stars в месяц, по 3 бесплатных в каждой категории);
- /prompts/ и https://prompts.v3ko.ru — 2 000+ бесплатных промптов для ChatGPT, Midjourney, Claude, Stable Diffusion;
- /zavod/ — контент-завод: система ведения соцсетей бизнеса на автопилоте (AI генерирует посты и картинки, проверяет факты, публикует в Telegram/VK/ОК/блог, учится на метриках), продаётся под ключ;
- Voice Assistant @VoiceV3k_bot — бесплатный голосовой AI-ассистент в Telegram;
- Telegram-канал @ai_vmasterke (https://t.me/ai_vmasterke) — ежедневные промпты и AI-новости.
НЕ выдумывай других фактов о V3Ko (цен, дат, имён, статистики) — только перечисленное.
"""

SYSTEM = """Ты — SEO-редактор блога v3ko.ru. Пишешь экспертные статьи на русском языке
для владельцев малого бизнеса и начинающих в AI. Стиль: конкретика, примеры, списки,
никакой воды и канцелярита. Числа и факты о V3Ko — только из переданного контекста.
Отвечаешь СТРОГО валидным JSON без markdown-обёрток."""


def load_keys():
    """AI_API_KEY/URL/MODEL из окружения или из .env тест-копии завода."""
    keys = {k: os.environ.get(k, "") for k in ("AI_API_KEY", "AI_API_URL", "AI_MODEL")}
    if not keys["AI_API_KEY"] and FACTORY_ENV.exists():
        for line in FACTORY_ENV.read_text().splitlines():
            m = re.match(r"^(AI_API_KEY|AI_API_URL|AI_MODEL)=(.*)$", line.strip())
            if m and not keys[m.group(1)]:
                keys[m.group(1)] = m.group(2).strip()
    if not keys["AI_API_KEY"]:
        sys.exit("Нет AI_API_KEY (ни в окружении, ни в %s)" % FACTORY_ENV)
    return (keys["AI_API_KEY"],
            (keys["AI_API_URL"] or "https://api.deepseek.com").rstrip("/"),
            keys["AI_MODEL"] or "deepseek-chat")


def llm(user_prompt, max_tokens=6000, temperature=0.7):
    key, base, model = load_keys()
    resp = requests.post(
        base + "/chat/completions",
        headers={"Authorization": "Bearer " + key},
        json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": user_prompt}]},
        timeout=300)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def existing_titles():
    titles = []
    for f in BLOG.glob("*.html"):
        if f.name == "index.html":
            continue
        m = re.search(r"<h1>(.*?)</h1>", f.read_text(), re.S)
        if m:
            titles.append(re.sub(r"<[^>]+>", "", m.group(1)).strip())
    return titles


def pick_topic():
    have = existing_titles()
    raw = llm(SITE_CONTEXT + f"""
В блоге уже есть статьи: {have}.
Предложи ОДНУ новую тему SEO-статьи для этого блога — с хорошим поисковым спросом
в рунете, релевантную продуктам сайта и не дублирующую существующие.
JSON: {{"topic": "..."}}""", max_tokens=200)
    return parse_json(raw)["topic"]


def gen_article(topic):
    raw = llm(SITE_CONTEXT + f"""
Напиши SEO-статью для блога на тему: «{topic}».

Требования к body_html:
- 1200–1800 слов, HTML-фрагмент БЕЗ <h1> (только <h2>/<h3>/<p>/<ul>/<ol>/<li>/<blockquote>/<strong>/<code>/<a>);
- структура: вводный абзац с <strong>ключевой фразой</strong>, 5–8 разделов <h2>, внутри — подразделы <h3>, списки и примеры;
- раздел «Часто задаваемые вопросы» с 3 вопросами <h3> ближе к концу;
- 2–4 внутренние ссылки на страницы сайта (пути вида ../n8n/, ../prompts/, ../zavod/ — статья лежит в /blog/);
- никаких выдуманных цифр, исследований и имён.

JSON-ответ:
{{
  "title": "заголовок до 65 символов с ключевой фразой",
  "slug": "korotkij-slug-3-5-slov-latinicej",
  "description": "meta description 140-160 символов",
  "keywords": "5-7 ключевых фраз через запятую",
  "category": "одно слово для рубрики, например Автоматизация",
  "tags": ["тег1", "тег2"],
  "excerpt": "анонс для карточки блога, 1-2 предложения",
  "body_html": "..."
}}""")
    return parse_json(raw)


def render(article):
    today = date.today()
    date_ru = f"{today.day} {MONTHS_RU[today.month - 1]} {today.year}"
    words = len(re.sub(r"<[^>]+>", " ", article["body_html"]).split())
    minutes = max(3, round(words / 180))
    tags_html = "".join(f'\n          <span class="tag">{t}</span>' for t in article["tags"][:3])
    url = f"https://v3ko.ru/blog/{article['slug']}.html"

    page = TEMPLATE
    for k, v in {
        "TITLE": article["title"], "DESCRIPTION": article["description"],
        "KEYWORDS": article["keywords"], "URL": url, "DATE_ISO": today.isoformat(),
        "DATE_RU": date_ru, "MINUTES": str(minutes), "TAGS": tags_html,
        "CATEGORY": article["category"], "BODY": article["body_html"],
    }.items():
        page = page.replace("{{%s}}" % k, v)
    return page, minutes


def update_blog_index(article, minutes):
    idx = BLOG / "index.html"
    html = idx.read_text()
    tags_html = "".join(f'\n          <span class="tag">{t}</span>' for t in article["tags"][:2])
    card = f'''      <div class="blog-card reveal" style="--blog-img:url('../public/bg-abstract.jpg')">
        <div class="b-cat">{article["category"]}</div>
        <h3><a href="{article["slug"]}.html">{article["title"]}</a></h3>
        <div class="b-excerpt">{article["excerpt"]}</div>
        <div class="b-meta">
          <span>{minutes} мин чтения</span>{tags_html}
        </div>
        <a href="{article["slug"]}.html" class="b-read">Читать статью →</a>
      </div>
'''
    marker = '<div class="blog-grid">\n'
    if marker not in html:
        print("⚠ blog/index.html: маркер blog-grid не найден, карточка не добавлена")
        return
    idx.write_text(html.replace(marker, marker + card, 1))


def update_sitemap(article):
    xml = SITEMAP.read_text()
    loc = f"https://v3ko.ru/blog/{article['slug']}.html"
    if loc in xml:
        return
    entry = (f"  <url>\n    <loc>{loc}</loc>\n    <priority>0.6</priority>\n"
             f"    <changefreq>monthly</changefreq>\n  </url>\n")
    SITEMAP.write_text(xml.replace("</urlset>", entry + "</urlset>"))


TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{TITLE}} — Блог V3Ko</title>
  <meta name="description" content="{{DESCRIPTION}}">
  <meta name="keywords" content="{{KEYWORDS}}">
  <meta property="og:title" content="{{TITLE}} — Блог V3Ko">
  <meta property="og:description" content="{{DESCRIPTION}}">
  <meta property="og:image" content="https://v3ko.ru/public/og-image.png">
  <meta property="og:url" content="{{URL}}">
  <meta property="og:type" content="article">
  <link rel="canonical" href="{{URL}}">
  <link rel="icon" type="image/svg+xml" href="../public/favicon.svg">
  <link rel="stylesheet" href="../css/style.css">
  <script type="application/ld+json">{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{{TITLE}}",
    "description": "{{DESCRIPTION}}",
    "datePublished": "{{DATE_ISO}}",
    "author": {"@type":"Organization","name":"V3Ko"}
  }</script>
  <!-- Yandex.Metrika counter -->
  <script type="text/javascript">
  (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
  m[i].l=1*new Date();k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
  (window,document,'script','https://mc.yandex.ru/metrika/tag.js?id=110451940','ym');
  ym(110451940,'init',{clickmap:true,trackLinks:true,accurateTrackBounce:true});
  </script>
  <noscript><div><img src="https://mc.yandex.ru/watch/110451940" style="position:absolute;left:-9999px" alt=""></div></noscript>
  <!-- /Yandex.Metrika counter -->
</head>
<body>

<nav class="navbar" id="navbar">
  <div class="nv">
    <a href="/" class="logo">V<span>3</span>Ko</a>
    <div class="nl">
      <a href="/">Главная</a>
      <a href="../n8n/">N8N</a>
      <a href="../prompts/">Промпты</a>
      <a href="../zavod/">Контент-завод</a>
      <a href="../pricing/">Цены</a>
      <a href="../blog/" class="active">Блог</a>
      <a href="https://t.me/ai_vmasterke">Канал</a>
      <a href="https://prompts.v3ko.ru" class="nav-cta">Начать</a>
    </div>
    <button class="nt" id="nt" aria-label="Меню"><span></span><span></span><span></span></button>
  </div>
</nav>

<article class="article">
  <div class="article-content">
    <div class="article-header reveal">
      <div class="page-breadcrumb" style="margin-bottom:1rem">
        <a href="/">Главная</a><span class="sep">/</span><a href="../blog/">Блог</a><span class="sep">/</span><span>{{CATEGORY}}</span>
      </div>
      <h1>{{TITLE}}</h1>
      <div class="meta">
        <span>{{MINUTES}} мин чтения</span>
        <span>·</span>
        <span>{{DATE_RU}}</span>
        <span>·</span>{{TAGS}}
      </div>
    </div>

    <div class="article-body reveal">
{{BODY}}

      <div class="art-cta">
        <p>💬 Хотите, чтобы соцсети и блог вашего бизнеса вёл AI? Посмотрите наш <a href="../zavod/">контент-завод</a> — или заберите 2 000+ бесплатных промптов.</p>
        <a href="https://prompts.v3ko.ru" class="btn btn-p btn-sm">Получить промпты →</a>
      </div>
    </div>

    <div class="page-nav reveal">
      <a href="../blog/">← Все статьи</a>
    </div>
  </div>
</article>

<footer class="ftr">
  <div class="container">
    <div class="ft">
      <div class="fb">
        <a href="/" class="fl">V<span style="color:var(--cyan)">3</span>Ko</a>
        <p class="fd2">AI-продукты и автоматизации для Telegram</p>
      </div>
      <div class="fl2">
        <div class="fc2">
          <h5>Продукты</h5>
          <a href="../n8n/">N8N Каталог</a>
          <a href="../prompts/">Промпты дня</a>
          <a href="../zavod/">Контент-завод</a>
          <a href="../pricing/">Цены и тарифы</a>
          <a href="https://t.me/VoiceV3k_bot">Voice Assistant</a>
        </div>
        <div class="fc2">
          <h5>Информация</h5>
          <a href="../blog/">Блог</a>
          <a href="n8n-avtomatizacia-biznesa.html">N8N гайд</a>
          <a href="prompty-dlya-neyrosetey.html">Промпты гайд</a>
        </div>
        <div class="fc2">
          <h5>Сообщество</h5>
          <a href="https://t.me/ai_vmasterke">Telegram Канал</a>
          <a href="https://t.me/vmasterke">Telegram Форум</a>
          <a href="https://github.com/manoliur">GitHub</a>
        </div>
      </div>
    </div>
    <div class="fb2">
      <span>© 2026 V3Ko</span>
      <span>Оплата звёздами Telegram</span>
    </div>
  </div>
</footer>

<script>
document.getElementById('nt').addEventListener('click', function(){
  document.querySelector('.nl').classList.toggle('active');
  this.classList.toggle('active');
});
document.querySelectorAll('.nl a').forEach(l => l.addEventListener('click', () => {
  document.querySelector('.nl').classList.remove('active');
  document.getElementById('nt').classList.remove('active');
}));
const rv = new IntersectionObserver(e => {
  e.forEach(e => { if (e.isIntersecting) { e.target.classList.add('revealed'); rv.unobserve(e.target); } });
}, { threshold: .1 });
document.querySelectorAll('.reveal').forEach(e => rv.observe(e));
window.addEventListener('scroll', () => { document.getElementById('navbar').classList.toggle('scrolled', window.pageYOffset > 50); });
</script>
</body>
</html>
"""


def main():
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]
    auto = "--auto" in sys.argv[1:]

    topic = args[0] if args else (pick_topic() if auto else None)
    if not topic:
        sys.exit(__doc__)
    print("Тема:", topic)

    article = gen_article(topic)
    slug = re.sub(r"[^a-z0-9-]", "", article["slug"].lower()) or "article"
    article["slug"] = slug
    page, minutes = render(article)

    if dry:
        print(json.dumps({k: v for k, v in article.items() if k != "body_html"},
                         ensure_ascii=False, indent=2))
        print("--- body_html:", len(article["body_html"]), "символов")
        return

    out = BLOG / f"{slug}.html"
    if out.exists():
        sys.exit(f"⚠ {out} уже существует — не перезаписываю")
    out.write_text(page)
    update_blog_index(article, minutes)
    update_sitemap(article)
    print(f"✓ {out.relative_to(ROOT)} ({minutes} мин чтения), "
          f"blog/index.html и sitemap.xml обновлены")


if __name__ == "__main__":
    main()

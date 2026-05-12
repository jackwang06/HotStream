from unittest.mock import Mock, patch

from hotstream.image_scraper import (
    build_image_search_url,
    build_news_search_url,
    extract_article_image_candidates,
    extract_news_result_urls,
    fetch_related_images,
)


def test_build_news_search_url_uses_topic_title_and_news_intent():
    url = build_news_search_url("赵文卓现身闽超再现郑成功经典形象")

    assert "sogou.com/web" in url
    assert "%E8%B5%B5%E6%96%87%E5%8D%93" in url
    assert "%E6%96%B0%E9%97%BB" in url


def test_extract_news_result_urls_from_sogou_results():
    html = '''
    <div class="vrwrap"><h3><a href="https://news.example.com/a.html&amp;from=sogou">报道 A</a></h3></div>
    <div class="vrwrap"><h3><a href="https://news.example.com/b.html">报道 B</a></h3></div>
    <div class="vrwrap"><h3><a href="https://news.example.com/a.html&amp;from=sogou">重复结果</a></h3></div>
    '''

    assert extract_news_result_urls(html, limit=5) == [
        "https://news.example.com/a.html&from=sogou",
        "https://news.example.com/b.html",
    ]


def test_extract_news_result_urls_from_duckduckgo_results():
    html = '''
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example.com%2Fa.html&amp;rut=1">报道 A</a>
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example.com%2Fb.html&amp;rut=2">报道 B</a>
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example.com%2Fa.html&amp;rut=3">重复结果</a>
    '''

    assert extract_news_result_urls(html, limit=5) == [
        "https://news.example.com/a.html",
        "https://news.example.com/b.html",
    ]


def test_extract_news_result_urls_from_bing_results():
    html = '''
    <li class="b_algo"><h2><a href="https://news.example.com/a.html">报道 A</a></h2></li>
    <li class="b_algo"><h2><a href="https://news.example.com/b.html">报道 B</a></h2></li>
    <li class="b_algo"><h2><a href="/local/path">无效结果</a></h2></li>
    <li class="b_algo"><h2><a href="https://news.example.com/a.html">重复结果</a></h2></li>
    '''

    assert extract_news_result_urls(html, limit=5) == [
        "https://news.example.com/a.html",
        "https://news.example.com/b.html",
    ]


def test_extract_article_image_candidates_prefers_og_and_article_images():
    html = '''
    <html><head>
      <meta property="og:title" content="赵文卓现身闽超" />
      <meta property="og:image" content="/cover.jpg" />
    </head><body>
      <article>
        <img src="/article-1.jpg" alt="赵文卓郑成功造型" />
        <img data-src="https://cdn.example.com/article-2.png" alt="闽超现场" />
      </article>
      <img src="/logo.png" alt="logo" />
    </body></html>
    '''

    images = extract_article_image_candidates(html, "https://news.example.com/path/story.html", source_title="报道 A")

    assert images[:3] == [
        {
            "url": "https://news.example.com/cover.jpg",
            "thumbnail": "https://news.example.com/cover.jpg",
            "title": "报道 A 封面图",
            "source_url": "https://news.example.com/path/story.html",
            "source": "新闻原文",
        },
        {
            "url": "https://news.example.com/article-1.jpg",
            "thumbnail": "https://news.example.com/article-1.jpg",
            "title": "赵文卓郑成功造型",
            "source_url": "https://news.example.com/path/story.html",
            "source": "新闻原文",
        },
        {
            "url": "https://cdn.example.com/article-2.png",
            "thumbnail": "https://cdn.example.com/article-2.png",
            "title": "闽超现场",
            "source_url": "https://news.example.com/path/story.html",
            "source": "新闻原文",
        },
    ]


def test_build_image_search_url_uses_topic_title_and_creative_commons_filter():
    url = build_image_search_url("AI 应用爆发")

    assert "bing.com/images/search" in url
    assert "AI+%E5%BA%94%E7%94%A8%E7%88%86%E5%8F%91" in url
    assert "qft=+filterui:license-L2_L3_L4_L5_L6_L7" in url


def test_fetch_related_images_prefers_images_from_news_articles():
    search_html = '<li class="b_algo"><h2><a href="https://news.example.com/story.html">热点报道</a></h2></li>'
    article_html = '''
    <html><head><meta property="og:image" content="https://news.example.com/hot-cover.jpg" /></head>
    <body><article><img src="https://news.example.com/hot-body.jpg" alt="热点现场" /></article></body></html>
    '''
    search_response = Mock()
    search_response.__enter__ = Mock(return_value=search_response)
    search_response.__exit__ = Mock(return_value=None)
    search_response.read.return_value = search_html.encode("utf-8")
    article_response = Mock()
    article_response.__enter__ = Mock(return_value=article_response)
    article_response.__exit__ = Mock(return_value=None)
    article_response.read.return_value = article_html.encode("utf-8")

    with patch("hotstream.image_scraper.urlopen", side_effect=[search_response, article_response]):
        images = fetch_related_images("赵文卓现身闽超再现郑成功经典形象", limit=3)

    assert images[0]["url"] == "https://news.example.com/hot-cover.jpg"
    assert images[0]["source"] == "新闻原文"
    assert images[0]["source_url"] == "https://news.example.com/story.html"


def test_fetch_related_images_does_not_return_generic_image_search_when_news_articles_have_no_images():
    html = '''
    <a class="iusc" m='{"murl":"https://example.com/a.jpg","turl":"https://example.com/a-thumb.jpg","t":"泛化图片"}'></a>
    '''
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    response.read.return_value = html.encode("utf-8")

    with patch("hotstream.image_scraper.urlopen", return_value=response):
        assert fetch_related_images("AI 应用爆发", limit=5) == []


def test_fetch_related_images_returns_empty_list_when_search_fails():
    with patch("hotstream.image_scraper.urlopen", side_effect=OSError("network down")):
        assert fetch_related_images("AI 应用爆发", limit=5) == []


def test_fetch_related_images_allows_up_to_thirty_images():
    search_html = "".join(
        f'<li class="b_algo"><h2><a href="https://news.example.com/story-{i}.html">报道 {i}</a></h2></li>'
        for i in range(35)
    )

    def response_for(text: str) -> Mock:
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = text.encode("utf-8")
        return response

    article_htmls = [
        f'<html><body><article><img src="https://news.example.com/image-{i}.jpg" alt="图片 {i}" /></article></body></html>'
        for i in range(35)
    ]
    responses = [response_for(search_html)] + [response_for(html) for html in article_htmls]

    with patch("hotstream.image_scraper.urlopen", side_effect=responses):
        images = fetch_related_images("热点", limit=30)

    assert len(images) == 30
    assert images[0]["url"] == "https://news.example.com/image-0.jpg"
    assert images[-1]["url"] == "https://news.example.com/image-29.jpg"


def test_fetch_related_images_caps_requested_limit_at_thirty():
    search_html = "".join(
        f'<li class="b_algo"><h2><a href="https://news.example.com/story-{i}.html">报道 {i}</a></h2></li>'
        for i in range(35)
    )

    def response_for(text: str) -> Mock:
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = text.encode("utf-8")
        return response

    article_htmls = [
        f'<html><body><article><img src="https://news.example.com/image-{i}.jpg" alt="图片 {i}" /></article></body></html>'
        for i in range(35)
    ]
    responses = [response_for(search_html)] + [response_for(html) for html in article_htmls]

    with patch("hotstream.image_scraper.urlopen", side_effect=responses):
        images = fetch_related_images("热点", limit=100)

    assert len(images) == 30

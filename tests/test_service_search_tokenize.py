from __future__ import annotations

from knowledge.services.service_search import ServiceSearchService


def test_tokenize_keeps_ascii_words():
    assert ServiceSearchService._tokenize("Agent Run manifest_v2") == {"agent", "run", "manifest_v2"}


def test_tokenize_emits_cjk_bigrams():
    # Chinese has no whitespace word boundaries; bigrams give lexical overlap a signal.
    assert ServiceSearchService._tokenize("读凭证") == {"读凭", "凭证"}
    assert ServiceSearchService._tokenize("扩容到 4 个") == {"扩容", "容到", "4", "个"}
    # Punctuation splits runs; mixed scripts keep both token kinds.
    assert ServiceSearchService._tokenize("worker，扩容") == {"worker", "扩容"}


def test_text_score_matches_chinese_query():
    service = ServiceSearchService()
    query = "读凭证用于什么场景"
    assert service._text_score(query, "读凭证用于浏览 warehouse 目录") > 0
    assert service._text_score(query, "worker lease ttl") == 0
    # A passage covering more of the query's bigrams outranks a weaker one.
    assert service._text_score(query, "读凭证用于浏览目录，写凭证用于上传场景") > service._text_score(query, "读凭证")

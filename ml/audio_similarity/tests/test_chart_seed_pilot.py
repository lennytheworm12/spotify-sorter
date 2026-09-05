import pytest

from audio_similarity.chart_seed_pilot import parse_chart, pilot_sources, write_json, validate_period


def test_aria_nested_text_and_entities():
    html = '<div class="c-chart-item__rank"><span>1</span></div><a class="c-chart-item__title">A &amp; B</a><a class="c-chart-item__artist"><b>Artist</b></a>'
    assert parse_chart(html, 'aria', 1) == [{'rank': 1, 'title': 'A & B', 'artist': 'Artist'}]


def test_billboard_uses_mobile_rank_once():
    html = '<td class="rank_td">1</td><p class="rank">1</p><p class="musuc_title">歌</p><p class="artist_name"><a>歌手</a></p>'
    assert parse_chart(html, 'billboard_japan', 1)[0]['artist'] == '歌手'


@pytest.mark.parametrize('html', ['', '<p class="rank">2</p>', '<p class="rank">1</p>'])
def test_incomplete_or_redirect_page_rejected(html):
    with pytest.raises(ValueError):
        parse_chart(html, 'billboard_japan', 1)


def test_pilot_is_bounded_and_has_no_future_annual_chart():
    sources = pilot_sources()
    assert len(sources) == 7
    assert {s['territory'] for s in sources} == {'AU', 'US', 'JP'}
    assert max(s['chart_year'] for s in sources) == 2025


def test_freeze_refuses_replacement(tmp_path):
    path = tmp_path / 'manifest.json'
    write_json(path, {'v': 1})
    write_json(path, {'v': 1})
    with pytest.raises(ValueError):
        write_json(path, {'v': 2})


def test_requested_year_in_navigation_does_not_prove_chart_period():
    html = '<a href="/2006">2006</a><button class="c-chart-years js-change-year">2005</button>'
    with pytest.raises(ValueError):
        validate_period(html, 'aria', 2006)
    validate_period(html, 'aria', 2005)

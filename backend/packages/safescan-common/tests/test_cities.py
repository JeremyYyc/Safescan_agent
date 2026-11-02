from safescan_common.cities import normalize_city, same_city


def test_same_city_fails_closed_and_allows_multiple_staff_in_one_city():
    assert same_city('sydney', 'sydney')
    assert not same_city(None, None)
    assert not same_city('sydney', 'melbourne')


def test_input_city_normalization_distinguishes_same_named_suburbs():
    assert normalize_city('Box Hill', 'NSW') == 'sydney'
    assert normalize_city('Box Hill', 'VIC') == 'melbourne'
    assert normalize_city('Fairfield', 'VIC') is None
    assert normalize_city(None, 'NSW') is None
    assert normalize_city(None, None, '687-689 LaTrobe Street, Docklands') == 'melbourne'

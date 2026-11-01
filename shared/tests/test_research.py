"""Rešerše bez sítě: čísla ve větách, sloučení do faktů se stavem, role obrázků, placená část se zamockovaným Claude."""
from types import SimpleNamespace as NS

import pytest

from ngm_shared import research as rs

NAMES = ["Pantheon", "Colosseum", "Koloseum"]


def numbers(sentence, lang="en", carried=None):
    return [(n["predmet"], q, n["hodnota"]) for n in rs.sentence_numbers(sentence, lang, NAMES, carried) for q in n["velicina"]]


@pytest.mark.parametrize("sentence,lang,expected", [
    # přepočet v závorce není další údaj, „in diameter“ za číslem a okulus v téže větě
    ("The weight of the dome is concentrated on a ring of voussoirs 9.1 metres (30 ft) in diameter that form the oculus.", "en", [("okulus", "průměr", 9.1)]),
    ("Vlastní chrám má v jehož středu je otvor (okulus) o průměru 9 m, zdroj světla.", "cs", [("okulus", "průměr", 9.0)]),
    ("Durchmesser Opaion (DO): 8,95 m", "de", [("okulus", "průměr", 8.95)]),
    # tisíce a desetinné čárky podle jazyka
    ("Kopule ovšem nemá armatury, přesto váží asi 4 500 t.", "cs", [("kupole", "hmotnost", 4500.0)]),
    ("The 4,535-tonne weight of the Roman concrete dome is huge.", "en", [("kupole", "hmotnost", 4535.0)]),
    # rozsah zůstane rozsahem a platí předmět řečený u veličiny, ne slovo za ním
    ("The thickness of the dome varies from 6.4 metres (21 ft) at the base of the dome to 1.2 metres (3.9 ft) around the oculus.", "en", [("kupole", "tloušťka", [1.2, 6.4])]),
    # konkrétnější slovo blízko čísla vyhraje nad obecným
    ("The large bronze doors to the cella, measuring 4.45 metres (14.6 ft) wide by 7.53 metres (24.7 ft) high, are old.", "en",
     [("dveře", "šířka", 4.45), ("dveře", "výška", 7.53)]),
    # dvě veličiny k jednomu číslu
    ("Aula o stejném průměru a výšce 43,22 m (150 římských stop) je velká.", "cs", [("rotunda", "výška", 43.22), ("rotunda", "průměr", 43.22)]),
    # věc jako celek: zájmeno na začátku; druhé číslo patří k témuž
    ("It is elliptical in plan and is 189 meters (615 ft / 640 Roman feet) long, and 156 meters (510 ft) wide, with a base area of 24,000 square metres.", "en",
     [("celek", "délka", 189.0), ("celek", "šířka", 156.0), ("celek", "plocha", 24000.0)]),
    # rozměr bez jednotky u prvního čísla
    ("Aréna samotná měla rozměry 83 × 48 metrů.", "cs", [("aréna", "délka", 83.0), ("aréna", "šířka", 48.0)]),
    ("The arena itself was 83 meters by 48 meters (272 ft by 157 ft).", "en", [("aréna", "délka", 83.0), ("aréna", "šířka", 48.0)]),
    # druhé číslo za spojkou je pořád aréna, i když za ním stojí zeď
    ("The central arena is an ellipse 87 m (287 ft) long and 55 m (180 ft) wide, surrounded by a wall 5 m (15 ft) high.", "en",
     [("aréna", "délka", 87.0), ("aréna", "šířka", 55.0), ("zeď", "výška", 5.0)]),
    ("It could hold an estimated 50,000 to 80,000 spectators at various points.", "en", [("celek", "kapacita", [50000.0, 80000.0])]),
])
def test_number_gets_its_part_and_quantity(sentence, lang, expected):
    assert numbers(sentence, lang) == expected


@pytest.mark.parametrize("sentence,lang", [
    ("A portico aligned with the second pediment would fit columns with shafts 50 Roman feet (14.8 metres) tall.", "en"),     # nikdy nepostavené
    ("They were held together by 300 tons of iron clamps along the outer wall.", "en"),                                     # materiál, ne hmotnost stavby
    ("The oculus is 30 Roman feet in diameter.", "en"),                                                                    # římské stopy se nepřevádějí
    ("Per il diametro la cupola del Brunelleschi misura 42,52 m e la cupola di Santa Sofia 31,24 m di diametro.", "it"),   # srovnání s něčím jiným
    ("A 45 metres (148 ft) tall scaffold was built for the project.", "en"),                                                # nevíme, o čem je
])
def test_doubtful_numbers_are_left_out(sentence, lang):
    assert numbers(sentence, lang) == []


def test_each_carries_the_part_from_the_previous_sentence():
    assert numbers("Each was 11.9 metres (39 ft) tall and 60 tonnes in weight.", carried="sloup") == [("sloup", "výška", 11.9), ("sloup", "hmotnost", 60.0)]


ENTITY = {"label": "Pantheon", "qid": "Q1"}


def mention(predmet, velicina, value, url, jazyk="en", presnost=0.05, unit="m"):
    return {"predmet": predmet, "velicina": velicina, "hodnota": value, "jednotka": unit, "presnost": presnost,
            "zdroj": {"url": url, "nazev": url, "citace": url, "datum": "2026-11-01", "jazyk": jazyk, "stranka": url}}


def test_values_within_rounding_agree_and_the_rest_is_a_conflict_shown_as_a_span():
    facts = rs.merge_facts([
        mention("okulus", "průměr", 9.1, "a"), mention("okulus", "průměr", 9.0, "b", presnost=0.5), mention("okulus", "průměr", 8.95, "c", "de", 0.005),
        mention("rotunda", "průměr", 43.3, "a"), mention("rotunda", "průměr", 43.22, "b", presnost=0.005), mention("rotunda", "průměr", 43.0, "a", presnost=0.5),
        mention("sloup", "výška", 11.9, "a"),
    ], ENTITY)
    by = {f["tvrzeni"].split(":")[0]: f for f in facts}
    assert by["Okulus"]["stav"] == "rozpor" and by["Okulus"]["hodnota"] == [8.95, 9.1] and by["Okulus"]["tvrzeni"] == "Okulus: průměr 8,95 až 9,1 m"
    assert by["Rotunda"]["stav"] == "shoda" and by["Rotunda"]["hodnota"] == 43.22 and len(by["Rotunda"]["zdroje"]) == 3
    assert by["Sloup"]["stav"] == "jediny_zdroj"
    assert facts[0]["stav"] == "rozpor"     # rozpory nahoře
    assert [f["id"] for f in facts] == ["f1", "f2", "f3"]


def test_two_sentences_of_one_page_are_not_agreement():
    same = rs.merge_facts([mention("sloup", "výška", 11.9, "a"), mention("sloup", "výška", 11.9, "a")], ENTITY)[0]
    assert same["stav"] == "jediny_zdroj" and len(same["zdroje"]) == 1


def test_whole_numbers_one_apart_are_two_values():
    fact = rs.merge_facts([mention("celek", "šířka", 155.0, "a", "wikidata", 0.5), mention("celek", "šířka", 156.0, "b", "en", 0.5)], ENTITY)[0]
    assert fact["stav"] == "rozpor" and fact["hodnota"] == [155.0, 156.0]


def test_outer_wall_is_not_the_arena_wall():
    assert numbers("The height of the outer wall is 48 meters (157 ft / 165 Roman feet).") == [("vnější zeď", "výška", 48.0)]


def test_ranges_compare_by_their_ends_and_a_value_inside_is_no_conflict():
    inside = rs.merge_facts([mention("kupole", "tloušťka", [1.2, 6.4], "a"), mention("kupole", "tloušťka", 1.35, "b", "de", 0.005)], ENTITY)[0]
    assert inside["stav"] == "shoda"
    ends = rs.merge_facts([mention("kupole", "tloušťka", [1.2, 6.4], "a"), mention("kupole", "tloušťka", [1.5, 5.9], "b")], ENTITY)[0]
    assert ends["stav"] == "rozpor" and ends["hodnota"] == [1.2, 6.4]


def test_other_languages_only_check_what_czech_english_or_wikidata_say():
    facts = rs.merge_facts([mention("podlaha", "výška", 2.0, "x", "it", 0.5), mention("okulus", "průměr", 8.95, "y", "de", 0.005), mention("okulus", "průměr", 9.1, "z")], ENTITY)
    assert [f["predmet"] for f in facts] == ["okulus"]


def test_page_facts_skip_references_and_keep_a_link_to_the_section():
    page = {"lang": "en", "title": "T", "url": "https://x/T", "permalink": "https://x/w?oldid=1", "datum": "2026-10-22", "text": (
        "The Pantheon is the world's largest unreinforced concrete dome.\n\n"
        "== History ==\nBuilt by someone, the dome was 99 metres in diameter elsewhere.\n\n"
        "== Structure ==\nThe oculus is 9 metres in diameter.\n\n"
        "== References ==\nThe oculus is 77 metres in diameter according to a catalogue entry.\n")}
    raw = rs.page_facts(page, ["Pantheon"])
    values = [r["hodnota"] for r in raw if r["hodnota"] is not None]
    assert values == [9.0]      # dějiny a reference čísla nedávají
    number = next(r for r in raw if r["hodnota"] == 9.0)
    assert number["zdroj"]["url"] == "https://x/w?oldid=1#Structure" and number["zdroj"]["datum"] == "2026-10-22"
    assert any("largest unreinforced" in r["tvrzeni"] for r in raw if r["hodnota"] is None)


def test_related_page_counts_only_where_it_names_the_thing_before_the_number():
    page = {"lang": "en", "title": "V", "url": "u", "permalink": "p", "datum": "d", "jen_s_nazvem": "Pantheon", "text": (
        "The oculus of the dome, 46 metres in diameter, would dwarf the rotunda of Hadrian's Pantheon.\n"
        "The arena was 63 m long, slightly smaller than the Pantheon's.\n"
        "The dome of the Pantheon is unreinforced concrete spanning 43.4 meters and more.\n"
        "Nothing here about it, the dome is 250 metres in diameter.\n")}
    assert [(r["predmet"], r["hodnota"]) for r in rs.page_facts(page, ["Pantheon"]) if r["hodnota"] is not None] == [("kupole", 43.4)]


def test_related_page_must_name_the_thing_in_its_lead():
    texts = {"Pantheon, Rome": "The Pantheon.", "Domes": "Domes like the Pantheon.\n== Hadrian ==\nPantheon and Pantheon.",
             "Volkshalle": "A planned hall.\n== Design ==\nPantheon, Pantheon, Pantheon, Pantheon."}

    def get(host, params):
        if params.get("list") == "search":
            return {"query": {"search": [{"title": "Domes"}, {"title": "Volkshalle"}]}}
        title = params["titles"]
        return {"query": {"pages": [{"title": title, "extract": texts[title], "fullurl": f"https://x/{title}", "revisions": [{"revid": 1, "timestamp": "2026-10-22T10:00:00Z"}]}]}}

    pages = rs.load_pages({"sitelinks": {"en": "Pantheon, Rome"}}, langs=("en",), get=get)
    assert [(p["title"], p.get("jen_s_nazvem")) for p in pages] == [("Pantheon, Rome", None), ("Domes", "Pantheon")]


def test_related_page_about_a_film_is_left_out():
    texts = {"Colosseum": "The Colosseum.", "Colosseum: Rome's Arena of Death": "Colosseum: Rome's Arena of Death is a 2003 BBC docudrama.\n== Plot ==\nColosseum, Colosseum, Colosseum."}

    def get(host, params):
        if params.get("list") == "search":
            return {"query": {"search": [{"title": "Colosseum: Rome's Arena of Death"}]}}
        title = params["titles"]
        return {"query": {"pages": [{"title": title, "extract": texts[title], "fullurl": f"https://x/{title}", "revisions": [{"revid": 1, "timestamp": "2026-10-22T10:00:00Z"}]}]}}

    assert [p["title"] for p in rs.load_pages({"sitelinks": {"en": "Colosseum"}}, langs=("en",), get=get)] == ["Colosseum"]


def test_related_page_sentence_about_something_else_is_left_out():
    page = {"lang": "en", "title": "Roman amphitheatre", "url": "u", "permalink": "p", "datum": "d", "jen_s_nazvem": "Colosseum", "text": (
        "== El Jem ==\nIt is a free-standing amphitheatre built entirely out of stone blocks, similar in structure to the Roman Colosseum.\n"
        "== Rome ==\nThe Colosseum was built of travertine and brick by the Flavian emperors.\n")}
    assert [r["tvrzeni"] for r in rs.page_facts(page, ["Colosseum"])] == ["The Colosseum was built of travertine and brick by the Flavian emperors."]


def test_wikidata_values_units_and_parts():
    entity = {"qid": "Q9", "url": "https://www.wikidata.org/wiki/Q9", "modified": "2026-10-01", "label": "X", "claims": {
        "P2048": [{"mainsnak": {"datavalue": {"value": {"amount": "+43.3", "unit": "http://www.wikidata.org/entity/Q11573"}}}}],
        "P2046": [{"mainsnak": {"datavalue": {"value": {"amount": "+1500", "unit": "http://www.wikidata.org/entity/Q25343"}}}, "qualifiers": {"P518": []}}],
        "P186": [{"mainsnak": {"datavalue": {"value": {"id": "Q22"}}}}],
        "P571": [{"mainsnak": {"datavalue": {"value": {"time": "+0128-00-00T00:00:00Z", "precision": 7}}}}, {"mainsnak": {"snaktype": "somevalue"}}],
    }}
    labels = {"entities": {"Q22": {"labels": {"cs": {"value": "beton"}}}}}
    raw = rs.wikidata_facts(entity, lambda host, params: labels)
    facts = {f["velicina"]: f for f in raw}
    assert facts["výška"]["hodnota"] == 43.3 and facts["výška"]["zdroj"]["url"].endswith("#P2048")
    assert "plocha" not in facts            # údaj pro část stavby není o celku
    assert facts["materiál"]["tvrzeni"] == "Materiál: beton"
    assert facts["vznik"]["tvrzeni"] == "Vznik: 2. století"


def test_search_picks_the_page_that_matches_the_qualifier_not_the_first_hit():
    def get(host, params):
        return {"query": {"pages": [
            {"title": "Pantheon (Paříž)", "index": 1, "pageprops": {"wikibase_item": "Q2"}, "extract": "Mauzoleum v Paříži."},
            {"title": "Pantheon", "index": 2, "pageprops": {"wikibase_item": "Q1"}, "extract": "Starověký chrám v Římě."},
            {"title": "Pantheon (rozcestník)", "index": 3, "pageprops": {"wikibase_item": "Q3", "disambiguation": ""}},
            {"title": "Řím", "index": 4, "pageprops": {"wikibase_item": "Q4"}, "extract": "Hlavní město, Řím."},
        ]}}
    assert rs._search_entity("Pantheon, Řím", "cs", get) == "Q1"
    assert rs._search_entity("Pantheon", "cs", get) == "Q2"     # bez zpřesnění první hit, dossier entitu ukáže
    assert rs._search_entity("Nic takového", "cs", get) is None


@pytest.mark.parametrize("name,role", [
    ("Dehio 1 Pantheon Floor plan.jpg", "pudorys"), ("Section of the colosseo.JPG", "rez"), ("14 518 Pantheon, innen.jpg", "interier"),
    ("Pantheon portico and dome, Rome.jpg", "pruceli"), ("Capitel corintio romano del Coliseo.jpg", "detail"),
    ("Ruined brick vault Pantheon.jpg", "material"), ("Roma - Pantheon - in 2024 v04.jpg", "nezarazeno"),
])
def test_image_role_from_the_name(name, role):
    assert rs.image_role({"nazev": name, "popis": "", "kategorie": ""}) == role


FILE = lambda name, w=2000, **page: {"title": name, "imageinfo": [{"url": f"https://u/{name}", "thumburl": "https://u/t", "width": w, "height": 1500, "extmetadata": {}}], **page}  # noqa: E731
COLOSSEUM = {"qid": "Q10285", "label": "Koloseum", "commons_category": "Colosseum", "sitelinks": {"cs": "Koloseum", "en": "Colosseum"}}
MODEL = {"uid": "m1", "name": "Colosseum, Rome", "viewerUrl": "https://sketchfab.com/m1", "likeCount": 9, "faceCount": 5000, "user": {"displayName": "Autor"},
         "license": {"label": "CC Attribution", "url": "https://cc/by"}, "thumbnails": {"images": [{"url": "https://s/200", "width": 200}, {"url": "https://s/1920", "width": 1920, "height": 1080}]}}


def colosseum_get(host, params):
    """Hesla ve dvou jazycích, kategorie s kamerou a sérií, podkategorie modelů, Sketchfab."""
    if host == rs.SKETCHFAB:
        return {"results": [MODEL, {**MODEL, "uid": "m2", "license": {"label": "CC Attribution-NonCommercial"}}, {**MODEL, "uid": "m3", "license": {"label": "Standard"}},
                            {**MODEL, "uid": "m4", "name": "Gerudo Desert (Colosseum)"}, {**MODEL, "uid": "m5", "thumbnails": {"images": [{"url": "https://s/200", "width": 200}]}}]}
    if params.get("generator") == "images":
        prefix = {"cs.wikipedia.org": "Soubor", "en.wikipedia.org": "File"}[host]
        return {"query": {"pages": [FILE(f"{prefix}:Colosseo 2020.jpg", imagerepository="shared"), FILE(f"{prefix}:Local fair use.jpg", imagerepository="local"),
                                    FILE(f"{prefix}:Colosseum {host[:2]}.jpg", imagerepository="shared")]}}
    if params.get("list") == "categorymembers":
        return {"query": {"categorymembers": [{"title": "Category:Models of the Colosseum"}, {"title": "Category:Sack of Rome"}]}}
    if params.get("gcmtitle") == "Category:Models of the Colosseum":
        return {"query": {"pages": [FILE("File:Maquette du Colisée.jpg")]}}
    if params.get("gcmtitle") == "Category:Colosseum":
        return {"query": {"pages": [FILE("File:Camera in the Colosseum of Rome.jpg"), FILE("File:01 Colosseum Exterior.jpg"), FILE("File:02 Colosseum Exterior.jpg")]}}
    return {"query": {"pages": []}}


def test_images_come_from_articles_models_and_sketchfab_not_from_the_alphabet():
    images = rs.find_images(COLOSSEUM, 4, colosseum_get)
    by_name = {i["nazev"]: i for i in images}
    assert "Camera in the Colosseum of Rome.jpg" not in by_name                 # kategorie bez jasné role se nebere
    assert "Local fair use.jpg" not in by_name                                  # místní soubor Wikipedie
    assert by_name["Colosseo 2020.jpg"]["jazyku"] == 2 and by_name["Colosseo 2020.jpg"]["file"] == "File:Colosseo 2020.jpg"     # „Soubor:“ z cs
    assert images[0]["role"] == "rekonstrukce"
    assert by_name["Maquette du Colisée.jpg"]["role"] == "rekonstrukce"         # podkategorie modelů
    assert sum("Exterior" in n for n in by_name) == 1                           # 01 a 02 jsou jedna série
    # nezařazené zůstává jen z hesla, to vybrali redaktoři; první je obrázek použitý ve víc jazycích
    assert [i["nazev"] for i in images if i["role"] == "nezarazeno"][0] == "Colosseo 2020.jpg"


def test_sketchfab_only_licences_that_allow_use_and_only_about_the_topic():
    models = rs.find_models(COLOSSEUM, 4, colosseum_get)
    assert [m["file"] for m in models] == ["sketchfab:m1"]
    m = models[0]
    assert m["url"] == "https://s/1920" and m["autor"] == "Autor" and m["licence"] == "CC Attribution" and m["role"] == "rekonstrukce" and m["stranka"] == "https://sketchfab.com/m1"


def test_sketchfab_or_one_wikipedia_outage_does_not_stop_the_images():
    def broken(host, params):
        if host == rs.SKETCHFAB or host == "cs.wikipedia.org":
            raise rs.ResearchError("neodpovídá")
        return colosseum_get(host, params)

    images = rs.find_images(COLOSSEUM, 4, broken)
    assert images and not any(i["puvod"] == "sketchfab" for i in images) and any(i["nazev"] == "Colosseum en.jpg" for i in images)


def test_pinterest_queries_use_the_english_name():
    queries = rs.pinterest_queries(COLOSSEUM)
    assert [q["dotaz"] for q in queries] == ["Colosseum 3D reconstruction", "Colosseum construction model", "Colosseum infographic", "Colosseum cross section"]
    assert queries[0]["url"] == "https://www.pinterest.com/search/pins/?q=Colosseum+3D+reconstruction"


def web_reply(text, urls=(), stop="end_turn", searches=2):
    results = NS(type="web_search_tool_result", content=[NS(type="web_search_result", url=u, title=u) for u in urls])
    return NS(content=[results, NS(type="text", text=text, citations=None)], stop_reason=stop, model="claude-sonnet-5-5",
              usage=NS(input_tokens=1000, output_tokens=500, server_tool_use=NS(web_search_requests=searches)))


def test_web_research_keeps_only_sources_it_read_and_reports_each_reply_to_the_ledger():
    answer = """{"facts": [
      {"tvrzeni": "Okulus má průměr 8,2 m.", "predmet": "okulus", "velicina": "průměr", "hodnota": 8.2, "jednotka": "m",
       "zdroje": [{"url": "https://moore.example/p", "nazev": "Moore", "citace": "8.2 m"}, {"url": "https://vymysleno.example", "nazev": "?", "citace": "?"}]},
      {"tvrzeni": "Vymyšlený fakt.", "zdroje": [{"url": "https://vymysleno.example"}]}
    ], "otazky_bez_odpovedi": ["Hustoty mezi vrstvami."]}"""
    costs = []

    def turn(text, system, *, on_reply, **kw):
        assert "okulus" in text.lower() and "web_search" not in text
        first, second = web_reply("", ["https://moore.example/p"], stop="pause_turn"), web_reply(answer)
        on_reply(first)
        on_reply(second)
        return [first, second]

    web = rs.web_research("Pantheon", ["Rozpor mezi zdroji: Okulus"], [], spend=costs.append, turn=turn, today="2026-11-01")
    assert [c["searches"] for c in costs] == [2, 2] and costs[0]["usd"] == 0.027    # 1000/500 tokenů Sonnet + 2 hledání
    assert web["bez_zdroje"] == 1 and len(web["raw"]) == 1
    assert web["raw"][0]["zdroj"]["url"] == "https://moore.example/p" and web["raw"][0]["zdroj"]["datum"] == "2026-11-01"


def test_extending_recomputes_conflicts_and_does_not_touch_the_old_dossier():
    old = {"tema": "Pantheon", "entita": ENTITY, "facts": rs.merge_facts([mention("okulus", "průměr", 9.1, "a")], ENTITY), "images": [], "zdroje": [],
           "otazky_bez_odpovedi": ["Z čeho to je?", "Chybí obrázek: řez."], "cost_usd": 0.0}
    snapshot = repr(old)
    web = {"raw": [mention("okulus", "průměr", 8.2, "https://moore", "web", 0.0)], "otazky_bez_odpovedi": ["Hustoty."], "bez_zdroje": 0, "hledani": ["https://moore"]}
    new = rs.extend_dossier(old, web, 0.4)
    assert new["facts"][0]["stav"] == "rozpor" and new["facts"][0]["hodnota"] == [8.2, 9.1]
    assert new["cost_usd"] == 0.4 and new["otazky_bez_odpovedi"] == ["Hustoty.", "Chybí obrázek: řez."]
    assert repr(old) == snapshot


def test_web_turn_needs_live_flag_in_tests():
    from ngm_shared import claude
    with pytest.raises(claude.ClaudeError, match="placené volání"):
        claude.web_turn("x", "y", what="rešerše", model="claude-sonnet-5-5")

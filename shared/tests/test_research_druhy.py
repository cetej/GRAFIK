"""Rešerše pro osobu a zvíře bez sítě: druh z Wikidaty, data a rozpory, čísla, výběr vět, role obrázků."""
import pytest

from ngm_shared import research as rs

TESLA = {"label": "Nikola Tesla", "qid": "Q9036", "druh": "osoba"}
ANIMAL_NAMES = ["Axolotl", "axolotl", "Ambystoma mexicanum"]


def claim(value):
    return {"mainsnak": {"datavalue": {"value": value}}}


@pytest.mark.parametrize("claims,kind", [
    ({"P31": [claim({"id": "Q5"})]}, "osoba"),
    ({"P31": [claim({"id": "Q16521"}), claim({"id": "Q213907"})]}, "zvire"),
    ({"P225": [claim("Ambystoma mexicanum")]}, "zvire"),
    ({"P31": [claim({"id": "Q16970"})]}, "vec"),
    ({}, "vec"),
])
def test_kind_comes_from_wikidata(claims, kind):
    assert rs.entity_kind(claims) == kind


def page(text, title="Nikola Tesla", lang="en", **extra):
    return {"lang": lang, "title": title, "url": f"https://{lang}/{title}", "permalink": f"https://{lang}/{title}?oldid=1", "datum": "2026-11-02", "text": text, **extra}


@pytest.mark.parametrize("lead,lang,born,died", [
    ("Nikola Tesla (10 July 1856 – 7 January 1943) was a Serbian-American engineer.", "en", "1856-07-10", "1943-01-07"),
    ("Nikola Tesla (srbsky Никола Тесла, 10. července 1856, Smiljan – 7. ledna 1943, New York) byl vynálezce.", "cs", "1856-07-10", "1943-01-07"),
    ("Nikola Tesla (serbisch Никола Тесла; * 10. Juli 1856 in Smiljan; † 7. Januar 1943 in New York City) war ein Erfinder.", "de", "1856-07-10", "1943-01-07"),
    ("Nikola Tesla (Smiljan, 10 luglio 1856 – New York, 7 gennaio 1943) è stato un inventore.", "it", "1856-07-10", "1943-01-07"),
    ("Marie Curie (známá též jako M. C.) (7. listopadu 1867 Varšava – 4. července 1934 Passy) byla fyzička.", "cs", "1867-11-07", "1934-07-04"),
])
def test_life_dates_from_the_lead_in_every_language(lead, lang, born, died):
    assert {r["predmet"]: r["hodnota"] for r in rs._life_dates(page(lead, lang=lang))} == {"narození": born, "úmrtí": died}


def test_lead_without_a_person_gives_no_life_dates():
    assert rs._life_dates(page("Nikola Tesla patented the Tesla coil circuit on April 25, 1891 and showed it on May 20, 1891.", "History of the Tesla coil")) == []


def date_fact(event, iso, url, lang="en"):
    return {"predmet": event, "velicina": "datum", "hodnota": iso, "jednotka": None, "presnost": 0.0,
            "zdroj": {"url": url, "nazev": url, "citace": url, "datum": "2026-11-02", "jazyk": lang, "stranka": url}}


def test_dates_are_compared_and_a_conflict_keeps_both_values():
    facts = rs.merge_facts([date_fact("narození", "1856-07-10", "a"), date_fact("narození", "1856-06-28", "b", "cs"),
                            date_fact("úmrtí", "1943-01-07", "a"), date_fact("úmrtí", "1943", "b", "cs")], TESLA)
    by = {f["predmet"]: f for f in facts}
    assert by["narození"]["stav"] == "rozpor" and by["narození"]["hodnota"] == ["1856-06-28", "1856-07-10"]
    assert by["narození"]["tvrzeni"] == "Narození: 28. 6. 1856 nebo 10. 7. 1856"
    assert {z["hodnota"] for z in by["narození"]["zdroje"]} == {"1856-06-28", "1856-07-10"}     # každý zdroj nese svou hodnotu
    assert by["úmrtí"]["stav"] == "shoda" and by["úmrtí"]["hodnota"] == "1943-01-07"            # rok a přesné datum si neodporují
    assert by["narození"]["tema"] == "zivot"


LISTING = "\n".join(
    ["== American =="]
    + [f"U.S. patent {300 + i},000 - Other thing {i} - 1890 March {i + 1} - Describes a thing" for i in range(25)]
    + ["U.S. patent 454,622 - System of Electric Lighting - 1891 June 23 - Apparatus devised",
       "U.S. patent 1,061,206 - Turbine - 1909 October 21 - Bladeless turbine design",
       "U.S. patent 613,809 - Method of Controlling Vessels - 1898 July 1 - Remote control"])


def patent_pages():
    return [page(LISTING, "List of Nikola Tesla patents"),
            page("The turbine was patented by Nikola Tesla on October 21, 1913, which was his 100th patent.", "Tesla turbine"),
            page("Tesla patented his Tesla coil circuit April 25, 1891. and first showed it May 20, 1891.", "Tesla coil"),
            page("SYSTEM OF ELECTRIC LIGHTING, April 25, 1891, U.S. patent 454,622, June 23, 1891.\n"
                 "METHOD OF CONTROLLING, July 1, 1898, U.S. patent 613,809 November 8, 1898.\n"
                 "OTHER THING, January 1, 1889, U.S. patent 300,000 March 1, 1890.", "World Wireless System")]


def test_patent_dates_stay_visible_as_conflicts():
    facts = rs.merge_facts(rs.patent_facts(patent_pages(), ["Nikola Tesla", "Tesla"]), TESLA)
    conflicts = [f for f in facts if f["stav"] == "rozpor"]
    turbine = next(f for f in conflicts if "1,061,206" in f["tvrzeni"])
    assert turbine["hodnota"] == ["1909-10-21", "1913-10-21"] and {z["hodnota"] for z in turbine["zdroje"]} == {"1909-10-21", "1913-10-21"}
    boat = next(f for f in conflicts if "613,809" in f["tvrzeni"])
    assert boat["hodnota"] == ["1898-07-01", "1898-11-08"]      # k patentu patří datum za číslem, ne to před ním
    coil = next(f for f in conflicts if f["predmet"] == "patent")
    assert "25. 4. 1891" in coil["tvrzeni"] and "US 454,622" in coil["tvrzeni"] and "23. 6. 1891" in coil["tvrzeni"]
    assert {z["nazev"].split(": ")[1] for z in coil["zdroje"]} == {"Tesla coil", "List of Nikola Tesla patents", "World Wireless System"}
    assert not any("300,000" in f["tvrzeni"] for f in facts)    # shodný řádek nic neříká
    assert any(f["tvrzeni"].startswith("Americké patenty podle seznamu na Wikipedii: 28.") for f in facts)


def test_short_list_of_patents_is_not_a_list():
    assert rs.patent_facts([page("U.S. patent 454,622 - System - 1891 June 23 - x"), page("Tesla patented it on April 25, 1891.", "Tesla coil")], ["Tesla"]) == []


def test_text_conflict_survives_a_paid_extension():
    raw = rs.patent_facts(patent_pages(), ["Tesla"])
    entity = {**TESLA}
    facts = rs.merge_facts(raw, entity)
    new = rs.extend_dossier({"tema": "t", "entita": entity, "facts": facts, "images": [], "zdroje": [], "otazky_bez_odpovedi": [], "cost_usd": 0.0},
                            {"raw": [], "otazky_bez_odpovedi": [], "bez_zdroje": 0, "hledani": []}, 0.1)
    assert sum(f["stav"] == "rozpor" for f in new["facts"]) == sum(f["stav"] == "rozpor" for f in facts)


@pytest.mark.parametrize("sentence,lang,expected", [
    ("Tesla obtained around 300 patents worldwide for his inventions.", "en", [("celek", 300.0)]),
    ("Přes 700 patentů si nechal přihlásit.", "cs", [("celek", 700.0)]),
    ("Allein in den USA konnte er in etwa 50 Berufsjahren 112 Patente anmelden.", "de", [("v USA", 112.0)]),
    ("Tesla erhielt in 26 Ländern über 280 Patente, davon 112 in den USA.", "de", [("celek", 280.0)]),
    ("His 1888 patents covered the motor.", "en", []),          # letopočet není počet
])
def test_patent_counts(sentence, lang, expected):
    assert [(n["predmet"], n["hodnota"]) for n in rs._counts(sentence, lang, rs.PROFILES["osoba"])] == expected


@pytest.mark.parametrize("sentence,lang,value", [
    ("The life expectancy of a wild axolotl is between 10 and 15 years.", "en", [10.0, 15.0]),
    ("V zajetí se axolotl dožívá až 25 let.", "cs", 25.0),
    ("Axolotl haben unter guten Bedingungen eine Lebenserwartung von bis zu 20 Jahren.", "de", 20.0),
    ("The wild axolotl is thought to reach sexual maturity at 1.5 years of age.", "en", None),     # dospívání není délka života
])
def test_lifespan(sentence, lang, value):
    found = [n["hodnota"] for n in rs._counts(sentence, lang, rs.PROFILES["zvire"]) if n["velicina"] == "délka života"]
    assert found == ([] if value is None else [value])


def animal(sentence, lang="en"):
    return [(n["predmet"], q, n["hodnota"]) for n in rs.sentence_numbers(sentence, lang, ANIMAL_NAMES, None, w=rs.ANIMAL) for q in n["velicina"]]


def test_animal_range_absorbs_the_common_value_inside_it():
    found = animal("A sexually mature adult axolotl, at age 18–27 months, ranges in length from 15 to 45 cm (6 to 18 in); a size close to 23 cm (9 in) is most common.")
    assert found == [("celek", "délka", [0.15, 0.45])]


def test_animal_body_parts_and_young():
    assert animal("Its tail is 80 to 105 cm (31 to 41 in) long.") == [("ocas", "délka", [0.8, 1.05])]
    assert animal("They weigh between 22 and 55 kg (49 and 121 lb).") == [("celek", "hmotnost", [22.0, 55.0])]
    assert animal("The cubs are born helpless and weigh 320 to 567 g (11.3 to 20.0 oz).")[0][0] == "mládě"
    assert animal("Its canine teeth are 28.6 mm (1.13 in) long.") == [("zuby", "délka", 0.0286)]


@pytest.mark.parametrize("sentence", [
    "It prefers prey ranging in weight from 36 to 76 kg (79 to 168 lb).",
    "Dospělý irbis obvykle při jednom krmení spořádá 2–3 kg masa.",
    "Nadmořská výška biotopů obývaných irbisem se obvykle pohybuje v rozmezí 1500–4000 m n. m.",
])
def test_prey_and_altitude_are_not_measures_of_the_animal(sentence):
    facts = rs._kind_page_facts(page(sentence, "Irbis"), ["irbis", "Irbis"], "zvire")
    assert not [f for f in facts if f["hodnota"] is not None]


@pytest.mark.parametrize("sentence", [
    "Tesla beschäftigte sich zu der Zeit auch mit einem 1,1 Meter langen unbemannten U-Boot.",
    "Tesla built a wood-framed tower 186 feet (57 m) tall.",
])
def test_things_around_a_person_are_not_her_measures(sentence):
    facts = rs._kind_page_facts(page(sentence, lang="de" if "beschäftigte" in sentence else "en"), ["Nikola Tesla", "Tesla"], "osoba")
    assert not [f for f in facts if f["predmet"] == "celek" and f["hodnota"] is not None]


def test_person_height_is_the_only_whole_measure():
    facts = rs._kind_page_facts(page("Tesla was 6 feet 2 inches (1.88 m) tall and very thin.", "Nikola Tesla"), ["Nikola Tesla", "Tesla"], "osoba")
    assert [(f["predmet"], f["velicina"], f["hodnota"]) for f in facts if f["hodnota"] is not None] == [("celek", "výška", 1.88)]


def test_every_section_gets_a_sentence_before_any_gets_a_second():
    text = "\n".join(["Nikola Tesla (10 July 1856 – 7 January 1943) was an inventor.", "== Money ==",
                      "In 1888 Tesla got $60,000 from Westinghouse.", "In 1889 Tesla got $70,000 from Westinghouse.", "In 1890 Tesla got $80,000 from Westinghouse.",
                      "== Early years ==", "Tesla was born in a village."])
    facts = rs._pick_texts({"Money": [(9, {"t": 1}), (9, {"t": 2})], "Early": [(2, {"t": 3})]}, 2)
    assert [f["t"] for f in facts] == [1, 3]
    assert any("born in a village" in f["tvrzeni"] for f in rs._kind_page_facts(page(text), ["Tesla"], "osoba") if f["hodnota"] is None)


def test_related_page_counts_only_where_the_sentence_names_the_person_not_the_eponym():
    text = "A Tesla coil is a transformer designed by Nikola Tesla in 1891.\nThe Tesla coil was used in 1926 by Tuve and Breit in an accelerator.\n"
    facts = rs._kind_page_facts(page(text, "Tesla coil", jen_s_nazvem="Tesla"), ["Nikola Tesla", "Tesla"], "osoba")
    assert [f["tvrzeni"] for f in facts] == ["A Tesla coil is a transformer designed by Nikola Tesla in 1891."]


def test_related_page_sentence_about_someone_else_is_left_out():
    text = "In 1919 she took a course on radioactivity at the Sorbonne with Marie Curie.\nThe institute was founded in 1909 for Marie Curie and her laboratory.\n"
    facts = rs._kind_page_facts(page(text, "Induced radioactivity", jen_s_nazvem="Curie"), ["Marie Curie", "Curie"], "osoba")
    assert [f["tvrzeni"] for f in facts] == ["The institute was founded in 1909 for Marie Curie and her laboratory."]


def test_list_of_patents_gives_no_sentences():
    assert rs._kind_page_facts(page(LISTING, "List of Nikola Tesla patents", jen_s_nazvem="Tesla"), ["Tesla"], "osoba") == []


def test_date_is_not_split_in_two_sentences():
    assert rs._sentences("Tesla (10. července 1856, Smiljan) byl vynálezce. Zemřel v New Yorku.", dates=True) == ["Tesla (10. července 1856, Smiljan) byl vynálezce.", "Zemřel v New Yorku."]


def wiki_file(name, w=2000, h=2500, cat="", **page_extra):
    return {"title": name, "imageinfo": [{"url": f"https://u/{name}", "thumburl": "https://u/t", "width": w, "height": h, "extmetadata": {
        "Artist": {"value": "Napoleon Sarony"}, "LicenseShortName": {"value": "Public domain"}, "Categories": {"value": cat}}}], **page_extra}


PERSON = {"qid": "Q9036", "label": "Nikola Tesla", "druh": "osoba", "short": "Tesla", "commons_category": "Nikola Tesla", "sitelinks": {"en": "Nikola Tesla"},
          "claims": {"P18": [claim("Tesla circa 1890.jpeg")], "P109": [claim("Tesla signature.png")]}}


def person_get(host, params):
    if host == rs.SKETCHFAB:
        raise AssertionError("u osoby se Sketchfab nevolá")
    if params.get("titles", "").startswith("File:Tesla circa"):
        return {"query": {"pages": [wiki_file("File:Tesla circa 1890.jpeg", 940, 1260)]}}
    if params.get("titles", "").startswith("File:Tesla signature"):
        return {"query": {"pages": [wiki_file("File:Tesla signature.png", 2000, 300)]}}
    if params.get("generator") == "images":
        return {"query": {"pages": [wiki_file("File:Tesla Sarony.jpg", cat="Black and white portrait photographs of male scientists", imagerepository="shared"),
                                    wiki_file("File:N.Tesla.JPG", cat="Photographs of Nikola Tesla", imagerepository="shared"),
                                    wiki_file("File:Nikola Tesla Airport Statue.jpg", imagerepository="shared"),
                                    wiki_file("File:TeslaTurbineOriginal.png", 2000, 1200, cat="Inventions by Nikola Tesla", imagerepository="shared"),
                                    wiki_file("File:Flag of Serbia.png", imagerepository="shared")]}}
    return {"query": {"pages": [], "categorymembers": []}}


def test_portrait_is_offered_with_author_and_licence():
    images = rs.find_images(PERSON, 4, person_get)
    by = {i["nazev"]: i for i in images}
    assert images[0]["nazev"] == "Tesla circa 1890.jpeg" and images[0]["role"] == "portret" and images[0]["puvod"] == "wikidata"
    assert images[0]["autor"] == "Napoleon Sarony" and images[0]["licence"] == "Public domain"
    assert by["Tesla Sarony.jpg"]["role"] == "portret" and by["N.Tesla.JPG"]["role"] == "portret"
    assert by["Nikola Tesla Airport Statue.jpg"]["role"] == "pamatka" and by["TeslaTurbineOriginal.png"]["role"] == "dilo" and by["Tesla signature.png"]["role"] == "rukopis"
    assert "Flag of Serbia.png" not in by


ANIMAL = {"qid": "Q22718", "label": "axolotl mexický", "druh": "zvire", "short": "Axolotl", "commons_category": "Ambystoma mexicanum", "sitelinks": {"en": "Axolotl"},
          "claims": {"P18": [claim("Axolotl Wild Type.jpg")], "P181": [claim("Axolotl distribution map.svg")]}}
CARTOON = {"uid": "c1", "name": "Cute Axolotl", "user": {"displayName": "A"}, "license": {"label": "CC Attribution"}, "tags": [{"name": "cute"}],
           "thumbnails": {"images": [{"url": "https://s/1920", "width": 1920, "height": 1080}]}}
SCAN = {**CARTOON, "uid": "c2", "name": "Axolotl skeleton", "tags": [{"name": "anatomy"}]}


def animal_get(host, params):
    if host == rs.SKETCHFAB:
        return {"results": [CARTOON, {**CARTOON, "uid": "c3", "name": "Minecraft Axolotl", "tags": []}, SCAN]}
    if params.get("titles", "").startswith("File:Axolotl Wild"):
        return {"query": {"pages": [wiki_file("File:Axolotl Wild Type.jpg", 4760, 1324)]}}
    if params.get("titles", "").startswith("File:Axolotl distribution"):
        return {"query": {"pages": [wiki_file("File:Axolotl distribution map.svg", 764, 558)]}}
    if params.get("generator") == "images":
        return {"query": {"pages": [wiki_file("File:Axolot's gills (Ambystoma mexicanum).jpg", 3264, 1840, cat="Ambystoma mexicanum", imagerepository="shared"),
                                    wiki_file("File:Leucistic Axolotl front.JPG", 3888, 2592, cat="Ambystoma mexicanum", imagerepository="shared"),
                                    wiki_file("File:Mexico City skyline.jpg", 3888, 2592, cat="Mexico City", imagerepository="shared")]}}
    return {"query": {"pages": [], "categorymembers": []}}


def test_range_map_is_offered_and_may_be_svg():
    images = rs.find_images(ANIMAL, 4, animal_get)
    by = {i["nazev"]: i for i in images}
    assert by["Axolotl distribution map.svg"]["role"] == "mapa" and by["Axolotl distribution map.svg"]["autor"] == "Napoleon Sarony"
    assert by["Axolotl Wild Type.jpg"]["role"] == "zvire" and by["Axolotl Wild Type.jpg"]["puvod"] == "wikidata"
    assert by["Axolot's gills (Ambystoma mexicanum).jpg"]["role"] == "detail" and by["Leucistic Axolotl front.JPG"]["role"] == "forma"
    assert "Mexico City skyline.jpg" not in by      # článek o zvířeti může ukazovat i město; soubor musí být o něm


def test_sketchfab_cartoons_are_left_out_for_an_animal():
    models = rs.find_models(ANIMAL, 4, animal_get)
    assert [(m["nazev"], m["role"]) for m in models] == [("Axolotl skeleton", "model")]


@pytest.mark.parametrize("artist,credit,expected", [
    ("NeznámýUnknown author", None, "autor neznámý"), ("Unknown authorUnknown author", None, "autor neznámý"),
    ("https://wellcomeimages.org/x", "Wellcome Library", "Wellcome Library"), ("https://wellcomeimages.org/x", None, None), ("Napoleon Sarony", "x", "Napoleon Sarony"),
])
def test_author_for_the_footer(artist, credit, expected):
    assert rs._author(artist, credit) == expected


def test_open_questions_and_missing_images_follow_the_kind():
    facts = [{"velicina": "délka", "predmet": "celek", "tema": "rozmery"}, {"velicina": None, "predmet": None, "tema": "ohrozeni"}]
    questions = rs._questions(facts, [{"role": "zvire"}], True, "zvire")
    assert "Kolik váží?" in questions and "Kde žije?" in questions and "Jak je velké?" not in questions and "Jak je ohrožené?" not in questions
    assert "Chybí obrázek: mapa výskytu." in questions and not any("půdorys" in q or "3D" in q for q in questions)


def test_pinterest_queries_follow_the_kind():
    assert rs.pinterest_queries(ANIMAL)[1]["dotaz"] == "Axolotl anatomy"
    assert rs.pinterest_queries(PERSON)[0]["dotaz"] == "Nikola Tesla infographic"


def test_wikidata_for_a_person_keeps_the_day_and_animal_units():
    def labels(host, params):
        return {"entities": {"Q1": {"labels": {"cs": {"value": "kriticky ohrožený druh"}}}}}

    person = {"qid": "Q9", "url": "https://w/Q9", "modified": "2026-10-01", "label": "X", "druh": "osoba", "claims": {
        "P569": [claim({"time": "+1856-07-10T00:00:00Z", "precision": 11})], "P570": [claim({"time": "+1943-00-00T00:00:00Z", "precision": 9})]}}
    by = {f["predmet"]: f for f in rs.wikidata_facts(person, labels)}
    assert by["narození"]["hodnota"] == "1856-07-10" and by["úmrtí"]["hodnota"] == "1943"
    beast = {"qid": "Q8", "url": "https://w/Q8", "modified": "2026-10-01", "label": "Y", "druh": "zvire", "claims": {
        "P141": [claim({"id": "Q1"})], "P225": [claim("Ambystoma mexicanum")],
        "P2043": [claim({"amount": "+18", "unit": "http://www.wikidata.org/entity/Q218593"})], "P2067": [claim({"amount": "+8", "unit": "http://www.wikidata.org/entity/Q48013"})]}}
    by = {f["velicina"]: f for f in rs.wikidata_facts(beast, labels)}
    assert by["délka"]["hodnota"] == pytest.approx(0.4572) and by["délka"]["jednotka"] == "m"
    assert by["hmotnost"]["hodnota"] == pytest.approx(0.2268) and by["hmotnost"]["jednotka"] == "kg"
    assert by["stav ohrožení"]["tvrzeni"] == "Stav ohrožení: kriticky ohrožený druh" and by["vědecké jméno"]["tvrzeni"] == "Vědecké jméno: Ambystoma mexicanum"


def test_small_values_keep_a_digit():
    assert rs._fmt(0.0023) == "0,0023" and rs._fmt(0.23) == "0,23"

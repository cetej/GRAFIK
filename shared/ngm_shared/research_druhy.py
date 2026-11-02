"""Slovníky rešerše podle druhu tématu: osoba a zvíře. Stavby a ostatní věci mají své slovníky přímo v `research.py`.

Druh určuje Wikidata (`research.entity_kind`). Tady jsou jen data, žádná logika: co číst z Wikidaty, které věty stojí za
přečtení, jak třídit obrázky. Vyladěné na Teslovi a axolotlovi, ověřené mimo vzorek (docs/spikes/2026-11-02-resers-osoba-zvire.md).
Rostlina jde cestou zvířete, neověřeno.
"""
from __future__ import annotations

MONTHS = {
    **{m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)},
    **{m: i for i, m in enumerate(("ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"), 1)},
    **{m: i for i, m in enumerate(("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"), 1)},
    **{m: i for i, m in enumerate(("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"), 1)},
}

# -- osoba ------------------------------------------------------------------------------------------------------------
OSOBA = {
    "wd_item": {"P19": "místo narození", "P20": "místo úmrtí", "P27": "občanství", "P106": "povolání", "P69": "vzdělání", "P108": "zaměstnavatel",
                "P800": "významné dílo", "P166": "ocenění", "P509": "příčina smrti", "P119": "místo pohřbu"},
    "wd_time": {"P569": "narození", "P570": "úmrtí"},
    "wd_quantity": {"P2048": "výška", "P2067": "hmotnost"},
    "wd_string": {},
    "image_claims": {"P18": "portret", "P109": "rukopis"},
    "roles": ("portret", "zivot", "dilo", "misto", "pamatka", "rukopis"),
    "role_words": {     # první shoda v pořadí; portrét až nakonec, aby socha nebo podpis nebyly portrétem
        "rukopis": r"signature|unterschrift|podpis|autograph|\bletter\b|handwrit|manuscript|notebook|\bdopis",
        "pamatka": r"statue|monument|memorial|\bbust\b|plaque|\bgrave|\btomb|\burn\b|ashes|banknote|bankovk|obverse|\bstamp|známk|\bcoin|\bmince|pomník|\bsocha|denkmal|museum|muzeum|named after|airport",
        "dilo": r"\bpatents?\b|\bUS\d{5,}|diagram|\bdrawing|schem|invention|experiment|apparatus|\bcoils?\b|turbine|\bmotor\b|painting|artwork|x-?ray|\bbook\b|works by",
        "misto": r"laborator|\bhouse\b|birthplace|\broom\d*\b|\bhotel|\bbuilding|\btower\b|village|\bchurch|university|rodný dům|\bexterior",
        "zivot": r"\bwith\b|\bfamily\b|\bgroup\b|meeting|banquet|conference",
        "portret": r"portrait|porträt|ritratto|portrét|retrato|headshot",
    },
    "role_search": {"portret": "portrait", "zivot": "photograph", "dilo": "invention diagram patent", "misto": "laboratory house", "pamatka": "monument statue", "rukopis": "signature"},
    "not_picture": r"\b(?:logo|flag|icon|coat of arms|seal)\b",
    "min_edge": 600,    # dobové fotky bývají malé (Twain v Teslově laboratoři 727 px); o tisku rozhoduje člověk
    "models": False,
    "pinterest": ("infographic", "biography timeline", "portrait illustration", "poster"),
    "themes": (
        ("myty", r"\bmyths?\b|legend|allegedly|claimed|\bclaims?\b|death.?(?:ray|beam)|teleforce|earthquake|conspira|\bpověst|\bmýt|\búdajn|\btvrdil"),
        ("penize", r"[$€£]\s?\d|\bUSD\b|royalt|\bdebts?\b|unpaid|bankrupt|\bcontract\b|\binvest(?:s|ed|ors?|ments?)\b|financ|funding|licens|licenc|dluh|smlouv|mortgage"),
        ("dilo", r"\bpatent|\binvent|demonstrat|lecture|experiment|laborator|\bmotor|\bcoil|turbine|transformer|oscillat|generator|wireless|x-ray|\bradio|remote|transmi|vynál|vynal|pokus|přednáš|cívk|publish|discover|objev|painted|composed|\bwrote\b|napsal"),
        ("odkaz", r"\baward|\bmedal|\bprize|named (?:after|in honou?r)|honou?r|\bunit\b|museum|monument|memorial|anniversar|pocta|pomník|muzeum|ocenění|jednotk"),
    ),
    "default_theme": "zivot",
    # život mezi tématy nemá slovo, které by větu odlišilo; tyhle ji pustí dál
    "events": r"\bborn\b|\bdied\b|emigrat|moved to|arrived|married|studied|graduated|citizen|worked|employed|hired|founded|\bhotel|\b\d+ feet\b|narodil|zemřel|odjel|přestěhoval|studoval|občan|pracoval|založil",
    "noise": r"$^",
    "skip_sections": r"in popular culture|popular culture|in fiction|literary works|v kultuře",
    "value_theme": {"narození": "zivot", "úmrtí": "zivot", "počet": "dilo", "datum patentu": "dilo", "významné dílo": "dilo", "ocenění": "odkaz"},
    "counts": (("počet", "patentů", r"(?P<a>{num})(?:\s*(?:–|-|to|až)\s*(?P<b>{num}))?\s*(?:[a-zA-Z.]+\s){{0,2}}(?:patents|patentů|Patente|brevetti)\b"),),
    "aspects": (
        ("Kdy se narodil(a)?", ("narození",)),
        ("Kdy zemřel(a)?", ("úmrtí",)),
        ("Odkud pochází?", ("místo narození", "občanství")),
        ("Čím se živil(a)?", ("povolání",)),
    ),
    "related": 8,
    "text_limits": {"hlavní en": 61, "hlavní cs": 10, "podobná": 4},
}
OSOBA_PARTS = {     # od nejmenšího k největšímu jako research.PARTS; věci kolem člověka, jeho míry jdou přes „celek“
    "oscilátor": r"\boscillators?\b|oscilátor",
    "výboj": r"\bdischarges?\b|lightning|\bbolts?\b|\bsparks?\b|výboj|\bjiskr",
    "cívka": r"\bcoils?\b|cívk",
    "turbína": r"turbin",
    "generátor": r"generator|generátor",
    "ponorka": r"U-Boot|submarine|ponork",
    "kupole": r"\bcupola\b|\bdomes?\b|kupol|Kuppel",
    "věž": r"\btowers?\b|\bvěž|\bTurm|\btorre",
}

# -- zvíře ------------------------------------------------------------------------------------------------------------
ZVIRE = {
    "wd_item": {"P141": "stav ohrožení", "P183": "endemit v", "P9714": "areál výskytu", "P1034": "hlavní potrava", "P2974": "prostředí"},
    "wd_time": {},
    "wd_quantity": {"P2043": "délka", "P2048": "výška", "P2067": "hmotnost", "P2250": "délka života"},
    "wd_string": {"P225": "vědecké jméno"},
    "image_claims": {"P18": "zvire", "P181": "mapa"},
    "roles": ("zvire", "mapa", "detail", "prostredi", "vyvoj", "forma", "ilustrace", "model"),
    "role_words": {
        "mapa": r"\bmaps?\b|distribution|verbreitung|distribuzione|rozšíření|\bmapa\b|\bkarte\b|\brange\b",
        "ilustrace": r"illustration|\bdrawing|engraving|\bplate\b|lithograph|painting|\bart\b|aztec|codex|sculpture|\bstatue|\bxolotl|kresba|rytina|zeichnung|\btafel\b|\bemoji|\bmural|\.svg$|\bAGTM\b",
        "vyvoj": r"\blarva|\beggs?\b|huevo|embryo|juvenile|hatchling|\bcubs?\b|\bcalf\b|mládě|vejce|vajíč|jikr|tadpole|metamorph|desarrollo|\bdevelopment",
        "forma": r"leuc?is|albin|melanoid|colou?rs?\b|\bmorphs?\b|wild.?type|barev",
        "detail": r"\bheads?\b|\bgills?\b|\beyes?\b|skull|skelet|anatomy|\blimbs?\b|\bfoot\b|\btail\b|\bteeth\b|close.?up|\bdetail|hlava|žábr|lebka|kostra",
        "prostredi": r"habitat|\blakes?\b|\bcanals?\b|\briver\b|\bforest\b|mountain|wetland|landscape|jezero|\bkanál",
    },
    "role_search": {"zvire": "", "mapa": "distribution map", "detail": "head close-up", "prostredi": "habitat", "vyvoj": "larva juvenile", "forma": "color morph", "ilustrace": "illustration engraving"},
    "not_picture": r"\b(?:logos?|flags?|icons?|coat of arms|banknotes?|stamps?|coins?|minecraft)\b",
    "min_edge": 800,
    "models": True,
    "pinterest": ("infographic", "anatomy", "life cycle", "scientific illustration"),
    "themes": (
        ("ohrozeni", r"endangered|\bextinct|\bthreat|IUCN|CITES|Red List|pollut|invasive|\bcarps?\b|tilapi|conservation|\bpopulations?\b|\bsurveys?\b|wastewater|urbani[sz]|poach|\bhunt|\btrade\b|ohrožen|vyhyn|znečiš|populac|ochran|chinamp|pytlač"),
        ("veda", r"regenerat|genome|chromosom|base pairs|model organism|laborator|\bresearch|scientist|Stock Center|transgenic|neoten|metamorph|thyroid|iodine|paedomorph|Dum[ée]ril|Chauvin|\bTSH\b|regener|genom|výzkum|laboratoř|neoteni"),
        ("kultura", r"\bnamed\b|Nahuatl|Aztec|\bgods?\b|deity|\bmyth|\bXolotl|banknote|\bpesos?\b|\bmural|Rivera|emoji|\bcultural|\bsymbol|folklore|etymolog|\bjméno|bůh|bankovk|kultur|vodní (?:sluha|netvor|otrok|pes|duch)"),
        ("vyskyt", r"\bnative\b|endemic|habitat|\blakes?\b|\bcanals?\b|\brivers?\b|altitude|elevation|temperature|\brange\b|distribution|inhabit|wetland|mountain|jezer|kanál|výskyt|nadmořsk|rozšířen|teplot"),
        ("biologie", r"carnivor|\bdiet\b|\bprey\b|\bfeed|\beats?\b|mollus|\bworms?\b|predat|lifespan|life expectancy|maturity|\bbreed|\bmating|spawn|\beggs?\b|\blarva|courtship|\bcubs?\b|\blitter|potrav|kořist|živí|rozmnož|vejce|vajíč|dožív|dospív"),
        ("vzhled", r"\bgills?\b|\blungs?\b|\bskin\b|\beyes?\b|lidless|\bdigits?\b|\btoes?\b|\blimbs?\b|\btail\b|\bfin\b|\bteeth\b|colou?r|pigment|leuc?is|albin|wild.?type|\blength\b|\bweigh|\bfur\b|plumage|\bwings?\b|\bclaws?\b|žábr|plíc|kůž|končet|ocas|ploutev|zbarven|srst|peří|křídl|\boči\b|\bprst"),
    ),
    "default_theme": "ostatni",
    "events": r"$^",
    "noise": r"minecraft|doodle|video game|chovatel|\bkrmit|akvári|\bpets?\b",
    "skip_sections": r"captive care|\bcare\b|herpetoculture|in fiction|popular culture|online model organism",
    "value_theme": {"stav ohrožení": "ohrozeni", "endemit v": "vyskyt", "areál výskytu": "vyskyt", "prostředí": "vyskyt", "hlavní potrava": "biologie", "délka života": "biologie", "počet vajec": "biologie", "vědecké jméno": "ostatni"},
    "counts": (
        ("délka života", "let", r"(?:life expectancy|life ?span|\blives? (?:for |up to )|longevity|dožív\w*|dožij\w*|Lebenserwartung|Lebensdauer|può vivere)[^.]{{0,60}}?(?P<a>{num})(?:\s*(?:–|-|to|and|až|bis|und|e|a)\s*(?P<b>{num}))?\s*(?:years?|let|roků|Jahre\w*|anni)\b"),
        ("počet vajec", "vajec", r"(?P<a>{num})(?:\s*(?:–|-|to|and|až|bis|und|e|a)\s*(?P<b>{num}))?\s*(?:eggs|vajec|vajíček|jiker|Eier|uova)\b"),
    ),
    "aspects": (
        ("Jak je velké?", ("délka", "výška")),
        ("Kolik váží?", ("hmotnost",)),
        ("Kde žije?", ("areál výskytu", "endemit v", "prostředí", "vyskyt")),
        ("Jak je ohrožené?", ("stav ohrožení", "ohrozeni")),
    ),
    "related": 4,
    "text_limits": {"hlavní en": 95, "hlavní cs": 10, "podobná": 3},
}
ZVIRE_PARTS = {     # od nejmenšího k největšímu jako research.PARTS
    "zuby": r"\bteeth\b|\bcanines?\b|\bzub[yůů]|\bZähne|\bdenti\b",
    "žábry": r"\bgills?\b|žábr|žaber|Kiemen|branchi",
    "vejce": r"\beggs?\b|vajíč|vajec|\bEier|\buova\b",
    "ocas": r"\btail\b|\bocas|Schwanz|\bcoda\b",
    "hlava": r"\bhead\b(?! to body| and body)|\bhlav[aěyu]\b(?! s tělem)|\bKopf\b|\btesta\b",
    "tělo": r"\bbody\b|\btěla\b|\btělo\b|Körper|\bcorpo\b",
}
ZVIRE_YOUNG = r"\blarva\w*|\bjuvenile|\bhatchling|\bcubs?\b|\bcalf\b|\bcalves\b|\bnewborn|mládě|mláďat|\blarv\w*|\bJungtier|\bcuccioli"
ZVIRE_NOT_BODY = r"\bprey\b|kořist|\bmas[oa]\b|Fleisch|\bBeute|\bfood\b|potrav|krmen|\beats?\b|\bconsume|nadmořsk|altitude|elevation|above sea level|\bHöhe\b|m n\. ?m\.|Flachland|za týden|per week|\bpřibýv|\bgain"
UNITS_ZVIRE = (
    (r"mm|millimet(?:re|er)s?|milimetr\w*|Millimeter\w*|millimetri", "m", 0.001),
    (r"km|kilomet(?:re|er)s?|kilometr\w*|Kilometer\w*|chilometri", "m", 1000.0),
    (r"cm|centimet(?:re|er)s?|centimetr\w*|Zentimeter\w*|centimetri", "m", 0.01),
    (r"m|met(?:re|er)s?|metr\w*|Meter\w*|metri|metro", "m", 1.0),
    (r"kg|kilogram\w*|Kilogramm\w*|chilogramm\w*", "kg", 1.0),
    (r"g|grams?|gramů|gramy|Gramm\w*|grammi", "kg", 0.001),
    (r"t|tonnes?|tons?|tun\w*|Tonnen?|tonnellate", "kg", 1000.0),
    (r"ft|feet|foot", "m", 0.3048),
)
WD_UNIT_ZVIRE = {"Q11573": ("m", 1.0), "Q828224": ("m", 1000.0), "Q174728": ("m", 0.01), "Q174789": ("m", 0.001), "Q3710": ("m", 0.3048), "Q218593": ("m", 0.0254),
                 "Q11570": ("kg", 1.0), "Q191118": ("kg", 1000.0), "Q41803": ("kg", 0.001), "Q48013": ("kg", 0.0283495), "Q100995": ("kg", 0.453592), "Q577": ("let", 1.0)}

# 3D model zvířete: realistický a věcný, ne maskot. Sketchfab u axolotla vracel Minecraft, princeznu a „cute“.
MODEL_CARTOON = r"\bcute\b|cartoon|minecraft|chibi|kawaii|styli[sz]ed|low.?poly|\btoys?\b|plush|pok[eé]mon|roblox|fortnite|\bgame\b|fan.?art|princess|\bfriend\b|\banime\b|\bbaby\b|voxel|blender.?guru|\bmascot"
MODEL_REAL = r"\bscan|photogramm|realistic|anatom|skelet|skull|specimen|\bmuseum|scientific|biolog"

# Krok 3g: série stránek pro telefon (2. 11.)

Co vzniklo: z vybraného návrhu série stránek. Text přepisuje model z faktů dossieru, rozvržení počítá kód, obraz je vlastní 3D. Zásady: [`docs/infografiky-zasady.md`](../infografiky-zasady.md), oddíl Logika stránky.

![Série o Teslovi na šířce telefonu](img/2026-11-02-serie-tesla-3d.png)

## Ukázka, ruční text, 0 USD

Stránka 1080 × 1350. Údaje z `panels.checks` a `serie.compose`.

| Stránka | Slov z asi 80 | Největší prázdná plocha | Splývá s pozadím | Nález o mobilu |
|---|---|---|---|---|
| Nikola Tesla, osa života | 40 | 3 % | ne | žádný |
| Motor bez kartáčů | 29 | 17 % | ne | žádný |
| Cívka a blesky | 28 | 8 % | ne | žádný |
| Věž Wardenclyffe | 32 | 17 % | ne | žádný |

Operátor k téhle verzi: „Ano, to je výrazně lepší.“

## Čím se měří

**Prázdná plocha** (`panels.empty_share`): největší prázdný obdélník pod titulkem jako podíl té plochy, obraz obsazuje jen tam, kde není průhledný. Práh 20 %. Stránka motoru, na kterou operátor reagoval, dává podle přesnosti rekonstrukce 27 až 37 %.

**Splývání** (`panels.faint_parts`): 80. percentil kontrastu proti stránce po 8 pásech obrazu, měří se jen objekt. Tenká část (plných pixelů pod 20 %) chce 2:1, plocha 1,2:1. Práhy jsou podle jediné série, na jiném tématu můžou chybět nebo přebývat.

| Obraz | Nejslabší pás (plnost, kontrast) | Nález |
|---|---|---|
| věž s tmavou kupolí | 0,09, 1,67:1 | horní část |
| věž se světlou kupolí | 0,55, 3,99:1 | žádný |
| motor | 0,29, 1,97:1 | žádný |
| turbína | 0,60, 1,32:1 | žádný |
| figura | 0,42, 1,49:1 | žádný |

**Co stroj nezměří:** že je podloží největší. Tomu pomohla jen příprava obrazu a prohlídka v plné velikosti.

## Staré dokumenty se nezměnily

- Panelové dokumenty: SVG všech 4 v knihovně je podle kódu masteru `1c2a39f` a větve shodné bajt po bajtu (SHA-1). Před odstraněním Rozdělit pro mobil totéž na 8 dokumentech proti `7b89a2f`. Řádek Zdroj zmizel ze starých dokumentů už na masteru (GRAFIK#162), rozhodnutím operátora.
- Editor: `svg.info-svg` dvou starých dokumentů (`20261101-090450-0447`, 10 popisků a 4 fakta; `20261023-133046-2ea6`) je mezi Studiem masteru a větve shodné (SHA-1). Přibyl jen řádek v Kontrole: titulek 9,6 px, nejmenší text 3,9 px, označení AI 3,1 px na telefonu.

## Proklikáno ve Studiu za 0 USD

Engine z větve s falešným modelem a dočasnou knihovnou, Studio přes `GRAFIK_ENGINE_URL`: návrhy se stránkami a zaškrtávátky, výběr, kontrola, Složit stránky, tři náhledy šířky 360 px s kontrolou. Konzole bez chyby. Nový dokument v editoru má `pismo: "mobil"` a řádek „písmo čitelné i na mobilu“.

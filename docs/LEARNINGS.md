# LEARNINGS — GRAFIK

## 2026-11-01 — Restart Engine: kontrola fronty těsně před zabitím

- **Co se stalo:** čekací skript po druhé kontrole prázdné fronty ještě 20 s spal a pak zabil Engine. Mezitím přišla úloha POHYB (`20261101-201901-b431cc`) a restart ji ve 20:19:26 přerušil. Klient ji za 11 s sám zopakoval se stejným semínkem, nic se neztratilo.
- **Jak příště:** poslední kontrola fronty je bezprostředně před `taskkill`, bez pauzy mezi nimi. Fronta je přes den prakticky pořád plná, okno je krátké; Engine zatím neumí přestat přijímat úlohy před restartem.

## 2026-11-01 — Plakát podle cizího vzoru přes 3D modely

- **FLUX si z předlohy `geometry` bere i barvy a povrch.** Render axolotla s červenými vlákny a leskem vyšel jako červené ostny a guma. Render pro FLUX má mít paletu a matnost cíle, nebo ať je bílý.
- **Podobu dělá kamera.** Hlava axolotla byla malá a nízko kvůli ohnisku 120 mm; na vzoru je zvíře blízko a hlava vpředu. Kameru změřit na vzoru dřív než generovat.
- **Přímá projekce barev na model Hunyuan kazí obličej a ruce** (fleky, rozmazaná ústa). Stejná geometrie jako `geometry` a čistý obrázek jako `subject` dá čistý výsledek ve stejné póze.
- **Relativní `render.filepath` v Blenderu míří jinam než pracovní adresář.** `OUT.mkdir` a `body.json` skončily ve scratchpadu, PNG jinde, exit 0, staré PNG zůstalo a vypadalo jako nové. Dvakrát jsem tak složil plakát se starým přijímačem. Cestu předat přes `Path.resolve()` a po renderu kontrolovat čas souboru.
- **`tesla_render.py` tiše nedělal nic, když název záběru nebyl v `SHOTS`.** Prázdný seznam teď končí chybou.
- **Lapač stínu šedí celý snímek.** Na papíře to byl šedý obdélník kolem stroje; `without_veil` v `tesla_kopie.py` odečte úroveň z okraje snímku.
- **Text u figury kontrolovat na plném náhledu.** Poznámka na okraji panelu skončila operátorovi přes obličej: figura se kreslí přes panely a žádná kontrola kolizi nehledá.

## 2026-11-01 — Stránka z modelu: panel musí říct, co hlavní obraz neřekne

- **Co se stalo:** první Koloseum z panelů mělo pod povedeným hlavním řezem čtyři menší rendery téhož modelu (řez, podzemí, fasáda, plachty). Operátor: „menší obrázky neukazují více než hlavní model“, celé „odbyté“. Pravidlo v `docs/infografiky-zasady.md` přitom existovalo; tvořil jsem panely podle toho, co Blender umí vyrenderovat, ne podle toho, co chce čtenář vědět.
- **Jak příště:** před skládáním napsat ke každému panelu jednou větou otázku, kterou hlavní obraz nezodpoví. Když je odpověď jen „totéž zblízka“, panel na stránku nepatří. Téma infografiky je víc než objekt: u stavby i to, co se v ní dělo.
- **Lidské tělo se nestaví z kapslí.** Ruka v Blenderu z kapslí a remeshe vypadala jako komiks i v mramoru; lokální FLUX udělal skutečnou ruku napoprvé a zdarma. Blender je na stavby a stroje, ne na tělo. Stejné semínko navíc dá šestkrát stejného člověka: u série postav jiné semínko a tělo.
- **Výřez postavy s kovem chce zelené plátno a klíč změřený na obrázku.** Na tmavém pozadí se kov ztrácí. Na zeleném odráží plátno, poměr barev selhal v obou směrech, rozhodla až převaha zelené změřená na vzorcích. Kontrolovat výřez ve zvětšení, ne na zmenšené stránce: zubaté okraje a sežraný kov jsem na listu neviděl, operátor ano.
- **Stín postavy se nevyrábí, bere se z obrázku.** Skvrna pod nohama udělala levitaci, vržený stín jedním směrem nesedl na světlo. Skutečný stín je v originálu na plátně a sedí sám.
- **Slavný volný obraz se nekopíruje modelem.** FLUX s obrazem jako předlohou vrátil skoro stejný obraz s chybami a operátor ho odmítl jako „rádoby kopii“. Když je předloha public domain, patří na stránku ona.

## 2026-11-01 — Model z dílů: kontrola, zadání a podklady od operátora

- **Dutá stavba je věc skladby, ne detailu.** Plný klín pod hledištěm s vyříznutými chodbami vypadal v řezu jako černá hmota s dírami. Až tenká deska pod stupni a radiální stěny daly prostor jako v rekonstrukčním řezu. Nejdřív oprav skladbu, potom přidávej díly.
- **Kontrola musí umět selhat.** Řez mimo stavbu prošel rozměry i kontaktem. `rezy_bez_ucinku` porovnává objem před a po. Každou novou kontrolu vyzkoušej na záměrně rozbitém modelu.
- **Co se měří, model splní i za cenu obsahu.** Výška počítaná s podzemím vedla k mazání hypogea, věta „model se ukazuje v řezu“ k odříznutí půlky stavby.
- **Záběr podle `bound_box` je volný.** Rohy kvádru kolem elipsy trčí v pohledu pod úhlem daleko z elipsy, model pak zabíral 2/3 šířky. `frame()` v `render_parts.py` měří vrcholy.
- **Obrázek od operátora po kompakci nevidím, jen svůj popis.** Leží v transkriptu jako `attachment.prompt[]` s base64, ne v řádku `user`. Popis z paměti nestačí: až síť po metrech přes jeho řez odhalila, že jsem patra odhadoval špatně.
- **Odečítání ze sítě.** Řez nebo půdorys s čarami po 5 m dá rozměry, které text neuvádí, a jde je zapsat jako `z řezu`. Zdroj má být obrázek, který jsem přeměřil, ne dojem z něj.
- **Zámek těžké práce drží i ostatní projekty, klidně minuty.** Testy se skutečným Blenderem se pak přeskočí (`s` ve výstupu pytestu). Přeskočené je neměřené, pusť je znovu a ukaž `passed`.
## 2026-11-01 — Slovník výslovnosti: co Whisper mění, i když to zní stejně

- **Zpětný přepis se liší i u správně namluvené věty.** Deset vět buňky (OmniVoice, Whisper small na CPU): bunka, Rybozome, výdou, Sou, douznovu, Vjádře, toho to, na jednou. Porovnání proto stírá diakritiku, i/y a j před s, d, spojuje slovo rozdělené nebo slepené přepisem a nebere rozdíl jen v koncovce. Těchto deset vět pak nedá žádného kandidáta a mitokondrie, orkerst a inustracie zůstanou nálezem.
- **Dosavadní kontrola v NG-ROBOT mitokondrii neviděla.** `unheard_words` bere od podobnosti 0,8 slovo jako slyšené a mitochondrie/mitokondrie má 0,87. Proto `kandidati` hlásí podobná slova a `unheard_words` jiná; překrývají se jen v pásmu 0,6–0,8.

## 2026-11-01 — Obrázky k tématu: špatný zdroj a výběr podle názvu souboru

Operátor u Kolosea: „takové sračky“, přitom krásných 3D rekonstrukcí je plno. Hledání šlo anglicky (`Colosseum`), jazyk nebyl příčina; český dotaz by dopadl hůř.
- **Měřil jsem počet, ne vzhled.** Spike hlásil „obrázky po rolích“ a nikdo se na ně nepodíval. Výsledek obrazového kroku se kontroluje očima na archu náhledů, stejně jako bílý model.
- **Výběr podle názvu a pixelů vybírá náhodu.** Kategorie Commons má 907 souborů, API vrátilo prvních 50 podle abecedy, role šla z názvu a řazení podle šířky. Tak se do podkladů dostala bezpečnostní kamera a hřebík. Lepší signál je, že obrázek vybrali redaktoři hesla, ideálně ve víc jazycích.
- **Podkategorie nečtené:** `Models of the Colosseum` neměla roli, tak se přeskočila.
- **Commons moderní 3D rekonstrukce nemá:** „Colosseum 3D reconstruction“ 0 výsledků. Volné modely jsou na Sketchfabu (hledání bez účtu, licence v odpovědi), nejvíc materiálu je na Pinterestu (3 dotazy = 384 pinů), ale jen přes přihlášený Chrome a s neznámou licencí. Mnoho pinů je generovaných, takže skladba a vzhled ano, fakta ne.
- **Soubor z hesla Wikipedie může být místní a fair use.** Brát jen `imagerepository == "shared"`. Název souboru se liší podle jazyka (`Soubor:`, `Datei:`).

## 2026-11-01 — Barevný render dílů (krok 3b)

- **`bpy_prop_collection` neumí krok v řezu.** `o.data.vertices[::5]` padne s `slice steps not supported`, indexovat přes `range`.
- **Kotva nemusí ležet na povrchu.** Střed okulu je vzduch, paprsek z kamery v něm nic netrefí. Viditelnost kotvy proto znamená „před bodem nic nestojí“, ne „paprsek trefil povrch v tomhle bodě“. Bod dílu naopak na díl dopadnout musí.
- **Render na GPU vs. CPU (1920 × 1080, 96 vzorků, Pantheon, 7 dílů):** 9 s na snímek proti 61 s. Barevný render proto na rozdíl od bílých pohledů jde na GPU a před ním se zastaví vlastní sd-server. S vrstvami je to 8 snímků, 74 s proti ~8 min, a po celou dobu se drží zámek pro všechny projekty.
- **Vrstvy přes `is_holdout` složené přes sebe dávají celý obraz:** průměrná odchylka barvy 0,26 z 255, p99 2,0, alfa 0,17 (Pantheon, řez, 7 vrstev). Vrstva si nechává stíny od ostatních dílů, takže se dá upravit bez přepočítání.

## 2026-11-01 — Řetězec kroků nad jednou frontou

- **Úloha se nesmí rozběhnout dřív, než je zapsaná.** `add_task` a uložení `step_job` jsou dva kroky a worker může úlohu vzít mezi nimi. Pak si přečte starý stav a API ho potom přepíše. Oba kroky proto drží jeden zámek a worker si stav čte přes tentýž zámek.
- **Selhání a přerušení jsou dvě věci.** Selhání stihne zapsat `stop`, přerušení nic nezapíše: krok stojí v aktivní fázi a jeho úloha je `failed`. Podle toho `resume` pozná, co dělat, a placený krok znovu nespustí.
- **Dlouhý heredoc s Pythonem v Bash nástroji padá** na `unexpected EOF`, když obsahuje apostrofy a backticky. Skript s úpravami psát přes Write do scratchpadu.

## 2026-11-01 — Popisek hotového plakátu skončil ve FLUX jako zadání

- **Nová cesta k datům dědí všechna tlačítka okolo.** Upload do Knihovny dostal druh `image` a Studio mu nabídlo totéž co generovanému obrázku. „Další varianta“ poslala popisek „Pantheon: velká infografika…“ do FLUX a stála 0,01 USD za překlad. Průzkum na to upozornil, ale tu pasti jsem hned neopravil. Kromě dat ověřit i tlačítka, která se u nového druhu ukážou.

## 2026-11-01 — Dossier z volných zdrojů

- **Výsledky hledání MediaWiki mění pořadí mezi voláními.** „Pantheon, Řím“ jednou vyšel na Paříž. První výsledek se proto nebere: entita se boduje podle hlavního slova v názvu a upřesnění v popisu a dossier ji ukazuje, aby šla opravit přes `qid`.
- **Commons: jméno bez uvozovek.** `filetype:bitmap "Pantheon Rome"` nenajde skoro nic, bez uvozovek je výtěžek použitelný.
- **Podobné stránky jsou největší zdroj falešných rozporů.** „Třikrát jmenuje“ nestačí: Volkshalle, Roman amphitheatre i dokument BBC to splňují. Podobná stránka musí věc jmenovat v úvodu a nesmí být o filmu nebo knize; z ní se bere jen věta s názvem, která věc nesrovnává.
- **Stejné číslo z jiné Wikipedie není druhé měření.** Stránky se překládají. Čeština a angličtina se na okulu shodly (9 a 9,1 m v mezích zaokrouhlení), rozpor ukázaly až němčina a italština.
- **`load_costs` drží poslední řádek na `job_id`.** Běh, který platí víc kroků, zapisuje jeden řádek s kumulativní částkou, ne součet řádků.

## 2026-11-01 — `gh pr merge` a smazání větve v jednom řetězci

- **Merge selhal na konfliktu, ale další příkaz v řetězci smazal vzdálenou větev a tím PR zavřel.** Větev se maže až po ověření výsledku merge, samostatným krokem. PR #107 šel obnovit přes `gh pr reopen`, teď merge kontroluji stavem PR.

## 2026-11-01 — Plakát 2:3 se ve VectorCraftu otevřel ořezaný na 16:9

- **Ověřit cestu, kterou půjde operátor.** Vrstvy plakátu jsem ověřil příkazem nad vlastním souborem. Operátor šel přes tlačítka: Knihovna → Studio → „→ Infografika“ → „Otevřít ve VectorCraftu“. Tam vznikl dokument s pevným 1920×1080 a renderer obraz ořízl (`preserveAspectRatio="xMidYMid slice"`). Příkaz v chatu není rozhraní.
- **Dokument dostane formát podle obrázku** (`fitting_size`, předvolba jen do 3 % rozdílu tvaru). Obrázek s vlastními vrstvami nese `image-0.svg` a Studio ho otevře přímo.
- **Chromium přidá k PDF s inline SVG prázdnou druhou stranu.** Mezera pod SVG přeteče stránku; `page_ranges="1"`.

## 2026-11-01 — Nahraný obrázek shodil celé Studio

- **Každý obrázek v Knihovně má plný záznam o původu.** `POST /api/v2/library/upload` zapisoval zkrácený záznam bez `cost_usd`, `params`, `refs` a `timing_s`. Studio po načtení vybere nejnovější obrázek, `HistoryPanel` spadl na `fmtUsd(undefined)` a bez error boundary zůstala bílá stránka celé aplikace (10:03 až 10:07, oprava dat přímo v `image-0.json`).
- **Test API nestačí, když data čte Studio.** Můj test kontroloval výpis úloh a `ai_generated`, ne to, co panel čte. Novou cestu k datům ověřovat otevřením Studia ještě před hlášením „je v Knihovně“.
- **Nezměřené je `null`, ne nula.** Render v Blenderu nemá u uploadu změřený čas, panel řádek Čas vynechá. Stejně tak štítek „AI“ se ukazuje jen při `ai_generated`.
- **Boundary chytí jen chybu v potomkovi.** JSX napsané přímo v `App` se vyhodnocuje v renderu `App`, takže `<PanelBoundary>` kolem něj nic nechytí. Záložky proto běží přes `Deferred` a celé `App` má druhou boundary v `main.tsx`. Ověřeno na dočasných datech: vadný záznam ukáže hlášku v panelu, požadavek bez `prompt` hlášku v Knihovně, ostatní záložky běží.

## 2026-11-01 — Render řezu v Blenderu: boolean, světlo a paprsek

- **Plocha po booleanu nese index materiálu z řezacího tělesa.** Řez země byl šedobílý, protože jeho plochy měly index mimo sloty a Cycles použil výchozí materiál. Po každém booleanu přiřazovat materiály znovu podle polohy a normály plochy.
- **Řezná rovina nesmí vést přes vrcholy.** Rotační tělesa jsou posunutá o půl segmentu, takže rovina `y = 0` prochází plochami a Manifold nedělá drobné plošky.
- **Odebraná polovina musí dál stínit slunce**, jinak zaleje celý vnitřek a z okulu žádný paprsek není. Kopie viditelná jen pro stíny a doplňkové světlo s `blocker_collection`, aby na něj nepůsobila.
- **Hustota vzduchu v paprsku zhasne skvrnu na podlaze.** Při 0,06 zbylo ze slunce u podlahy asi 6 %. Viditelný paprsek dělá slabá emise objemu, rozptyl je jen 0,012.
- **Druhé slunce se stejným směrem a `receiver_collection` jen pro paprsek zhaslo to první** (fasáda zmodrala, skvrna zmizela). Příčinu jsem nehledal, emise objemu to řeší jednodušeji.
- **FLUX s předlohou `geometry` nedrží nápis ani proluky.** Tvar stavby zůstal, písmena se rozpadla a díly se posunuly o desítky pixelů. Kde záleží na nápisu nebo na popiscích přesně na bodech modelu, je render lepší podklad.
- **Sesazení dvou obrazů s jiným jasem přes ECC na obraze selže potichu.** Render a malba: ECC 0,77 a posun až 37 px, přitom bez posunu seděly (IoU silueta 0,973). ECC na rozmazaných siluetách: 0,9997, IoU 0,995, posuny do 6 px. Výsledek sesazení kontrolovat překryvem hran.
- **Kolečka v Voronoi nevypadají jako beton.** Plné buňky dají mozaiku, kruhy kolem středů pepperoni. Lepší je vzdálenost od hrany buňky s mezerou, část buněk prázdná a pod tím drť v menším měřítku.
- **Realismus dělá hlavně tmavnutí v koutech a kvádry.** Uzel Ambient Occlusion v barvě a spáry v `Brick Texture` zvedly dojem víc než šum v materiálu; Brick bere jen x a y, proto mapování (x + y, z) a na válci (úhel × poloměr, z).
- **Objekty do vrstev: holdout, ne schovat.** S `o.is_holdout` ostatní objekty dál zakrývají a vrhají stín a vrstvy se složí zpět na celek (odchylka 0,18 z 255). Schované objekty by změnily světlo. Kde se dva objekty dotýkají, jsou oba poloprůhledné a prosvítá stránka: pomáhá zvednout alfu `1 - (1 - a)²`.
- **SVG pro VectorCraft: horní `<g id>` je vrstva, `<g id>` uvnitř pojmenovaná skupina.** Obraz oříznout na objekt, jinak se v okně vybere plátno přes celou stránku. Kopii pro okno nepřepisovat, může v ní být ruční úprava.
- **Editor kontroluje délku popisku včetně vysvětlení** (název + vysvětlení do 40 znaků). Delší první verze prošla API bez chyby, hlášení je až ve Studiu, tak po každé změně otevřít sekci Kontrola.

## 2026-10-31 — Výpis úloh četl celou databázi, Studio tím hladovělo

- **Řazení bez indexu přečte i bloby.** `SELECT * … ORDER BY seq DESC LIMIT 60` bez indexu na `seq` načetl všech 499 řádků včetně předloh v base64 (167 MB) a držel přitom zámek `JobStore`. Na kopii skutečné databáze 1,51 s, s indexem 0,02 s.
- **`setInterval` nečeká na odpověď.** Studio se ptá na `/health` a `/jobs` každé 2 s, i když předchozí dotaz ještě běží. Dotazy se hromadí a obrázky čekají: `/jobs` 11,5 s, `/health` 6 až 9 s, 9 náhledů se nenačetlo ani za 45 s, Engine na 90 % jednoho jádra. Samotný obrázek přitom Engine vydal za 30 ms. Po indexu `/jobs` 0,10 s, `/health` 0,7 s, 9 náhledů 0,9 s, Engine 23 % jádra. `setInterval` zůstal, při pomalém Engine se dotazy hromadit můžou dál.
- **Pomalou stránku nejdřív změř na serveru bez prohlížeče.** Rychlý soubor a pomalý `/health` ukázaly frontu, ne velikost obrázků. Skrytý panel prohlížeče navíc nespouští `loading="lazy"`, takže čekání na `img.complete` v něm nic neříká.

## 2026-10-31 — Karta stylu: FLUX kreslí každé podstatné jméno, i když popisuje techniku

- **Slova o technice se mění v předměty.** „Glow of a tallow lamp“ dokreslilo do jeskynní malby lampu na zdi, „realistic objects and vehicles“ přidalo do ligne claire dvě červená auta na polní cestu. Do karty stylu patří vlastnosti (měkké, ploché, bez stínu), ne věci, které v obraze být nemají. Zdroj světla pojmenovat, jen když do obrazu patří.
- **Slova o střihu a výbavě kamery dopadnou stejně.** „Extreme close-ups mixed with vast long shots“ udělalo z westernu koláž tří záběrů, „stabilised mount“ pověsilo nad velrybu kameru, „static tripod“ postavilo vedle sedláka kameru na stativu. Karta popisuje jeden snímek.
- **Karta umí přebít zadání a umí ho zanechat beze stylu.** „Arch of the galaxy“ v astrofotografii dal na zadání o Měsíci dvakrát Mléčnou dráhu. Surrealismus popsaný jen technikou byl obyčejná krajina, pomohl až balvan ve vzduchu přímo v kartě. Když styl stojí na obsahu, věc do karty patří; když ne, karta jmenuje jen vlastnosti.
- **YAML katalogu:** dvojtečka v textu rozbije nekvotovanou hodnotu a čárka ve `[…]` rozdělí zadání ukázky na dvě. `test_styles_katalog.py` hlídá počet ukázek u každého stylu.

## 2026-10-31 — Převzetí ruční úpravy: kontrola textu v SVG nestačí, zámek nesmí mít vlastníka fronty

- **SVG export VectorCraftu obsahuje i text mimo plátno.** Patička posunutá o 500 px prošla kontrolou nad SVG, v PNG věta o AI chyběla. Co čtenář uvidí, říká `inspect_document`: `visible` a `bounds` proti `artboards[0]`. Skrytý objekt v SVG není.
- **`HeavyLock` je re-entrantní pro stejný PID a `owner`.** `VectorCraft(lock_owner="grafik-engine")` uvnitř Engine by za běžícího FLUX zámek „získal“ a při `close()` ho uvolnil. Druhá těžká práce ve stejném procesu potřebuje vlastní jméno.
- **`.vectorcraft` drží obrázky uvnitř**, když vznikl z SVG s `data:` obrázky (5,5 MB, `missingLinks` prázdné). Propojený obrázek se ale ztratit může, proto `open_file` hlídá `missingLinks`.

## 2026-10-31 — Vada tvaru v obrázku pochází z bílého modelu; kontrola patří před FLUX

- **FLUX s předlohou `geometry` sleduje model víc, než spike z 27. 10. předpokládal.** Tatra „limuzína“ po zarovnání sedí na bílý snímek téměř přesně včetně klik. Vadu vyrobilo natažení středu. Porovnání bílý snímek / FLUX ji proto najít nemůže, ani kdyby tok fungoval ([spike](spikes/2026-10-31-tvar-hrany-tok.md)).
- **Mapa hran + optický tok tvar neměří.** Medián toku odliší správný snímek od jiného pohledu (12/13), ale pevný práh mezi dobrými a špatnými dvojicemi nedá: 4/10 falešných poplachů. Tok počítá posun objektu a texturu pozadí.
- **Kontrola se známou odpovědí je levnější než vyvozovat závěr z popisku.** Stejný výsledek FLUX proti jinému pohledu a jinému modelu ze stejného úhlu ukázal, co metrika umí, a 3 označené dvojice by na to nestačily.
- **Volba podle lepšího skóre umí lhát.** `lod_check` si zpočátku sám vybíral zrcadlení podle IoU a Tatře přiřadil příď k zádi siluety, s lepším číslem (0,821 proti 0,795). Našlo se to jen pohledem na překryv. Směr teď říká autor (`--zrcadlit`).
- **`tatra-87` v2 je natažený na špatném konci** (příď, oválné kolo), a poměry přitom sedí přesně. Poměry nestačí, obrys je potřeba zvlášť.

## 2026-10-31 — SVG ve VectorCraftu: co čte a co tiše vynechá

- **`font-stretch` ignoruje**, `file.info` přesto hlásí `status: exact`. Text je o 15 % širší než v Chromiu. Řez musí být ve jméně rodiny (`Bahnschrift SemiCondensed`); samotné jméno ale ztratí tučnost, proto `Bahnschrift Bold SemiCondensed`. Shodu ověřuj šířkou a pohledem na render, ne stavem z `info`.
- **Vrstva = `<g id>` přímo pod `<svg>`.** `inkscape:groupmode`, `data-name` ani `data-layer` vrstvu samy nedělají (test bez `id`). Vnořený `<g id>` je pojmenovaná skupina. Diakritika a mezery v `id` projdou.
- **Násilné ukončení okna** (`Stop-Process`) nechá po dalším spuštění záložku „[Recovered]“.
- **Otevření editoru v `npm run dev` přepisovalo `updated` infografiky** (kvinquerema 27. 10. → 31. 10., obsah beze změny). Příčina: React StrictMode načte dokument dvakrát (v síti dva GET), druhé `setDoc` je nový objekt a autosave ho bral jako úpravu; `loaded.current` zastavil jen první běh. Oprava: autosave porovná JSON s naposledy načteným nebo uloženým stavem. Přeskakování prvního běhu přes ref na StrictMode nestačí.

## 2026-10-30 — Mazání textu z mapy: na reliéfu a barevných pruzích selhává, T2 to nezachytil

- **T2 měřil mapu s plochými barvami, Everest je stínovaný reliéf.** Šedé písmo má stejnou barvu jako stíny skal, takže maska z barvy zabere i terén a `cv2.inpaint` ho rozmaže. Tmavá fialová trasa a hranice v pásu otočeného popisku padly do masky a jsou přerušené. Bílý text na fialovém pruhu: bílá je i okolní sníh, pruh se rozteče a nový text není čitelný.
- **Kontroly to nehlásí:** `warnings` zachytily jen 20 % zbytků u „NORTH FACE“, nic o trase ani pruzích. Nízké `residue` neznamená neporušený obraz.
- **Volný snímek ai2html grafiky má popisky v HTML vrstvě.** JPG u článku je bez nich (prázdné pruhy), snímek obrazovky je má zapečené.
- **PhotoCraft `paint.remove` bere vzorky z obrazu:** tahy poslané po dávkách doplnily do díry ještě nesmazaný text z jiného místa. Všechny tahy patří do jednoho volání. Na ploché mapě nechává skvrny, tam je čistší `cv2.inpaint`.
- **Překlad bez kontroly není hotový:** „Lhotská stěna“ jsem napsal sám jako správnou bez ověření. Termdb tyhle horolezecké názvy nezná (test: 0 shod), takže prázdná kontrola nic nedokazuje.

## 2026-10-30 — Funkce bez tlačítka pro operátora neexistuje

- **Backend hotový, UI „navazuje“, a funkce zmizela.** Počeštění prošlo testem T2 i Enginem (29. 10.), ale `STAV.md` nechal UI čekat na algoritmus, který už byl dodaný, a operátor ho pak nikde nenašel. Stejně dopadlo `/api/localize-map/*` v NG-ROBOT, které od dubna nemělo tlačítko. Hotovo u funkce pro operátora znamená viditelné v aplikaci. Když UI odkládáš, zapiš ho jako úkol s nositelem a podmínku u něj znovu ověř.

## 2026-10-29 — Sdílená knihovna (fáze 4): import `engine.app` zapisuje, test musí přesměrovat data už v conftestu

- **`engine/app.py` končí `app = create_app()`, takže už import modulu postaví celý Engine s výchozím `Settings()`.** Testy importují `engine.app` při sběru, dřív než běží jakákoli fixture. Když `create_app` začal při prázdné knihovně kopírovat výchozí styly (`StyleLibrary`), první běh testů je nasypal do skutečné `KNIHOVNA/` (3 styly z gitu, nic operátorova se nepřepsalo). Autouse fixture s `monkeypatch.setenv` to nezachytí. Cesty ke sdíleným datům proto nastavuje `tests/conftest.py` přímo do `os.environ` při načtení (jako `GRAFIK_TERMDB`) a fixture je pak přesměruje pro každý test zvlášť. Kontrola: snímek časů souborů KNIHOVNY před a po běhu testů.
- **Shoda textu promptu po převodu stylů se ověřuje proti dnešnímu kódu, ne proti vlastní nové funkci.** GRAFIK: zmrazená kopie `prompt_text()` z ee7fd78, svázaná s doslovným výstupem výchozích stylů. KLAPKA: skutečná třída `Style` a `imaging._look` z checkoutu KLAPKY, staré načítání karty (`model.Library._load`) jako jednořádek v testu. Skutečné styly KLAPKY jsou v soukromém repu, proto je test čte z disku a na stroji bez nich se přeskočí; do veřejného GRAFIKU se nekopírují.

## 2026-10-29 — Mazání textu z obrázku: barva od Claude nestačí, mapy sázejí popisky násobením

- **„Popisky v barvě podkladu“ z T2 byly popisky sázené násobením podkladu.** Šedý popisek (#808080) mapy je na zelené ploše tmavě zelený (2, 77, 21), na žluté tmavě žlutý. Maska podle jedné barvy písma ho nemůže chytit; `ngm_shared.textlayer.localize` proto zkouší dvě hypotézy, plnou barvu a podklad × barva, a podle té, která vysvětlí víc pixelů, i sází (PNG násobením, SVG `mix-blend-mode: multiply`).
- **Claude se u barvy a rámečku plete.** U Vinlandu řekl šedá místo černé. Barva od Claude platí, dokud změřená barva (jádro tahů v rámečku) nevysvětlí aspoň o polovinu víc výrazných pixelů. Vyhlazené okraje cizí barvy podporu dodají vždy, proto rozhoduje počet vysvětlených pixelů, ne to, jestli nějaká podpora existuje.
- **Podklad pod písmem z mediánu okolí selhává na rozeklaném pobřeží**: v rohu zálivu je většina okna druhá plocha, medián ji bere za podklad a hranu plochy za písmo (smazal kus země). Podklad bez písma dává morfologické uzavření a otevření po kanálech (tahy užší než jádro zmizí, plochy zůstanou).
- **Písmo je směs podkladu a své barvy.** Pixel písma leží na úsečce podklad → barva písma (vyhlazený okraj); vzdálenost od ní odliší zelený čtvereček značky vedle černého popisku, prostý práh vzdálenosti od barvy ho bral taky.
- **Otočený popisek: písmo jen v pásu podél jeho osy a nejdál o konec rámečku od Claude.** Jinak se k němu přilepí hranice území a sousední popisky (Britské ostrovy) a písmo vyjde o třetinu větší. Rámečky otočených popisků od Claude měly v T2 délku ±10 %; velikost se bere z měřené délky, nejvýš 1,15× odhadu z rámečku.
- **Kontrola zbytků po mazání chytá vlastní chyby.** Podíl písma barvy popisku, který po `inpaint` zůstal v okolí, nad 15 % = poradní upozornění; hned ukázal špatnou barvu Vinlandu (19 %).
- **Session s automatickou archivací po zavření PR:** řetěz PR slučuj až na konci a jedním skriptem (sloučení, pull, restart, ověření), placené ověření předtím na dočasném Engine z worktree s vlastním `GRAFIK_DATA_DIR` a `GRAFIK_SD_PORT` (fronta operátora se nepotká).

## 2026-10-29 — Zámek ze souboru: O_EXCL nestačí, opuštěný zámek je závod

- **Starý zámek GPU měl dvě díry, které testy nechytaly (jeden proces).** (1) `O_CREAT|O_EXCL` vytvoří soubor prázdný a JSON zapíše až potom; druhý proces mezitím přečte prázdný soubor, vyhodnotí ho jako opuštěný, smaže ho a vezme si zámek taky. (2) Dva procesy, které naráz vidí mrtvý PID, oba smažou a oba vytvoří: druhý smaže už čerstvý zámek prvního. `ngm_shared.heavy_lock` proto mění zámek jen pod krátkým zámkem OS (`msvcrt.locking` na `~/.gpu-lock.mutex`, Windows ho uvolní i po pádu procesu), zapisuje do dočasného souboru a vymění ho `os.replace` a rozepsaný soubor bere 10 s jako obsazený.
- **Důkaz musí být víc procesů.** Šest procesů se stejným startem a 6 × 20 kol se značkou „uvnitř“ (`shared/tests/test_heavy_lock.py`); se zakázaným mutexem vyhrají čtyři najednou a kola se překrývají, takže testy hlídají právě tohle.
- **Windows recykluje PID.** Mrtvý držitel, jehož PID dostal jiný proces, by zámek držel navždy. Proces spuštěný po `since` zámku proto není držitel (`psutil.Process(pid).create_time()`).
- **`os.replace` a `unlink` na Windows padají `PermissionError`, když má soubor otevřený někdo jiný** (čtenář, antivir): krátké opakování. `holder()` pro `/api/v2/health` čte bez mutexu; health nesmí čekat ani spadnout, klienti podle něj poznávají, že Engine běží.
- **Engine si `shared/` dává na `sys.path` sám** (`engine/__init__.py`): Engine startuje `start-grafik.bat`, autostart klienta i testy ve worktree a žádná z těch cest nemusí mít knihovnu nainstalovanou. Vlastní checkout má přednost před editovatelnou instalací z jiného checkoutu.
- **Re-export staré cesty klienta přes `sys.modules[__name__] = modul`**, ne `from … import *`: volající i testy nastavují `grafik_client.ENGINE_URL` a monkeypatchují `_request`, `time.sleep`, `webbrowser.open`; s hvězdičkovým importem by měnili kopii jmen, ne skutečný modul.
- **…a k tomu `globals().update(...)`**: kdo soubor načítá podle cesty (`importlib.util.spec_from_file_location` + `exec_module`), dostane objekt modulu, který `sys.modules` nevymění. Tak to dělal `engine/variants.py` a dělají to kopie klienta v KLAPCE a STOPA (`_variants_page_module()` → `GRAFIK/clients/variants_page.py`); bez kopie jmen byl modul prázdný a padly tři testy dávky variant. Ověřeno skutečnými kopiemi z KLAPKY a STOPA.

## 2026-10-28 — Nesvařenou síť dělal náš export, ne Hunyuan

- **Oprava záznamu z 10-27 „Generované GLB nejsou svařené“.** Syrový Hunyuan3D je svařený: `tatra-87/v1` a `slon-hunyuan3d` mají 500 000 ploch na 250 000 vrcholů a jen `POSITION`. Tři vrcholy na plochu měla až natažená Tatra v2 (1 498 732 vrcholů, 42 MB). Blender po importu GLB bez normál označí plochy jako ploché a výchozí export pak zapíše normálu každé plochy zvlášť, takže každou plochu odpojí. `stretch.py` (a `scripts/3d/stretch_glb.py`) proto exportuje s `export_normals=False`: stejná Tatra má 249 976 vrcholů a 9,0 MB, obálka beze změny (GRAFIK#73).
- **Dopad mimo velikost:** KLAPKA kreslí modely z knihovny Line Artem a nesvařenou síť nakreslila jako plochu plnou čmáranic za 113 s místo 25 s (pojistka v KLAPKA#185).
- Každý další export z Blenderu, který jde do knihovny, bez normál, nebo s normálami jen tam, kde je model opravdu vyhlazený. Test: `tests/test_blender_stretch.py` (skutečný Blender, krychle bez normál musí zůstat na 8 vrcholech).

## 2026-10-27 — glTF Transform: `optimize` s výchozím `join` rozhodí stínování tenkých dílů

- **Spojení meshů + kvantizace = jiné normály.** `gltf-transform optimize` výchozí spojí díly do jednoho meshe a kvantizuje pozice v jeho obálce. Loď z Blenderu (993 dílů, 48 m) tak měla vesla a lana kvantizovaná po ~3 mm a stínovala se jinak (3,4 % pixelů). `--join false` nechá každý díl v jeho vlastní obálce: 0,004 %. Trojúhelníky i obálka přitom seděly, takže rozdíl ukáže jen pixelové srovnání, ne počty.
- **`--instance` mění počty trojúhelníků.** Opakované díly se stanou `InstancedMesh` a součet `index.count` počítá jen jeden exemplář; prohlížeč podle něj volí `flatShading` (< 20k). Pro prohlížeč `--instance false`.
- Srovnání originálu a kopie: stejný záběr do vlastního `WebGLRenderer` s `preserveDrawingBuffer`, rozdíl pixelů v prohlížeči (`docs/spikes/2026-10-27-gltf-optimize.md`).

## 2026-10-27 — 3D scény: co z bílého snímku FLUX drží a co ne

- **Velké tvary drží, drobné ne.** Snímek Loď u mola (kvinquerema 48 m, molo, tři amfory 0,7 m) jako předloha „tvar“: FLUX zachoval stěžeň, plachtu, tři řady vesel, havran i záď. Amfory ale zvětšil asi na 1,2 m a přesunul do popředí a přidal velkou postavu v popředí, přestože zadání obsahovalo větu o měřítku (`docs/spikes/2026-10-27-3d-sceny.md`).
- **Kontrolní postava ve snímku nepomůže, když je malá.** Při 48m lodi v záběru má postava 1,72 m pár pixelů a FLUX z ní udělal sloupek na molu, jinak vyšel stejný obraz (stejný seed). Proto zůstává ve snímku pro FLUX vypnutá (Q4). Na měřítko lidí je potřeba bližší kamera, nebo postavy dokreslit zvlášť.
- **Co pomohlo (operátor: „poměr mola a ženy vůči lodi je příšerný“):** (1) Zadání nesmí lidi a předměty zvát („a sailor and amphorae on the pier“ = obří žena a amfory v popředí). Bez nich a se zákazem přidávat do popředí FLUX nikoho nepřidal. (2) Bližší a nižší kamera (32 m, 10°, 35 mm), kde má postava ve snímku ~40 px, a v zadání „the small standing figure in the reference is a person 1.72 m tall, keep it exactly there“: postava zůstala na místě ve velikosti člověka proti lodi a amfory skoro správně. Věta o měřítku to teď dělá sama (`size_hint(meta, figure)`).
- **Skript s vlastní měřítkovou postavou nafoukne rozměr modelu.** `lod_kvinquerema.py` staví vedle přídě panáčka na podstavci; v exportu zvětšil nejdelší stranu z 48,45 m na 52,25 m a ve scéně stál mimo loď. Export (`scripts/3d/export_kvinquerema_glb.py`) ho vynechává.
- **Model postavený v metrech má rozměr = nejdelší strana obálky**, ne délka trupu (kvinquerema: trup 45 m, s beranem a zádí 48,45 m). Do `rozmer_m` patří obálka, jinak se model zmenší.
- **Kolize kliknutí a OrbitControls:** výběr a tažení objektu musí poslouchat `pointerdown` v capture fázi a vypnout `controls.enabled`, jinak se při tažení objektu zároveň točí kamera.

## 2026-10-27 — 3D v2: zmenšení GLB, test prohlížeče, srovnání obrysů

- **Generované GLB nejsou svařené.** Hunyuan3D dává 3 vrcholy na plochu (Tatra v2: 1,5 M vrcholů na 500k ploch). Decimace bez svaření dala 8,4 MB, se svařením (`bmesh.ops.remove_doubles`) a bez normál 1,2 MB. Normály si prohlížeč spočítá sám (`computeVertexNormals`), u ručních low-poly modelů (< 20k trojúhelníků) `flatShading`, jinak se hrany rozmažou.
- **Blender 5.2 glTF export:** parametr je `export_texcoords` (množné číslo), `export_texcoord` spadne na TypeError.
- **OrbitControls nejde řídit syntetickými `PointerEvent`.** `setPointerCapture` na vymyšleném `pointerId` vyhodí výjimku a handler skončí, takže posun (pan) z JS neproběhne; ani `left_click_drag` s modifikátorem `shift` v Claude Browser se jako Shift nepropíše. Otáčení skutečným tažením funguje. Výpočet kamery s posunutým cílem jsme proto ověřili mimo prohlížeč: tatáž matematika v three.js (Playwright) proti `render_views.py --camera`.
- **Srovnání obrysů potřebuje průhledné plátno.** Playwright `omit_background` vrátí alfu jen tehdy, když stránka nemá vlastní pozadí; s `body{background:…}` vyšla shoda 26 % místo 99,9 %.
- **Převod os glTF → Blender:** `(x, y, z)` → `(x, -z, y)`. Azimut prohlížeče se počítá jako `atan2(-z, x)` v glTF, pak sedí na azimuty sheetu (0° z +X, 90° z -Z) a předek generovaných modelů je na 270°.

## 2026-10-27 — TRELLIS z fotky zepředu shora vymyslí záď

**Kontext:** první placený model přes 3D krok v1 (0,30 USD, `library/3d/tatra-87-trellis-2-commons-ntm/v1`), předloha *Tatra 87 at NTM, Prague.jpg* (CC0): auto zepředu a shora, záď na fotce vůbec není.

- Příď sedí (tři světla, kapota, blatníky, kola). Záď je vymyšlená a rozbitá: chuchvalec úlomků, díra, kotouč jako rezerva, žádná hřbetní ploutev. Poměr šířka/délka 0,50 proti skutečným 0,35.
- Použitelné jsou jen pohledy na příď (180°, 225°). Na celý tvar Tatry je lepší Hunyuan3D se třemi pohledy (`tatra87-hunyuan3d`) nebo Blender z rozměrů.
- Před placeným TRELLIS se podívat, jestli předloha ukazuje bok i záď; fotka jen zepředu dá jen příď.

## 2026-10-27 — Bílé pohledy na CPU stačí; „záď“ modelu se nedá odhadnout z os

**Kontext:** 3D krok v1 (`engine/models3d.py`, měření `docs/spikes/2026-10-27-3d-t1.md`).

1. Cycles na procesoru (32 vzorků + denoise) vykreslí 8 bílých pohledů za 38 s s 0 MB VRAM, EEVEE za 16–28 s s +1,25 GB. Na oko stejné. Rozdíl 10–20 s je levnější než studený start FLUX po zastavení sd-serveru, takže render jede na CPU a FLUX zůstane načtený.
2. Orientace generovaného GLB je náhodná: u Tatry z Hunyuan3D leží délka v ose Y a příď na záporném konci. Natažení „zadní části“ by natáhlo příď i s kolem. Studio proto pojmenuje konec podle pohledu, na kterém je vidět („konec u pohledu 270°“), a operátor vybírá podle obrázku.
3. Nové `node_modules` ve worktree chybí a `npx tsc` bez nich skončí nulou s prázdným výstupem, nic nezkontroluje. Ve worktree nejdřív `npm ci`, pak `npm run build`.

## 2026-10-27 — 3D model hodnotit na velkých renderech po končetinách, ne z náhledů

**Kontext:** Hunyuan3D slon (`library/3d/slon-hunyuan3d/`). Agent ho podle náhledů 400 px vyhlásil za nejlepší model. Operátor si pak všiml páté končetiny na zádi a nesloních zadních chodidel. Vadu převzal i výsledek z FLUX.

- Před verdiktem si model prohlédnout ve 4 pohledech v plném rozlišení. U zvířat a postav spočítat končetiny a zkontrolovat chodidla, ruce a místa, kde se části těla překrývají.
- Zvíře z fotky zezadu: když je mezi zadními nohama vidět chobot nebo ocas, generátor z něj udělá končetinu.

## 2026-10-27 — Blender render vedle načteného FLUX shodí úlohu FLUX; bílý model musí nést poměry, ne detail

**Kontext:** měření TRELLIS proti Blenderu na třech objektech (`docs/spikes/2026-10-27-3d-trellis-vs-blender.md`).

1. Bílý render v Blenderu (EEVEE) sám bere ~1,2 GB VRAM. Spuštěný ve chvíli, kdy sd-server drží FLUX, vyhnal špičku na 7,2 GB z 8 GB a úloha FLUX dvakrát spadla (`flux3 segment … failed during workspace capacity check`). Restart sd-serveru nepomohl, protože Blender paměť pořád držel. Engine bere zámek GPU jen pro `flux-local` (`engine/jobs.py`), takže Blender musí jít pod stejný zámek, nebo běžet na CPU.
2. FLUX s `role: geometry` dokreslí detail a materiál sám. Hrubý Blender model se správnými rozměry dal poznatelnou Tatru 87, detailní TRELLIS model z tříčtvrteční fotky dal obecný sedan (převzal zkrácení perspektivy). U bílého modelu záleží na poměrech a obrysu.
3. Výřez rembg nechá cedulky a pozadí mezi nohama. TRELLIS z nich udělá plovoucí úlomky, které zkreslí i měření bboxu.

## 2026-10-23 — Generátor zvětšuje postavy; měřítko hlídat kótami a promptem

Nano Banana Pro podle hliněného renderu držel tvar lodi, ale postavy si zvětšil asi o polovinu. Pomohlo: výška člověka v metrech a jako zlomek délky lodi přímo v promptu („a man is 1.7 metres tall, about one twenty-sixth of the ship's length … do not enlarge them“). Před placenou kresbou ukázat ortogonální půdorys a bokorys s kótami a kontrolní postavou (`scripts/3d/dims_overlay.py`); úzkou loď tak operátor uvidí dřív, než se zaplatí.

## 2026-10-23 — Hliněný render jako předloha: stíny se mění v předměty, poměry jen z čísel

- Vržený stín plachty na palubě v hliněném renderu FLUX.2 pro „vysvětlil“ jako spuštěný můstek přes palubu. Do předloh renderovat bez vržených stínů (měkké světlo) nebo stín výslovně popsat.
- TRELLIS kopíruje poměry předlohy i s chybami (stavebnicová hračka → tlustý stěžeň, tenké ráhno). Na správné poměry stavět model z rozměrů rekonstrukce (`scripts/3d/lod_kvinquerema.py`, každé číslo se zdrojem).
- Na finální kresbu podle hliněného renderu je Nano Banana Pro věrnější než FLUX.2 pro (nic nepřidává); lokální Klein jen na náčrty. `nb-pro` přímo přes Google vrátil 402 Payment Required (fakturace účtu), `fal:fal-ai/nano-banana-pro` funguje.

## 2026-10-23 — Tvar složitého objektu: 3D model jako předloha, ne prompt

FLUX 3 Klein bez předlohy kreslil kvinqueremu deformovaně (dva stěžně, vesla různé délky a směru). Model z TRELLIS 2 (jeden obrázek čistého modelu lodi) vyrenderovaný v Blenderu a poslaný jako `role: geometry` předloha tvar udržel: jeden stěžeň, pravidelná vesla. TRELLIS ale věrně kopíruje předlohu, takže historickou správnost určuje volba předlohy. Render z TRELLIS je tmavý lesklý plast: světlejší svět a `view_transform = Standard`.

## 2026-10-23 — Restart Engine z větve nechá osiřelý sd-server

Engine z větve (vlastní `GRAFIK_DATA_DIR`) si sd-server zapsal do `run/sd-server.json` ve worktree. Po zabití toho Engine a startu Engine z hlavního checkoutu držel :8390 osiřelý sd-server a nový Engine ho právem odmítl vypnout („Port 8390 už obsluhuje jiný sd-server“), takže úlohy KLAPKY padaly. Před vypnutím Engine z větve vypni i jeho sd-server podle PID z `<data_dir>/run/sd-server.json` a soubor smaž.

## 2026-10-23 — Termdb: past na stejná slova a pomalý poddotaz

- „liška obecná“ má v doméně biology jediný primární záznam *Cantharellus cibarius* (houba), slovník (foreign_words) říká red fox; „Most“ je město i most; „Věž“ obec. Slepé dosazování by škodilo — nápověda jen při shodě odborného a slovníkového významu, zeměpis jen s velkým písmenem.
- Dotaz na anglický název přes korelovaný poddotaz trval 170–570 ms na slovo: plánovač zvolil `idx_translations_lang_primary` (400 tis. anglických řádků). `INDEXED BY idx_translations_term_lang` → 18 ms za celou větu. U `name = ? COLLATE NOCASE` taky `INDEXED BY idx_translations_name`.

## 2026-10-23 — Servery spuštěné z Claude session zmizí s její obnovou

Dvakrát za den Engine (:8300), jeho sd-server a studio (:5174) zmizely bez záznamu v logu (poslední řádek běžný `GET /health`). Společné: všechny byly spuštěné z této Claude session (`Start-Process` z nástroje PowerShell), a zmizely po obnovení session. Procesy jsou ve stromu session a s ní končí. Trvalý provoz: spouštět `start-grafik.bat` ručně (nebo z Plánovače úloh), ne z Claude. Po obnovení session vždy nejdřív ověřit :8300 a :5174 a teprve pak tvrdit „běží“.

## 2026-10-23 — Živé ověření větve: Engine z worktree nad daty hlavního checkoutu (G4)

Na jedné GPU smí běžet jen jeden Engine a jeden sd-server. Kód z větve se ověří tak, že se Engine na :8300 (jen vlastní PID, prázdná fronta) nahradí procesem z worktree s `GRAFIK_DATA_DIR=<hlavní checkout>`: převezme `run/sd-server.json` (stejný sd-server), frontu i knihovnu. Studio z větve běží vedle na :5175 (`npm --prefix studio run dev -- --port 5175`). Soubory, které tím vzniknou v hlavním checkoutu (např. `styles/`), se před `git pull` po merge smažou, jinak pull skončí na „untracked files would be overwritten“. Po merge Engine znovu z hlavního checkoutu.

## 2026-10-23 — Claude Haiku 5.5 přemýšlí ve výchozím stavu a sní tím max_tokens

První živé „Rozepsat zadání“ s delší instrukcí (celek → části → celek) vrátilo **prázdný text a stálo 0,01 USD**. Haiku 5.5 má adaptivní přemýšlení zapnuté, i když se `thinking` nepošle, a přemýšlení se počítá do `max_tokens` (500): na text nezbylo nic. Engine prázdnou odpověď vrátil jako úspěch.
- `claude_text` u Haiku posílá `thinking: {"type": "disabled"}` (povoleno do effort `high`, výchozí je `medium`). U Sonnet 5.5 se `disabled` nesmí poslat (400), tam dát velké `max_tokens` (soudce 4000).
- Prázdná odpověď z Claude je vždy `BackendError` s `stop_reason`, nikdy prázdný výsledek.
- Překlady z G2 prošly, protože krátký úkol se do 600 tokenů vešel i s přemýšlením. Na to nespoléhat.

## 2026-10-23 — FLUX na 8 GB: předlohy v nativním rozlišení a cizí programy na GPU (G3)

**Kontext:** průvodce historickým objektem, bokorys 1920×640 se dvěma předlohami (pin 736×387 + Commons foto 2048×1028); souběžně běžel Illustrator (Beta) a aplikace ChatGPT (~2,5 GB VRAM).

**Poučení:**
1. sd-server posílá předlohy do modelu **v jejich vlastním rozlišení** (`preprocess ref[1]: 2048x1028 … output=2048x1028`). Velká fotka z Commons tak sežere paměť. Engine teď dává všem předlohám dohromady rozpočet ~1,1 MP (`FluxLocal.fit_refs`); ověřený test z 22. 10. měl předlohu 1100×350.
2. Out-of-memory se ukáže až u **druhého** obrázku úlohy (první prošel za 149 s, druhý spadl za 0,2 s: `need 4453 MB device / 3941 MB budget`). Paměť se mezi obrázky fragmentuje → Engine při OOM restartuje vlastní sd-server a zkusí obrázek znovu (`SdServer.generate`).
3. FLUX Q4 potřebuje ~4,45 GB zařízení na obrázek; zbytek auto-fit odloží. Práh volné VRAM pro start proto 4,6 GB (dřív 6,3 GB byl zbytečně přísný a se zapnutým Illustratorem by FLUX vůbec nespustil).

## 2026-10-23 — Wikimedia Commons a Pinterest jako zdroje předloh (G3)

1. Hledání v Commons (`generator=search`, namespace 6) bez `filetype:bitmap` vrací napřed naskenované knihy (PDF/DjVu). S filtrem jen obrázky. Licence a autor jsou v `extmetadata` (`LicenseShortName`, `Artist` jako HTML → odstranit značky). Import přes `iiurlwidth=2048` stáhne zmenšenou verzi, ne 10 MB originál.
2. Pinterest bez přihlášení ukáže jen přihlašovací zeď; robotům (Engine, vestavěný prohlížeč) pin nevydá spolehlivě. Obrázky na `i.pinimg.com` jsou ale veřejné. Proto: záložka „→ GRAFIK“ a Claude in Chrome běží v operátorově přihlášeném Chrome a předávají Engine adresu obrázku; Engine stránku pinu jen zkusí přes `og:image`.
3. Záložka nesmí volat `fetch` na localhost ze stránky Pinterestu (CORS + Private Network Access). Otevírá studio s `#addref=…` a obrázek uloží studio.

## 2026-10-23 — FLUX 3 Klein a čeština: překládat, ne doufat (G2)

**Kontext:** úprava v rámečku a text → obraz ve studiu, `docs/spikes/2026-10-23-g2-studio.md`.

**Poučení:**
1. Encoder Qwen3-VL-4B češtinu „trochu“ chápe: barvy, náladu a médium trefí, ale klíčová podstatná jména ztrácí (maják → dům) a české pokyny k úpravě skoro neprovede (rozdíl v rámečku 6,7 vs 13,8 u téhož pokynu anglicky). Řešení: překlad v Engine (`engine/translate.py`), ne rada „pište anglicky“.
2. Úprava s předlohou trvá ~1,9× déle než text → obraz stejné velikosti; odhady časů to musí počítat, jinak průběh v UI lže.
3. Paste-back drží okolí přesně (mimo rámeček 0,000 i po přeložení pokynu); změna se projeví jen uvnitř rámečku + 2 % okraje.

## 2026-10-23 — Python heredoc v Bash: `\n` v náhradním textu se stane skutečným koncem řádku

Čtyřikrát za session: `python - <<'EOF'` s `s.replace(..., """... "\n" ...""")` zapsal do zdrojáku skutečný konec řádku uprostřed řetězce → `SyntaxError: unterminated string literal` (a v bat souboru `studio\node_modules` → `studio` + nový řádek). Víceřádkové úpravy kódu dělat nástrojem Edit/Write, ne Pythonem v heredocu; když už heredoc, psát `\\n`.

## 2026-10-22 — sd-server (stable-diffusion.cpp): stdout do souboru, defaulty přepsat, procesy jen podle vlastního PID (G1)

**Kontext:** GRAFIK Engine spravuje `sd-server.exe` pro lokální FLUX 3 Klein. Živé ověření `docs/spikes/2026-10-22-g1-engine.md`, API `docs/capabilities/sd-server-master-987.md`.

**Poučení:**
1. sd-server (Rust obal) **panikne, když se mu zavře stdout** (`failed printing to stdout … os error 109`) — stalo se při `curl … | head`. Spouštět vždy s přesměrováním do souboru, nikdy do roury, kterou nikdo nečte.
2. Defaulty serveru jsou pro jiné modely (`--steps 20`, `--cfg-scale 7.0`, port 1234). Pro Klein předávat `--steps 16 --cfg-scale 1.0 --sampling-method euler` jako v `models/flux3-klein/run.sh`; per-request `sample_params.sample_steps` a `seed` se propíšou (ověřeno v PNG tEXt `parameters`).
3. Na stroji běžně leží víc `sd-server.exe` se stejnou cestou (ruční testy v `models/flux3-klein`). Identita vlastního procesu = PID + `create_time` + exe uložené při startu (`run/sd-server.json`); jméno image ani cesta nestačí. Test i živé ověření: cizí server na :8391 přežil idle stop.
4. Edit s jednou referencí trvá u 1024×576 stejně jako t2i (~38 s), ne dvojnásobek.

## 2026-08-15 — Generativní přepis textu: maska glyfů vězní model, pás zapéká sousedy — band + SAM re-cutout (M6-UX1)

**Kontext:** rewrite-text v1 (qwen edit-style). Tři iterace téhož dne, každá s měřeným selháním: (1) maska = alfa starých glyfů (+4 px) → rozlámaná písmena přes ducha starého textu — model nemá kam kreslit JINÉ tvary; (2) pásová maska (bbox glyfů + 0,4× výška řádku, MERGE cesta) → text čistý, ALE pásy sousedních text vrstev se protínají a **zapékají si navzájem kopie** (pás titulku nesl starý podtitulek a překryl ten přepsaný) a iterované přepisy pás nafukují (bbox pásu > bbox glyfů); (3) fix: po editu **SAM „letters" re-cutout** (+$0.005) zúží alfu na nové glyfy → vrstva zůstane čistý text-cutout, pásy se nikdy nepotkají. Commity `4fb5841`, `775317c`; testy pinují pás i re-cutout.

**Poučení:**
1. Maska pro ZMĚNU TVARU obsahu nesmí být stopa starého tvaru — modelu se dává PROSTOR (pás), a čistota vrstvy se obnovuje až post-hoc segmentací výsledku. „Maska = alfa" platí jen pro edity zachovávající siluetu (recolor apod.).
2. Merge-cesta s velkou maskou mění SÉMANTIKU vrstvy (nese pak kus okolí) — každé rozšíření masky ⇒ otázka „co teď vrstva reprezentuje a co se stane při další iteraci?". Iterační invariant (bbox glyfů se nesmí zvětšovat) je nutné vynutit, jinak operace není opakovatelná.
3. Model-level limity qwenu na plakátové typografii (v1 neřeší, jen dokumentuje): 1písmenková typa na malém textu (stochastická — retry), vícerádkový pás → text PŘIDÁ místo nahradí (přepisovat po jednom řádku, vyplňovat původní znění), I2L text zdvojuje do duchových vrstev (skóre ~0,98 „text card" — skrýt/inpaint-behind).

## 2026-08-15 — Hidden tab (claude-in-chrome): CDP screenshot je opravný nástroj, stage.draw() po resize, mutace a čtení v oddělených callech (M6-UX1)

**Kontext:** E2E jelo ve skrytém tabu Claude pane (visibilityState hidden). Nálezy, všechny empirické: (a) po reloadu byl Konva Stage 1×1 (známé z M2.5) — **CDP screenshot vynutí BeginFrame a doručí zamrzlé ResizeObserver/rAF callbacky** → stage se změří správně (screenshot ≠ jen diagnostika); (b) po resize stage `getIntersection` (layer-level hit canvas) vrací null, zatímco `getAllIntersections` (per-shape hit z drawHitFromCache) funguje — layer hit canvas se překreslí až `stage.draw()` (synchronní; batchDraw visí na throttled rAF) → bez něj Konva eventy necílí na shapes; (c) in-page `setTimeout` smyčky background throttling protahuje na minuty (CDP evaluate timeout) a `__editorState` (plněný přes useEffect) je v témže callu stale → protokol „mutace v callu N, verifikace v callu N+1" (RTT mezi cally ~1 s stačí); (d) `save_to_disk` u MCP screenshotů nikam nezapisuje (potvrzeno hledáním v Downloads/Temp) — disk-důkazy = DPI-aware `CopyFromScreen` VIDITELNÉHO okna (GetWindowRect region) + real-mouse SendInput (hover funguje nativně!); souřadnice VŽDY z čerstvého capture (nové UI posunulo layout → klik trefil hlavičku sekce — stejná lekce jako M5 hint řádek). Pozor na okna: SetForegroundWindow blokuje foreground lock, minimize+restore Chrome okno ZAVŘELO — nové okno přes `Start-Process chrome --new-window <url>` je bezpečná cesta.

**Poučení:** Skrytý tab je plnohodnotný pro logiku (fetch, dispatch, __editorState s per-call protokolem), ale VŠECHNO závislé na frame pipeline (RO, rAF, batchDraw, layer hit canvas) potřebuje explicitní vynucení (CDP screenshot / stage.draw()). Vizuální disk-důkazy dělat ve viditelném okně real-mouse pipeline — je věrnější (skutečný hover/click stream) a CopyFromScreen je jediná spolehlivá cesta na disk.

## 2026-08-15 — SAM-3 koncept „text" nedetekuje text — funguje „letters" (M6-UX1 sonda)

**Kontext:** Detektor textových vrstev (M6-UX1) měl stát na text-concept segmentaci `prompt: "text"`. Sonda na plakátu 1792×2400 s obřím kontrastním titulkem: `"text"` → 0 masek, `"writing"` → 0, `"white text"` → 0; **`"letters"` → 1 maska, coverage 3,73 %, přesně přes oba řádky** (y 94–420, 100 % v textovém pásmu); `"words"` → maska jen přes titulek (y 94–280). Vedlejší nález: fal upload URL po pár minutách expiruje (`file_download_error`) — série sond musí uploadovat per volání. Sondy à $0.005.

**Poučení:** Otevřený slovník SAM-3 není synonymický — „text" jako koncept nezabírá, konkrétnější „letters" ano („words" seká po řádcích). Concept prompt pro produkční feature vybírat sondou s měřitelným kritériem (coverage + poloha vs. známá ground truth), ne intuicí; vítěze zapsat jako pojmenovanou konstantu s odkazem na empirii. A fal media URLs necachovat mezi voláními.

## 2026-08-15 — fal si podle vstupních flagů tiše mění i SÉMANTIKU výstupu: SAM `apply_mask` (M5)

**Kontext:** M5 E2E: box_prompts vrátil „masku" celého lva, která po `convert("L")` měla medián alfy 59 a coverage >127 jen 2,47 %. Nebyla to maska — se schema defaultem `apply_mask: true` obsahuje `masks[]` VYŘÍZNUTÝ OBRAZ (cutout) a alfa se tak vyrobila z JASU obsahu (Pearson korelace alfa × jas kompozitu = 1.000 na 499k px; tmavý bronz zmizel, světlý kámen zůstal). Fix `3a874d3`: `_segment_remote` posílá `apply_mask: false` VŽDY → binární masky 0/255. Empirie: `docs/capabilities/sam3-point.md`.

**Poučení:** Rodina pravidel o fal defaultech má třetí člen: (1) neznámá pole tiše ignoruje, (2) vynechané známé klíče tiše doplní defaultem (SAM `prompt`→„wheel"), (3) **flagy umí tiše přepnout SÉMANTIKU výstupu — „masks" nemusí být masky.** Každý klíč, který mění tvar/význam odpovědi, posílat explicitně a výstup první den PŘEMĚŘIT (histogram alfy odhalil za minutu, co by v UI vypadalo jen jako „divně průhledná vrstva"). Korelace s jasem je rychlý diagnostický trik na „je to maska, nebo obraz?".

## 2026-08-15 — Verifikace klipu: lokální optimalizátor nestačí na generativní kameru — feature-first + řetězení + jasový offset (M5)

**Kontext:** Kamerová kompenzace (findTransformECC, affine) prošla na syntetice (zoom 8 %), ale na reálném M3 klipu nehnula residualem (54,2 vs raw 55,4). Důvody, všechny změřené: (a) prompt „zoom_in 0,25" model vyrenderoval jako ~3,5× nájezd → mezi 5 vzorky skoky scale >1,3× a ECC z identity skončilo v near-identity lokálním minimu (cc ~0,4); (b) jas driftoval +24/255 → i perfektní zarovnání by nechalo „pohyb"; (c) obsah morfuje (dav, přepózování sochy). Fix `bca5ed0`: ORB+RANSAC po SOUSEDNÍCH párech (matching nemá konvergenční kotlinu; RANSAC vyřadí pohybující se prvky jako outliery), kompozice transformací na frame 0, ECC jen jako refinement se seedem, 13 vzorků místo 5, jasový offset z mediánu pozadí. Výsledek: M3 klip ratio 0,95→1,94 („weak"→„yes"), nový E2E klip in 46,4/out 33,7/ratio 1,38 → „yes", maska ze submitu, 12/12 snímků.

**Poučení:**
1. **Generativní video není rigidní transformace vstupu** — kompenzace musí počítat s velkým kumulativním pohybem (řetězit malé kroky, ne fitovat celek), expozičním driftem (odečíst offset pozadí) a zbytkovým morfem (residual neklesne k nule; cílem je správná atribuce in/out, ne nula).
2. Syntetické testy cvičí jen cestu, kterou jim postavíš: šumové pozadí nemá ORB rohy → featurová (produkčně nosná) větev byla netestovaná, dokud nevznikl test s blocky mozaikou. Ke každé fallback kaskádě test, který vynutí KAŽDOU větev.
3. Magnitude v promptu je přání, ne měřítko — model si ji škáluje po svém (0,25 → 3,5×). Verifikace se nesmí opírat o očekávanou velikost pohybu kamery.

## 2026-08-15 — E2E přes Chrome/Konva: syntetické eventy s čerstvou geometrií, ne CDP drag (M5)

**Kontext:** CDP `left_click_drag` nedodal Konva Stage průběžný mousemove stream → box-drag se vyhodnotil jako klik (a spustil nechtěný placený single-point call). Navíc přepnutí nástroje přidalo hint řádek, který posunul plátno o ~24 px — souřadnice spočtené ze staršího screenshotu mířily vedle (klik do budovy místo hřívy).

**Poučení:** Konva gesta v E2E řídit syntetickými MouseEventy na `.konvajs-content` s clientX/Y počítanými z ČERSTVÉHO `getBoundingClientRect()` + `__editorState.fitScale/offset`, s `await sleep()` mezi eventy (React batching — bez yieldu čte mouseup handler zastaralý state z closure). Po každé změně nástroje/layoutu geometrii přepočítat. A pozor na `el?.click() ?? fallback.click()` — `click()` vrací undefined, takže fallback běží VŽDY (dvojitý DELETE v destructive logu; server idempotenci ustál).

## 2026-08-15 — Layout quad je JEDINÝ canvas-space rozměr vrstvy — třetí výskyt téže třídy chyby (M4)

**Kontext:** M4 E2E: flux-fill edit draka minul cíl a přepsal vrstvu zmenšeným výřezem. `ai-edit` (a stejně `inpaint-behind`) stavěl masku z alfy v NATIVNÍM rozlišení PNG (~0,4 MP po M2.5 I2L fixu) a vkládal ji na (x,y) — u vrstvy s layout 1024² a nativními 640² tak maska kryla levý horní box místo prvku a crop-back psal zpět 640px fragment. Docstring routy dokonce tvrdil „layers are canvas-sized already" — pravda jen do M2.5. Fix `f6a0cba`: maska i crop-back v layout prostoru (resize nativní→layout na hranici routy) + regresní testy s vrstvou native≠layout (`test_ai_edit_mask_and_crop_use_layout_geometry`, `test_inpaint_behind_uses_layout_geometry`).

**Poučení:**
1. Pravidlo (třetí výskyt: hittest M2 → decompose M2.5 → ai-edit/inpaint-behind M4): **každá canvas-space operace nad vrstvou (maska, crop, merge, hit-test) počítá s layout quadem (x/y/width/height/rotation); nativní rozměr PNG existuje jen uvnitř load/save hranice.** Nový kód dotýkající se geometrie vrstvy začíná otázkou „ve kterém prostoru počítám?".
2. Testy s vrstvou native == layout tuhle třídu regresí nikdy nechytí (stejné poučení jako mock-rozměry u M2.5) — geometrické testy vždy s native ≠ layout.
3. Změna invariantu (M2.5: „vrstvy už nejsou canvas-sized") musí projít grepem na všechny konzumenty invariantu — ai-edit docstring invariant explicitně jmenoval, a stejně přežil.

## 2026-08-15 — Fill model nevidí obsah masky: prompt popisuje cílový obsah díry, ne relativní změnu (M4)

**Kontext:** flux-fill („make the dragon bright green") na vrstvě draka vrátil jinou kompozici (drak jinde, věž pryč) — fill endpoint dostává obraz s dírou + prompt a do díry generuje NOVÝ obsah; původní pixely masky nezná, „make X green" nemá k čemu vztáhnout. Druhý pokus s fill-style promptem („an old parchment banner scroll with the text GRAFIK…") vrátil přesně lokalizovaný výsledek (pixel-diff uvnitř masky 72,9, mimo 3,7). Detail: `docs/spikes/2026-08-15-m4-e2e.md`.

**Poučení:** U mask-based editů rozlišovat dvě sémantiky: **edit-style** (qwen-image-edit — vidí celý obraz, rozumí relativní instrukci „přebarvi") vs **fill-style** (flux-fill — generuje obsah díry z okolí + promptu). Recolor/úprava existujícího prvku → qwen-inpaint; náhrada/odstranění/nový obsah → flux-fill s promptem popisujícím CO má v díře být. Kandidát M5: hint u přepínače provideru v UI.

## 2026-08-15 — Qwen I2L decompose: vrstvy v nativním rozlišení (~0,4 MP), ne v rozlišení vstupu

**Kontext:** Obnova projektu openart (`75778f1bd1a4`): `decompose/file` auto-setuje canvas z uploadu (1792×2400), ale I2L vrátí vrstvy 544×736 (3:4) — `FalClient.decompose` nastavoval `layer.width/height` z fal výstupu a canvas už neměnil → kompozit měl obsah jen v bboxu (0,0,544,736) vlevo nahoře (~30 % plátna). Endpoint dekompozice z URL rozměry zdroje vůbec nezná (canvas přebírá z prvního fal PNG), proto starší projekty (e2e-sc1, decompose-test) mají canvas == 544×736 a bug se u nich neprojevil; kanonický ui-web flow (`createProject` 0×0 + drag&drop) byl postižený u každého velkého vstupu.

**Poučení:**
1. I2L (qwen-image-layered) resampluje výstup na nativní rozlišení modelu ~0,4 MP (544×736 pro 3:4 — stejná rodina omezení jako inpaint cap ~1536 px). Rozměry fal výstupu nikdy nebrat jako rozměry zdroje.
2. Fix = varianta (a): `FalClient.decompose` roztáhne layout vrstev (width/height) na canvas projektu; pixel data zůstávají nativní a composer resizuje při kompozici (width/height ≠ PNG umí od M2 hittest fixe). Stejná hranice jako resize-back u QwenInpaintProvider — výstup provideru se mapuje do geometrie projektu hned na hranici provideru. Zachovává plné rozlišení plátna (export, budoucí crop-based inpaint). Varianta (b) — canvas z fal výstupu — by plátno degradovala na ~0,4 MP a přepisovala explicitně zadané rozměry projektu.
3. Kompatibilita: canvas se z fal výstupu setuje jen když nebyl → staré projekty (canvas == vrstvy 544×736) jsou no-op, projekty na disku se nemění.
4. Testovací nuance: mock fal musí vracet záměrně JINÝ rozměr než upload — mock se shodnými rozměry by tuhle třídu regresí nikdy neodhalil. Testy `tests/test_api_decompose_canvas.py` (offline, včetně pixel-proof kompozitu: roh plátna mimo nativní box musí být neprůhledný).
5. Obnova openart proběhla ještě před fixem: layout vrstev narovnán ručně přes `POST /layers/{id}/transform` na rozměr plátna — kompozit pak pokrývá celé plátno, mean diff vs zdroj 6,08/255 (před narovnáním 4,78/255 po downscale, ale jen v rohu); drobné roztažení aspektu jen vrací fal deformaci 544×736 zpět na poměr zdroje.

## 2026-08-15 — INCIDENT: tichá ztráta projektu během E2E; destruktivní routy bez access logu = nulová forenzika

**Kontext:** M2.5 E2E. Během okna s ~2 min zaseknutým uvicornem (corrupt multipart upload, pre-fix éra) a dvěma restarty API zmizel z disku projekt `openart-…grafik`; současně se v UI objevil failnutý request, který nikdo vědomě neposlal. API tehdy běželo bez access logu (Start-Process bez redirectu), takže neexistuje záznam requestů. Detail: `docs/spikes/2026-08-15-m25-e2e.md` (sekce INCIDENT).

**Dořešeno (tatáž noc):** náhodně zachycený `/api/projects` response z okamžiku incidentu (soubor `-w` z nepovedeného curlu) ukázal openart s **novým id** — manifest přepsal pre-fix `create_project` při kolizi jmen adresářů (nejspíš souběžný ruční drop `openart-image_….png` z Downloads); „rozbitý" 0-vrstvý projekt byl pak smazán přes UI ještě před startem logu. Root cause = bug opravený v `0d14ed2`; žádný replay/misroute.

**Poučení:**
1. Jakmile API dostane destruktivní routu (DELETE projektu), access log není nice-to-have ale podmínka provozu — `uvicorn --access-log` s `-RedirectStandardOutput logs/uvicorn-out.log` od prvního startu. Bez něj se incident nedá ani vyšetřit, ani vyvrátit (tady zdržel diagnózu o hodiny; vyřešila ho až náhodná stopa).
2. Před E2E nad živými daty udělat zálohu `projects/` (copy je levná; forenzika po ztrátě nemožná). Záloha session: `projects-backup-<stamp>/`.
3. „Tichý přepis dat" vypadá zvenku stejně jako „tiché smazání" — při ztrátě dat nejdřív hledat write-cesty s kolizí identifikátorů (tady `safe_name` adresáře), ne jen delete-cesty.
4. Neznámé soubory nalezené po incidentu jsou potenciální evidence — archivovat, pak mazat (tady byl soubor po přečtení smazán; obsah přežil jen v transcriptu).
5. Kandidát M4: soft-delete (koš) místo okamžitého `rmtree`.

## 2026-08-15 — fal schema defaulty: vynechaný klíč ≠ „bez hodnoty" — server si default dosadí sám

**Kontext:** SAM-3 point mode. `point_prompts` bez klíče `prompt` → **0 masek**: schema deklaruje `prompt` default `"wheel"`, server ho při chybějícím klíči dosadí a textová detekce „wheel" nic nenajde. `prompt: ""` + bod → maska prvku pod bodem (part-level granularita ~jednotky % plátna; celý objekt = víc bodů se stejným `object_id` / box / text). Empirie + payload pravidla: `docs/capabilities/sam3-point.md`, fix `ccdf5a8`, test `test_segment_remote_point_only_sends_empty_prompt`.

**Poučení:** Rozšíření pravidla „jediný zdroj pravdy je raw OpenAPI": fal pole s defaultem se chová, jako by ho poslal klient. Při stavbě payloadu projít defaulty VŠECH vynechaných polí (stejná rodina jako `generate_audio:true` u Klingu — default umí změnit cenu, tady umí vynulovat výsledek).

## 2026-08-15 — FastAPI: neošetřená výjimka = 500 bez CORS hlaviček → frontend vidí jen „Failed to fetch"

**Kontext:** Drop poškozeného PNG → PIL výjimka v `decompose/file` → 500 mimo CORSMiddleware (výjimky obcházejí middleware stack) → banner „Network error … Failed to fetch" místo důvodu.

**Poučení:** Všechno, co může selhat na uživatelském vstupu (upload, parsování), balit do `HTTPException(4xx, důvod)` — ta projde exception handlerem UVNITŘ middleware stacku a prohlížeč důvod přečte. Vzor shodný s M2 „provider faily → 502 s důvodem". Fix `53a880b` + `test_decompose_file_not_an_image_400`.

## 2026-08-15 — claude-in-chrome (tato instance): ref-kliky lžou, souřadnice jsou screenshot-space, background tab rozbíjí ResizeObserver

Doplnění M3 zápisu o E2E automatizaci:
1. **Ref-based kliky** (`computer` + `ref`) hlásí úspěch, ale klik do stránky nedorazí (i s čerstvým `find`) — klikat na **souřadnice** odečtené ze screenshotu, nebo JS `.click()` (plnohodnotný DOM event přes React). Kalibrace: screenshot px = CSS px × (šířka_screenshotu / window.innerWidth) — zde ×0,8167; opačným směrem při přepočtu z `getBoundingClientRect`.
2. **Background tab**: reload stránky v tabu, který není aktivní, nechá Konva Stage na 1×1 — ResizeObserver callbacky jedou přes rAF a ten je v background tabu throttlovaný. Nejde o bug aplikace (viditelný tab se změří správně); pro programové exporty nutná ruční korekce (`stage.width/height` + layer transform + pozor na `strokeWidth: 1/fitScale` spočtený z 1×1 → 736px tah přes celé plátno).
3. **html2canvas nevykreslí Konva canvasy** (stacked canvas vrstvy) — kompozici exportovat přímo `stage.toDataURL()`; DOM chrome a plátno skládat zvlášť. Soubory na disk z prohlížeče: mini HTTP receiver (PowerShell HttpListener) + fetch POST base64 — `save_to_disk` u screenshotů nikam viditelně neukládá.
4. `window.confirm` nejde obsloužit přes CDP (nativní dialog) — pro E2E intercept `window.confirm = (msg) => {…; return true}` se záznamem zprávy; existenci dialogu dokládá zachycený text.

## 2026-08-14 — Servírování videa: FileResponse (206), a jak odlišit bug od rozbité media pipeline

**Kontext:** M3 E2E — `<video>` v editoru stál na readyState 0. Route vracela mp4 přes `Response(content=…)` (200 na všechno včetně Range probe). Fix: `FileResponse` (starlette ≥0.36 umí Range → 206), commit `a732042`.

**Poučení:**
1. Binární média vždy přes `FileResponse`/streaming s Range podporou — Chromium media stack bez 206 umí odmítnout hrát, i když `fetch()` téže URL funguje.
2. Diagnostický žebřík media problémů: (a) curl mimo prohlížeč → server OK?; (b) `fetch()` ze stránky → síť z prohlížeče OK?; (c) `blob:` URL s daty v paměti do `video.src` → pokud stall i tady a resource timing nemá pro media URL žádný záznam, je rozbitá media pipeline celé instance prohlížeče (environmentální — restart Chrome), ne aplikace. Přesně tenhle případ nastal: fetch 33 ms, blob stall, prázdný resource timing + opakované >30 s freezy rendereru.

## 2026-08-14 — Pixel-diff atribuce prvku nefunguje pod globálním pohybem kamery

**Kontext:** M3 E2E klip (Wan 2.6): socha se reálně hýbala (vizuální kontrola framů), ale kamera zoomovala mnohem silněji než „slowly" → global_motion 55/255, in/out ratio 0,95 → verdikt „weak".

**Poučení:** In-mask vs out-mask poměr měří *atribuci*, ne pohyb — jakmile kamera hýbe vším, poměr →1 a verdikt „weak" je pravdivé přiznání ne-atribuce (žádoucí chování closed-loop, ne bug). Pro čistou atribuci prvku: generovat verifikační klip s kamerou „Žádná", nebo (M4 kandidát) kompenzovat globální pohyb (optical flow / homografie) před diffem. Modely navíc interpretují adverbia intenzity („slowly") volně — kompilovaný prompt intenzitu kamery negarantuje.

## 2026-08-14 — Konva: „klik do prázdna" neexistuje na scéně s celoplošným pozadím

**Kontext:** M3 motion tool — gesto „klik na prázdný Stage přidá bod trajektorie" na reálném projektu nikdy nenastalo: spodní vrstva pokrývá celé plátno, alfa hit-test pohltí každý klik (výběr vrstvy místo bodu).

**Poučení:** Gesta na canvasu nesmí spoléhat na „klik mimo vrstvy", pokud scéna může mít opaque pozadí. Vzor: v režimu nástroje s aktivním výběrem interpretovat VŠECHNY kliky do plátna jako akci nástroje; změna výběru jde přes panel vrstev; overlay prvky (kotvy) chránit Konva `name` checkem v Stage handleru. Commit `01eb06a`.

## 2026-08-14 — E2E přes claude-in-chrome: zoom akce a syntetické dragy

1. Akce `zoom` (region screenshot) po timeoutu zanechala tab s device-metrics override (viewport 464×220 = rozměr regionu) → všechny další kliky/screenshoty mimo, `resize_window` ani Ctrl+0 to nevrátí. Oprava: nový tab (nový CDP target). Na Konva-heavy stránkách `zoom` nepoužívat.
2. Syntetický CDP drag (mousedown/move/up v jednom ticku) nespustí Konva drag (vrstvy ani kotvy) — reálná myš ano. Drag chování ověřovat Playwrightem (editor-verify.mjs vzor z M2) nebo nechat operátorovi; klikací E2E to má zapsat jako limitaci, ne FAIL.
3. Screenshot souřadnice ↔ CSS px: mapování se mění s viewportem (po reloadu jiné) — pro přesné kliky brát `getBoundingClientRect` přes JS, nebo klikat přes `find`→ref. Ref může po přerenderování ukazovat na odpojený uzel — před klikem vždy čerstvý `find`.

## 2026-08-14 — imageio_ffmpeg.read_frames: meta first-yield, konec streamu bez výjimky

`read_frames` generator: první yield je meta dict (`size` (w,h), `fps`, `duration`, …), pak syrové RGB24 bytes (w×h×3). Kratší stream než odhad `fps×duration` prostě skončí iteraci — žádná výjimka, netřeba try/except. Binárka bundlovaná ve wheelu (`site-packages/imageio_ffmpeg/binaries/`), ffmpeg na PATH není potřeba. (Empiricky ověřeno v grafik/motion/verify.py; testy test_motion_verify.py.)

## 2026-08-14 — API sémantika: /motion je full-replace, /transform je partial-patch

`POST /layers/{id}/motion` nahrazuje celý LayerMotion tím, co přišlo (vynechaná pole = Pydantic defaulty), zatímco `/transform` aplikuje jen poslaná pole. Klient proto u motion vždy posílá kompletní objekt (`persistMotion` v EditorApp). Past pro budoucí přispěvatele: nekopírovat transform vzor na motion (tiše by nuloval nedotčená pole).

## 2026-08-14 — Sdílené live fixtures: testy si musí pinovat baseline

M2 E2E posunula vrstvy ve sdíleném `projects/decompose-test.grafik` (gitignored, společný pro všechny worktrees) → 2 předexistující inpaint-behind testy spadly o den později. Fix: `api` fixture v `test_api_m2.py` po copytree pinuje geometrii/viditelnost známých vrstev (a maže `history.json`). Pravidlo: (a) testy nad živým sdíleným adresářem si baseline vynucují samy, nikdy mu nevěří; (b) živá UI práce patří do `e2e-*` projektů, ne do referenčních fixtures.

**Kontext:** M3 příprava. Raw OpenAPI fetch (metodika viz níže „jediný zdroj pravdy") odhalil, že `fal-ai/kling-video/v2.6/pro/image-to-video` bere **`start_image_url`** (REQUIRED), zatímco v1.5/v1.6 i Wan/Seedance berou `image_url`. Sdílený `build_video_payload` z fáze 1 posílal `image_url` všem → na Kling 2.6 by submit spadl na validaci (latentní bug, nikdy nevolán naostro — mock testy tvar payloadu vůči schématu neověřují). Navíc rizikové defaulty: Kling 2.6 pro a Seedance 2.5 mají `generate_audio` **default True** (≈2× cena), Wan 2.6 má `resolution` default **1080p** ($0.15/s místo $0.10/s) a `enable_prompt_expansion` default True (model přepisuje náš prompt — proti smyslu kompilovaného MotionSpec promptu).

**Poučení:**
1. Payload builder pro video musí být **per-endpoint mapovaný z registry** (image_field + payload_defaults + duration_choices), ne sdílený tvar. Capability sweep má zaznamenávat i jména povinných polí a defaulty, ne jen existenci featur.
2. Schema defaulty jsou součást capability dat — default, který tiše zdvojnásobí cenu nebo přepíše prompt, je stejně důležitý jako existence pole.
3. Mock testy payload tvaru neodhalí drift vůči reálnému schématu — při přidání video providera vždy znovu fetchnout raw OpenAPI a diffnout povinná pole.

## 2026-08-14 — Hit-test musí sdílet transformační model s rendererem

**Kontext:** M2 E2E — serverová route `/hittest` predikovala „Layer 1", reálný klik v editoru vybral „Layer 0". Server testuje alfu v nativních pixelech PNG (`lx = x - layer.x`), klient renderuje protažené na `layer.width/height` (a decompose může uložit width/height ≠ rozměry PNG). Dvě „správné" odpovědi na tentýž bod.

**Poučení:** Jakákoli geometrická logika (hit-test, maska→souřadnice, budoucí trajektorie) musí explicitně říct, v jakém prostoru počítá (nativní PNG vs. layout width/height vs. canvas), a sdílet přepočet s composerem/rendererem. Pro UI výběr je autoritativní klientský Konva `drawHitFromCache`; `/transform` snapshot fix ukázal totéž z druhé strany — každá mutace stavu musí jít přes tentýž history mechanismus.

**Opraveno (2026-08-14):** `/hittest` invertuje forward model composeru v jeho pořadí: un-translate → inverzní rotace kolem kotvy (Konva cw, y-down) → rescale layout→nativní px (`math.floor`, ne `int()` — truncation k nule by pustila body těsně vlevo/nad vrstvou). Regresní testy `tests/test_api_hittest.py` mají ručně odvozenou geometrii (syntetická vrstva s levou půlkou opaque) a na starém kódu selhávaly přesně E2E symptomem (vrácen jiný layer). Pořadí operací pinuje test rotace+scale — scale-before-rotate by četl průhledný pixel.

## 2026-08-14 — Worktree session nemůže smazat vlastní adresář

Claude Code host drží Windows handle na cwd worktree po celou dobu session — `git worktree remove` odregistruje, ale smazání adresáře selže „Device or resource busy", i když procesy uvnitř skončily (obsah smazat jde, zbyde prázdná skořápka). Řešení: po merge hned smazat větev + `git worktree prune`, prázdný adresář smazat odloženě (detached retry skript) nebo z jiné session. Pozor: i wrapper `run_in_background` úlohy drží handle spawn-cwd — dlouhoběžící servery spouštět `Start-Process -WorkingDirectory <hlavní checkout>`, ne z worktree.

## 2026-08-14 — RTK hook blokuje víceřádkový `git commit -m`

Víceřádkový commit message v `-m` přes Bash selže ještě před spuštěním: RTK PreToolUse hook přepíše příkaz a přepsaný vstup neprojde schema validací („command contains control characters that would be hidden in the approval dialog"). Obejití: zapsat message do souboru (scratchpad) a `git commit -F <soubor>`.

## 2026-08-14 — RTK hook maskuje pytest výstup

`python -m pytest` přes Bash s RTK hookem hlásí „No tests collected", i když testy proběhly. Obejít: `rtk proxy python -m pytest tests/... -q` — ukáže reálný výstup. Platí pro celou session i subagenty.

## 2026-08-14 — fal.ai schema: jediný zdroj pravdy je syrový OpenAPI JSON

**Kontext:** Plánovací research (unified editor, 2026-08-14) tvrdil, že Kling 1.6 Pro má `dynamic_masks` + `advanced_camera_control`. Task 1.4 to vyvrátil raw fetchem: motion brush existuje jen na `v1/standard` a `v1.5/pro`, kamerová kontrola na žádném image-to-video endpointu (jen `v1/standard/text-to-video`). Detail: `docs/capabilities/kling-versions.md`.

**Poučení:**
1. Jediný zdroj pravdy o fal endpointu je syrový OpenAPI JSON: `curl "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>"` + grep na přesná jména polí. WebFetch/WebSearch AI souhrny si pole vymýšlejí (fabrikovaly `static_mask_url` u „Kling 2.0 Master", který nic takového nemá).
2. fal může neznámá pole v payloadu tiše ignorovat — „úspěšný" call nedokazuje, že feature fungovala. Před stavbou na parametru ověř jeho existenci ve schématu; jinak vzniká falešná evidence.
3. Neexistující endpoint vrací doslova `null` (4 byty) — levný existence check.

**Aplikace:** Provider capability map (`grafik/providers/`) plnit výhradně z raw schema fetchů s datem ověření; capability zápisy patří do `docs/capabilities/` s reprodukovatelnými URL.

## 2026-08-14 — Kling motion brush: mrtvá API cesta (gate Fáze 1)

**Kontext:** Smoke testy task 1.2. v1.6+ pole `dynamic_masks` nemá a **payload s neznámými poli tiše přijme** (klip se vygeneruje bez motion controlu — falešný „úspěch"). v1.5/pro pole má, ale efekt slabý (in/out diff 1,40×→1,04). Detail: `docs/spikes/2026-08-14-kling-smoke.md`, verdikt: `docs/plans/2026-08-14-phase1-gate.md`.

**Poučení:** Per-element video motion nestavět na API mask parametrech — kompilovat MotionSpec na strukturovaný prompt + pixel-diff verifikaci výsledného klipu vůči masce. Capability sweep je datovaný snapshot: discovery přes fal search je neúplná (Seedance 2.5 a GPT-Image 2 doplnil až uživatel) → capability map musí nést `verified_at` a jména modelů od uživatele brát jako discovery vstup.

## 2026-08-14 — Qwen inpaint: empirický output cap ~1536 px (4K re-test A1)

**Kontext:** Re-test A1 na 4K (`smoke_inpaint.py --long-edge 3872`, plátno 2862×3872 ≈ 11 MP). Endpoint vrátil **1536×1536 bez ohledu na požadované `image_size`** — schema přitom deklaruje max 14142 px (empirie ≠ schema). Paste-back metriky drží i na 4K: outside-mask diff po paste-backu 0.024 (baseline 0.095), boundary ratio 1.063, beze švů → **A1 PASS na 4K**.

**Poučení:**
1. Resize-back výsledku na vstupní rozměr (v `QwenInpaintProvider._run_remote`→`edit`) je **load-bearing** větev — nad ~1536 px dlouhé hrany by se bez ní výsledek vůbec nesložil s originálem.
2. Efektivní detail vygenerovaného obsahu uvnitř masky je na 4K plátně jen ~1.5K (upscale LANCZOS) → pro jemné edity na velkých plátnech zvážit crop-based workflow (poslat endpointu jen výřez kolem masky) — kandidát M3/M4, ne M2.
3. Schema `max` hodnoty jsou jen deklarace — ke capability ověření patří i empirický behavior test (rozšíření pravidla „jediný zdroj pravdy je raw OpenAPI": schema říká, co API *přijme*, ne co *udělá*).

Detail: `docs/spikes/2026-08-14-inpaint-4k.md`.

## 2026-08-14 — Qwen inpaint: paste-back v pixel space je povinný

**Kontext:** Smoke test `fal-ai/qwen-image-edit/inpaint` (task 1.3): raw výstup endpointu má globální drift i mimo masku (mean diff ~20/255, 48 % pixelů), tj. endpoint překóduje celý obraz.

**Poučení:** Výsledek inpaintu nikdy nebrat celý — vždy kompozitovat zpět jen vnitřek masky (feather ~2 px, dilate ~4 px) nad originál. Pak je diff mimo masku ~0 a hranice bez švů (gradient ratio 1.035 @ 544×736). Před M2 přeměřit na 4K.

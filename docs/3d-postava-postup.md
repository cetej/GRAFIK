# 3D postava z podkladu: postup a pasti (legionář, 2026-11-05)

Ověřeno na římském legionáři z doby Trajánovy, knihovna `library/3d/rimsky-legionar-trajanova-doba`, verze v1–v16 (platné: **v15** čistý, **v16** opotřebovaný; v12–v13 zbytek starého jílce u lokte, v14 díra v boku; v4–v7 mají zdvojený meč a dýku v boku, v8–v9 nakřivo puklici a pugio bez rukojeti, v10–v11 pugio u lokte a zezadu odstává). Celkem **USD 0,90** (bílý model 0,375 + obarvený 0,525), všechno ostatní v Blenderu za 0 USD. Skripty: `scripts/3d/postava/legionar_*.py` (souřadnice a prahy jsou pro tohoto legionáře, u jiné postavy je změř sondou znovu). Plný zápis průběhu: STOPA `outputs/2026-11-05-legionar-3d/README.md`.

## Kdy tahle cesta, kdy jiná

- **Postava, zvíře, organický tvar** (proporce nejsou dané rozměry): generátor přes fal.
- **Stavba, stroj, nic s rozměry** (Trajánův sloup, loď): Blender z rozměrů nebo skutečný sken, ne generátor. Generátor z fotky udělá tvar „podle oka“ a detail rozmaže.
- **Povrch** (vrásky, reliéf, opotřebení) z AI sítě nezapečeš: generátory dělají hladký povrch. Pokus s vorvaněm (STOPA `outputs/2026-11-05-vorvan-bake-detail`) z AI sítě přenesl jen posunuté rysy. Povrch se dělá procedurálně v Blenderu.

## Postup

| Krok | Co | Cena | Skript |
|---|---|---|---|
| 1 | **Podklad se 4 pohledy** (zepředu, zezadu, zleva, zprava) na jednotném pozadí. Reálie zkontrolovat proti seznamu ze zdrojů, než se platí. | 0 | – |
| 2 | Rozřezat a vyříznout pozadí: klíč šedého pozadí, v pásu podlahy sytost + rembg | 0 | `legionar_cutout.py` |
| 3 | Pohledy, které si odporují, **vynechat** (zleva visel meč na druhém boku) | 0 | – |
| 4 | Bílý model: Engine, Hunyuan3D v3 multi-view, Geometry | 0,375 | Engine `POST /models3d` |
| 5 | Obarvený model: Hunyuan3D v3 `generate_type: Normal` + pohledy, přímo přes fal (Engine má generátor napevno na Geometry) | 0,525 | `legionar_fal_barevny.py` |
| 6 | Lesk kovu: metallic-roughness mapa z barvy textury | 0 | `legionar_lesk_zbroje.py` |
| 7 | Vyráběné díly vymodelovat a položit **přes** původní (pilum, puklice, pugio); co nový díl nezakryje ze všech stran, nechat z generátoru (meč) | 0 | `legionar_hrot_pila.py`, `legionar_dily_kov.py` |
| 8 | Kování a prvky přilby jako mosaz, ocel sjednotit | 0 | `legionar_dily_kov.py` |
| 9 | Opotřebení na tažení zapéct do textur | 0 | `legionar_opotrebeni.py` |
| 10 | Kontrola: rendery se studiovým HDRI, **výřezy v plné velikosti** (hlava, kování, meč, nohy) | 0 | `legionar_render_pohledy.py` |
| 11 | Nahrát jako novou verzi (`glb_b64`), starou nepřepisovat; po schválení `review` | 0 | Engine API |

Polohy dílů (osa pochvy, střed puklice) dává `legionar_sonda_dily.py`: barva textury pod každým vrcholem + souřadnice do `sonda.npz`, analýza v numpy.

## Pasti, které stály kolo navíc

**Podklad a výřez**
- FLUX předlohy legionáře měly zbroj pod pas, šupinové nýty, holenice: dvě kola po 4 variantách zamítnuta. Operátorův podklad se 4 pohledy byl lepší než cokoli vygenerovaného.
- rembg v Engine smaže tenké předměty (pilum) a někdy i celý štít zezadu. Pohledy si pak odporují. Klíčovat pozadí vlastním kódem.
- Odhad barvy pozadí z okrajů výřezu: kde okraj tvoří předmět (štít), brát jen nesyté pixely okraje.

**Barvy**
- Promítnutí fotek podkladu na hotovou síť (vertex colors, dorovnání podle obrysu, IoU 0,73–0,81) dalo zepředu ostrý výsledek, z boků smouhy. Operátor: „ten, kdo to barvil, se ožral“. Obarvení generátorem stálo 0,525 USD a bylo čisté ze všech stran.
- PNG z `img.pixels` je sRGB, barevný atribut a emise jsou lineární: bez převodu vybledlé barvy.
- Studio v prohlížeči ukazuje hlínu (`viewer.glb` bez textur, DECISIONS ř. 336). Barvy jsou jen v `model.glb`, kontroluj rendery z Blenderu.

**Masky materiálů (kov, mosaz, kůže)**
- Odstín mosazného kování (18–23°) je stejný jako obličej (19–23°): barva nestačí, rozhoduje místo (trup, přilba), u obličeje odstín (pleť 7–12°, lem lícnic 15–23°).
- Oblast (přilba, trup) kreslená do textury jen v UV bodech vrcholů nechává díry → výsledek vypadá jako „písek“ nebo mozaika. Rozšířit masku o ~7 px. Rozmazání textury samo nepomohlo.
- Generátor do textury zapéká odlesky a stíny z fotky; na kovu z nich jsou bílé a černé šmouhy. Všechny nesyté texely zbroje brát jako ocel a jas stáhnout k šedé.
- Vertex dirt (`paint.vertex_color_dirt`): medián ~0,06, ne 0,5. Pevný práh označí celý model za záhyb. Práh z percentilů (záhyb = nejnižší čtvrtina). A atribut `FLOAT_COLOR`, bajtový se čte přes sRGB.

**Vymodelované díly**
- **Díl položený přes původní funguje jen tam, kde ho původní zakryje ze všech stran.** Gladius přes původní meč zepředu seděl, ale z boku, zezadu a šikmo shora přes ruku byly vidět dva (operátor ve v7 při zvětšení). Polohu jsem měřil jen z přední strany, původní pochva byla o 2 cm silnější. Kontrolovat z boku, zezadu a shora, ne jen zepředu. U legionáře nakonec zůstal meč z generátoru (sám zdvojený není) a vymodelovaný byl vyřazen (v8).
- **Síť z generátoru je jeden souvislý kus** (po spojení švů UV: 1 komponenta, meč, dýka, štít i pilum srostlé s tělem). Původní díl nejde vyříznout. Po načtení glTF se síť jeví jako tisíce kousků, to jsou ostrůvky textury; `remove_doubles` je spojí.
- **Odstranit vyčnívající díl:** vyhlazení okna (300 iterací) stáhlo i okolní tuniku (posun 9 758 z 11 876 bodů). Zatlačení pod povrch zmačkalo texturu do viditelné skvrny. Funguje jen u malého dílu, který pak zakryje nový: dýka zatlačena radiálně k povrchu boku, **jen body blízko osy** (poloměr < 0,16): bez té podmínky zatlačení roztrhlo horní okraj štítu, který leží ve stejném úhlu. Kontrola výpočtem: nejbližší bod v nové síti pro každý bod štítu, posun 0,0 mm (`legionar_sonda_kusy.py`, `legionar_detail_render.py`).
- Osu dílu měř z profilu (řezy po výšce, okraj předmětu), ne z PCA malého vzorku: pochva vyšla nakloněná a 2,5 cm vedle, byly dva jílce.
- Díly pokládat přes původní tvar, nic nemazat: v síti nevzniknou díry. Pochvu o 1–3 mm před původní plochu, jinak prosvítají kousky původního kování.
- Puklice na prohnutém štítu: osa = **skutečná normála štítu** (průměr normál vrcholů v prstenci 5–7,5 cm kolem desky), ne PCA desky (lišila se o 12°, puklice byla nakřivo i po vyrovnání svislé složky). Střed = průmět vrcholu původního vyboulení. Žádný rovný kroužek kolem (na prohnutém štítu z jedné strany zapadá).
- Díl na boku (pugio) podél **změřeného povrchu po výškách**, ne na jednom poloměru: tunika dole 0,124, pas 0,098, opasek 0,115, zbroj 0,13. Na jednom poloměru se pochva dole zabořila, u pasu visela ve vzduchu a rukojeť zmizela uvnitř zbroje. Rukojeť ven před zbroj, k opasku poutka (`legionar_sonda_normaly.py`).
- Sdílený materiál upravovat jednou: smyčka přes díly ho ztlumila tolikrát, kolik dílů ho používá (mosaz 12×, zčernala).
- Ploché mosazné pásky odrážejí studiové světlo krémově: zkosit hrany, drsnost ≥ 0,45.

**Provoz**
- Lokální GLB mazat až po ověřeném nahrání: Engine během práce spadl a v5 zmizela (vyrobena znovu, render shodný na pixel).
- Engine může zastavit jiná session; před nahráním `netstat` na :8300.
- Placené volání jen se svolením a odhadem; po odeslání hned uložit `request_id` (`request.json`), výsledek jde vyzvednout bez druhé platby.

## Co zbývá u legionáře

Postava je jeden mesh se štítem a pilem, na pózy se nehodí (DECISIONS 2026-11-05). Základ pro kostru je `library/3d/rimsky-legionar-v-a-poze-zaklad-pro-kostru` v1. Podklad v A-póze bez zbraní vygeneroval lokální FLUX z `ref-front.png` v1, pohled zezadu a z boku vznikl ze stejné postavy s pohledem v1 jako druhou předlohou. Model z Hunyuan3D `Normal` stál USD 0,525. Podklady a `request.json` jsou v `v1/podklad/`. v2 má lesk kovu a kostru s 19 kostmi (bez prstů), měřítko 1,74 m s helmou, `kostra.blend` leží vedle. Kostru staví `legionar_kostra.py`, zkušební pózy `legionar_pozy.py`, klouby se odečítají z pravoúhlých pohledů s mřížkou (`legionar_orto_mrizka.py`). Zbývá: kosti prstů na úchop, skutečné pózy podle pramenů, díly (štít, pilum, gladius s pochvou, pugio) připnuté ke kostem. 

**Kostra, pasti:** automatické váhy (bone heat) na síti z generátoru počítej na uzavřené pomocné síti (voxel remesh 6 mm), na model je přenes podle nejbližší plochy. Asi 170 bodů zůstane bez váhy, v póze stojí na klidovém místě a od chodidel vedou trny: doplň jim váhu od sousedů. Tunika má dvojitou stěnu a uvnitř jsou namodelovaná stehna. Při váhách podle plochy stehno látku prorazí, proto mají body v pásu tuniky váhy jen podle polohy (pánev u opasku, stehno u lemu). Licence operátorova podkladu je neznámá, před publikací ověřit původ.

**Podklad v A-póze z FLUXu:** když zadání nechá zbraně na opasku, generátor ve 4 ze 6 variant místo pugia namaluje druhý dlouhý meč. Pohled z boku: varianty s rukou nataženou dopředu vyřadit, při A-póze ruka z boku visí podél těla. Výřez: rembg z Engine bez šedi pozadí (zbytek mezi nohama), klíč pozadí přidávat jen u okraje rembg (prsty). Klíč po řádcích na celé ploše nechal skvrny pozadí.


## Přidaný díl kontroluj ze všech stran, i zezadu

Pugio v10 vypadalo zepředu dobře, zezadu odstávalo od boku a rukojeť vedla do lokte (operátor u v11). Před umístěním změř profil těla v několika úhlech a výškách i s rukama (`r` do 0,24): ruka opřená o štít zabírá úhly, kde by díl jinak seděl. Vtlačení původního dílu omez barvou i polohou: kůže dál od osy je paže, ne díl, a vynech i její sousedy, jinak zůstane trn.


## Nechtěný díl z generátoru vyřízni a díru zacel vějířem

Vtlačení dílu do těla nechá zmuchlaný zbytek. Díl, který leží těsně u povrchu, podle vzdálenosti od osy nenajdeš. Pomůže mapa hloubky paprsků z kamery: zbytek, opasek, zbroj a paže mají každý jinou hloubku. Po smazání `holes_fill` a `triangle_fill` u zubatých okrajů selhávají (díra, nebo plochy přes celé tělo). Spolehlivý je vějíř: pro každou souvislou skupinu okrajových hran jeden nový vrchol ve středu (zasunutý pod povrch), trojúhelník na hranu, jedna UV pro celý vějíř a krátké vyhlazení okolí. Ověř 0 otevřených hran a prohlédni i `viewer.glb` (hlína ve Studiu).

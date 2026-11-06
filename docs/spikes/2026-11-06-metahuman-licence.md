# MetaHuman a Reallusion: smí být tělo legionáře vstupem do AI generátorů? (2026-11-06)

Analýza bez instalace, bez účtů, bez plateb. **Hlavní omezení: primární texty Epicu (`unrealengine.com/eula/mhc`, `/eula/content`, oznámení o změně, `metahuman.com/license`) vrací HTTP 403 nebo vyžadují přihlášení. Plné znění jsem tedy nečetl.** Vše o Epicu níže je ze sekundárních zdrojů (zpravodajství, fórum Epicu, citace ve vláknech) a je označeno. Citace jsou krátké a z druhé ruky, ne z originálu.

## Verdikt

| Otázka | Verdikt | Opora |
|---|---|---|
| MetaHuman smí mimo Unreal (Blender)? | **Spíš ano, neověřeno z originálu** | Od UE 5.6 platí na MetaHuman Unreal Engine EULA; digitalproduction (22. 7. 2026): licence „allows MetaHuman characters and animation in any engine or creative software“; zdarma do 1 M USD ročního příjmu |
| Render smí být vstupem do generativní AI (FLUX, Nano Banana, GPT Image, Kling)? | **Nejasné** | Zákaz se týkal *trénování a testování* AI, ne vstupu; 27. 10. 2026 Sweeney oznámil rušení omezení, znění a účinnost neznámé |
| Zákaz trénování AI? | **Ano platil, ruší se** | viz níže |
| Zákaz redistribuce 3D souborů? | **Ano, předpokládám** (typicky), neověřeno | Reallusion výslovně ano; Epic: „UE-Only Content“ dřív, dnes nepotvrzeno |
| Komerční publikace renderů (časopis, web)? | **Spíš ano** | Epic: renderované obrázky a video jsou vaše; do 1 M USD zdarma |
| Reallusion: render jako vstup do generátoru? | **Nejasné, spíš ano** | zakázáno je *trénování*; vstup není výslovně řešen |

**Doporučení:** MetaHuman nepoužívat jako jistotu, dokud Epic neodpoví (návrh dotazu dole). Je to nejlepší kandidát na kvalitu (ruce, pleť), ale u Daz je zákaz doslovný, u MetaHuman je jen nejasný a mění se. Pro AI vstup (img2img/ControlNet z renderu) je riziko nižší než u trénování, ale není vyloučené.

## 1. Epic: co o licenci víme

**Nalezené, s odkazem:**
- Od UE 5.6 platí pro MetaHuman Unreal Engine EULA; původní MetaHuman Creator EULA zůstává jen pro cloudový Creator na UE ≤ 5.5 ([stránka EULA MHC, čínská verze, přes vyhledávání](https://www.unrealengine.com/eula/mhc?lang=zh-CN)).
- „currently places MetaHuman under the standard Unreal Engine licence“, zdarma pod 1 M USD ročního příjmu; Character DNA (Poly Hammer) základní verze zdarma, GPLv3, Pro 79 USD ([digitalproduction, 22. 7. 2026](https://digitalproduction.com/2026/07/22/character-dna-goes-free/)). Článek **neřeší** generativní AI ani redistribuci a nejde o změnu licence, jen o doplněk.
- Dřívější zákaz v MetaHuman Creator EULA, citace z fóra: použít MetaHuman Technology „for the purpose of building or enhancing any database or training or testing any artificial intelligence, machine learning, deep learning, neural network“ ([fórum Epicu](https://forums.unrealengine.com/t/can-metahuman-be-used-for-ai-training-in-academic-purposes/2037347)). Je to *trénování a testování*, ne vstup obrázku.
- Komentář (ne Epic, makléř): „You can't use them to train or test any AI at all.“ ([fórum](https://forums.unrealengine.com/t/has-anyone-licensed-their-ue-projects-source-code-for-ai-training-notes-on-what-epics-licenses-allow/2845767)). UE EULA 6(e) zakazuje použít engine a obsah „to train generative AI“.
- **27. 10. 2026 Tim Sweeney:** Epic „works on removing this restriction“; týká se MetaHuman postav, animačních dat a výstupů; autoři na Fabu si mohou nechat tag NoAI. Neřekl kdy ani které paragrafy ([wnhub.io](https://wnhub.io/news/engines/item-52519)). Jiný výsledek vyhledávání tvrdí, že EULA byla změněna 29. 10. 2026 a MetaHuman Creator, Animator a Mesh to MetaHuman jsou pokryty; **originál Epicu jsem nenačetl (403)**, bráno jako neověřené.
- Fab NoAI obsah: zákaz jako „inputs“ do generativních programů ([vlákno](https://forums.unrealengine.com/t/noai-content-inputs-or-training-inputs/2838630)). Pozor: kdyby se na stažené postavy vztahoval Fab/Content EULA s „inputs“, byl by render jako vstup zakázán. Rozlišení „Technology“ vs. „stažená postava“ je jen názor jednoho uživatele fóra.

**Nenalezeno:** doslovná klauzule o použití mimo Unreal v aktuální EULA; doslovná klauzule o redistribuci stažených postav; text po změně z 27.–29. 10.

### Návrh dotazu na Epic (neposlán, pro operátora)

> Subject: MetaHuman characters rendered in Blender as image input to generative AI
>
> We make illustrations and video using a MetaHuman character (downloaded via MetaHuman for UE 5.6+, edited in Blender via Character DNA). We render the character in Blender (not Unreal) and use the render as a shape/pose reference input (img2img / ControlNet-style, no training, no fine-tuning) to third-party image and video generators (FLUX, Gemini image, GPT Image, Kling). Final images are published commercially (web, magazine). Annual revenue is below USD 1M.
> 1. Is rendering MetaHuman characters in Blender permitted under the current UE EULA?
> 2. Is using such a render as an input/reference to a generative AI model permitted, given the restriction (and its announced removal, Oct 2026) on MetaHuman use with AI? Which EULA section applies, and since which date?
> 3. Do downloaded MetaHuman characters fall under the Technology EULA, the Content EULA, or Fab EULA ("NoAI" / "inputs")?
> 4. May the 3D files (mesh, DNA, textures) be stored in a private repository and shared among our own team?

## 2. Postup MetaHuman → Blender (z dostupných zdrojů)

- Postavu vytvoří a stáhne MetaHuman Creator v Unreal Engine 5.6+ (účet Epic, instalace UE a MetaHuman pluginu). **Velikost instalace a čas nejsou ověřeny; počítat v desítkách GB a hodinách prvního nastavení.**
- Export: Epic MetaHuman Character Export Tool umí round-trip s DCC, volba DCC Export je nutná pro MetaHuman for Maya/Houdini ([doc](https://dev.epicgames.com/documentation/metahuman/metahuman-creator-export-tool-in-unreal-engine)).
- Blender: doplněk **Character DNA** (Poly Hammer) importuje a exportuje `.dna`, edituje obličejovou i tělesnou kostru včetně RBF korekcí; základ zdarma od 17. 7. 2026 ([CG Channel](https://www.cgchannel.com/tag/edit-metahuman-in-blender/)). **Character Control Rig** (Rigify meta-rig podle proporcí postavy, přenos animace do UE) je zvlášť placený, 79 USD jednorázově, od 5. 2026, vyžaduje Character DNA ([CG Channel](https://www.cgchannel.com/tag/character-dna/)). Podporované Blendery: 4.5, 5.1, 5.2.
- Prsty: žádný zdroj výslovně nepotvrdil prstovou kostru v Blenderu; tělo MetaHuman ji má, ale její dostupnost přes Character DNA je třeba vyzkoušet. **Neověřeno.**
- Odhad práce: nastavení UE + účet + stažení postavy ~půl dne; import do Blenderu a ověření kostry a pózy ~1 den; sladění s naším `heavy_lock`/Blender pipeline zvlášť. Cena: 0 USD (Character DNA základ), 79 USD volitelně Control Rig. Odhady jsou moje, ne ze zdroje.

## 3. Reallusion (Character Creator / ActorCore)

Zdroj: [EULA](https://www.reallusion.com/Content/EULA/EULA.htm) (shrnutí z načtení, citace přepisuji krátce):
- 2.1(C)(5): Standard License zakazuje použití „for machine learning, artificial intelligence (AI) training, fine-tuning, or model validation“; 2.2: takové použití vyžaduje Enterprise License.
- 2.1(A): výtvory v obrazovém a video formátu smíte prodávat a šířit.
- 2.1(B), 6.3: zákaz redistribuce obsahu a nabízení extrahovatelných assetů koncovým uživatelům.
- Render jako vstup do generátoru (bez trénování) text **výslovně neřeší**: verdikt nejasné, spíš ano. Rizikové je, když generátor s vaším vstupem sám dotrénuje (fine-tune/LoRA na renderech): to je zakázáno.

## Zdroje, které nešly číst
`unrealengine.com/eula/mhc`, `/eula/content`, `/ue-devs-can-now-choose-to-train-ai-models-on-their-projects`, `metahuman.com/en-US/license` (přihlášení), `dev.epicgames.com/.../metahuman-licensing` (prázdné). Doporučení: operátor si text otevře v prohlížeči po přihlášení k Epic účtu a ověří odstavce o AI a použití mimo Unreal, nebo pošle dotaz výše.

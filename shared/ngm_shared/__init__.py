"""ngm_shared — lehký sdílený kód projektů NGM, jeden zdroj místo kopií (GRAFIK/shared).

Moduly se importují jednotlivě, balíček sám nic nenačítá:
    from ngm_shared.grafik_client import generate      # jen stdlib
    from ngm_shared.heavy_lock import heavy            # zámek těžké práce pro celý stroj
"""

"""Série postav: zelené plátno a vlastní semínko, jinak by vyšel pokaždé stejný člověk."""
from ngm_shared import grafik_client as gc


def test_figures_each_get_their_own_seed_on_a_green_screen(monkeypatch):
    sent, waited = [], []
    monkeypatch.setattr(gc, "submit", lambda prompt, **kw: sent.append((prompt, kw)) or f"job{len(sent)}")
    monkeypatch.setattr(gc, "wait", lambda job, timeout=0: waited.append(job))
    ids = gc.figures(["A retiarius.", "A secutor."], common="A Roman gladiator. ", caller="test")
    assert ids == ["job1/0", "job2/0"] and waited == ["job1", "job2"]
    assert [kw["seed"] for _, kw in sent] == [101, 102] and sent[0][1]["size"] == "768x1152" and sent[1][1]["caller"] == "test"
    assert "chroma key green" in sent[0][0] and "A Roman gladiator. A retiarius." in sent[0][0]

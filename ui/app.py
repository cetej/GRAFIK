"""GRAFIK — Streamlit UI for layered image editing."""

from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import httpx
import streamlit as st

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "http://localhost:8100"
TIMEOUT = httpx.Timeout(120.0)


def _api(method: str, path: str, **kwargs) -> httpx.Response | None:
    """Call the GRAFIK API."""
    try:
        resp = httpx.request(method, f"{API_BASE}{path}", timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except httpx.ConnectError:
        st.error("Nelze se připojit k GRAFIK API. Spusť: `grafik serve --port 8100`")
        return None
    except httpx.HTTPStatusError as e:
        st.error(f"API chyba: {e.response.status_code} — {e.response.text}")
        return None


def main():
    st.set_page_config(page_title="GRAFIK", page_icon="🎨", layout="wide")
    st.title("GRAFIK — Editor vrstev")

    # Initialize session state
    if "project_id" not in st.session_state:
        st.session_state.project_id = None
    if "selected_layer" not in st.session_state:
        st.session_state.selected_layer = None

    # --- Sidebar ---
    with st.sidebar:
        st.header("Projekt")

        # Project picker
        resp = _api("GET", "/api/projects")
        projects = resp.json() if resp else []

        if projects:
            options = {p["id"]: f'{p["name"]} ({p["layer_count"]} vrstev)' for p in projects}
            selected = st.selectbox(
                "Vybrat projekt",
                options=list(options.keys()),
                format_func=lambda x: options[x],
                index=0 if not st.session_state.project_id else
                    list(options.keys()).index(st.session_state.project_id)
                    if st.session_state.project_id in options else 0,
            )
            if selected != st.session_state.project_id:
                st.session_state.project_id = selected
                st.session_state.selected_layer = None
                st.rerun()

        st.divider()

        # New project
        with st.expander("Nový projekt"):
            new_name = st.text_input("Název", value="untitled")
            if st.button("Vytvořit"):
                resp = _api("POST", "/api/projects", json={"name": new_name})
                if resp:
                    data = resp.json()
                    st.session_state.project_id = data["id"]
                    st.success(f"Vytvořen: {data['name']}")
                    st.rerun()

        st.divider()

        # Decompose
        if st.session_state.project_id:
            st.header("Dekompozice")
            image_url = st.text_input("URL obrázku")
            uploaded = st.file_uploader("Nebo nahrát soubor", type=["png", "jpg", "jpeg", "webp"])
            num_layers = st.slider("Počet vrstev", 1, 10, 4)

            if st.button("Rozložit na vrstvy", type="primary"):
                if uploaded:
                    # Upload via API
                    resp = _api(
                        "POST",
                        f"/api/projects/{st.session_state.project_id}/layers",
                        files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    )
                    if resp:
                        st.info("Soubor nahrán. Pro dekompozici použij URL.")
                elif image_url:
                    with st.spinner("Rozkládám obrázek na vrstvy..."):
                        resp = _api(
                            "POST",
                            f"/api/projects/{st.session_state.project_id}/decompose",
                            json={"image_url": image_url, "num_layers": num_layers},
                        )
                        if resp:
                            layers = resp.json()
                            st.success(f"Vytvořeno {len(layers)} vrstev!")
                            st.rerun()
                else:
                    st.warning("Zadej URL nebo nahraj soubor.")

            st.divider()

            # Export
            st.header("Export")
            if st.button("Stáhnout composite PNG"):
                resp = _api("POST", f"/api/projects/{st.session_state.project_id}/export/png")
                if resp:
                    st.download_button(
                        "💾 Uložit PNG",
                        data=resp.content,
                        file_name="composite.png",
                        mime="image/png",
                    )

    # --- Main area ---
    if not st.session_state.project_id:
        st.info("Vyber nebo vytvoř projekt v postranním panelu.")
        return

    # Load layers
    resp = _api("GET", f"/api/projects/{st.session_state.project_id}/layers")
    if not resp:
        return
    layers = resp.json()

    if not layers:
        st.info("Projekt nemá žádné vrstvy. Použij dekompozici v postranním panelu.")
        return

    # Three-column layout
    col_layers, col_canvas, col_inspector = st.columns([1, 2, 1])

    # --- Layer list ---
    with col_layers:
        st.subheader("Vrstvy")
        for layer in reversed(layers):  # Top to bottom
            lid = layer["id"]
            vis_icon = "👁" if layer["visible"] else "⬜"
            label = f'{vis_icon} {layer["name"]} (z={layer["z_order"]})'

            col_sel, col_vis = st.columns([4, 1])
            with col_sel:
                if st.button(label, key=f"sel_{lid}", use_container_width=True):
                    st.session_state.selected_layer = lid
                    st.rerun()
            with col_vis:
                if st.button("👁", key=f"vis_{lid}"):
                    _api("POST", f"/api/projects/{st.session_state.project_id}/layers/{lid}/visibility")
                    st.rerun()

    # --- Canvas ---
    with col_canvas:
        st.subheader("Náhled")
        resp = _api("GET", f"/api/projects/{st.session_state.project_id}/composite")
        if resp:
            st.image(resp.content, use_container_width=True)

        # Individual layer previews
        with st.expander("Náhledy jednotlivých vrstev"):
            cols = st.columns(min(len(layers), 4))
            for i, layer in enumerate(layers):
                with cols[i % len(cols)]:
                    resp_l = _api("GET", f"/api/projects/{st.session_state.project_id}/layers/{layer['id']}/png")
                    if resp_l:
                        st.image(resp_l.content, caption=layer["name"], use_container_width=True)

    # --- Inspector ---
    with col_inspector:
        st.subheader("Vlastnosti")
        sel = st.session_state.selected_layer
        if not sel:
            st.info("Vyber vrstvu kliknutím.")
            return

        layer = next((l for l in layers if l["id"] == sel), None)
        if not layer:
            st.warning("Vrstva nenalezena.")
            return

        st.markdown(f"**{layer['name']}** (`{layer['id']}`)")
        st.markdown(f"Rozměry: {layer.get('width', '?')}×{layer.get('height', '?')}")
        st.markdown(f"Pozice: ({layer['x']}, {layer['y']})")
        st.markdown(f"Zdroj: {layer['source']}")

        # Opacity slider
        new_opacity = st.slider(
            "Průhlednost",
            0.0, 1.0, float(layer["opacity"]),
            key=f"opacity_{sel}",
        )
        if new_opacity != layer["opacity"]:
            if st.button("Uložit průhlednost"):
                _api(
                    "POST",
                    f"/api/projects/{st.session_state.project_id}/layers/{sel}/opacity",
                    json={"opacity": new_opacity},
                )
                st.rerun()

        # Transform
        st.markdown("**Pozice**")
        new_x = st.number_input("X", value=layer["x"], key=f"x_{sel}")
        new_y = st.number_input("Y", value=layer["y"], key=f"y_{sel}")
        if st.button("Uložit pozici"):
            _api(
                "POST",
                f"/api/projects/{st.session_state.project_id}/layers/{sel}/transform",
                json={"x": int(new_x), "y": int(new_y)},
            )
            st.rerun()

        st.divider()

        # Delete
        if st.button("🗑️ Smazat vrstvu", type="secondary"):
            _api("DELETE", f"/api/projects/{st.session_state.project_id}/layers/{sel}")
            st.session_state.selected_layer = None
            st.rerun()


if __name__ == "__main__":
    main()

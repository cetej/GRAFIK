"""GRAFIK — Streamlit UI for layered image editing."""

from __future__ import annotations

import sys
from io import BytesIO

import httpx
import streamlit as st

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "http://localhost:8200"
TIMEOUT = httpx.Timeout(120.0)

# Checkerboard CSS for transparent layer backgrounds
CHECKER_CSS = """
<style>
.layer-card {
    background-color: #1e1e1e;
    border-radius: 8px;
    padding: 8px;
    margin-bottom: 8px;
    border: 2px solid transparent;
    transition: border-color 0.2s;
}
.layer-card.selected {
    border-color: #ff4b4b;
}
.layer-card:hover {
    border-color: #666;
}
.checker-bg {
    background-image:
        linear-gradient(45deg, #333 25%, transparent 25%),
        linear-gradient(-45deg, #333 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #333 75%),
        linear-gradient(-45deg, transparent 75%, #333 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
    border-radius: 4px;
    padding: 4px;
    display: flex;
    justify-content: center;
}
.composite-area {
    background-image:
        linear-gradient(45deg, #2a2a2a 25%, transparent 25%),
        linear-gradient(-45deg, #2a2a2a 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #2a2a2a 75%),
        linear-gradient(-45deg, transparent 75%, #2a2a2a 75%);
    background-size: 20px 20px;
    background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
    border-radius: 8px;
    padding: 8px;
    background-color: #1a1a1a;
}
div[data-testid="stHorizontalBlock"] {
    align-items: stretch;
}
section[data-testid="stSidebar"] {
    min-width: 320px;
}
</style>
"""


def _api(method: str, path: str, **kwargs) -> httpx.Response | None:
    try:
        resp = httpx.request(method, f"{API_BASE}{path}", timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except httpx.ConnectError:
        st.error("Nelze se pripojit k GRAFIK API. Spust: `grafik serve`")
        return None
    except httpx.HTTPStatusError as e:
        st.error(f"API chyba: {e.response.status_code} — {e.response.text}")
        return None


def main():
    st.set_page_config(page_title="GRAFIK", page_icon="layers", layout="wide")
    st.markdown(CHECKER_CSS, unsafe_allow_html=True)

    # Session state
    if "project_id" not in st.session_state:
        st.session_state.project_id = None
    if "selected_layer" not in st.session_state:
        st.session_state.selected_layer = None

    # ============================================================
    # SIDEBAR — project, decompose, workflows, export
    # ============================================================
    with st.sidebar:
        st.title("GRAFIK")

        # --- Project picker ---
        resp = _api("GET", "/api/projects")
        projects = resp.json() if resp else []

        if projects:
            options = {p["id"]: f'{p["name"]} ({p["layer_count"]} vrstev)' for p in projects}
            selected = st.selectbox(
                "Projekt",
                list(options.keys()),
                format_func=lambda x: options[x],
                index=0 if not st.session_state.project_id else
                    list(options.keys()).index(st.session_state.project_id)
                    if st.session_state.project_id in options else 0,
            )
            if selected != st.session_state.project_id:
                st.session_state.project_id = selected
                st.session_state.selected_layer = None
                st.rerun()

        # --- New project ---
        with st.expander("+ Novy projekt"):
            new_name = st.text_input("Nazev", value="untitled")
            c1, c2 = st.columns(2)
            new_w = c1.number_input("Sirka", value=1920, step=100)
            new_h = c2.number_input("Vyska", value=1080, step=100)
            if st.button("Vytvorit", use_container_width=True):
                resp = _api("POST", "/api/projects", json={
                    "name": new_name, "canvas_width": int(new_w), "canvas_height": int(new_h)
                })
                if resp:
                    st.session_state.project_id = resp.json()["id"]
                    st.rerun()

        if not st.session_state.project_id:
            st.info("Vyber nebo vytvor projekt.")
            return

        pid = st.session_state.project_id
        st.divider()

        # --- Decompose ---
        st.subheader("Dekompozice")
        image_url = st.text_input("URL obrazku")
        uploaded = st.file_uploader("Nebo nahrat soubor", type=["png", "jpg", "jpeg", "webp"])
        num_layers = st.slider("Pocet vrstev", 2, 10, 4)
        if st.button("Rozlozit na vrstvy", type="primary", use_container_width=True):
            if uploaded:
                _api("POST", f"/api/projects/{pid}/layers",
                     files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
                st.rerun()
            elif image_url:
                with st.spinner("Rozkladam obrazek..."):
                    resp = _api("POST", f"/api/projects/{pid}/decompose",
                                json={"image_url": image_url, "num_layers": num_layers})
                    if resp:
                        st.success(f"Vytvoreno {len(resp.json())} vrstev!")
                        st.rerun()
            else:
                st.warning("Zadej URL nebo nahraj soubor.")

        st.divider()

        # --- Undo / Redo ---
        hist_resp = _api("GET", f"/api/projects/{pid}/history")
        hist = hist_resp.json() if hist_resp else {"undo_count": 0, "redo_count": 0}
        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"Zpet ({hist['undo_count']})", use_container_width=True,
                         disabled=hist["undo_count"] == 0):
                _api("POST", f"/api/projects/{pid}/undo")
                st.rerun()
        with c2:
            if st.button(f"Vpred ({hist['redo_count']})", use_container_width=True,
                         disabled=hist["redo_count"] == 0):
                _api("POST", f"/api/projects/{pid}/redo")
                st.rerun()

        st.divider()

        # --- Export ---
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Export PNG", use_container_width=True):
                resp = _api("POST", f"/api/projects/{pid}/export/png")
                if resp:
                    st.download_button("Ulozit", data=resp.content,
                                       file_name="composite.png", mime="image/png")
        with c2:
            if st.button("Export vrstev", use_container_width=True):
                resp = _api("POST", f"/api/projects/{pid}/export/layers")
                if resp:
                    st.success(f"{len(resp.json().get('exported', []))} PNG")

        st.divider()

        # --- Workflow ---
        with st.expander("Workflow"):
            wf_type = st.selectbox("Typ", ["map_localization", "hero_edit"])
            wf_url = st.text_input("URL (workflow)", key="wf_url")
            wf_n = st.slider("Vrstvy", 2, 10, 4, key="wf_n")
            if st.button("Spustit", use_container_width=True):
                if wf_url:
                    with st.spinner(f"Workflow {wf_type}..."):
                        resp = _api("POST", f"/api/projects/{pid}/workflows/run",
                                    json={"workflow": wf_type, "image_url": wf_url, "num_layers": wf_n})
                        if resp:
                            for s in resp.json():
                                st.write(f"{'OK' if s['success'] else 'FAIL'}: {s['name']}")
                            st.rerun()

    # ============================================================
    # MAIN AREA
    # ============================================================
    pid = st.session_state.project_id
    if not pid:
        return

    resp = _api("GET", f"/api/projects/{pid}/layers")
    if not resp:
        return
    layers = resp.json()

    if not layers:
        st.info("Projekt nema zadne vrstvy. Pouzij dekompozici v postrannim panelu.")
        return

    # --- Top: Composite preview ---
    st.subheader("Kompozice")
    resp_comp = _api("GET", f"/api/projects/{pid}/composite")
    if resp_comp:
        st.image(resp_comp.content, use_container_width=True, caption="Vysledna kompozice vsech viditelnych vrstev")

    st.divider()

    # ============================================================
    # LAYER GRID — each layer as a card with thumbnail
    # ============================================================
    st.subheader(f"Vrstvy ({len(layers)})")

    # Load all layer thumbnails
    layer_images = {}
    for layer in layers:
        resp_l = _api("GET", f"/api/projects/{pid}/layers/{layer['id']}/png")
        if resp_l:
            layer_images[layer["id"]] = resp_l.content

    # Grid: 4 columns
    n_cols = min(len(layers), 4)
    cols = st.columns(n_cols)

    for i, layer in enumerate(layers):
        lid = layer["id"]
        is_selected = st.session_state.selected_layer == lid

        with cols[i % n_cols]:
            # Layer thumbnail
            if lid in layer_images:
                st.image(layer_images[lid], use_container_width=True)

            # Layer info
            vis_label = "VISIBLE" if layer["visible"] else "HIDDEN"
            blend = layer.get("blend_mode", "normal")
            opacity_pct = int(layer["opacity"] * 100)
            st.caption(
                f"**{layer['name']}** | z={layer['z_order']}\n\n"
                f"{vis_label} | {blend} | {opacity_pct}%\n\n"
                f"{layer.get('width', '?')} x {layer.get('height', '?')} px"
            )

            # Action buttons
            c1, c2 = st.columns(2)
            with c1:
                btn_type = "primary" if is_selected else "secondary"
                if st.button("Upravit", key=f"edit_{lid}", use_container_width=True, type=btn_type):
                    st.session_state.selected_layer = lid
                    st.rerun()
            with c2:
                vis_btn = "Skryt" if layer["visible"] else "Zobrazit"
                if st.button(vis_btn, key=f"vis_{lid}", use_container_width=True):
                    _api("POST", f"/api/projects/{pid}/layers/{lid}/visibility")
                    st.rerun()

    # ============================================================
    # INSPECTOR — edit selected layer
    # ============================================================
    sel = st.session_state.selected_layer
    if not sel:
        return

    layer = next((l for l in layers if l["id"] == sel), None)
    if not layer:
        return

    st.divider()
    st.subheader(f"Uprava: {layer['name']}")

    # Show selected layer preview + controls side by side
    col_preview, col_controls = st.columns([1, 2])

    with col_preview:
        if sel in layer_images:
            st.image(layer_images[sel], use_container_width=True, caption=f"{layer['name']} (nahled)")

    with col_controls:
        tab_basic, tab_recolor, tab_mask = st.tabs(["Zakladni", "Recolor", "Maska"])

        # --- Tab: Basic ---
        with tab_basic:
            c1, c2 = st.columns(2)
            with c1:
                new_opacity = st.slider("Pruhlednost", 0.0, 1.0, float(layer["opacity"]),
                                        key=f"op_{sel}")
                if new_opacity != layer["opacity"]:
                    if st.button("Ulozit pruhlednost", key=f"save_op_{sel}"):
                        _api("POST", f"/api/projects/{pid}/layers/{sel}/opacity",
                             json={"opacity": new_opacity})
                        st.rerun()

                blend_modes = ["normal", "multiply", "screen", "overlay", "soft_light"]
                cur_blend = layer.get("blend_mode", "normal")
                new_blend = st.selectbox("Blend mode", blend_modes,
                                         index=blend_modes.index(cur_blend) if cur_blend in blend_modes else 0,
                                         key=f"bl_{sel}")
                if new_blend != cur_blend:
                    if st.button("Ulozit blend", key=f"save_bl_{sel}"):
                        _api("POST", f"/api/projects/{pid}/layers/{sel}/blend_mode",
                             json={"blend_mode": new_blend})
                        st.rerun()

            with c2:
                new_x = st.number_input("X", value=layer["x"], key=f"x_{sel}")
                new_y = st.number_input("Y", value=layer["y"], key=f"y_{sel}")
                if st.button("Ulozit pozici", key=f"save_pos_{sel}"):
                    _api("POST", f"/api/projects/{pid}/layers/{sel}/transform",
                         json={"x": int(new_x), "y": int(new_y)})
                    st.rerun()

                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    if st.button("Flip H", key=f"fh_{sel}", use_container_width=True):
                        _api("POST", f"/api/projects/{pid}/layers/{sel}/flip",
                             json={"direction": "horizontal"})
                        st.rerun()
                with fc2:
                    if st.button("Flip V", key=f"fv_{sel}", use_container_width=True):
                        _api("POST", f"/api/projects/{pid}/layers/{sel}/flip",
                             json={"direction": "vertical"})
                        st.rerun()
                with fc3:
                    scale_val = st.number_input("Scale", value=1.0, step=0.1, min_value=0.1,
                                                max_value=5.0, key=f"sc_{sel}")
                    if scale_val != 1.0:
                        if st.button("Scale", key=f"do_sc_{sel}", use_container_width=True):
                            _api("POST", f"/api/projects/{pid}/layers/{sel}/scale",
                                 json={"factor": scale_val})
                            st.rerun()

        # --- Tab: Recolor ---
        with tab_recolor:
            hue = st.slider("Hue shift", -180.0, 180.0, 0.0, key=f"hue_{sel}")
            sat = st.slider("Saturation", 0.0, 2.0, 1.0, step=0.1, key=f"sat_{sel}")
            light = st.slider("Lightness", -0.5, 0.5, 0.0, step=0.05, key=f"lgt_{sel}")
            if hue != 0.0 or sat != 1.0 or light != 0.0:
                if st.button("Aplikovat recolor", key=f"do_rec_{sel}", use_container_width=True,
                             type="primary"):
                    _api("POST", f"/api/projects/{pid}/layers/{sel}/recolor",
                         json={"hue_shift": hue, "saturation_scale": sat, "lightness_shift": light})
                    st.rerun()

        # --- Tab: Mask ---
        with tab_mask:
            mask_op = st.selectbox("Operace", ["feather", "threshold", "set_opacity"],
                                   key=f"mop_{sel}")
            mask_params = {}
            if mask_op == "feather":
                mask_params["radius"] = st.slider("Radius", 1, 50, 5, key=f"mr_{sel}")
            elif mask_op == "threshold":
                mask_params["threshold"] = st.slider("Threshold", 0, 255, 128, key=f"mt_{sel}")
            elif mask_op == "set_opacity":
                mask_params["opacity"] = st.slider("Opacity", 0.0, 1.0, 1.0, key=f"mo_{sel}")
            if st.button("Aplikovat masku", key=f"do_mask_{sel}", use_container_width=True):
                _api("POST", f"/api/projects/{pid}/layers/{sel}/mask",
                     json={"operation": mask_op, **mask_params})
                st.rerun()

    # Delete at the bottom
    st.divider()
    if st.button("Smazat vrstvu", key=f"del_{sel}", type="secondary"):
        _api("DELETE", f"/api/projects/{pid}/layers/{sel}")
        st.session_state.selected_layer = None
        st.rerun()


if __name__ == "__main__":
    main()

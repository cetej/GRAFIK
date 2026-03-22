"""GRAFIK — layer decomposition UI."""

from __future__ import annotations

import sys
from io import BytesIO

import httpx
import streamlit as st

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "http://localhost:8300"
TIMEOUT = httpx.Timeout(180.0)


def _api(method: str, path: str, **kwargs) -> httpx.Response | None:
    try:
        resp = httpx.request(method, f"{API_BASE}{path}", timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except httpx.ConnectError:
        st.error("API nebezi. Spust: `python -m uvicorn grafik.api.app:app --port 8300`")
        return None
    except httpx.HTTPStatusError as e:
        st.error(f"Chyba: {e.response.text}")
        return None


def _ensure_project() -> str | None:
    """Get or create a working project. Returns project ID."""
    if "project_id" in st.session_state and st.session_state.project_id:
        return st.session_state.project_id
    # Auto-create
    resp = _api("POST", "/api/projects", json={"name": "grafik-session"})
    if resp:
        pid = resp.json()["id"]
        st.session_state.project_id = pid
        return pid
    return None


def main():
    st.set_page_config(page_title="GRAFIK", layout="wide", page_icon="layers")

    # Session state
    if "project_id" not in st.session_state:
        st.session_state.project_id = None
    if "selected_layer" not in st.session_state:
        st.session_state.selected_layer = None
    if "has_layers" not in st.session_state:
        st.session_state.has_layers = False

    # Check for existing project with layers
    if st.session_state.project_id:
        resp = _api("GET", f"/api/projects/{st.session_state.project_id}/layers")
        if resp and resp.json():
            st.session_state.has_layers = True

    # ============================================================
    # STEP 1: No layers yet — show upload/decompose UI
    # ============================================================
    if not st.session_state.has_layers:
        _show_upload_screen()
        return

    # ============================================================
    # STEP 2: Has layers — show results
    # ============================================================
    _show_layer_editor()


def _show_upload_screen():
    """Simple screen: upload image, pick layer count, decompose."""
    st.title("GRAFIK")
    st.markdown("Nahraj obrazek a rozloz ho na vrstvy.")

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded = st.file_uploader(
            "Vyber obrazek",
            type=["png", "jpg", "jpeg", "webp"],
            label_visibility="collapsed",
        )
        image_url = st.text_input("Nebo vloz URL obrazku", placeholder="https://...")

        if uploaded:
            st.image(uploaded, caption="Nahled", use_container_width=True)

    with col2:
        st.markdown("### Nastaveni")
        num_layers = st.slider("Pocet vrstev", 2, 10, 4)
        st.caption("Vice vrstev = jemnejsi rozklad, ale trvá dele a stoji vic.")

        decompose_clicked = st.button(
            "ROZLOZIT NA VRSTVY",
            type="primary",
            use_container_width=True,
            disabled=not (uploaded or image_url),
        )

    if decompose_clicked:
        pid = _ensure_project()
        if not pid:
            return

        with st.spinner("Rozkladam obrazek na vrstvy... (muze trvat 30-60s)"):
            if uploaded:
                # Upload file to project, then decompose via URL
                resp_upload = _api(
                    "POST", f"/api/projects/{pid}/layers",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                )
                if not resp_upload:
                    return
                # Need to upload to fal CDN for decompose
                # Use the decompose_file approach — upload via fal, then decompose
                resp_decompose = _api(
                    "POST", f"/api/projects/{pid}/decompose/file",
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)},
                    params={"num_layers": num_layers},
                )
                if resp_decompose:
                    st.session_state.has_layers = True
                    st.rerun()
                else:
                    st.error("Dekompozice selhala.")
            elif image_url:
                resp = _api(
                    "POST", f"/api/projects/{pid}/decompose",
                    json={"image_url": image_url, "num_layers": num_layers},
                )
                if resp:
                    st.session_state.has_layers = True
                    st.rerun()

    # Show existing projects to load
    st.divider()
    with st.expander("Nacist existujici projekt"):
        resp = _api("GET", "/api/projects")
        if resp:
            projects = resp.json()
            projects_with_layers = [p for p in projects if p["layer_count"] > 0]
            if projects_with_layers:
                for p in projects_with_layers:
                    if st.button(f'{p["name"]} ({p["layer_count"]} vrstev)', key=f'load_{p["id"]}',
                                 use_container_width=True):
                        st.session_state.project_id = p["id"]
                        st.session_state.has_layers = True
                        st.rerun()
            else:
                st.caption("Zadne projekty s vrstvami.")


def _show_layer_editor():
    """Main editor: composite + layer grid + inspector."""
    pid = st.session_state.project_id

    resp = _api("GET", f"/api/projects/{pid}/layers")
    if not resp:
        return
    layers = resp.json()
    if not layers:
        st.session_state.has_layers = False
        st.rerun()
        return

    # --- Top bar ---
    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.title("GRAFIK")
    with top_right:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            # Undo/redo
            hist_resp = _api("GET", f"/api/projects/{pid}/history")
            hist = hist_resp.json() if hist_resp else {"undo_count": 0, "redo_count": 0}
            if st.button(f"Zpet ({hist['undo_count']})", use_container_width=True,
                         disabled=hist["undo_count"] == 0):
                _api("POST", f"/api/projects/{pid}/undo")
                st.rerun()
        with col_b:
            if st.button(f"Vpred ({hist['redo_count']})", use_container_width=True,
                         disabled=hist["redo_count"] == 0):
                _api("POST", f"/api/projects/{pid}/redo")
                st.rerun()
        with col_c:
            if st.button("Novy", use_container_width=True):
                st.session_state.project_id = None
                st.session_state.has_layers = False
                st.session_state.selected_layer = None
                st.rerun()

    # --- Composite ---
    st.subheader("Vysledek (kompozice)")
    resp_comp = _api("GET", f"/api/projects/{pid}/composite")
    if resp_comp:
        # Export button next to composite
        col_img, col_export = st.columns([4, 1])
        with col_img:
            st.image(resp_comp.content, use_container_width=True)
        with col_export:
            resp_dl = _api("POST", f"/api/projects/{pid}/export/png")
            if resp_dl:
                st.download_button(
                    "Stahnout PNG", data=resp_dl.content,
                    file_name="composite.png", mime="image/png",
                    use_container_width=True,
                )
            if st.button("Export vrstev", use_container_width=True):
                resp_el = _api("POST", f"/api/projects/{pid}/export/layers")
                if resp_el:
                    st.success(f"{len(resp_el.json().get('exported', []))} PNG exportovano")

    st.divider()

    # --- Layer grid ---
    st.subheader(f"Vrstvy ({len(layers)})")
    st.caption("Kazda vrstva je cast obrazku s pruhlednosti. Klikni 'Upravit' pro editaci.")

    # Load thumbnails on checker bg
    layer_images = {}
    for layer in layers:
        resp_l = _api("GET", f"/api/projects/{pid}/layers/{layer['id']}/png?checker=true")
        if resp_l:
            layer_images[layer["id"]] = resp_l.content

    n_cols = min(len(layers), 4)
    cols = st.columns(n_cols)

    for i, layer in enumerate(layers):
        lid = layer["id"]
        is_selected = st.session_state.selected_layer == lid

        with cols[i % n_cols]:
            # Thumbnail
            if lid in layer_images:
                st.image(layer_images[lid], use_container_width=True)

            # Info
            vis = "Viditelna" if layer["visible"] else "Skryta"
            opacity_pct = int(layer["opacity"] * 100)
            alpha_info = f"{vis} | {opacity_pct}%"
            if layer.get("blend_mode", "normal") != "normal":
                alpha_info += f' | {layer["blend_mode"]}'

            st.caption(f'**{layer["name"]}**  \n{layer.get("width", "?")} x {layer.get("height", "?")} px  \n{alpha_info}')

            # Buttons
            c1, c2 = st.columns(2)
            with c1:
                btn_type = "primary" if is_selected else "secondary"
                if st.button("Upravit", key=f"edit_{lid}", use_container_width=True, type=btn_type):
                    st.session_state.selected_layer = lid if not is_selected else None
                    st.rerun()
            with c2:
                vis_label = "Skryt" if layer["visible"] else "Zobrazit"
                if st.button(vis_label, key=f"vis_{lid}", use_container_width=True):
                    _api("POST", f"/api/projects/{pid}/layers/{lid}/visibility")
                    st.rerun()

    # ============================================================
    # INSPECTOR — only if a layer is selected
    # ============================================================
    sel = st.session_state.selected_layer
    if not sel:
        return

    layer = next((l for l in layers if l["id"] == sel), None)
    if not layer:
        return

    st.divider()
    st.subheader(f"Uprava: {layer['name']}")

    col_preview, col_controls = st.columns([1, 2])

    with col_preview:
        if sel in layer_images:
            st.image(layer_images[sel], use_container_width=True)

    with col_controls:
        tab_basic, tab_recolor, tab_mask = st.tabs(["Zakladni", "Barvy", "Maska"])

        with tab_basic:
            c1, c2 = st.columns(2)
            with c1:
                new_opacity = st.slider("Pruhlednost", 0.0, 1.0, float(layer["opacity"]),
                                        key=f"op_{sel}")
                if abs(new_opacity - layer["opacity"]) > 0.01:
                    _api("POST", f"/api/projects/{pid}/layers/{sel}/opacity",
                         json={"opacity": new_opacity})
                    st.rerun()

                blend_modes = ["normal", "multiply", "screen", "overlay", "soft_light"]
                cur_blend = layer.get("blend_mode", "normal")
                new_blend = st.selectbox("Blend mode", blend_modes,
                                         index=blend_modes.index(cur_blend) if cur_blend in blend_modes else 0,
                                         key=f"bl_{sel}")
                if new_blend != cur_blend:
                    _api("POST", f"/api/projects/{pid}/layers/{sel}/blend_mode",
                         json={"blend_mode": new_blend})
                    st.rerun()

            with c2:
                new_x = st.number_input("X", value=layer["x"], key=f"x_{sel}")
                new_y = st.number_input("Y", value=layer["y"], key=f"y_{sel}")
                if int(new_x) != layer["x"] or int(new_y) != layer["y"]:
                    if st.button("Posunout", key=f"mv_{sel}"):
                        _api("POST", f"/api/projects/{pid}/layers/{sel}/transform",
                             json={"x": int(new_x), "y": int(new_y)})
                        st.rerun()

                fc1, fc2 = st.columns(2)
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

        with tab_recolor:
            hue = st.slider("Odstin (hue)", -180.0, 180.0, 0.0, key=f"hue_{sel}")
            sat = st.slider("Sytost", 0.0, 2.0, 1.0, step=0.1, key=f"sat_{sel}")
            light = st.slider("Svetlost", -0.5, 0.5, 0.0, step=0.05, key=f"lgt_{sel}")
            if hue != 0.0 or sat != 1.0 or light != 0.0:
                if st.button("Aplikovat", key=f"rec_{sel}", type="primary", use_container_width=True):
                    _api("POST", f"/api/projects/{pid}/layers/{sel}/recolor",
                         json={"hue_shift": hue, "saturation_scale": sat, "lightness_shift": light})
                    st.rerun()

        with tab_mask:
            mask_op = st.radio("Operace", ["Rozmazat okraje", "Ostry prah", "Zmenit pruhlednost"],
                               key=f"mop_{sel}", horizontal=True)
            mask_params = {}
            if mask_op == "Rozmazat okraje":
                mask_params = {"operation": "feather",
                               "radius": st.slider("Polomer", 1, 50, 5, key=f"mr_{sel}")}
            elif mask_op == "Ostry prah":
                mask_params = {"operation": "threshold",
                               "threshold": st.slider("Prah", 0, 255, 128, key=f"mt_{sel}")}
            else:
                mask_params = {"operation": "set_opacity",
                               "opacity": st.slider("Pruhlednost masky", 0.0, 1.0, 1.0, key=f"mo_{sel}")}
            if st.button("Aplikovat masku", key=f"mask_{sel}", use_container_width=True):
                _api("POST", f"/api/projects/{pid}/layers/{sel}/mask", json=mask_params)
                st.rerun()

    # Delete at the very bottom
    if st.button("Smazat tuto vrstvu", key=f"del_{sel}"):
        _api("DELETE", f"/api/projects/{pid}/layers/{sel}")
        st.session_state.selected_layer = None
        st.rerun()


if __name__ == "__main__":
    main()

"""
Solar Quotation Tool (POC)
--------------------------
A Streamlit app for solar/renewables sales consultants.

Flow:
1. Consultant enters a UK postcode -> address list (postcodes.io, free API)
2. Satellite map centred on the property, with a draw-a-box tool for
   tracing the usable south-facing roof area
3. Panel count + total wattage calculated from the traced area
4. Customer-facing quote: both purchase and rental options
5. Password-protected admin panel to edit panel specs, pricing, commission

Config (panel specs, pricing, admin password hash) lives in config.json
so it can be tweaked without touching code, and committed to the repo.
"""

import json
import hashlib
import math
from pathlib import Path

import requests
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw

CONFIG_PATH = Path(__file__).parent / "config.json"

st.set_page_config(page_title="Solar Quotation Tool", page_icon="\u2600\ufe0f", layout="wide")


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Postcode / address lookup (postcodes.io - free, no API key required)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def lookup_postcode(postcode: str):
    """Return (lat, lon, admin_district) for a UK postcode, or None if invalid."""
    postcode = postcode.strip().replace(" ", "")
    url = f"https://api.postcodes.io/postcodes/{postcode}"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code != 200:
            return None
        result = resp.json().get("result")
        if not result:
            return None
        return {
            "lat": result["latitude"],
            "lon": result["longitude"],
            "postcode": result["postcode"],
            "district": result.get("admin_district", ""),
        }
    except requests.RequestException:
        return None


# ---------------------------------------------------------------------------
# Geometry: area of a drawn polygon (rectangle) in square metres
# ---------------------------------------------------------------------------

def polygon_area_m2(coords) -> float:
    """
    Approximate the area (m^2) of a small lat/lon polygon using an
    equirectangular projection. Fine for building-scale shapes (~tens of
    metres across); not intended for large-scale surveying.
    coords: list of [lon, lat] pairs (GeoJSON order), first point may repeat last.
    """
    if len(coords) < 3:
        return 0.0

    # De-duplicate closing point if present
    pts = coords[:-1] if coords[0] == coords[-1] else coords[:]

    lat0 = sum(p[1] for p in pts) / len(pts)
    lat0_rad = math.radians(lat0)

    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(lat0_rad)

    xy = [(p[0] * m_per_deg_lon, p[1] * m_per_deg_lat) for p in pts]

    # Shoelace formula
    area = 0.0
    n = len(xy)
    for i in range(n):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


# ---------------------------------------------------------------------------
# Solar calculations
# ---------------------------------------------------------------------------

def calculate_solar(area_m2: float, cfg: dict) -> dict:
    panel = cfg["panel"]
    panel_area = panel["width_m"] * panel["height_m"]
    usable_area = area_m2 * panel.get("packing_efficiency", 0.85)
    num_panels = int(usable_area // panel_area) if panel_area > 0 else 0
    total_wattage_w = num_panels * panel["wattage_w"]
    return {
        "num_panels": num_panels,
        "total_wattage_w": total_wattage_w,
        "total_wattage_kw": round(total_wattage_w / 1000, 2),
        "roof_area_m2": round(area_m2, 1),
        "usable_area_m2": round(usable_area, 1),
    }


def calculate_quote(num_panels: int, cfg: dict) -> dict:
    pricing = cfg["pricing"]
    purchase_total = (
        num_panels * pricing["cost_per_panel_gbp"]
        + pricing["install_base_cost_gbp"]
        + num_panels * pricing["install_cost_per_panel_gbp"]
    )
    rental_monthly = num_panels * pricing["rental_monthly_per_panel_gbp"]
    rental_term_total = rental_monthly * pricing["term_months"]
    return {
        "purchase_total_gbp": round(purchase_total, 2),
        "rental_monthly_gbp": round(rental_monthly, 2),
        "rental_term_months": pricing["term_months"],
        "rental_term_total_gbp": round(rental_term_total, 2),
    }


# ---------------------------------------------------------------------------
# UI: sidebar (mode switch + admin unlock)
# ---------------------------------------------------------------------------

cfg = load_config()

st.sidebar.title(cfg["branding"]["company_name"])
mode = st.sidebar.radio("Mode", ["Quotation Tool", "Admin Panel"])

if "admin_unlocked" not in st.session_state:
    st.session_state.admin_unlocked = False


# ---------------------------------------------------------------------------
# Admin Panel
# ---------------------------------------------------------------------------

if mode == "Admin Panel":
    st.title("\U0001F512 Admin Panel")

    if not st.session_state.admin_unlocked:
        pw = st.text_input("Admin password", type="password")
        if st.button("Unlock"):
            if hash_password(pw) == cfg["admin_password_hash"]:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

    st.success("Admin unlocked.")
    if st.button("Lock admin panel"):
        st.session_state.admin_unlocked = False
        st.rerun()

    st.subheader("Panel Specification")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        panel_w = st.number_input("Panel width (m)", value=cfg["panel"]["width_m"], step=0.05, format="%.2f")
    with c2:
        panel_h = st.number_input("Panel height (m)", value=cfg["panel"]["height_m"], step=0.05, format="%.2f")
    with c3:
        panel_watts = st.number_input("Wattage per panel (W)", value=cfg["panel"]["wattage_w"], step=5)
    with c4:
        packing_eff = st.slider("Usable roof %", 0.5, 1.0, cfg["panel"].get("packing_efficiency", 0.85))

    st.subheader("Pricing & Commercials")
    p1, p2, p3 = st.columns(3)
    with p1:
        cost_per_panel = st.number_input("Cost per panel (£)", value=cfg["pricing"]["cost_per_panel_gbp"], step=10)
        install_base = st.number_input("Base install cost (£)", value=cfg["pricing"]["install_base_cost_gbp"], step=50)
    with p2:
        install_per_panel = st.number_input("Install cost per panel (£)", value=cfg["pricing"]["install_cost_per_panel_gbp"], step=5)
        rental_monthly_per_panel = st.number_input("Rental (£/panel/month)", value=cfg["pricing"]["rental_monthly_per_panel_gbp"], step=1)
    with p3:
        term_months = st.number_input("Rental term (months)", value=cfg["pricing"]["term_months"], step=6)
        commission = st.number_input("Consultant commission (£)", value=cfg["pricing"]["commission_gbp"], step=10)

    st.subheader("Change Admin Password")
    new_pw = st.text_input("New admin password (leave blank to keep current)", type="password")

    if st.button("Save Settings", type="primary"):
        cfg["panel"]["width_m"] = panel_w
        cfg["panel"]["height_m"] = panel_h
        cfg["panel"]["wattage_w"] = panel_watts
        cfg["panel"]["packing_efficiency"] = packing_eff
        cfg["pricing"]["cost_per_panel_gbp"] = cost_per_panel
        cfg["pricing"]["install_base_cost_gbp"] = install_base
        cfg["pricing"]["install_cost_per_panel_gbp"] = install_per_panel
        cfg["pricing"]["rental_monthly_per_panel_gbp"] = rental_monthly_per_panel
        cfg["pricing"]["term_months"] = term_months
        cfg["pricing"]["commission_gbp"] = commission
        if new_pw:
            cfg["admin_password_hash"] = hash_password(new_pw)
        save_config(cfg)
        st.success("Settings saved.")

    with st.expander("Current commission on this session's quote"):
        st.write(f"£{cfg['pricing']['commission_gbp']} per completed install (not shown to customer).")

    st.stop()


# ---------------------------------------------------------------------------
# Quotation Tool (customer/consultant-facing)
# ---------------------------------------------------------------------------

st.title("\u2600\ufe0f Solar Quotation Tool")
st.caption("Enter a postcode, trace the usable south-facing roof area on the map, and generate an instant quote.")

postcode_input = st.text_input("Property postcode", placeholder="e.g. ST1 3JD")

location = None
if postcode_input:
    location = lookup_postcode(postcode_input)
    if location is None:
        st.error("Postcode not found. Please check and try again.")

if location:
    st.write(f"**Location:** {location['postcode']} — {location['district']}")

    st.subheader("Trace the south-facing roof area")
    st.caption(
        "Use the rectangle tool (top-left of the map) to draw around the usable "
        "south-facing roof section, using the satellite image as a guide."
    )

    m = folium.Map(
        location=[location["lat"], location["lon"]],
        zoom_start=20,
        tiles=None,
    )
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        overlay=False,
        control=False,
        max_zoom=21,
    ).add_to(m)
    folium.Marker(
        [location["lat"], location["lon"]],
        tooltip=location["postcode"],
        icon=folium.Icon(color="red", icon="home"),
    ).add_to(m)

    Draw(
        export=False,
        draw_options={
            "polyline": False,
            "polygon": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
            "rectangle": True,
        },
        edit_options={"edit": True},
    ).add_to(m)

    map_data = st_folium(m, width=900, height=550, key="roof_map")

    roof_area = None
    if map_data and map_data.get("all_drawings"):
        drawings = map_data["all_drawings"]
        if drawings:
            last_shape = drawings[-1]
            coords = last_shape["geometry"]["coordinates"][0]
            roof_area = polygon_area_m2(coords)

    if roof_area:
        st.info(f"Traced roof area: **{roof_area:.1f} m²**")

        solar = calculate_solar(roof_area, cfg)
        quote = calculate_quote(solar["num_panels"], cfg)

        st.subheader("System Estimate")
        m1, m2, m3 = st.columns(3)
        m1.metric("Panels", solar["num_panels"])
        m2.metric("System size", f"{solar['total_wattage_kw']} kW")
        m3.metric("Usable roof area", f"{solar['usable_area_m2']} m²")

        if solar["num_panels"] == 0:
            st.warning("Traced area is too small to fit a panel — try drawing a larger box.")
        else:
            st.subheader("Your Quote")
            q1, q2 = st.columns(2)
            with q1:
                st.markdown("### Purchase")
                st.metric("One-off cost", f"£{quote['purchase_total_gbp']:,.2f}")
                st.caption("Includes hardware and installation.")
            with q2:
                st.markdown("### Rental")
                st.metric("Monthly rental", f"£{quote['rental_monthly_gbp']:,.2f}")
                st.caption(
                    f"Over a {quote['rental_term_months']}-month term "
                    f"(total £{quote['rental_term_total_gbp']:,.2f}). "
                    "No upfront cost."
                )
    else:
        st.warning("Draw a rectangle on the map over the roof to generate an estimate.")
else:
    st.info("Enter a postcode above to get started.")

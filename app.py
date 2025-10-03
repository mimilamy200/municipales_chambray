# app.py — Chambray-lès-Tours (37050) – Observatoire & Ciblage
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Chambray-lès-Tours – Outil Municipales", layout="wide")

# --- Chemins
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "outputs"
ASSETS = BASE / "assets"
OUT.mkdir(exist_ok=True, parents=True)

st.title("Chambray-lès-Tours (37050) – Observatoire & Ciblage")

# --- Logo optionnel
logo = ASSETS / "logo.png"
cols = st.columns([1, 3])
if logo.exists():
    cols[0].image(str(logo), use_container_width=True)
cols[1].caption("Données agrégées (IRIS/BV). Exports CSV/PDF. Carte SPT incluse.")

# --- Helper de chargement
def load_csv(name, cols=None):
    p = DATA / name
    if not p.exists():
        return pd.DataFrame(columns=cols or [])
    df = pd.read_csv(p)
    if cols:
        for c in cols:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[cols]
    return df

# --- Jeux de données (vides = OK)
df_rp = load_csv(
    "insee_rp_iris_37050.csv",
    [
        "code_iris",
        "pop",
        "age_median",
        "moins18",
        "plus65",
        "menages",
        "locataires",
        "proprietaires",
        "diplome_bacplus",
        "chomage",
        "pcs_ouvriers",
        "pcs_cadres",
    ],
)
df_filo = load_csv(
    "filosofi_iris_37050.csv",
    ["code_iris", "revenu_median", "part_bas_revenus", "part_haut_revenus"],
)
df_mobi = load_csv(
    "mobilites_iris_37050.csv",
    ["code_iris", "temps_travail_moy", "part_voiture", "part_tc", "part_velo", "part_marche"],
)
df_cross = load_csv("cross_bv_iris_37050.csv", ["code_bv", "code_iris", "proportion"])
df_bv = load_csv(
    "muni2020_bv_37050.csv",
    ["code_bv", "inscrits", "votants", "blancs", "nuls", "exprimes", "liste_A", "liste_B", "liste_C"],
)

# --- Base IRIS
base = pd.DataFrame(columns=["code_iris"])
if not df_rp.empty:
    base = pd.DataFrame({"code_iris": pd.unique(df_rp["code_iris"].dropna())})
for df in [df_filo, df_mobi, df_rp]:
    if not df.empty:
        base = base.merge(df, on="code_iris", how="outer") if not base.empty else df.copy()

# --- Participation 2020 (si cross + BV)
base["participation_2020"] = pd.NA
base["abstention_2020"] = pd.NA
if not df_cross.empty and not df_bv.empty:
    tmp = df_bv.merge(df_cross, on="code_bv", how="left")
    tmp["inscrits_w"] = tmp["inscrits"] * tmp["proportion"]
    tmp["votants_w"] = tmp["votants"] * tmp["proportion"]
    part = tmp.groupby("code_iris", as_index=False).agg(inscrits=("inscrits_w", "sum"), votants=("votants_w", "sum"))
    part["participation_2020"] = (100 * part["votants"] / part["inscrits"]).round(1)
    part["abstention_2020"] = (100 - part["participation_2020"]).round(1)
    base = base.merge(part[["code_iris", "participation_2020", "abstention_2020"]], on="code_iris", how="left")

# --- KPIs
def kpi_fmt(v, suffix=""):
    if pd.isna(v):
        return "—"
    try:
        if float(v).is_integer():
            return f"{int(v):,}{suffix}".replace(",", " ")
        return f"{float(v):.1f}{suffix}"
    except Exception:
        return f"{v}{suffix}"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Population (somme)", kpi_fmt(base["pop"].sum() if "pop" in base else pd.NA))
c2.metric("Âge médian (moy.)", kpi_fmt(base["age_median"].mean() if "age_median" in base else pd.NA, " ans"))
c3.metric("Revenu médian (méd.)", kpi_fmt(base["revenu_median"].median() if "revenu_median" in base else pd.NA, " €"))
c4.metric("Participation 2020 (moy.)", kpi_fmt(base["participation_2020"].mean() if "participation_2020" in base else pd.NA, " %"))

st.divider()
st.header("Ciblage IRIS – Score de Priorité Terrain (SPT)")

# Poids ajustables
w1 = st.slider("Poids abstention", 0.0, 3.0, 1.0, 0.1)
w2 = st.slider("Poids 18–24 (proxy via -18)", 0.0, 3.0, 1.0, 0.1)
w3 = st.slider("Poids locataires", 0.0, 3.0, 1.0, 0.1)
w4 = st.slider("Poids (100 - participation 2020)", 0.0, 3.0, 1.0, 0.1)

# S'assure que les colonnes existent
for c in ["abstention_2020", "moins18", "locataires", "participation_2020"]:
    if c not in base.columns:
        base[c] = pd.NA

# Coercition en numérique (évite dtype "object")
for c in ["abstention_2020", "moins18", "locataires", "participation_2020", "pop", "age_median", "revenu_median"]:
    if c in base.columns:
        base[c] = pd.to_numeric(base[c], errors="coerce")

# Valeurs par défaut si NaN
a = base["abstention_2020"].fillna(0.0)
u18 = base["moins18"].fillna(0.0)
loc = base["locataires"].fillna(0.0)
part = base["participation_2020"].fillna(50.0)

# Calcul SPT (force en float avant round)
base["SPT"] = (w1 * a + w2 * u18 + w3 * loc + w4 * (100.0 - part)).astype(float).round(2)

st.subheader("Top 10 IRIS (SPT)")
st.dataframe(
    base.fillna("")[["code_iris", "SPT", "abstention_2020", "moins18", "locataires", "participation_2020"]]
        .sort_values("SPT", ascending=False)
        .head(10)
)

# --- Exports
colA, colB = st.columns(2)
with colA:
    if st.button("Exporter shortlist (CSV)"):
        path = OUT / "shortlist_iris.csv"
        base.sort_values("SPT", ascending=False)[["code_iris", "SPT"]].head(10).to_csv(path, index=False)
        st.success(f"Exporté : {path}")

with colB:
    if st.button("Générer toutes les fiches (PDF)"):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
            from reportlab.lib.utils import ImageReader

            # Helper pour dessiner une ligne et renvoyer le nouveau y
            def line(canvas_obj, y_pos, txt):
                canvas_obj.drawString(2 * cm, y_pos, "• " + txt)
                return y_pos - 0.8 * cm

            count = 0
            for _, row in base.iterrows():
                code = row.get("code_iris") or "NA"
                pdf_path = OUT / f"fiche_{code}.pdf"
                c = canvas.Canvas(str(pdf_path), pagesize=A4)
                width, height = A4

                # Logo optionnel
                if logo.exists():
                    try:
                        c.drawImage(
                            ImageReader(str(logo)),
                            width - 6 * cm,
                            height - 3 * cm,
                            4.5 * cm,
                            1.5 * cm,
                            preserveAspectRatio=True,
                            mask="auto",
                        )
                    except Exception:
                        pass

                # En-tête
                c.setFont("Helvetica-Bold", 18)
                c.drawString(2 * cm, height - 2.5 * cm, f"Fiche IRIS – {code}")
                c.setFont("Helvetica", 11)
                c.drawString(2 * cm, height - 3.5 * cm, "Commune : Chambray-lès-Tours (37050)")

                # Corps
                y = height - 5 * cm
                y = line(c, y, f"Population (RP): {row.get('pop','—')} | Âge médian: {row.get('age_median','—')}")
                y = line(c, y, f"Revenu médian: {row.get('revenu_median','—')} € | Locataires: {row.get('locataires','—')}%")
                y = line(c, y, f"Participation 2020: {row.get('participation_2020','—')}% | Abstention: {row.get('abstention_2020','—')}%")
                y = line(c, y, f"Part -18 (proxy 18–24): {row.get('moins18','—')}% | SPT: {row.get('SPT','—')}")

                # Bloc messages
                y -= 0.4 * cm
                c.setFont("Helvetica-Bold", 12)
                c.drawString(2 * cm, y, "Messages suggérés :")
                y -= 0.8 * cm
                c.setFont("Helvetica", 11)
                for m in [
                    "Mobilités du quotidien (fréquences, sécurité piétons).",
                    "Pouvoir d’achat local (commerces, circuits courts).",
                    "Apaisement circulation résidentielle.",
                ]:
                    c.drawString(2 * cm, y, m)
                    y -= 0.7 * cm

                # Source
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(2 * cm, 1.8 * cm, "Sources: INSEE, Ministère de l’Intérieur, IGN, Data.gouv — préciser millésimes")

                # Finalisation PDF
                c.showPage()
                c.save()
                count += 1

            st.success(f"{count} fiche(s) générée(s) dans {OUT}")

        except Exception as e:
            st.error(f"PDF: {e}")

# --- Carte SPT par IRIS
st.divider()
st.subheader("Carte SPT par IRIS")

geo = None
for name in ["iris_37050.geojson", "iris_37050_demo.geojson"]:
    p = DATA / name
    if p.exists():
        geo = p
        break

if geo is None:
    st.info("Ajoutez un GeoJSON (iris_37050.geojson) dans data/ pour afficher la carte.")
else:
    try:
        import json, folium
        from streamlit_folium import st_folium

        gj = json.loads(geo.read_text(encoding="utf-8"))

        # Dictionnaire SPT par IRIS (robuste)
        spt = {}
        if not base.empty and "code_iris" in base.columns and "SPT" in base.columns:
            tmp = base[["code_iris", "SPT"]].copy().dropna(subset=["code_iris"])
            for _, r in tmp.iterrows():
                try:
                    key = str(r["code_iris"])
                    val = float(r["SPT"]) if pd.notna(r["SPT"]) else 0.0
                    spt[key] = val
                except Exception:
                    pass

        # Centre de carte
        def guess_center(gj_obj):
            try:
                feat = gj_obj["features"][0]["geometry"]
                if feat["type"] == "Point":
                    return feat["coordinates"][1], feat["coordinates"][0]
            except Exception:
                pass
            return 47.33, 0.74  # fallback Chambray approx.

        lat, lon = guess_center(gj)
        m = folium.Map(location=[lat, lon], zoom_start=12, tiles="cartodbpositron")

        def style_fn(f):
            cid = str(f["properties"].get("code_iris") or f["properties"].get("CODE_IRIS") or "")
            val = spt.get(cid, 0.0)
            vmax = max(spt.values()) if spt else 1.0
            ratio = (val / vmax) if vmax else 0.0

            # Dégradé HSV simple: vert (faible) → rouge (fort)
            import colorsys
            hue = max(0.0, 0.33 * (1 - ratio))
            r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
            return {
                "fillColor": f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}",
                "color": "#333",
                "weight": 1,
                "fillOpacity": 0.6,
            }

        folium.GeoJson(
            gj,
            style_function=style_fn,
            tooltip=folium.GeoJsonTooltip(fields=[], aliases=[]),
        ).add_to(m)

        st_folium(m, width=900, height=500)

    except Exception as e:
        st.warning(f"Carte indisponible: {e}")

st.caption("Données: INSEE, Ministère de l’Intérieur, IGN, Data.gouv — Agrégées au niveau IRIS/BV.")

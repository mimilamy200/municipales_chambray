import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Chambray-lès-Tours – Outil Municipales", layout="wide")

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "outputs"
ASSETS = BASE / "assets"
OUT.mkdir(exist_ok=True, parents=True)

st.title("Chambray-lès-Tours (37050) – Observatoire & Ciblage")

# Logo optionnel
logo = ASSETS / "logo.png"
cols = st.columns([1,3])
if logo.exists():
    cols[0].image(str(logo), use_column_width=True)
cols[1].caption("Données agrégées (IRIS/BV). Exports CSV/PDF. Carte SPT incluse.")

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

# Jeux de données
df_rp = load_csv("insee_rp_iris_37050.csv",
    ["code_iris","pop","age_median","moins18","plus65","menages","locataires","proprietaires","diplome_bacplus","chomage","pcs_ouvriers","pcs_cadres"])
df_filo = load_csv("filosofi_iris_37050.csv", ["code_iris","revenu_median","part_bas_revenus","part_haut_revenus"])
df_mobi = load_csv("mobilites_iris_37050.csv", ["code_iris","temps_travail_moy","part_voiture","part_tc","part_velo","part_marche"])
df_cross = load_csv("cross_bv_iris_37050.csv", ["code_bv","code_iris","proportion"])
df_bv = load_csv("muni2020_bv_37050.csv", ["code_bv","inscrits","votants","blancs","nuls","exprimes","liste_A","liste_B","liste_C"])

base = pd.DataFrame(columns=["code_iris"])
if not df_rp.empty:
    base = pd.DataFrame({'code_iris': pd.unique(df_rp['code_iris'].dropna())})
for df in [df_filo, df_mobi, df_rp]:
    if not df.empty:
        base = base.merge(df, on="code_iris", how="outer") if not base.empty else df.copy()

# Participation 2020
base["participation_2020"] = pd.NA
base["abstention_2020"] = pd.NA
if not df_cross.empty and not df_bv.empty:
    tmp = df_bv.merge(df_cross, on="code_bv", how="left")
    tmp["inscrits_w"] = tmp["inscrits"] * tmp["proportion"]
    tmp["votants_w"] = tmp["votants"] * tmp["proportion"]
    part = tmp.groupby("code_iris", as_index=False).agg(inscrits=("inscrits_w","sum"), votants=("votants_w","sum"))
    part["participation_2020"] = (100 * part["votants"] / part["inscrits"]).round(1)
    part["abstention_2020"] = (100 - part["participation_2020"]).round(1)
    base = base.merge(part[["code_iris","participation_2020","abstention_2020"]], on="code_iris", how="left")

def kpi_fmt(v, suffix=""):
    if pd.isna(v): return "—"
    try:
        if float(v).is_integer(): return f"{int(v):,}{suffix}".replace(",", " ")
        return f"{float(v):.1f}{suffix}"
    except Exception:
        return f"{v}{suffix}"

c1,c2,c3,c4 = st.columns(4)
c1.metric("Population (somme)", kpi_fmt(base["pop"].sum() if "pop" in base else pd.NA))
c2.metric("Âge médian (moy.)", kpi_fmt(base["age_median"].mean() if "age_median" in base else pd.NA, " ans"))
c3.metric("Revenu médian (méd.)", kpi_fmt(base["revenu_median"].median() if "revenu_median" in base else pd.NA, " €"))
c4.metric("Participation 2020 (moy.)", kpi_fmt(base["participation_2020"].mean() if "participation_2020" in base else pd.NA, " %"))

st.divider()
st.header("Ciblage IRIS – Score de Priorité Terrain (SPT)")
w1 = st.slider("Poids abstention", 0.0, 3.0, 1.0, 0.1)
w2 = st.slider("Poids 18–24 (proxy via -18)", 0.0, 3.0, 1.0, 0.1)
w3 = st.slider("Poids locataires", 0.0, 3.0, 1.0, 0.1)
w4 = st.slider("Poids (100 - participation 2020)", 0.0, 3.0, 1.0, 0.1)

for c in ["abstention_2020","moins18","locataires","participation_2020"]:
    if c not in base.columns: base[c] = 0

base["SPT"] = (
    w1 * base["abstention_2020"].fillna(0) +
    w2 * base["moins18"].fillna(0) +
    w3 * base["locataires"].fillna(0) +
    w4 * (100 - base["participation_2020"].fillna(50))
).round(2)

st.subheader("Top 10 IRIS (SPT)")
st.dataframe(base.fillna("")[["code_iris","SPT","abstention_2020","moins18","locataires","participation_2020"]]
             .sort_values("SPT", ascending=False).head(10))

colA,colB = st.columns(2)
with colA:
    if st.button("Exporter shortlist (CSV)"):
        path = OUT / "shortlist_iris.csv"
        base.sort_values("SPT", ascending=False)[["code_iris","SPT"]].head(10).to_csv(path, index=False)
        st.success(f"Exporté : {path}")

with colB:
    if st.button("Générer toutes les fiches (PDF)"):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
            from reportlab.lib.utils import ImageReader

            # Helper: dessine une ligne et renvoie le nouveau y
            def line(canvas_obj, y_pos, txt):
                canvas_obj.drawString(2*cm, y_pos, "• " + txt)
                return y_pos - 0.8*cm

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
                            width - 6*cm, height - 3*cm,
                            4.5*cm, 1.5*cm,
                            preserveAspectRatio=True, mask='auto'
                        )
                    except Exception:
                        pass

                # En-tête
                c.setFont("Helvetica-Bold", 18)
                c.drawString(2*cm, height - 2.5*cm, f"Fiche IRIS – {code}")
                c.setFont("Helvetica", 11)
                c.drawString(2*cm, height - 3.5*cm, "Commune : Chambray-lès-Tours (37050)")

                # Corps
                y = height - 5*cm
                y = line(c, y, f"Population (RP): {row.get('pop','—')} | Âge médian: {row.get('age_median','—')}")
                y = line(c, y, f"Revenu médian: {row.get('revenu_median','—')} € | Locataires: {row.get('locataires','—')}%")
                y = line(c, y, f"Participation 2020: {row.get('participation_2020','—')}% | Abstention: {row.get('abstention_2020','—')}%")
                y = line(c, y, f"Part -18 (proxy 18–24): {row.get('moins18','—')}% | SPT: {row.get('SPT','—')}")

                # Bloc messages
                y -= 0.4*cm
                c.setFont("Helvetica-Bold", 12)
                c.drawString(2*cm, y, "Messages suggérés :")
                y -= 0.8*cm
                c.setFont("Helvetica", 11)
                for m in [
                    "Mobilités du quotidien (fréquences, sécurité piétons).",
                    "Pouvoir d’achat local (commerces, circuits courts).",
                    "Apaisement circulation résidentielle."
                ]:
                    c.drawString(2*cm, y, m)
                    y -= 0.7*cm

                # Source
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(2*cm, 1.8*cm, "Sources: INSEE, Ministère de l’Intérieur, IGN, Data.gouv — préciser millésimes")

                # Finalisation PDF
                c.showPage()
                c.save()
                count += 1

            st.success(f"{count} fiche(s) générée(s) dans {OUT}")

        except Exception as e:
            st.error(f"PDF: {e}")

st.divider()
st.subheader("Carte SPT par IRIS")

geo = None
for name in ["iris_37050.geojson","iris_37050_demo.geojson"]:
    p = DATA / name
    if p.exists(): geo = p; break

if geo is None:
    st.info("Ajoutez un GeoJSON (iris_37050.geojson) dans data/ pour afficher la carte.")
else:
    try:
        import json, folium
        from streamlit_folium import st_folium
        gj = json.loads(geo.read_text(encoding="utf-8"))
        spt = {str(r["code_iris"]): float(r["SPT]()_]()

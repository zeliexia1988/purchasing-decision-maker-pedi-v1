import re
import pandas as pd
import streamlit as st

FICHIER = "prix_fonte.xlsx"


def _norm(c):
    """去掉表头里的换行和多余空格"""
    return re.sub(r"\s+", " ", str(c)).strip()


def _to_rate(x):
    """折扣率 -> 0~1 的小数；NC 或空值 -> None"""
    if pd.isna(x):
        return None
    try:
        v = float(str(x).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None  # 'NC' 等文字
    return v / 100 if v >= 1 else v


@st.cache_data
def load_fonte(path=FICHIER):
    df = pd.read_excel(path)
    df.columns = [_norm(c) for c in df.columns]

    def find(pred):
        return next((c for c in df.columns if pred(c.lower())), None)

    c_dn = find(lambda l: l == "dn")
    c_len = find(lambda l: l.startswith("long"))
    c_cl = find(lambda l: l.startswith("classe"))
    c_seul = find(lambda l: "seul" in l)
    c_vi = find(lambda l: "std vi" in l)
    c_std = find(lambda l: "std" in l and "std vi" not in l)
    fixed = [c_dn, c_len, c_cl, c_seul, c_std, c_vi]
    if None in fixed:
        raise ValueError(f"Colonnes introuvables dans {path}. Colonnes lues : {list(df.columns)}")

    regions = [c for c in df.columns if c not in fixed]

    df = df.dropna(subset=[c_dn]).copy()
    df["DN"] = pd.to_numeric(df[c_dn], errors="coerce")
    df = df.dropna(subset=["DN"])
    df["DN"] = df["DN"].astype(int)
    df["Classe"] = df[c_cl].astype(str).str.strip()
    df["Long"] = pd.to_numeric(df[c_len], errors="coerce")
    df["P_seul"] = pd.to_numeric(df[c_seul], errors="coerce")
    df["P_std"] = pd.to_numeric(df[c_std], errors="coerce")
    df["P_vi"] = pd.to_numeric(df[c_vi], errors="coerce")
    for r in regions:
        df[r] = df[r].apply(_to_rate)

    return df, regions


def render_fonte_pricing():
    st.title("🔩 Prix net Fonte ductile par région")

    try:
        df, regions = load_fonte()
    except FileNotFoundError:
        st.error(f"Fichier {FICHIER} introuvable. Placez-le dans le même dossier que l'application.")
        return
    except Exception as e:
        st.error(f"Erreur de lecture de {FICHIER} : {e}")
        return

    c1, c2, c3, c4 = st.columns(4)
    dn = c1.selectbox("DN", sorted(df["DN"].unique()))
    classes = sorted(df[df["DN"] == dn]["Classe"].unique())
    classe = c2.selectbox("Classe", classes)
    region = c3.selectbox("Région", regions)
    qty = c4.number_input("Quantité (ml) – optionnel", min_value=0, step=1)

    row = df[(df["DN"] == dn) & (df["Classe"] == classe)].iloc[0]
    rem = row[region]
    if rem is None or pd.isna(rem):
        st.error(f"NC – DN {dn} / {classe} non commercialisé à {region}")
        return

    long_u = row["Long"] if pd.notna(row["Long"]) else 6
    st.metric(f"Remise {region}", f"{rem * 100:.0f} %")

    produits = [("Tuyau seul", row["P_seul"]),
                ("Tuyau + joint STD", row["P_std"]),
                ("Tuyau + joint STD Vi", row["P_vi"])]
    rows = []
    for nom, cat in produits:
        net = cat * (1 - rem)
        r = {"Produit": nom,
             "Catalogue (€/m)": f"{cat:,.2f} €",
             "Net (€/m)": f"{net:,.2f} €",
             f"Net / tuyau {long_u:g} m": f"{net * long_u:,.2f} €"}
        if qty:
            r["Total HT"] = f"{net * qty:,.2f} €"
        rows.append(r)
    st.table(pd.DataFrame(rows))
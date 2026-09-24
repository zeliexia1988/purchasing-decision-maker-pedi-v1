import math
import re
import pandas as pd
import streamlit as st

FICHIER = "prix_fonte.xlsx"


def _norm(c):
    return re.sub(r"\s+", " ", str(c)).strip()


def _to_rate(x):
    if pd.isna(x):
        return None
    try:
        v = float(str(x).replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None
    return v / 100 if v >= 1 else v


def _is_pam(fournisseur):
    return "pam" in str(fournisseur).lower()

COLONNES_FIXES = {
    "Gamme": "Gamme",
    "DN": "DN",
    "Long": "Long. utile moyenne (m)",
    "Classe": "Classe tuyau",
    "P_seul": "Prix tuyau seul (€/m)",
    "P_std": "Prix avec joint STD (€/m)",
    "P_vi": "Prix avec joint STD Vi (€/m)",
    "Fournisseur": "Fournisseur",
    "Reference": "Référence fournisseur",
}
@st.cache_data
def load_fonte(path=FICHIER):
    df = pd.read_excel(path)
    df.columns = [_norm(c) for c in df.columns]

    manquantes = [nom for nom in COLONNES_FIXES.values() if nom not in df.columns]
    if manquantes:
        raise ValueError(f"Colonnes introuvables ({manquantes}) dans {path}. "
                          f"Colonnes lues : {list(df.columns)}")

    # 合并单元格（Gamme/DN/Classe/Long 只在区块第一行有值，下方为空）向下填充
    df[COLONNES_FIXES["Gamme"]] = df[COLONNES_FIXES["Gamme"]].ffill()
    df[COLONNES_FIXES["DN"]] = df[COLONNES_FIXES["DN"]].ffill()
    df[COLONNES_FIXES["Classe"]] = df[COLONNES_FIXES["Classe"]].ffill()
    df[COLONNES_FIXES["Long"]] = df[COLONNES_FIXES["Long"]].ffill()

    fixed_cols = list(COLONNES_FIXES.values())
    code_cols = [c for c in df.columns if "code" in c.lower()]
    fixed = fixed_cols + code_cols
    regions = [c for c in df.columns if c not in fixed]

    df = df.dropna(
        subset=[COLONNES_FIXES["Fournisseur"], COLONNES_FIXES["P_seul"],
                COLONNES_FIXES["P_std"], COLONNES_FIXES["P_vi"]],
        how="all",
    ).copy()

    df["DN"] = pd.to_numeric(df[COLONNES_FIXES["DN"]], errors="coerce")
    df = df.dropna(subset=["DN"])
    df["DN"] = df["DN"].astype(int)
    df["Gamme"] = df[COLONNES_FIXES["Gamme"]].astype(str).str.strip()
    df["Classe"] = df[COLONNES_FIXES["Classe"]].astype(str).str.strip()
    df["Long"] = pd.to_numeric(df[COLONNES_FIXES["Long"]], errors="coerce")
    df["P_seul"] = pd.to_numeric(df[COLONNES_FIXES["P_seul"]], errors="coerce")
    df["P_std"] = pd.to_numeric(df[COLONNES_FIXES["P_std"]], errors="coerce")
    df["P_vi"] = pd.to_numeric(df[COLONNES_FIXES["P_vi"]], errors="coerce")
    df["Fournisseur"] = df[COLONNES_FIXES["Fournisseur"]].astype(str).str.strip()
    df["Reference"] = df[COLONNES_FIXES["Reference"]].astype(str).str.strip()

    for r in regions:
        df[r] = df[r].apply(_to_rate)

    return df, regions
def render_fonte_pricing():
    st.title("Tuyaux Fonte Prix maximum conseillé")

    try:
        df, regions = load_fonte()
    except FileNotFoundError:
        st.error(f"Fichier {FICHIER} introuvable. Placez-le dans le même dossier que l'application.")
        return
    except Exception as e:
        st.error(f"Erreur de lecture de {FICHIER} : {e}")
        return

    c0, c1, c2, c3, c4 = st.columns(5)

    gammes = sorted(df["Gamme"].dropna().unique())
    gamme = c0.selectbox("Gamme", gammes, index=None, placeholder="Choisir...")

    # DN 的可选项跟随 Gamme 收窄；Gamme 未选时展示全部 DN
    df_g = df[df["Gamme"] == gamme] if gamme is not None else df
    dn = c1.selectbox("DN", sorted(df_g["DN"].unique()), index=None, placeholder="Choisir...")

    # Classe 的可选项跟随 Gamme + DN 收窄
    df_dn = df_g[df_g["DN"] == dn] if dn is not None else df_g
    classe = c2.selectbox("Classe", sorted(df_dn["Classe"].unique()), index=None, placeholder="Choisir...")

    region = c3.selectbox("Région", regions, index=None, placeholder="Choisir...")
    qty = c4.number_input("Quantité (ml)", min_value=0, step=1, value=0)

    if None in (gamme, dn, classe, region):
        st.info("Sélectionnez toutes les options ci-dessus pour afficher les résultats.")
        return

    rows = df_dn[df_dn["Classe"] == classe]
    if rows.empty:
        st.warning("Aucune donnée pour cette combinaison.")
        return

    produits = [("Tuyau seul", "P_seul"), ("Tuyau + joint STD", "P_std"), ("Tuyau + joint STD Vi", "P_vi")]

    unit_rows = []
    total_rows = []
    nc_flag = False

    for _, row in rows.iterrows():
        fournisseur = row["Fournisseur"]
        is_pam = _is_pam(fournisseur)
        long_u = row["Long"] if pd.notna(row["Long"]) else 6
        nb_tuyaux = math.ceil(qty / long_u) if qty and long_u else 0

        rem_region = row[region] if is_pam else None
        rem_values = [row[r] for r in regions if row[r] is not None] if is_pam else []
        rem_max = max(rem_values) if rem_values else None
        rem_min = min(rem_values) if rem_values else None

        if is_pam and rem_region is None:
            nc_flag = True

        for nom, col in produits:
            cat = row[col]
            if pd.isna(cat):
                continue

            if is_pam:
                net = cat * (1 - rem_region) if rem_region is not None else None
                mini = cat * (1 - rem_max) if rem_max is not None else None
                maxi = cat * (1 - rem_min) if rem_min is not None else None
            else:
                net = mini = maxi = cat

            def fmt_unit(v):
                return f"{v:,.2f} €/m" if v is not None else "NC"

            unit_rows.append({
                "Fournisseur": f"{fournisseur} ({long_u:g} m/tuyau)",
                "Produit": nom,
                "Référence Fournisseur": row["Reference"],
                f"Prix net {region}": fmt_unit(net),
                "Prix mini PAM": fmt_unit(mini) if is_pam else "—",
                "Prix maxi PAM": fmt_unit(maxi) if is_pam else "—",
            })

            def fmt_total(v):
                if v is None:
                    return "NC"
                if not nb_tuyaux:
                    return "—"
                return f"{v * long_u * nb_tuyaux:,.2f} €"

            total_rows.append({
                "Fournisseur": f"{fournisseur} ({long_u:g} m/tuyau)",
                "Produit": nom,
                "Référence Fournisseur": row["Reference"],
                f"Prix net {region}": fmt_total(net),
                "Prix mini PAM": fmt_total(mini) if is_pam else "—",
                "Prix maxi PAM": fmt_total(maxi) if is_pam else "—",
            })

    if nc_flag:
        st.warning(f"⚠️ PAM : NC pour {region} sur au moins une référence de cette sélection.")

    st.write("### Prix unitaires (€/m)")
    st.dataframe(pd.DataFrame(unit_rows), hide_index=True, use_container_width=True)

    st.write("### Prix totaux")
    if qty:
        st.caption(f"Pour {qty} ml demandés — nombre de tuyaux et ml facturés calculés selon la longueur propre à chaque fournisseur.")
        st.dataframe(pd.DataFrame(total_rows), hide_index=True, use_container_width=True)
    else:
        st.info("Saisissez une quantité (ml) pour afficher les prix totaux.")

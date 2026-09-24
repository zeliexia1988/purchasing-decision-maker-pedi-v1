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


@st.cache_data
def load_fonte(path=FICHIER):
    df = pd.read_excel(path)
    df.columns = [_norm(c) for c in df.columns]

    def find(pred):
        return next((c for c in df.columns if pred(c.lower())), None)

    c_gamme = find(lambda l: l == "gamme")
    c_dn = find(lambda l: l == "dn")
    c_len = find(lambda l: l.startswith("long"))
    c_cl = find(lambda l: l.startswith("classe"))
    c_seul = find(lambda l: "seul" in l)
    c_vi = find(lambda l: "std vi" in l)
    c_std = find(lambda l: "std" in l and "std vi" not in l and "code" not in l)
    c_frn = find(lambda l: "fournisseur" in l)

    required = {"DN": c_dn, "Long. utile": c_len, "Classe": c_cl,
                "Prix seul": c_seul, "Prix STD": c_std, "Prix STD Vi": c_vi,
                "Fournisseur": c_frn}
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise ValueError(f"Colonnes introuvables ({missing}) dans {path}. "
                          f"Colonnes lues : {list(df.columns)}")

    # 合并单元格（Gamme/DN/Classe/Long 只在区块第一行有值，下方为空）向下填充
    if c_gamme:
        df[c_gamme] = df[c_gamme].ffill()
    df[c_dn] = df[c_dn].ffill()
    df[c_cl] = df[c_cl].ffill()
    df[c_len] = df[c_len].ffill()

    code_cols = [c for c in df.columns if "code" in c.lower()]
    fixed = [c for c in [c_gamme, c_dn, c_len, c_cl, c_seul, c_std, c_vi, c_frn] if c] + code_cols
    regions = [c for c in df.columns if c not in fixed]

    # 只有价格三列全空、且供应商也空的行才算真正的空行，才丢弃
    df = df.dropna(subset=[c_frn, c_seul, c_std, c_vi], how="all").copy()

    df["DN"] = pd.to_numeric(df[c_dn], errors="coerce")
    df = df.dropna(subset=["DN"])
    df["DN"] = df["DN"].astype(int)
    df["Gamme"] = df[c_gamme].astype(str).str.strip() if c_gamme else "AEP"
    df["Classe"] = df[c_cl].astype(str).str.strip()
    df["Long"] = pd.to_numeric(df[c_len], errors="coerce")
    df["P_seul"] = pd.to_numeric(df[c_seul], errors="coerce")
    df["P_std"] = pd.to_numeric(df[c_std], errors="coerce")
    df["P_vi"] = pd.to_numeric(df[c_vi], errors="coerce")
    df["Fournisseur"] = df[c_frn].astype(str).str.strip()
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
    if gamme is None:
        st.info("Sélectionnez une Gamme pour commencer.")
        return
    df_g = df[df["Gamme"] == gamme]

    if df_g.empty:
        st.warning(f"Aucune ligne trouvée pour la gamme {gamme}.")
        return

    dn = c1.selectbox("DN", sorted(df_g["DN"].unique()), index=None, placeholder="Choisir...")
    if dn is None:
        return
    df_dn = df_g[df_g["DN"] == dn]

    classes = sorted(df_dn["Classe"].unique())
    classe = c2.selectbox("Classe", classes, index=None, placeholder="Choisir...")
    if classe is None:
        return

    region = c3.selectbox("Région", regions, index=None, placeholder="Choisir...")
    if region is None:
        return

    qty = c4.number_input("Quantité (ml)", min_value=0, step=1, value=100)

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
        rem_max = max(rem_values) if rem_values else None   # remise max -> prix mini
        rem_min = min(rem_values) if rem_values else None   # remise min -> prix maxi

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
                net = mini = maxi = cat  # 非 PAM 不打折

            def fmt_unit(v):
                return f"{v:,.2f} €/m" if v is not None else "NC"

            unit_rows.append({
                "Fournisseur": f"{fournisseur} ({long_u:g} m/tuyau)",
                "Produit": nom,
                f"Prix net {region}": fmt_unit(net),
                "Prix net mini PAM": fmt_unit(mini) if is_pam else "—",
                "Prix net maxi PAM": fmt_unit(maxi) if is_pam else "—",
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
                f"Prix net Totaux {region}": fmt_total(net),
                "Prix net Totaux mini PAM": fmt_total(mini) if is_pam else "—",
                "Prix net Totaux maxi PAM": fmt_total(maxi) if is_pam else "—",
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

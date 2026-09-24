import re
import pandas as pd
import streamlit as st

FICHIER = "prix_vanne.xlsx"

COLONNES = ["Gamme", "Type de Produit", "Installation", "Système de Fermeture",
            "Sens d'ouverture/fermeture", "DN", "PN"]


def _norm(c):
    return re.sub(r"\s+", " ", str(c)).strip()


def _sort_key(val):
    """DN : trie numériquement si possible ('60' avant '125'),
    sinon (ex. 'PN10/16') trie par texte, placé après les valeurs numériques."""
    s = str(val).strip()
    try:
        return (0, float(s.replace(",", ".")))
    except ValueError:
        return (1, s)


@st.cache_data
def load_vanne(path=FICHIER):
    df = pd.read_excel(path)
    df.columns = [_norm(c) for c in df.columns]

    manquantes = [c for c in COLONNES + ["Fournisseur", "Prix unitaire", "Référence fournisseur", "Franco"]
                  if c not in df.columns]
    if manquantes:
        raise ValueError(f"Colonnes introuvables ({manquantes}) dans {path}. "
                          f"Colonnes lues : {list(df.columns)}")

    for c in ["DN", "PN"]:
        df[c] = df[c].apply(lambda x: str(x).strip() if pd.notna(x) else None)

    df["Prix unitaire"] = pd.to_numeric(df["Prix unitaire"], errors="coerce")
    df["Franco"] = pd.to_numeric(df["Franco"], errors="coerce")

    df = df.dropna(subset=["Fournisseur", "Prix unitaire"], how="all")
    return df

def render_vanne_pricing():
    st.title("Vannes Prix maximum conseillé")

    try:
        df = load_vanne()
    except FileNotFoundError:
        st.error(f"Fichier {FICHIER} introuvable. Placez-le dans le même dossier que l'application.")
        return
    except Exception as e:
        st.error(f"Erreur de lecture de {FICHIER} : {e}")
        return

    col_gauche, col_droite = st.columns([1.5, 4])

    with col_gauche:
        subset = df.copy()
        tout_selectionne = True

        for col in COLONNES:
            options = sorted(subset[col].dropna().unique(), key=_sort_key)
            if not options:
                continue

            val = st.selectbox(col, options, index=None, placeholder="Choisir...", key=f"vanne_{col}")

            if val is None:
                tout_selectionne = False
            else:
                subset = subset[(subset[col] == val) | (subset[col].isna())]

        qty = st.number_input("Quantité (unités)", min_value=0, step=1, value=1)

    with col_droite:
        
        if not tout_selectionne:
            st.info("Sélectionnez toutes les options ci-contre pour afficher les résultats.")
        elif subset.empty:
            st.warning("Aucun résultat pour cette combinaison de critères.")
        else:
            resultat = subset[["Fournisseur", "Référence fournisseur", "Prix unitaire", "Franco"]].copy()

            if qty:
                resultat["Prix total (€)"] = resultat["Prix unitaire"] * qty

                def _statut_franco(row):
                    if pd.isna(row["Franco"]):
                        return "—"
                    if row["Prix total (€)"] >= row["Franco"]:
                        return "✅ Franco atteint"
                    manque = row["Franco"] - row["Prix total (€)"]
                    return f"⚠️ Reste {manque:,.2f} € pour atteindre le Franco ({row['Franco']:,.0f} €)"

                resultat["Statut Franco"] = resultat.apply(_statut_franco, axis=1)
                resultat["Prix total (€)"] = resultat["Prix total (€)"].map(lambda v: f"{v:,.2f} €")

            resultat["Prix unitaire"] = resultat["Prix unitaire"].map(lambda v: f"{v:,.2f} €")
            resultat = resultat.drop(columns=["Franco"])

            st.write(f"**{len(resultat)} référence(s) correspondante(s)**")
            st.dataframe(
                resultat,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Fournisseur": st.column_config.TextColumn("Fournisseur", width="medium"),
                },
            )

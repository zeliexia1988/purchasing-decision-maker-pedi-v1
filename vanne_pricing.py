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

    manquantes = [c for c in COLONNES + ["Fournisseur", "Prix unitaire"] if c not in df.columns]
    if manquantes:
        raise ValueError(f"Colonnes introuvables ({manquantes}) dans {path}. "
                          f"Colonnes lues : {list(df.columns)}")

    # DN / PN peuvent contenir du texte (ex. "PN10/16") -> on garde en texte, pas de conversion numérique
    for c in ["DN", "PN"]:
        df[c] = df[c].apply(lambda x: str(x).strip() if pd.notna(x) else None)

    df["Prix unitaire"] = pd.to_numeric(df["Prix unitaire"], errors="coerce")

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

    subset = df.copy()
    tout_selectionne = True

    for col in COLONNES:
        options = sorted(subset[col].dropna().unique(), key=_sort_key)
        if not options:
            # Cette colonne n'a aucune valeur dans le périmètre actuel -> pas de contrainte, on saute
            continue

        val = st.selectbox(col, options, index=None, placeholder="Choisir...", key=f"vanne_{col}")

        if val is None:
            tout_selectionne = False
        else:
            subset = subset[(subset[col] == val) | (subset[col].isna())]

    st.divider()

    if not tout_selectionne:
        st.info("Sélectionnez toutes les options ci-dessus pour afficher les résultats.")
        return

    if subset.empty:
        st.warning("Aucun résultat pour cette combinaison de critères.")
        return

    qty = st.number_input("Quantité (unités)", min_value=0, step=1, value=1)

    resultat = subset[["Fournisseur", "Prix unitaire"]].copy()
            
    
    if qty:
        resultat["Prix total"] = resultat["Prix unitaire"] * qty
        resultat["Prix total"] = resultat["Prix total"].map(lambda v: f"{v:,.2f} €")
    resultat["Prix unitaire"] = resultat["Prix unitaire"].map(lambda v: f"{v:,.2f} €")

    st.write(f"### Résultats ({len(resultat)} référence(s) correspondante(s))")
    st.dataframe(resultat, hide_index=True, use_container_width=True)

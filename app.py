
import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="REInbox CSV Cleaner", page_icon="🧹", layout="wide")
st.title("REInbox CSV Cleaner 🧹 (DealMachine - multi-contact aware)")

# Liberal but solid email regex
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)

def robust_read_csv(file_bytes: bytes) -> pd.DataFrame | None:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
        except Exception:
            continue
    return None

def strip_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for c in work.select_dtypes(include=["object"]).columns:
        work[c] = work[c].astype(str).str.strip()
    return work

def looks_valid_email(e: str) -> bool:
    if not isinstance(e, str): return False
    e = e.strip().lower()
    if not EMAIL_RE.fullmatch(e): return False
    if e.startswith(".") or e.endswith("."): return False
    if ".." in e: return False
    local, _, domain = e.partition("@")
    if not local or not domain: return False
    if local.startswith((".", "-")) or local.endswith((".", "-")): return False
    if domain.startswith((".", "-")) or domain.endswith((".", "-")): return False
    labels = domain.split(".")
    if "." not in domain or any(len(lbl) == 0 for lbl in labels): return False
    if any(lbl.startswith("-") or lbl.endswith("-")) for lbl in labels: return False
    if len(labels[-1]) < 2: return False
    return True

def detect_contact_indices(columns: list[str]) -> list[int]:
    idxs = set()
    for c in columns:
        m = re.match(r"contact_(\d+)_email$", str(c), re.I)
        if m:
            idxs.add(int(m.group(1)))
    # also allow flags-only contacts (rare, but safe)
    for c in columns:
        m = re.match(r"contact_(\d+)_flags$", str(c), re.I)
        if m:
            idxs.add(int(m.group(1)))
    return sorted(idxs)

def explode_by_contacts(df: pd.DataFrame, contact_idxs: list[int]) -> pd.DataFrame:
    """
    For each row, emit one row per contact index with Email + Flags.
    Keeps original columns, adds 'Email' and 'Flags' from matching contact_{i}_*.
    Drops rows where both Email and Flags are blank unless caller chooses otherwise.
    """
    if not contact_idxs:
        return df.copy()

    out_rows = []
    for _, row in df.iterrows():
        emitted = False
        for i in contact_idxs:
            email_col = f"contact_{i}_email"
            flags_col = f"contact_{i}_flags"
            email = row.get(email_col, pd.NA)
            flags = row.get(flags_col, pd.NA)

            email_list = []
            if pd.notna(email):
                # Extract any/all emails present in that cell (handles "Name <a@b.com>, other@c.com")
                found = EMAIL_RE.findall(str(email))
                email_list = list(dict.fromkeys([e.lower() for e in found]))

            if not email_list:
                # still emit a row so we can optionally drop later
                new_row = row.copy()
                new_row["Email"] = pd.NA
                new_row["Flags"] = (str(flags).strip().lower() if pd.notna(flags) else pd.NA)
                out_rows.append(new_row)
                emitted = True
            else:
                for e in email_list:
                    new_row = row.copy()
                    new_row["Email"] = e
                    new_row["Flags"] = (str(flags).strip().lower() if pd.notna(flags) else pd.NA)
                    out_rows.append(new_row)
                    emitted = True

        if not emitted:
            # No contact slots -> keep original with empty Email/Flags
            new_row = row.copy()
            new_row["Email"] = pd.NA
            new_row["Flags"] = pd.NA
            out_rows.append(new_row)

    exploded = pd.DataFrame(out_rows)
    # Remove the raw per-contact email/flags columns to avoid confusion
    to_drop = [c for i in contact_idxs for c in (f"contact_{i}_email", f"contact_{i}_flags") if c in exploded.columns]
    exploded = exploded.drop(columns=to_drop, errors="ignore")
    return exploded

with st.sidebar:
    st.header("Options")
    mode = st.radio(
        "Choose mode",
        [
            "Clone: remove renters only",
            "Owner-only: keep renters, remove only 'Likely Owner…'",
        ],
        index=0,
    )
    do_trim = st.checkbox("Trim spaces in text fields", value=True)
    drop_no_email = st.checkbox("Drop rows with no email after explode", value=True)
    filter_valid = st.checkbox("Keep only valid-looking emails", value=True)
    dedupe_by_email = st.checkbox("De-duplicate by Email", value=True)
    st.caption("This version reads contact_N_email + contact_N_flags and keeps the matching flag per email.")

st.write("**Step 1. Upload CSV**")
uploaded = st.file_uploader("Choose a DealMachine CSV", type=["csv"])

if uploaded is not None:
    content = uploaded.read()
    df = robust_read_csv(content)
    if df is None:
        st.error("Could not read CSV. Try re-exporting or saving with UTF-8 encoding.")
        st.stop()

    if do_trim:
        df = strip_object_columns(df)

    # Detect contact slots from headers
    contact_idxs = detect_contact_indices(list(df.columns))
    if not contact_idxs:
        st.warning("No contact_N_email columns found. This app is tailored to DealMachine’s per-contact export.")
    else:
        st.info(f"Detected contact slots: {contact_idxs}")

    st.write("**Step 2. Explode to one email per row (keeping matched flags)**")
    before = len(df)
    work = explode_by_contacts(df, contact_idxs)
    st.write(f"Exploded by contacts → rows: {before:,} → {len(work):,}")

    if drop_no_email:
        work = work.dropna(subset=["Email"])
        st.write(f"Dropped rows without Email → {len(work):,} rows remain")

    if filter_valid and "Email" in work.columns:
        b = len(work)
        work = work[work["Email"].apply(looks_valid_email)]
        st.write(f"Filtered invalid-looking emails → removed {b - len(work):,} rows")

    # --- Phrase filters driven by per-contact Flags (lowercased already) ---
    renters_only = [
        "resident, likely renting",
        "likely renting",
        "renter",
    ]
    owner_excl = [
        "likely owner, resident",
        "likely owner",
        "likely owner, family",
    ]

    # Build a matching function that looks for any target phrase inside Flags
    def flags_match(flags_val: str, targets: list[str]) -> bool:
        if not isinstance(flags_val, str) or not flags_val:
            return False
        f = flags_val.lower()
        return any(t in f for t in targets)

    if mode.startswith("Clone"):
        # Remove renters only
        mask_remove = work["Flags"].apply(lambda v: flags_match(v, renters_only))
        removed = int(mask_remove.sum())
        work = work.loc[~mask_remove].copy()
        st.info(f"Mode 1: removed {removed:,} renter rows based on Flags.")
    else:
        # Keep renters; remove only 'Likely Owner…'
        mask_remove = work["Flags"].apply(lambda v: flags_match(v, owner_excl))
        removed = int(mask_remove.sum())
        work = work.loc[~mask_remove].copy()
        st.info(f"Mode 2: removed {removed:,} 'Likely Owner…' rows. Renters kept.")

    if dedupe_by_email and "Email" in work.columns:
        b = len(work)
        work = work.drop_duplicates(subset=["Email"], keep="first")
        st.write(f"De-duplicated by Email → removed {b - len(work):,} rows")

    st.success(f"Done. {len(work):,} rows ready for verification.")

    with st.expander("Preview cleaned data", expanded=False):
        st.dataframe(work.head(50), use_container_width=True)

    cleaned_bytes = work.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download cleaned CSV",
        data=cleaned_bytes,
        file_name="dealmachine_cleaned_emails.csv",
        mime="text/csv",
    )

else:
    st.info("Upload a DealMachine CSV to get started.")

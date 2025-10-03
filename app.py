import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="REInbox CSV Cleaner", page_icon="🧹", layout="wide")
st.title("REInbox CSV Cleaner 🧹 (DealMachine - multi-contact aware)")

# Liberal but solid email regex
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I)

def robust_read_csv(file_bytes: bytes) -> pd.DataFrame | None:
    """Try common encodings so weird CSVs still load."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
        except Exception:
            continue
    return None

def strip_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace across all text columns."""
    work = df.copy()
    for c in work.select_dtypes(include=["object"]).columns:
        work[c] = work[c].astype(str).str.strip()
    return work

def looks_valid_email(e: str) -> bool:
    """Quick sanity checks (not MX/SMTP)."""
    if not isinstance(e, str):
        return False
    e = e.strip().lower()
    if not EMAIL_RE.fullmatch(e):
        return False
    if e.startswith(".") or e.endswith("."):
        return False
    if ".." in e:
        return False
    local, _, domain = e.partition("@")
    if not local or not domain:
        return False
    if local.startswith((".", "-")) or local.endswith((".", "-")):
        return False
    if domain.startswith((".", "-")) or domain.endswith((".", "-")):
        return False
    labels = domain.split(".")
    if "." not in domain or any(len(lbl) == 0 for lbl in labels):
        return False
    if any(lbl.startswith("-") or lbl.endswith("-") for lbl in labels):
        return False
    if len(labels[-1]) < 2:
        return False
    return True

def detect_contact_indices(columns: list[str]) -> list[int]:
    """Find contact_N_email / contact_N_flags slots from headers."""
    idxs = set()
    for c in columns:
        m = re.match(r"contact_(\d+)_email$", str(c), re.I)
        if m:
            idxs.add(int(m.group(1)))
    for c in columns:
        m = re.match(r"contact_(\d+)_flags$", str(c), re.I)
        if m:
            idxs.add(int(m.group(1)))
    return sorted(idxs)

def explode_by_contacts(df: pd.DataFrame, contact_idxs: list[int]) -> pd.DataFrame:
    """
    For each row, emit one row per contact index with Email + Flags.
    Keeps original columns, adds 'Email' and 'Flags' from matching contact_{i}_*.
    """
    if not contact_idxs:
        out = df.copy()
        if "Email" not in out.columns:
            out["Email"] = pd.NA
        if "Flags" not in out.columns:
            out["Flags"] = pd.NA
        return out

    out_rows = []
    for _, row in df.iterrows():
        emitted = False
        for i in contact_idxs:
            email_col = f"contact_{i}_email"
            flags_col = f"contact_{i}_flags"
            email = row.get(email_col, pd.NA)
            flags = row.get(flags_col, pd.NA)

            # Extract any/all emails from that cell
            email_list = []
            if pd.notna(email):
                found = EMAIL_RE.findall(str(email))
                email_list = list(dict.fromkeys([e.lower() for e in found]))

            if not email_list:
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
            new_row = row.copy()
            new_row["Email"] = pd.NA
            new_row["Flags"] = pd.NA
            out_rows.append(new_row)

    exploded = pd.DataFrame(out_rows)

    # Guarantee columns exist
    if "Email" not in exploded.columns:
        exploded["Email"] = pd.NA
    if "Flags" not in exploded.columns:
        exploded["Flags"] = pd.NA

    # Drop raw per-contact columns so output is clean
    to_drop = [c for i in contact_idxs for c in (f"contact_{i}_email", f"contact_{i}_flags") if c in exploded.columns]
    exploded = exploded.drop(columns=to_drop, errors="ignore")
    return exploded

# ---------------- Sidebar UI ----------------
with st.sidebar:
    st.header("Filters & Options")

    mode = st.radio(
        "Select list type",
        options=[
            "Owners list — Removes renters (keeps owners)",
            "Renters list — Removes owners (keeps renters)",
        ],
        index=0,
        help=(
            "Owners list: drops rows flagged as renters (e.g., 'Resident, Likely Renting').\n"
            "Renters list: drops rows flagged as 'Likely Owner…' so only renters remain."
        ),
    )

    if mode.startswith("Owners"):
        st.caption("Result: **owners-focused** list (renter rows removed).")
    else:
        st.caption("Result: **renters-focused** list (owner rows removed).")

    do_trim = st.checkbox("Trim spaces in text fields", value=True)
    drop_no_email = st.checkbox("Drop rows with no email after explode", value=True)
    filter_valid = st.checkbox("Keep only valid-looking emails", value=True)
    dedupe_by_email = st.checkbox("De-duplicate by Email", value=True)

# ---------------- Main flow ----------------
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

    contact_idxs = detect_contact_indices(list(df.columns))
    if not contact_idxs:
        st.warning("No contact_N_email columns found. This app is tailored to DealMachine’s per-contact export.")
    else:
        st.info(f"Detected contact slots: {contact_idxs}")

    st.write("**Step 2. Explode to one email per row (with matched flags)**")
    before = len(df)
    work = explode_by_contacts(df, contact_idxs)
    st.write(f"Exploded → rows: {before:,} → {len(work):,}")

    # Safety: ensure required columns exist
    if "Email" not in work.columns:
        work["Email"] = pd.NA
    if "Flags" not in work.columns:
        work["Flags"] = pd.NA

    if drop_no_email:
        work = work.dropna(subset=["Email"])
        st.write(f"Dropped rows without Email → {len(work):,}")

    if filter_valid and "Email" in work.columns:
        b = len(work)
        work = work[work["Email"].apply(looks_valid_email)]
        st.write(f"Filtered invalid-looking emails → removed {b - len(work):,} rows")

    # Phrase sets (lowercased comparisons)
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

    def flags_match(flags_val: str, targets: list[str]) -> bool:
        if pd.isna(flags_val):
            return False
        f = str(flags_val).lower()
        return any(t in f for t in targets)

    # --- SAFETY: use a guarded series so we never KeyError ---
    flags_series = work["Flags"] if "Flags" in work.columns else pd.Series(pd.NA, index=work.index)

    # Apply mode logic using the safe Flags series
    if mode.startswith("Owners"):
        # Owners list — remove renters
        mask_remove = flags_series.apply(lambda v: flags_match(v, renters_only))
        removed = int(mask_remove.sum())
        work = work.loc[~mask_remove].copy()
        st.info(f"Owners list: removed {removed:,} renter-flagged rows.")
    else:
        # Renters list — remove 'Likely Owner…'
        mask_remove = flags_series.apply(lambda v: flags_match(v, owner_excl))
        removed = int(mask_remove.sum())
        work = work.loc[~mask_remove].copy()
        st.info(f"Renters list: removed {removed:,} 'Likely Owner…' rows (owners removed).")

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



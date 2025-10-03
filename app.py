import io
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="REInbox CSV Cleaner", page_icon="🧹", layout="wide")
st.title("REInbox CSV Cleaner 🧹 (DealMachine - multi-contact aware)")

# Email regex
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
    # Ensure Email/Flags exist even if nothing to explode
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

def ensure_flags_series(df: pd.DataFrame) -> pd.Series:
    """
    Always return a valid Flags Series indexed to df.index,
    creating the column if missing.
    """
    if "Flags" in df.columns:
        s = df["Flags"]
        # Normalize to string-lower for matching (NaNs become 'nan' later; handle below)
        s = s.astype("string

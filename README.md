
# REInbox CSV Cleaner (DealMachine - multi-contact aware)

This Streamlit app cleans DealMachine CSVs by:
- Exploding **contact_N_email** into **one row per email**
- Carrying over the matched **contact_N_flags** into a unified **Flags** column
- Letting you choose a mode:
  - **Clone:** remove renters only (drops rows with Flags like "resident, likely renting")
  - **Owner-only:** keep renters; remove only "Likely Owner…" rows
- Optional sanity filtering of malformed emails and de-duplication by Email

## Deploy on Streamlit Cloud (no local Python needed)
1. Create a new GitHub repo and add these files: `app.py` and `requirements.txt` (this folder's contents).
2. Go to https://share.streamlit.io (Streamlit Community Cloud), connect your GitHub, and select the repo.
3. Set **Main file path** to `app.py` and deploy.
4. Open the app URL, upload your DealMachine CSV, select a mode, and download the cleaned CSV.

## Local run (optional)
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes
- Works with older DealMachine exports that have `contact_1_email`, `contact_1_flags`, etc.
- If DealMachine changes column names, update detection in `detect_contact_indices` or share a sample so we can adjust.

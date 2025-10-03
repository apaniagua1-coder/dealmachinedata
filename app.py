with st.sidebar:
    st.header("Filters & Options")

    # Clear, explicit modes
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

    # Dynamic helper text
    if mode.startswith("Owners"):
        st.caption("Result: **owners-focused** list (renter rows removed).")
    else:
        st.caption("Result: **renters-focused** list (owner rows removed).")

    do_trim = st.checkbox("Trim spaces in text fields", value=True)
    drop_no_email = st.checkbox("Drop rows with no email after explode", value=True)
    filter_valid = st.checkbox("Keep only valid-looking emails", value=True)
    dedupe_by_email = st.checkbox("De-duplicate by Email", value=True)

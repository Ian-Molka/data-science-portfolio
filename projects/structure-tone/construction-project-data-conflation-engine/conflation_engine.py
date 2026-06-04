# conflation_target_sub_includes_cycle.py
# pip install pandas openpyxl python-dateutil

from pathlib import Path
import re
import pandas as pd
from openpyxl import load_workbook
from dateutil import parser
from openpyxl.worksheet.protection import SheetProtection
from openpyxl.styles import Protection, Border, Side
from copy import copy
from collections import Counter

# ==============================
# CONFIG
# ==============================
SOURCE_HEADER_ROW_1BASED = 1
TARGET_HEADER_ROW_1BASED = 4

TARGET_KEY_HEADER = "Submittal #"
COSTCTR_TG_HEADER = "Cost Center"

# NOTE: ANCHOR_HEADER is used ONLY for finding/validating the active table & required CC logic (not for formulas)
ANCHOR_HEADER     = "Estimated Delivery"

# ---- Blue columns logic ----
DIFF_HEADER_CANDIDATES = [
    "Differential", "Differential ", "Differential (Days)", "Days Differential",
    "Difference", "Differiential", "Differiential ",
]
STATUS_HEADER_CANDIDATES = ["Submittal Status", "Submittal status"]
SUBMITTED_HEADER_CANDIDATES = [
    "Date Submitted to design team", "Date Submitted to Design Team", "Date Submitted to design team ",
]
RETURNED_HEADER_CANDIDATES = [
    "Returned Date to STI", "Returned date to STI", "Returned Date to STI ",
]
STATUS_FOR_APPROVAL = "For Approval"

SUBMITTED_COUNTER_HEADER_CANDIDATES = ["Submitted Counter", "Submitted counter", "SubmittedCounter"]
RESUBMITTED_COUNTER_HEADER_CANDIDATES = [
    "Resubmitted Counter", "ReSubmitted Counter", "Resubmitted counter",
    "ResubmittedCounter", "Re-Submitted Counter",
]

# ---- Required Release Date formula column logic ----
REQUIRED_RELEASE_HEADER_CANDIDATES = ["Required Release Date", "Required Release", "Required Release Dt"]
ROJ_HEADER_CANDIDATES = [
    "Required on Job (ROJ)", "Required on Job", "Required on Job Date",
    "Required On Job (ROJ)", "Required on Job (ROJ) "
]
LEAD_WEEKS_HEADER_CANDIDATES = [
    "Lead Times (Weeks)", "Lead Time (Weeks)", "Lead Times", "Lead Time"
]

# ---- Estimated Delivery formula column logic ----
ESTIMATED_DELIVERY_HEADER_CANDIDATES = ["Estimated Delivery", "Est. Delivery", "Estimated Deliv"]
RELEASED_BY_CONTRACTOR_HEADER_CANDIDATES = [
    "Date Released by Contractor", "Date Released by Contractor ",
    "Date Released", "Released by Contractor"
]

# ---- Release Date Delta formula column logic ----
RELEASE_DATE_DELTA_HEADER_CANDIDATES = ["Release Date Delta", "Release Delta", "Release Date Δ"]

# ---- Delivered? formula column logic ----
DELIVERED_HEADER_CANDIDATES = ["Delivered?", "Delivered", "Delivered ?"]
ACTUAL_DELIVERY_HEADER_CANDIDATES = ["Actual Delivery Date", "Actual Delivery", "Actual Delivery Date "]

# ---- Delivery Date Delta formula column logic ----
DELIVERY_DATE_DELTA_HEADER_CANDIDATES = ["Delivery Date Delta", "Delivery Delta", "Delivery Date Δ"]

# ---- Orange target columns → preferred source names (first match wins) ----
TARGET_TO_SOURCE_MAP = {
    "Cost Center": ["Cost Center", "Cost Cen", "Cost Cen Current Cycle Name", "Cost Center Name"],
    "Spec. Section": ["Spec. Section", "Spec Section", "Spec Section #"],
    "Subcontractor": ["Subcontractor", "From Partner", "From Partner Name"],
    "Items": ["Items", "Name", "Cycle Items", "Item Name"],
    "Submittal Status": ["Submittal Status", "Status"],
    "Complete (Y/N)": ["Complete (Y/N)", "Complete", "Completed", "Is Complete"],
    "Date Received from Sub": ["Received Date from Sub", "Received Date f", "Received Date", "Date Received"],
    "Date Submitted to design team": ["Sent Date to Design Team", "Sent Date to De", "Sent Date", "Date Submitted"],
    "Return Due Date": ["Return Due Date", "Due Date", "Return Due"],
    "Returned Date to STI": ["Returned Date to STI", "Returned To ST Date", "Returned Date"],
    "Days Out": ["Days Out"],
    "Approved Submittal Returned to Contractor": ["Forwarded To", "Forwarded Date", "Approved Returned Date", "Approved Submittal Returned Date"],
    "Responsible Partner": ["Resp. Partner", "Responsible Partner"],
    "Responsible Contact": ["Resp. Contact", "Responsible Contact"],
}

DATE_LIKE_TARGETS = {
    "Date Received from Sub",
    "Date Submitted to design team",
    "Return Due Date",
    "Returned Date to STI",
    "Approved Submittal Returned to Contractor",
}

# Source aliases
SUBMITTAL_SRC_ALIASES = ["Submittal No.", "Submittal #", "SUBMITTAL NO.", "SUBMITTAL #"]
CURRENT_SRC_ALIASES   = ["Current Cycle", "Current", "Cycle", "Current Cycle Number", "Current Cycle Name"]
COSTCTR_SRC_ALIASES   = ["Cost Center", "Cost Cen", "Cost Center Name", "Cost Cen Current Cycle Name"]

SHEET_CC_DEFAULT = {"Hotel Infrastructure": "HI", "Infrastructure": "HI"}

# ---- Password protection ----
PROTECT_PASSWORD = "examplepassword123"  # Change this to your desired password
PROTECTED_HEADERS = [
    "Cost Center",
    "Submittal #",
    "Date Received from Sub",
    "Date Submitted to design team",
    "Return Due Date",
    "Subcontractor",
    "Items",
    "Submittal Status",
    "Returned Date to STI",
    "Days Out",
    "Approved Submittal Returned to Contractor",
    "Responsible Partner",
    "Responsible Contact",
    "Differential",
    "Submitted Counter",
    "Resubmitted Counter",
    "Required Release Date",
    "Estimated Delivery",
    "Release Date Delta",
    "Delivered?",
    "Delivery Date Delta",
]

# ---- Cleanup behavior (prevents deleting your big colored buffer) ----
CLEANUP_SCAN_ROWS = 50

# ---- IMPORTANT FIX FOR YOUR ISSUE ----
# Your workbook sometimes uses "Date Needed" instead of "Release Date Needed".
# We treat BOTH as equivalent, and for Delivery Date Delta we return whatever text is already in Estimated Delivery.
EST_DELIVERY_TEXT_ALIASES = ("Release Date Needed", "Date Needed")

# ==============================
# Helpers
# ==============================
def parse_date_maybe(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.upper() in {"N/A", "NA", "NONE"}:
        return None
    try:
        return parser.parse(s, dayfirst=False).date()
    except Exception:
        return s

def pick_col_by_alias(df_cols, aliases):
    cols = set(df_cols)
    for a in aliases:
        if a in cols:
            return a
    norm = {str(c).strip().lower(): c for c in df_cols}
    for a in aliases:
        k = str(a).strip().lower()
        if k in norm:
            return norm[k]
    return None

def normalize_cc(val: str) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    token = s.split()[0] if s else ""
    return token.upper()

def normalize_current_cycle_str_to_int(val) -> int:
    if val is None:
        return -1
    s = re.sub(r"\D+", "", str(val))
    if s == "":
        return -1
    try:
        return int(s)
    except Exception:
        return -1

def clean_submittal_text(v):
    if v is None:
        return ""
    s = str(v).strip()
    s = re.split(r"\s*\(", s)[0].strip()
    return s

def split_target_submittal(sub_with_maybe_cycle: str):
    if sub_with_maybe_cycle is None:
        return "", -1
    s = str(sub_with_maybe_cycle).strip()
    if "-" not in s:
        return s, -1
    parts = s.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return s, -1

def resubmitted_counter_from_submittal_minus1(submittal_value):
    if submittal_value is None:
        return None
    s = str(submittal_value).strip()
    m = re.search(r"-(\d+)\s*$", s)
    if not m:
        return None
    try:
        return max(int(m.group(1)) - 1, 0)
    except Exception:
        return None

def norm_header(x):
    if x is None:
        return ""
    s = str(x).replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def excel_col_letter(n: int) -> str:
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

def set_differential_formula(ws, row_idx: int, diff_col: int, status_col: int, submitted_col: int, returned_col: int):
    scol = excel_col_letter(status_col)
    subcol = excel_col_letter(submitted_col)
    rcol = excel_col_letter(returned_col)

    status_ref = f"{scol}{row_idx}"
    submitted_ref = f"{subcol}{row_idx}"
    returned_ref = f"{rcol}{row_idx}"

    formula = (
        f'=IF({submitted_ref}="",'
        f' "",'
        f' IF(TRIM({status_ref})="{STATUS_FOR_APPROVAL}",'
        f'     TODAY()-{submitted_ref},'
        f'     IF({returned_ref}="", "", {returned_ref}-{submitted_ref})'
        f' )'
        f')'
    )
    cell = ws.cell(row_idx, diff_col)
    cell.value = formula
    cell.number_format = "0"

def set_required_release_formula(ws, row_idx: int, req_release_col: int, roj_col: int, lead_weeks_col: int):
    roj_letter  = excel_col_letter(roj_col)
    lead_letter = excel_col_letter(lead_weeks_col)
    roj_ref  = f"{roj_letter}{row_idx}"
    lead_ref = f"{lead_letter}{row_idx}"

    formula = (
        f'=IF(OR({roj_ref}="",{roj_ref}=0),'
        f' "Missing Required on Job Date",'
        f' ({roj_ref}-({lead_ref}*7))'
        f')'
    )
    ws.cell(row_idx, req_release_col).value = formula

def set_estimated_delivery_formula(ws, row_idx: int, est_deliv_col: int, released_col: int, lead_weeks_col: int):
    rel_letter  = excel_col_letter(released_col)
    lead_letter = excel_col_letter(lead_weeks_col)
    rel_ref  = f"{rel_letter}{row_idx}"
    lead_ref = f"{lead_letter}{row_idx}"

    # Keep your existing behavior; ONLY text handling is fixed downstream
    formula = (
        f'=IF(OR({rel_ref}="",{rel_ref}=0),'
        f' "Release Date Needed",'
        f' ({rel_ref}-({lead_ref}*7))'
        f')'
    )
    ws.cell(row_idx, est_deliv_col).value = formula

def set_release_date_delta_formula(ws, row_idx: int, release_delta_col: int, req_release_col: int, released_col: int):
    rel_letter = excel_col_letter(released_col)
    req_letter = excel_col_letter(req_release_col)

    rel_ref = f"{rel_letter}{row_idx}"
    req_ref = f"{req_letter}{row_idx}"

    formula = (
        f'=IF(OR({rel_ref}="",{rel_ref}=0),'
        f' "WHY NOT RELEASED?",'
        f' ({req_ref}-{rel_ref})'
        f')'
    )
    ws.cell(row_idx, release_delta_col).value = formula

# ✅ FIX: Delivered? should be a TRUE/FLAG style column (matches your expected output)
def set_delivered_formula(ws, row_idx: int, delivered_col: int, actual_delivery_col: int):
    act_letter = excel_col_letter(actual_delivery_col)
    act_ref = f"{act_letter}{row_idx}"

    formula = (
        f'=IF(OR({act_ref}="",{act_ref}=0),'
        f' "NOT DELIVERED",'
        f' "DELIVERED"'
        f')'
    )
    ws.cell(row_idx, delivered_col).value = formula

# ✅ FIX: Delivery Date Delta should stop when Estimated Delivery contains either "Release Date Needed" OR "Date Needed"
# and return that exact text (so your output stays consistent even if wording differs).
def set_delivery_date_delta_formula(
    ws,
    row_idx: int,
    delivery_delta_col: int,
    est_delivery_col: int,
    actual_delivery_col: int,
    roj_col: int,
):
    """
    Matches your working/expected formula exactly, but also accepts "Date Needed".
      =IF(OR(U5="Release Date Needed",U5="Date Needed"),
          "Release Date Needed",
          IF((V5=0),
             DAYS(X5,TODAY()),
             DAYS(X5,V5)
          )
        )
    """
    est_letter = excel_col_letter(est_delivery_col)
    act_letter = excel_col_letter(actual_delivery_col)
    roj_letter = excel_col_letter(roj_col)

    est_ref = f"{est_letter}{row_idx}"   # U
    act_ref = f"{act_letter}{row_idx}"   # V
    roj_ref = f"{roj_letter}{row_idx}"   # X

    formula = (
    f'=IF(OR({est_ref}="Release Date Needed",{est_ref}="Date Needed"),'
    f' "Release Date Needed",'
    f' IF(({act_ref}=0),'
    f'     1*({roj_ref}-TODAY()),'
    f'     1*({roj_ref}-{act_ref})'
    f' )'
    f')'
)

    ws.cell(row_idx, delivery_delta_col).value = formula


def find_active_last_row(ws, first_data_row: int, key_col: int, blank_run: int = 25) -> int:
    last = first_data_row - 1
    blanks = 0
    for r in range(first_data_row, ws.max_row + 1):
        v = ws.cell(r, key_col).value
        v = "" if v is None else str(v).strip()
        if v == "":
            blanks += 1
            if blanks >= blank_run:
                break
        else:
            blanks = 0
            last = r
    return last

def row_has_any_value(ws, r: int, max_col: int) -> bool:
    for c in range(1, max_col + 1):
        v = ws.cell(r, c).value
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return True
    return False

def clear_row_values(ws, r: int, max_col: int):
    for c in range(1, max_col + 1):
        ws.cell(r, c).value = None

def cleanup_stray_rows_below_table(ws, first_data_row: int, key_col: int, max_col: int, scan_rows: int = 50):
    last_key_row = find_active_last_row(ws, first_data_row, key_col, blank_run=25)
    start = last_key_row + 1
    end = min(ws.max_row, last_key_row + scan_rows)

    cleared = 0
    for r in range(start, end + 1):
        key_val = ws.cell(r, key_col).value
        key_val = "" if key_val is None else str(key_val).strip()
        if key_val != "":
            break
        if row_has_any_value(ws, r, max_col):
            clear_row_values(ws, r, max_col)
            cleared += 1
    return cleared

def delete_blank_rows_below_table(ws, first_data_row: int, key_col: int, max_col: int, scan_rows: int = 50):
    last_key_row = find_active_last_row(ws, first_data_row, key_col, blank_run=25)
    start = last_key_row + 1
    end = min(ws.max_row, last_key_row + scan_rows)

    rows_to_delete = []
    for r in range(start, end + 1):
        key_val = ws.cell(r, key_col).value
        key_val = "" if key_val is None else str(key_val).strip()
        if key_val != "":
            break
        if not row_has_any_value(ws, r, max_col):
            rows_to_delete.append(r)

    for r in reversed(rows_to_delete):
        ws.delete_rows(r, 1)

    return len(rows_to_delete)

# ==============================
# MAIN
# ==============================
def run_conflation(source_path, target_path, output_path, target_sheet):
    SOURCE_XLSX = Path(source_path)
    TARGET_XLSX = Path(target_path)
    OUT_XLSX = Path(output_path)
    TARGET_SHEET = target_sheet

    # ----- SOURCE -----
    with pd.ExcelFile(SOURCE_XLSX, engine="openpyxl") as xf:
        sheet_names = xf.sheet_names
    if not sheet_names:
        raise RuntimeError("Source workbook has no sheets.")
    src_sheet = sheet_names[0]

    src_df = pd.read_excel(
        SOURCE_XLSX,
        sheet_name=src_sheet,
        header=SOURCE_HEADER_ROW_1BASED - 1,
        dtype=str,
        engine="openpyxl",
    )
    src_df.columns = [c.strip() if isinstance(c, str) else c for c in src_df.columns]

    sub_src = pick_col_by_alias(src_df.columns, SUBMITTAL_SRC_ALIASES)
    cur_src = pick_col_by_alias(src_df.columns, CURRENT_SRC_ALIASES)
    cc_src  = pick_col_by_alias(src_df.columns, COSTCTR_SRC_ALIASES)

    if not sub_src or not cc_src:
        raise RuntimeError(
            f"Missing required source columns. Need Submittal and Cost Center.\n"
            f"Found Submittal={sub_src}, CostCenter={cc_src}. Columns: {list(src_df.columns)}"
        )

    src_df["_sub"] = src_df[sub_src].astype(str).str.strip()
    src_df["_cc"]  = src_df[cc_src].apply(normalize_cc)
    src_df["_cur"] = src_df[cur_src].apply(normalize_current_cycle_str_to_int) if cur_src else -1

    # Lookup A) exact (sub, cur)
    look_by_sub_cur = {}
    if cur_src:
        for _, row in src_df.iterrows():
            sub = row["_sub"]
            cur = row["_cur"]
            if sub and cur >= 0:
                look_by_sub_cur[(sub, cur)] = row

    # Lookup B) best by (sub, cc) with max cycle
    src_df_sorted = src_df.sort_values(by=["_sub", "_cc", "_cur"], ascending=[True, True, False])
    src_best = src_df_sorted.drop_duplicates(subset=["_sub", "_cc"], keep="first")
    look_by_sub_cc = {(row["_sub"], row["_cc"]): row for _, row in src_best.iterrows()}

    # Resolve source columns for target writes
    resolved_source_for_target = {}
    for t_col, candidates in TARGET_TO_SOURCE_MAP.items():
        for name in candidates:
            if name in src_df.columns:
                resolved_source_for_target[t_col] = name
                break

    # ----- TARGET -----
    wb_read = load_workbook(TARGET_XLSX, data_only=True)
    if TARGET_SHEET not in wb_read.sheetnames:
        raise RuntimeError(f"Sheet '{TARGET_SHEET}' not found in target.")
    ws_read = wb_read[TARGET_SHEET]

    wb_write = load_workbook(TARGET_XLSX, data_only=False)
    ws = wb_write[TARGET_SHEET]

    hdr_row = TARGET_HEADER_ROW_1BASED
    first_data_row = hdr_row + 1

    # Build header maps
    header_to_col = {}
    header_to_col_norm = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(hdr_row, c).value
        h = norm_header(v)
        if h:
            header_to_col[h] = c
            header_to_col_norm[h.lower()] = c

    def get_col(*names):
        for name in names:
            h = norm_header(name)
            if h in header_to_col:
                return header_to_col[h]
        for name in names:
            h = norm_header(name).lower()
            if h in header_to_col_norm:
                return header_to_col_norm[h]
        return None

    sub_tg_col = get_col(TARGET_KEY_HEADER)
    cc_tg_col  = get_col(COSTCTR_TG_HEADER)
    anchor_col = get_col(ANCHOR_HEADER)
    if not sub_tg_col or not cc_tg_col or not anchor_col:
        raise RuntimeError("Could not find required headers (Submittal # / Cost Center / Estimated Delivery).")

    diff_col      = get_col(*DIFF_HEADER_CANDIDATES)
    status_col    = get_col(*STATUS_HEADER_CANDIDATES)
    submitted_col = get_col(*SUBMITTED_HEADER_CANDIDATES)
    returned_col  = get_col(*RETURNED_HEADER_CANDIDATES)
    submitted_counter_col   = get_col(*SUBMITTED_COUNTER_HEADER_CANDIDATES)
    resubmitted_counter_col = get_col(*RESUBMITTED_COUNTER_HEADER_CANDIDATES)

    # Formula columns
    req_release_col = get_col(*REQUIRED_RELEASE_HEADER_CANDIDATES)
    roj_col         = get_col(*ROJ_HEADER_CANDIDATES)
    lead_weeks_col  = get_col(*LEAD_WEEKS_HEADER_CANDIDATES)

    est_deliv_col = get_col(*ESTIMATED_DELIVERY_HEADER_CANDIDATES)
    released_col  = get_col(*RELEASED_BY_CONTRACTOR_HEADER_CANDIDATES)

    release_delta_col = get_col(*RELEASE_DATE_DELTA_HEADER_CANDIDATES)

    delivered_col     = get_col(*DELIVERED_HEADER_CANDIDATES)
    actual_deliv_col  = get_col(*ACTUAL_DELIVERY_HEADER_CANDIDATES)

    delivery_delta_col = get_col(*DELIVERY_DATE_DELTA_HEADER_CANDIDATES)

    # Orange columns write positions
    write_positions = {}
    for t_col in TARGET_TO_SOURCE_MAP.keys():
        tg_col = get_col(t_col)
        if tg_col and t_col in resolved_source_for_target:
            write_positions[t_col] = tg_col

    # IMPORTANT: Do not overwrite formula columns with source values
    write_positions.pop("Estimated Delivery", None)
    write_positions.pop("Required Release Date", None)
    write_positions.pop("Release Date Delta", None)
    write_positions.pop("Delivered?", None)
    write_positions.pop("Delivery Date Delta", None)

    # ✅ determine ACTIVE range ONCE (prevents stray writes)
    active_last_row_read = find_active_last_row(ws_read, first_data_row, sub_tg_col, blank_run=25)
    active_last_row_write = find_active_last_row(ws, first_data_row, sub_tg_col, blank_run=25)
    active_last_row = max(active_last_row_read, active_last_row_write)
    if active_last_row < first_data_row:
        active_last_row = first_data_row

    # ---- Update existing rows (ONLY within active table) ----
    for r in range(first_data_row, active_last_row + 1):
        sub_raw = ws_read.cell(r, sub_tg_col).value
        cc_raw  = ws_read.cell(r, cc_tg_col).value
        sub_clean = clean_submittal_text(sub_raw)

        # BLUE columns
        if submitted_counter_col:
            ws.cell(r, submitted_counter_col).value = 1
            ws.cell(r, submitted_counter_col).number_format = "0"

        if resubmitted_counter_col:
            rc = resubmitted_counter_from_submittal_minus1(sub_clean)
            ws.cell(r, resubmitted_counter_col).value = rc
            ws.cell(r, resubmitted_counter_col).number_format = "0"

        if diff_col and status_col and submitted_col and returned_col:
            set_differential_formula(ws, r, diff_col, status_col, submitted_col, returned_col)

        # ✅ formulas
        if req_release_col and roj_col and lead_weeks_col:
            set_required_release_formula(ws, r, req_release_col, roj_col, lead_weeks_col)

        if est_deliv_col and released_col and lead_weeks_col:
            set_estimated_delivery_formula(ws, r, est_deliv_col, released_col, lead_weeks_col)

        if release_delta_col and req_release_col and released_col:
            set_release_date_delta_formula(ws, r, release_delta_col, req_release_col, released_col)

        # ✅ FIXED Delivered?
        if delivered_col and actual_deliv_col:
            set_delivered_formula(ws, r, delivered_col, actual_deliv_col)

        # ✅ FIXED Delivery Date Delta (handles both "Release Date Needed" and "Date Needed")
        if delivery_delta_col and est_deliv_col and actual_deliv_col and roj_col:
            set_delivery_date_delta_formula(ws, r, delivery_delta_col, est_deliv_col, actual_deliv_col, roj_col)

        # ORANGE updates only when match exists
        base_sub, cycle_from_target = split_target_submittal(sub_clean)
        cc_norm = normalize_cc(cc_raw)
        if not base_sub or not cc_norm:
            continue

        src_row = None
        if cycle_from_target >= 0 and (base_sub, cycle_from_target) in look_by_sub_cur:
            candidate = look_by_sub_cur[(base_sub, cycle_from_target)]
            src_cc = normalize_cc(candidate.get(cc_src, ""))
            if not src_cc or src_cc == cc_norm:
                src_row = candidate

        if src_row is None:
            src_row = look_by_sub_cc.get((base_sub, cc_norm))
        if src_row is None:
            continue

        for t_col, col_idx in write_positions.items():
            s_col = resolved_source_for_target.get(t_col)
            if not s_col:
                continue
            val = src_row.get(s_col, None)
            if t_col in DATE_LIKE_TARGETS:
                val = parse_date_maybe(val)
            ws.cell(r, col_idx).value = val

    # ---- Determine existing pairs (active only) ----
    existing_target_pairs = set()
    for r in range(first_data_row, active_last_row_read + 1):
        sub_raw_tg = ws_read.cell(r, sub_tg_col).value
        cc_raw_tg  = ws_read.cell(r, cc_tg_col).value
        base_sub_tg, _ = split_target_submittal(clean_submittal_text(sub_raw_tg))
        cc_norm_tg     = normalize_cc(cc_raw_tg)
        if base_sub_tg and cc_norm_tg:
            existing_target_pairs.add((base_sub_tg, cc_norm_tg))

    # Determine required CC from active only
    cc_candidates = []
    for r in range(first_data_row, active_last_row_read + 1):
        v = normalize_cc(ws_read.cell(r, cc_tg_col).value)
        if v:
            cc_candidates.append(v)

    required_cc = Counter(cc_candidates).most_common(1)[0][0] if cc_candidates else None
    if not required_cc:
        required_cc = SHEET_CC_DEFAULT.get(TARGET_SHEET)

    # ---- Insert new rows after active table ----
    if required_cc:
        source_best_pairs = set(look_by_sub_cc.keys())
        missing_pairs = [
            pair for pair in source_best_pairs
            if pair not in existing_target_pairs and pair[1] == required_cc
        ]
        missing_pairs.sort(key=lambda x: (x[0], x[1]))
        rows_to_insert = [look_by_sub_cc[pair] for pair in missing_pairs]

        if rows_to_insert:
            n_new = len(rows_to_insert)
            insert_at = active_last_row_read + 1
            ws.insert_rows(insert_at, amount=n_new)

            for i, src_row in enumerate(rows_to_insert):
                r = insert_at + i

                base_sub = str(src_row["_sub"]).strip()
                cur_val  = src_row["_cur"]
                sub_with_cycle = f"{base_sub}-{cur_val}" if isinstance(cur_val, (int, float)) and cur_val >= 0 else base_sub
                cc_value = src_row["_cc"]

                ws.cell(r, sub_tg_col).value = sub_with_cycle
                ws.cell(r, cc_tg_col).value  = cc_value

                for t_col, col_idx in write_positions.items():
                    s_col = resolved_source_for_target.get(t_col)
                    if not s_col:
                        continue
                    val = src_row.get(s_col, None)
                    if t_col in DATE_LIKE_TARGETS:
                        val = parse_date_maybe(val)
                    ws.cell(r, col_idx).value = val

                if submitted_counter_col:
                    ws.cell(r, submitted_counter_col).value = 1
                    ws.cell(r, submitted_counter_col).number_format = "0"

                if resubmitted_counter_col:
                    rc = resubmitted_counter_from_submittal_minus1(sub_with_cycle)
                    ws.cell(r, resubmitted_counter_col).value = rc
                    ws.cell(r, resubmitted_counter_col).number_format = "0"

                if diff_col and status_col and submitted_col and returned_col:
                    set_differential_formula(ws, r, diff_col, status_col, submitted_col, returned_col)

                # ✅ formulas for inserted rows too
                if req_release_col and roj_col and lead_weeks_col:
                    set_required_release_formula(ws, r, req_release_col, roj_col, lead_weeks_col)

                if est_deliv_col and released_col and lead_weeks_col:
                    set_estimated_delivery_formula(ws, r, est_deliv_col, released_col, lead_weeks_col)

                if release_delta_col and req_release_col and released_col:
                    set_release_date_delta_formula(ws, r, release_delta_col, req_release_col, released_col)

                # ✅ FIXED Delivered?
                if delivered_col and actual_deliv_col:
                    set_delivered_formula(ws, r, delivered_col, actual_deliv_col)

                # ✅ FIXED Delivery Date Delta
                if delivery_delta_col and est_deliv_col and actual_deliv_col and roj_col:
                    set_delivery_date_delta_formula(ws, r, delivery_delta_col, est_deliv_col, actual_deliv_col, roj_col)

    # ---- Force Excel recalc on open ----
    try:
        wb_write.calculation.calcMode = "auto"
        wb_write.calculation.fullCalcOnLoad = True
    except Exception:
        pass

    # ==========================================================
    # ✅ CLEANUP BELOW TABLE
    # ==========================================================
    cleared = cleanup_stray_rows_below_table(ws, first_data_row, sub_tg_col, ws.max_column, scan_rows=CLEANUP_SCAN_ROWS)
    if cleared:
        print(f"🧹 Cleared {cleared} stray row(s) below the active table.")

    deleted = delete_blank_rows_below_table(ws, first_data_row, sub_tg_col, ws.max_column, scan_rows=CLEANUP_SCAN_ROWS)
    if deleted:
        print(f"🗑️ Deleted {deleted} completely blank row(s) below the active table to remove empty space.")

    # ==========================================================
    # ✅ FINAL VISUAL PASS: header-based fills + black borders (ACTIVE ONLY)
    # ==========================================================
    active_last_row_final = find_active_last_row(ws, first_data_row, sub_tg_col, blank_run=25)
    if active_last_row_final < first_data_row:
        active_last_row_final = first_data_row

    thin = Side(style="thin", color="000000")
    black_grid_border = Border(left=thin, right=thin, top=thin, bottom=thin)

    fill_by_col_from_header = {c: copy(ws.cell(hdr_row, c).fill) for c in range(1, ws.max_column + 1)}
    template_by_col = {c: ws.cell(first_data_row, c) for c in range(1, ws.max_column + 1)}
    template_row_height = ws.row_dimensions[first_data_row].height

    for r in range(first_data_row, active_last_row_final + 1):
        if template_row_height is not None:
            ws.row_dimensions[r].height = template_row_height
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(r, c)
            cell.font = copy(template_by_col[c].font)
            cell.alignment = copy(template_by_col[c].alignment)
            cell.number_format = template_by_col[c].number_format
            cell.fill = copy(fill_by_col_from_header[c])
            cell.border = black_grid_border

    # ==============================
    # PASSWORD PROTECT SPECIFIC COLUMNS
    # ==============================
    header_to_col_norm2 = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(hdr_row, c).value
        h = re.sub(r"\s+", " ", str(v).replace("\n", " ").replace("\r", " ")).strip() if v is not None else ""
        if h:
            header_to_col_norm2[h.lower()] = c

    def col_for_header(name: str):
        key = re.sub(r"\s+", " ", str(name)).strip().lower()
        return header_to_col_norm2.get(key)

    min_lock_row = hdr_row
    max_lock_row = ws.max_row

    for row in ws.iter_rows(min_row=min_lock_row, max_row=max_lock_row, min_col=1, max_col=ws.max_column):
        for cell in row:
            cell.protection = Protection(locked=False)

    for h in PROTECTED_HEADERS:
        col_idx = col_for_header(h)
        if not col_idx:
            continue
        for r in range(min_lock_row, max_lock_row + 1):
            ws.cell(r, col_idx).protection = Protection(locked=True)

    ws.protection = SheetProtection(sheet=True, password=PROTECT_PASSWORD)
    ws.protection.enable()
    ws.protection.autoFilter = True
    ws.protection.sort = True

    wb_write.save(OUT_XLSX)
    print(f"💾 Saved: {OUT_XLSX}")

# This file is designed to be imported by app.py / Streamlit.
# Example:
# run_conflation("source.xlsx", "target.xlsx", "output.xlsx", "Hotel Infrastructure")

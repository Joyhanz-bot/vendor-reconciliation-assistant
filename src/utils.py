from pathlib import Path
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATA_ROOT = PROJECT_ROOT / "sample_data"
BUILTIN_FILES = {
    "内部系统账单": SAMPLE_DATA_ROOT / "dayq_system.xlsx",
    "Vendor_A": SAMPLE_DATA_ROOT / "Vendor_A_bill.xlsx",
    "Vendor_B": SAMPLE_DATA_ROOT / "Vendor_B_bill.xlsx",
    "Vendor_C": SAMPLE_DATA_ROOT / "Vendor_C_bill.xlsx",
}

SYSTEM_COLUMNS = {
    "访谈编号", "供应商", "访谈日期", "访谈类型", "项目名称", "访谈人",
    "系统单价", "系统时长(小时)", "系统倍率", "系统金额", "系统状态",
}
VENDOR_COLUMNS = {
    "访谈编号", "访谈日期", "访谈类型", "项目名称", "访谈人", "单价",
    "实际时长(小时)", "计价方式", "倍率", "供应商总价",
}


def read_excel_source(source):
    return pd.read_excel(source)


def validate_columns(df, required_columns):
    return sorted(required_columns - set(df.columns))


def infer_vendor_name(file_name, dataframe=None):
    """Use a vendor column when available, otherwise create a readable label."""
    if dataframe is not None and "供应商" in dataframe.columns:
        values = dataframe["供应商"].dropna().astype(str).unique().tolist()
        if len(values) == 1:
            return values[0]
    stem = Path(str(file_name)).stem
    stem = re.sub(r"(?i)(_bill|_账单|供应商账单)$", "", stem)
    stem = stem.replace("_", " ").replace("-", " ").strip()
    return stem or "未命名供应商"


def display_vendor_name(vendor_name):
    return str(vendor_name).replace("_", " ")


def resolve_vendor_name(candidate, system_df):
    """Align readable upload labels with the system vendor code when possible."""
    values = system_df["供应商"].dropna().astype(str).unique().tolist()
    normalize = lambda value: re.sub(r"[\s_-]+", "", str(value)).lower()
    for value in values:
        if normalize(value) == normalize(candidate):
            return value
    return candidate


def format_amount(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def format_date(value):
    if value is None or pd.isna(value):
        return "—"
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(value)


def build_detail_views(rec_all, vendor_frames, system_df):
    """Add display-only source details to matching rows for review cards."""
    views = []
    for vendor_name, rows in rec_all.groupby("供应商", sort=False):
        view = rows.copy()
        vendor = vendor_frames[vendor_name].copy()
        system = system_df[system_df["供应商"] == vendor_name].copy()
        vendor["访谈编号"] = vendor["访谈编号"].astype(str)
        system["访谈编号"] = system["访谈编号"].astype(str)
        view["访谈编号"] = view["访谈编号"].astype(str)
        vendor_details = vendor[
            ["访谈编号", "访谈日期", "项目名称", "访谈类型", "访谈人", "备注"]
        ].drop_duplicates("访谈编号")
        system_details = system[
            ["访谈编号", "访谈日期", "项目名称", "访谈类型", "访谈人", "备注"]
        ].drop_duplicates("访谈编号")
        vendor_details = vendor_details.rename(
            columns={column: f"供应商_{column}" for column in vendor_details.columns if column != "访谈编号"}
        )
        system_details = system_details.rename(
            columns={column: f"系统_{column}" for column in system_details.columns if column != "访谈编号"}
        )
        view = view.merge(vendor_details, on="访谈编号", how="left")
        view = view.merge(system_details, on="访谈编号", how="left")
        for field in ["访谈日期", "项目名称", "访谈类型", "访谈人", "备注"]:
            view[field] = view[f"供应商_{field}"].combine_first(view[f"系统_{field}"])
        views.append(view)
    return pd.concat(views, ignore_index=True) if views else rec_all.copy()

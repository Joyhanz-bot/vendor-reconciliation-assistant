from io import BytesIO

import pandas as pd


def build_reconciliation_workbook(logic_all, rec_all, summary_df, vendor_outputs):
    """Export the complete reconciliation workbook, including vendor splits."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        logic_all.to_excel(writer, index=False, sheet_name="全量_账单逻辑校验")
        rec_all.to_excel(writer, index=False, sheet_name="全量_双向匹配")
        summary_df.to_excel(writer, index=False, sheet_name="供应商问题汇总")
        vendor_outputs.get("field_diff", pd.DataFrame()).to_excel(
            writer, index=False, sheet_name="字段级差异"
        )

        for index, (vendor_name, parts) in enumerate(
            vendor_outputs.get("by_vendor", {}).items(), start=1
        ):
            parts["logic"].to_excel(writer, index=False, sheet_name=f"V{index}_逻辑异常")
            parts["system_only"].to_excel(
                writer, index=False, sheet_name=f"V{index}_系统有供应商无"
            )
            parts["vendor_only"].to_excel(
                writer, index=False, sheet_name=f"V{index}_供应商有系统无"
            )

    return buffer.getvalue()

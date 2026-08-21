import pandas as pd

from .logic_checker import month_from_interview_id, suspect_suffix


def reconcile(vendor_df, system_df, vendor_name):
    """Keep the V1.1 two-way matching and field-difference rules unchanged."""
    vendor = vendor_df.copy()
    system = system_df[system_df["供应商"] == vendor_name].copy()
    vendor_ids = set(vendor["访谈编号"].astype(str))
    system_ids = set(system["访谈编号"].astype(str))
    rows = []

    for interview_id in sorted(vendor_ids | system_ids):
        vendor_rows = vendor[vendor["访谈编号"].astype(str) == interview_id]
        system_rows = system[system["访谈编号"].astype(str) == interview_id]

        if len(vendor_rows) > 1:
            rows.append(
                {
                    "供应商": vendor_name,
                    "访谈编号": interview_id,
                    "匹配状态": "重复编号",
                    "建议处理": "供应商与业务确认后重新申请编号；重复编号对应访谈延至下个周期结算",
                    "供应商金额": vendor_rows["供应商总价"].sum(),
                    "系统金额": system_rows["系统金额"].iloc[0]
                    if len(system_rows)
                    else None,
                    "时长差异": "",
                    "倍率差异": "",
                    "金额差异": "",
                    "需谁确认": "供应商 + 业务",
                }
            )
            continue

        if len(vendor_rows) and not len(system_rows):
            row = vendor_rows.iloc[0]
            if float(row["供应商总价"]) == 0:
                status = "供应商有 / 系统无（无效访谈）"
                action = "0结算，无影响"
                owner = "—"
            elif (
                month_from_interview_id(interview_id)
                and month_from_interview_id(interview_id) != "2608"
            ):
                status = "供应商有 / 系统无（跨期）"
                action = "按访谈编号日期延至对应月份结算"
                owner = "供应商"
            elif suspect_suffix(interview_id):
                status = "供应商有 / 系统无（编号疑似错误）"
                action = "确认访谈编号是否填写错误"
                owner = "供应商"
            else:
                status = "供应商有 / 系统无"
                action = "向业务确认是否实际发生；若实际发生在次月，则延期至下月结算"
                owner = "业务"
            rows.append(
                {
                    "供应商": vendor_name,
                    "访谈编号": interview_id,
                    "匹配状态": status,
                    "建议处理": action,
                    "供应商金额": row["供应商总价"],
                    "系统金额": None,
                    "时长差异": "",
                    "倍率差异": "",
                    "金额差异": "",
                    "需谁确认": owner,
                }
            )
            continue

        if len(system_rows) and not len(vendor_rows):
            row = system_rows.iloc[0]
            if float(row["系统金额"]) == 0 or str(row["系统状态"]) == "无效":
                status = "系统有 / 供应商无（无效访谈）"
                action = "0结算，无影响"
                owner = "—"
            else:
                status = "系统有 / 供应商无"
                action = "询问供应商是否遗漏，并提醒补充至账单"
                owner = "供应商"
            rows.append(
                {
                    "供应商": vendor_name,
                    "访谈编号": interview_id,
                    "匹配状态": status,
                    "建议处理": action,
                    "供应商金额": None,
                    "系统金额": row["系统金额"],
                    "时长差异": "",
                    "倍率差异": "",
                    "金额差异": "",
                    "需谁确认": owner,
                }
            )
            continue

        vendor_row = vendor_rows.iloc[0]
        system_row = system_rows.iloc[0]
        time_diff = round(
            float(vendor_row["实际时长(小时)"]) - float(system_row["系统时长(小时)"]), 2
        )
        multiplier_diff = round(
            float(vendor_row["倍率"]) - float(system_row["系统倍率"]), 2
        )
        amount_diff = round(
            float(vendor_row["供应商总价"]) - float(system_row["系统金额"]), 2
        )
        issues = []
        actions = []
        owner = "—"
        if abs(time_diff) > 0.001:
            issues.append(f"时长差异 {time_diff:+.2f}h")
        if abs(multiplier_diff) > 0.001:
            issues.append(f"倍率差异 {multiplier_diff:+.2f}")
        if abs(amount_diff) > 0.01:
            issues.append(f"金额差异 {amount_diff:+.2f}")
        if not issues:
            status = "双方一致"
            action_text = "可进入后续结算流程"
        else:
            status = "字段有差异"
            if abs(amount_diff) > 0.01 and abs(time_diff) <= 0.08 and abs(multiplier_diff) <= 0.001:
                actions.append("可能为分钟换算/小数位差异：与业务核对后以系统导出金额为参考口径")
                owner = "业务"
            if abs(multiplier_diff) > 0.001:
                actions.append("核对倍率是否由业务或供应商侧录入错误")
                owner = "业务"
            if abs(amount_diff) > 0.01 and not actions:
                actions.append("核对单价、时长、倍率及供应商选择是否正确")
                owner = "业务 / 供应商"
            action_text = "；".join(actions)

        rows.append(
            {
                "供应商": vendor_name,
                "访谈编号": interview_id,
                "匹配状态": status,
                "建议处理": action_text,
                "供应商金额": vendor_row["供应商总价"],
                "系统金额": system_row["系统金额"],
                "时长差异": time_diff,
                "倍率差异": multiplier_diff,
                "金额差异": amount_diff,
                "需谁确认": owner,
            }
        )

    return pd.DataFrame(rows)

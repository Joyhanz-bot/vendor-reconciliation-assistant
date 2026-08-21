import math
import re

import pandas as pd


BILL_MONTH = "2608"


def ceil_quarter(value):
    return math.ceil(float(value) * 4 - 1e-9) / 4


def month_from_interview_id(interview_id):
    match = re.search(r"#(\d{4})", str(interview_id))
    return match.group(1) if match else ""


def suspect_suffix(interview_id):
    return bool(re.search(r"[A-Za-z]$", str(interview_id)[-3:]))


def logic_check(df, vendor_name):
    """Apply the V1.1 vendor-bill logic checks without changing their rules."""
    work = df.copy()
    duplicate_ids = set(
        work.loc[work["访谈编号"].duplicated(keep=False), "访谈编号"].astype(str)
    )
    rows = []
    for _, row in work.iterrows():
        interview_id = str(row["访谈编号"])
        interview_type = str(row["访谈类型"])
        issues = []
        status = "通过"
        expected = None

        if interview_id in duplicate_ids:
            issues.append("访谈编号重复：一个 call 应对应一个编号")
            status = "待确认"
        if (
            month_from_interview_id(interview_id)
            and month_from_interview_id(interview_id) != BILL_MONTH
        ):
            issues.append("访谈编号日期不属于当前账单月")
            status = "延期/待确认"
        if suspect_suffix(interview_id):
            issues.append("访谈编号末尾含英文，可能存在编号填写问题")
            status = "待确认"
        if float(row["供应商总价"]) == 0:
            issues.append("0结算：标记为无效访谈")
            status = "无效访谈"
        if interview_type == "普通访谈" and float(row["供应商总价"]) != 0:
            duration = float(row["实际时长(小时)"])
            billing_method = str(row["计价方式"])
            billed_duration = (
                ceil_quarter(duration) if "进位" in billing_method else round(duration, 2)
            )
            expected = round(
                float(row["单价"]) * billed_duration * float(row["倍率"]), 2
            )
            if abs(expected - float(row["供应商总价"])) > 0.01:
                issues.append(f"金额逻辑不一致：按当前计价规则应为 {expected:.2f}")
                status = "金额异常"
        elif interview_type == "数据采买":
            issues.append("数据采买/打包价：跳过普通访谈乘法校验")

        rows.append(
            {
                "供应商": vendor_name,
                "访谈编号": interview_id,
                "访谈日期": row["访谈日期"],
                "访谈类型": interview_type,
                "项目名称": row["项目名称"],
                "访谈人": row["访谈人"],
                "单价": row["单价"],
                "实际时长(小时)": row["实际时长(小时)"],
                "计价方式": row["计价方式"],
                "倍率": row["倍率"],
                "供应商总价": row["供应商总价"],
                "理论金额": expected,
                "账单逻辑状态": status,
                "账单逻辑提示": "；".join(issues) if issues else "—",
            }
        )
    return pd.DataFrame(rows)

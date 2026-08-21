import pandas as pd
import streamlit as st

from src.exporter import build_reconciliation_workbook
from src.logic_checker import logic_check
from src.reconciler import reconcile
from src.utils import (
    BUILTIN_FILES,
    SYSTEM_COLUMNS,
    VENDOR_COLUMNS,
    build_detail_views,
    display_vendor_name,
    format_amount,
    format_date,
    infer_vendor_name,
    read_excel_source,
    resolve_vendor_name,
    validate_columns,
)


st.set_page_config(page_title="供应商对账与异常复核助手", page_icon="📊", layout="wide")

st.title("供应商对账与异常复核助手")
st.subheader("Vendor Reconciliation & Exception Review Assistant")
st.write(
    "用于模拟财务供应商月度对账流程。系统通过 Python 对供应商账单进行逻辑校验，并与内部系统账单双向匹配，"
    "自动识别缺失记录、金额差异、时长差异、倍率差异及账单逻辑异常。异常事项按供应商整理，最终由财务人员确认并沟通处理。"
    "所有演示数据均为模拟数据。"
)


def _logic_display(value):
    return "✅ 通过" if value == "通过" else "⚠️ 待确认"


def _safe_value(row, key, fallback="—"):
    value = row.get(key, fallback)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return fallback
    return value


def _render_source_card(row, source_label, available=True):
    st.markdown(f"**{source_label}**")
    if not available:
        st.write("当前未找到对应记录")
        return
    prefix = "供应商_" if source_label == "供应商账单" else "系统_"
    left, right = st.columns(2)
    with left:
        st.write(f"项目名称：{_safe_value(row, prefix + '项目名称')}")
        st.write(f"访谈日期：{format_date(_safe_value(row, prefix + '访谈日期', None))}")
    with right:
        amount_key = "供应商金额" if source_label == "供应商账单" else "系统金额"
        st.write(f"金额：{format_amount(_safe_value(row, amount_key, None))}")
        st.write(f"访谈人：{_safe_value(row, prefix + '访谈人')}")


def _followup_reason(row, category):
    if category == "系统有 / 供应商账单无":
        return "内部系统存在该访谈，但供应商本月账单中未找到对应编号。"
    if category == "供应商账单有 / 系统无":
        return "供应商账单存在该访谈，但内部系统中未找到对应编号，需确认是否漏录或跨期。"
    return _safe_value(row, "账单逻辑提示")


def _render_followup_card(row, category):
    vendor = display_vendor_name(_safe_value(row, "供应商"))
    interview_id = _safe_value(row, "访谈编号")
    match_status = _safe_value(row, "匹配状态", "账单逻辑异常")
    st.markdown(f"**🔴 {vendor}｜{interview_id}｜{match_status}**")
    st.caption(f"问题类型：{category}")

    if category == "供应商账单自身逻辑异常":
        st.write(f"访谈类型：{_safe_value(row, '访谈类型')}")
        st.write(f"项目名称：{_safe_value(row, '项目名称')}")
        st.write(f"访谈日期：{format_date(_safe_value(row, '访谈日期', None))}")
        st.write(f"供应商金额：{format_amount(_safe_value(row, '供应商总价', None))}")
        st.write(f"核心原因：{_safe_value(row, '账单逻辑提示')}")
        st.write("建议处理：请供应商解释计价依据，并由财务确认是否需要更正账单。")
        st.write("建议确认方：供应商 / 财务")
    else:
        left, right = st.columns(2)
        if category == "系统有 / 供应商账单无":
            with left:
                _render_source_card(row, "内部系统记录")
            with right:
                _render_source_card(row, "供应商账单", available=False)
        else:
            with left:
                _render_source_card(row, "内部系统记录", available=False)
            with right:
                _render_source_card(row, "供应商账单")
        st.write(f"核心原因：{_followup_reason(row, category)}")
        st.write(f"建议处理：{_safe_value(row, '建议处理')}")
        st.write(f"建议确认方：{_safe_value(row, '需谁确认')}")


def _render_field_diff_card(row):
    vendor = display_vendor_name(_safe_value(row, "供应商"))
    st.markdown(f"**🔴 {vendor}｜{_safe_value(row, '访谈编号')}｜字段有差异**")
    st.write(f"供应商金额：{format_amount(_safe_value(row, '供应商金额', None))}")
    st.write(f"系统金额：{format_amount(_safe_value(row, '系统金额', None))}")
    st.write(f"时长差异：{_safe_value(row, '时长差异')}")
    st.write(f"倍率差异：{_safe_value(row, '倍率差异')}")
    st.write(f"金额差异：{_safe_value(row, '金额差异')}")
    action = _safe_value(row, "建议处理")
    if action in ("", "—"):
        action = "核对双方时长记录及计价方式"
    st.write(f"建议处理：{action}")
    st.write(f"建议确认方：{_safe_value(row, '需谁确认')}")


def _prepare_inputs(mode):
    if mode == "使用内置模拟数据":
        return (
            BUILTIN_FILES["内部系统账单"],
            [(label, path) for label, path in BUILTIN_FILES.items() if label != "内部系统账单"],
        )

    system_file = st.sidebar.file_uploader("内部系统账单", type=["xlsx"], key="system_upload")
    vendor_files = st.sidebar.file_uploader(
        "供应商账单（可多选）", type=["xlsx"], accept_multiple_files=True, key="vendor_uploads"
    )
    if not system_file or not vendor_files:
        return None, []
    return system_file, [(file.name, file) for file in vendor_files]


def _process(system_source, vendor_sources):
    system_df = read_excel_source(system_source)
    missing = validate_columns(system_df, SYSTEM_COLUMNS)
    if missing:
        raise ValueError(f"内部系统账单缺少必要字段：{'、'.join(missing)}")

    vendor_frames = {}
    logic_frames = []
    reconciliation_frames = []
    for display_name, source in vendor_sources:
        vendor_df = read_excel_source(source)
        missing = validate_columns(vendor_df, VENDOR_COLUMNS)
        if missing:
            raise ValueError(f"{display_name} 缺少必要字段：{'、'.join(missing)}")
        candidate_name = (
            display_name
            if hasattr(source, "read_bytes")
            else infer_vendor_name(display_name, vendor_df)
        )
        vendor_name = resolve_vendor_name(candidate_name, system_df)
        vendor_frames[vendor_name] = vendor_df
        logic_frames.append(logic_check(vendor_df, vendor_name))
        reconciliation_frames.append(reconcile(vendor_df, system_df, vendor_name))

    logic_all = pd.concat(logic_frames, ignore_index=True)
    reconciliation_all = pd.concat(reconciliation_frames, ignore_index=True)
    detail_all = build_detail_views(reconciliation_all, vendor_frames, system_df)
    field_diff = detail_all[detail_all["匹配状态"] == "字段有差异"].copy()

    by_vendor = {}
    summary_rows = []
    for vendor_name in logic_all["供应商"].drop_duplicates().tolist():
        vendor_logic = logic_all[
            (logic_all["供应商"] == vendor_name) & (logic_all["账单逻辑状态"] != "通过")
        ].copy()
        vendor_reconciliation = detail_all[detail_all["供应商"] == vendor_name].copy()
        system_only = vendor_reconciliation[
            vendor_reconciliation["匹配状态"].str.startswith("系统有 / 供应商无", na=False)
        ].copy()
        vendor_only = vendor_reconciliation[
            vendor_reconciliation["匹配状态"].str.startswith("供应商有 / 系统无", na=False)
        ].copy()
        by_vendor[vendor_name] = {
            "logic": vendor_logic,
            "system_only": system_only,
            "vendor_only": vendor_only,
        }
        followup_total = len(vendor_logic) + len(system_only) + len(vendor_only)
        summary_rows.append(
            {
                "供应商": display_vendor_name(vendor_name),
                "账单记录数": len(vendor_frames[vendor_name]),
                "逻辑异常": len(vendor_logic),
                "系统有 / 供应商无": len(system_only),
                "供应商有 / 系统无": len(vendor_only),
                "字段级差异": int((vendor_reconciliation["匹配状态"] == "字段有差异").sum()),
                "待沟通事项合计": followup_total,
                "状态": "✅ 正常" if followup_total == 0 else "⚠️ 需关注",
            }
        )

    return {
        "system_df": system_df,
        "vendor_frames": vendor_frames,
        "logic_all": logic_all,
        "rec_all": detail_all,
        "field_diff": field_diff,
        "summary_df": pd.DataFrame(summary_rows),
        "by_vendor": by_vendor,
    }


st.sidebar.header("Step 1｜选择数据")
mode = st.sidebar.radio("数据来源", ["使用内置模拟数据", "上传自有测试文件"])
if mode == "使用内置模拟数据":
    st.sidebar.success("已选择内置模拟数据")
    st.sidebar.caption("内部系统账单 + Vendor A / B / C，共 4 个模拟文件。")
else:
    st.sidebar.info("请先上传内部系统账单，再上传一个或多个供应商账单。")

system_source, vendor_sources = _prepare_inputs(mode)

st.subheader("Step 1｜选择数据")
if system_source and vendor_sources:
    recognized = ["✅ 内部系统账单"] + [f"✅ {display_vendor_name(name)}" for name, _ in vendor_sources]
    st.write("已识别数据源：" + "、".join(recognized))
    st.caption("系统会优先读取账单字段识别供应商；上传文件名仅作为无法读取供应商字段时的备用标签。")
else:
    st.info("请在左侧选择内置模拟数据，或上传内部系统账单和供应商账单。")

st.subheader("Step 2｜运行对账")
run_reconciliation = st.button("开始对账", type="primary", use_container_width=True)

if run_reconciliation:
    if not system_source or not vendor_sources:
        st.warning("请先完成数据选择。")
    else:
        try:
            with st.spinner("账单读取 → 逻辑校验 → 双向匹配 → 字段差异识别 → 按供应商汇总"):
                st.session_state["reconciliation_result"] = _process(system_source, vendor_sources)
        except Exception as exc:
            st.error(f"文件无法处理：{exc}")

result = st.session_state.get("reconciliation_result")
if result:
    logic_all = result["logic_all"]
    rec_all = result["rec_all"]
    field_diff = result["field_diff"]
    summary_df = result["summary_df"]
    by_vendor = result["by_vendor"]

    st.divider()
    st.subheader("1. 对账概览")
    followup_count = int(summary_df["待沟通事项合计"].sum())
    metrics = st.columns(5)
    metrics[0].metric("供应商数量", len(by_vendor))
    metrics[1].metric("供应商账单记录数", len(logic_all))
    metrics[2].metric("账单逻辑异常数", int((logic_all["账单逻辑状态"] != "通过").sum()))
    metrics[3].metric("对账差异数", int((rec_all["匹配状态"] != "双方一致").sum()))
    metrics[4].metric("待沟通事项数", followup_count)

    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.subheader("2. 待沟通事项")
    st.caption("优先展示需要供应商、业务或财务确认的事项；正常记录不在这里重复展开。")
    for vendor_name, parts in by_vendor.items():
        display_name = display_vendor_name(vendor_name)
        total = len(parts["logic"]) + len(parts["system_only"]) + len(parts["vendor_only"])
        with st.expander(f"{display_name}｜{total} 条待沟通事项", expanded=total > 0):
            categories = [
                ("供应商账单自身逻辑异常", parts["logic"]),
                ("系统有 / 供应商账单无", parts["system_only"]),
                ("供应商账单有 / 系统无", parts["vendor_only"]),
            ]
            for category, rows in categories:
                st.markdown(f"**⚠️ {category}**")
                if rows.empty:
                    st.success("无")
                else:
                    for _, row in rows.iterrows():
                        with st.container():
                            _render_followup_card(row, category)
                            st.divider()
            if total == 0:
                st.success("该供应商本月无待沟通事项。")

    st.subheader("3. 供应商账单逻辑校验")
    st.caption("Python 负责单价、时长、倍率、计价方式、0 结算、重复编号和账期等确定性检查。")
    for vendor_name in logic_all["供应商"].drop_duplicates().tolist():
        vendor_logic = logic_all[logic_all["供应商"] == vendor_name].copy()
        display_name = display_vendor_name(vendor_name)
        exception_count = int((vendor_logic["账单逻辑状态"] != "通过").sum())
        with st.expander(f"{display_name}｜查看账单逻辑校验（{exception_count} 条需关注）"):
            logic_display = vendor_logic[
                [
                    "访谈编号", "访谈日期", "访谈类型", "项目名称", "单价",
                    "实际时长(小时)", "计价方式", "倍率", "供应商总价",
                    "理论金额", "账单逻辑状态", "账单逻辑提示",
                ]
            ].copy()
            logic_display.insert(
                logic_display.columns.get_loc("账单逻辑状态"),
                "校验结果",
                vendor_logic["账单逻辑状态"].map(_logic_display).values,
            )
            logic_display = logic_display.drop(columns=["账单逻辑状态"])
            logic_display = logic_display.rename(columns={"账单逻辑提示": "异常说明"})
            st.dataframe(logic_display, use_container_width=True, hide_index=True)

    st.subheader("4. 双向匹配与字段差异")
    consistent = rec_all[rec_all["匹配状态"] == "双方一致"]
    with st.expander(f"双方一致｜{len(consistent)} 条", expanded=False):
        st.success(f"共有 {len(consistent)} 条记录双方一致，可进入后续结算流程。")
    if field_diff.empty:
        st.success("当前无字段级差异。")
    else:
        st.markdown(f"**🔴 字段有差异｜{len(field_diff)} 条**")
        for _, row in field_diff.iterrows():
            with st.container():
                _render_field_diff_card(row)
                st.divider()

    st.subheader("5. 结果导出")
    export_payload = build_reconciliation_workbook(
        logic_all,
        rec_all,
        summary_df,
        {"field_diff": field_diff, "by_vendor": by_vendor},
    )
    st.download_button(
        "下载供应商对账结果",
        data=export_payload,
        file_name="vendor_reconciliation_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.caption("导出文件保留全量逻辑校验、双向匹配、供应商汇总、字段级差异及按供应商拆分结果。")
    st.info("本工具仅提供对账初审和沟通整理建议，最终结算与供应商沟通结果仍需由财务人员确认。")

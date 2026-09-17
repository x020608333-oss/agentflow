"""演示数据种子脚本：知识库 FAQ、CRM 客户、4 个预置 Agent、销售数据样例表。

用法（在 backend 目录下）:
    python -m scripts.seed_demo            # 首次初始化（已有 Agent 时跳过）
    python -m scripts.seed_demo --force    # 清空业务数据后重建
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import get_settings
from app.db.models import Agent, CrmCustomer, Dataset, Document
from app.db.session import get_engine, get_session_factory
from app.agents.templates import TEMPLATES

FAQ_DOCS = [
    ("产品概述", "云途 CRM 是一款面向中小企业的客户关系管理 SaaS 产品，提供客户管理、商机跟进、数据报表三大模块。"
        "支持 20 人以下团队免费使用基础版，专业版 99 元/人/月，企业版 299 元/人/月，可随时升降级。"),
    ("注册与登录", "用户可通过官网注册手机号账号，或使用微信扫码登录。忘记密码时，在登录页点击\"忘记密码\"，"
        "系统会向绑定手机号发送 6 位验证码，5 分钟内有效。连续 5 次输错密码账号将被锁定 30 分钟。"),
    ("数据导入导出", "云途 CRM 支持从 Excel（.xlsx）和 CSV 文件批量导入客户数据，单次上限 10000 行。"
        "导入模板可在\"设置-数据管理\"页面下载。所有报表和客户列表均支持一键导出 Excel。"),
    ("权限管理", "企业版支持角色权限体系：超级管理员、管理员、主管、普通成员四级。"
        "主管可以查看下属成员的全部客户数据；普通成员默认只能看到自己名下的客户。权限变更实时生效。"),
    ("数据安全", "云途 CRM 通过 ISO27001 认证，全链路 HTTPS 加密传输，数据库每日自动备份并保留 30 天。"
        "企业版支持操作审计日志，记录所有数据的增删改查行为。"),
    ("退款政策", "付费版本支持 7 天内无理由退款，需在\"设置-订单管理\"中提交退款申请，1-3 个工作日原路退回。"
        "超过 7 天或年付超过 30 天的订单不支持退款，可申请转让账号。"),
    ("发票开具", "支持开具增值税普通发票和专用发票，可在\"设置-订单管理-申请开票\"中提交。"
        "普票电子版实时发送至邮箱，专票纸质版 5 个工作日内寄出，满 1000 元免邮费。"),
    ("API 与集成", "云途 CRM 提供开放 API（REST 风格），支持客户、商机、跟进记录的读写，"
        "企业版可申请 API Key。同时提供企业微信、钉钉、飞书集成，扫码即可绑定。"),
    ("常见故障排查", "页面加载缓慢时建议先清理浏览器缓存或更换 Chrome/Edge 浏览器；"
        "数据不同步时可尝试下拉刷新或退出重新登录；如仍无法解决，请联系在线客服或拨打 400-888-9999。"),
]

CRM_CUSTOMERS = [
    ("张伟", "宏图物流", "13800000001", "方案报价", 86000, "物流运输", "2026-09-01", "关注批量导入与权限分级，物流网点多"),
    ("李娜", "星辰教育", "13800000002", "初步接触", 35000, "在线教育", "2026-08-28", "校区分散，需要多校区数据汇总报表"),
    ("王强", "蓝天制造", "13800000003", "谈判阶段", 152000, "装备制造", "2026-09-05", "对比了竞品 A，看重 API 与审计日志"),
    ("刘洋", "美家家居", "13800000004", "商机确认", 64000, "家居零售", "2026-09-08", "60 家门店，关注企业微信集成"),
    ("陈静", "绿源农业", "13800000005", "初步接触", 22000, "农业科技", "2026-07-15", "预算有限，推荐基础版"),
    ("杨帆", "远航贸易", "13800000006", "方案报价", 98000, "进出口贸易", "2026-09-10", "需要多币种与发票管理，下周出方案"),
    ("赵磊", "光速传媒", "13800000007", "成交", 46000, "广告传媒", "2026-06-20", "已签约年付，续约 2027-06，满意度高"),
    ("孙丽", "康和医疗", "13800000008", "谈判阶段", 210000, "医疗器械", "2026-09-11", "大客户，要求私有化部署，法务审核中"),
    ("周涛", "锐步体育", "13800000009", "商机确认", 57000, "体育用品", "2026-09-02", "电商+线下混合场景，关注 API 对接订单系统"),
    ("吴敏", "天润食品", "13800000010", "流失", 30000, "食品饮料", "2026-05-30", "选择了低价竞品，半年后可再触达"),
    ("郑军", "华信咨询", "13800000011", "初步接触", 72000, "管理咨询", "2026-09-12", "顾问团队移动办公多，重视手机端体验"),
    ("冯雪", "盛世文旅", "13800000012", "方案报价", 128000, "文化旅游", "2026-09-09", "景区票务+会员体系，需要定制报表"),
]


def seed(force: bool = False) -> None:
    settings = get_settings()
    settings.ensure_dirs()
    get_engine()
    db = get_session_factory()()

    if force:
        print("force 模式：清空业务数据表 ...")
        from sqlalchemy import text

        from app.db.models import Base

        with get_engine().begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
            # 清理历史遗留的表格数据集物理表（pandas to_sql 创建，不在 ORM 元数据中）
            stale = [r[0] for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tbl_%'"))]
            for name in stale:
                conn.execute(text(f'DROP TABLE "{name}"'))
            if stale:
                print(f"  已清理 {len(stale)} 张遗留数据表")

    # ---------- Agents ----------
    if db.query(Agent).count() > 0:
        print("已存在 Agent 数据，跳过（使用 --force 重建）。")
    else:
        datasets_by_hint = {}

        # 客服知识库（文档）
        ds_faq = Dataset(name="客服知识库", description="云途 CRM 产品常见问题 FAQ", kind="docs")
        db.add(ds_faq)
        db.flush()
        from app.rag.ingestion import ingest_document, ingest_table
        import tempfile

        for title, content in FAQ_DOCS:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(f"【{title}】\n{content}")
                tmp_path = Path(f.name)
            ingest_document(db, settings, ds_faq, tmp_path, f"{title}.txt")
            tmp_path.unlink(missing_ok=True)
        doc_count = db.query(Document).filter(Document.dataset_id == ds_faq.id).count()
        print(f"✓ 客服知识库：{doc_count} 篇文档")
        datasets_by_hint["faq"] = ds_faq.id

        # 销售数据样例表
        rng = np.random.default_rng(42)
        dates = pd.date_range("2026-06-01", periods=180, freq="D")
        regions = ["华东", "华南", "华北", "西南", "东北"]
        products = ["CRM专业版", "CRM企业版", "增值服务包"]
        rows_n = 600
        df = pd.DataFrame({
            "日期": rng.choice(dates, rows_n),
            "地区": rng.choice(regions, rows_n),
            "产品": rng.choice(products, rows_n, p=[0.5, 0.3, 0.2]),
            "销量": rng.integers(1, 30, rows_n),
            "金额": np.round(rng.uniform(500, 30000, rows_n), 2),
        })
        upload_path = settings.uploads_dir / "销售数据样例.csv"
        df.to_csv(upload_path, index=False, encoding="utf-8-sig")

        ds_sales = Dataset(name="销售数据样例", description="2026 年 6-11 月模拟销售流水，供数据分析 Agent 使用", kind="table")
        db.add(ds_sales)
        db.flush()
        ingest_table(db, settings, ds_sales, upload_path, "销售数据样例.csv")
        print(f"✓ 销售数据样例表：{len(df)} 行（{upload_path.name}）")
        datasets_by_hint["sales_table"] = ds_sales.id

        # 4 个预置 Agent
        for key, tpl in TEMPLATES.items():
            ds_ids = [datasets_by_hint[tpl["dataset_hint"]]] if tpl.get("dataset_hint") else []
            agent = Agent(
                name=tpl["name"], emoji=tpl["emoji"], description=tpl["description"],
                agent_type=tpl["agent_type"], system_prompt=tpl["system_prompt"],
                tools=tpl["tools"], dataset_ids=ds_ids, llm_config=tpl["llm_config"],
                pipeline=tpl["pipeline"], max_iterations=8 if tpl["agent_type"] == "react" else 4,
            )
            db.add(agent)
        print("✓ 预置 Agent：客服助手 / 销售顾问 / 行业研究员 / 数据分析师")

    # ---------- CRM ----------
    if db.query(CrmCustomer).count() == 0:
        for row in CRM_CUSTOMERS:
            db.add(CrmCustomer(name=row[0], company=row[1], phone=row[2], stage=row[3],
                               deal_size=row[4], industry=row[5], last_contact=row[6], notes=row[7]))
        print(f"✓ CRM 客户：{len(CRM_CUSTOMERS)} 条")

    db.commit()
    db.close()
    print("\n初始化完成。启动服务： cd backend && python -m app.main")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="清空业务数据后重建")
    args = parser.parse_args()
    try:
        seed(force=args.force)
    except Exception as exc:
        print(f"初始化失败: {exc}", file=sys.stderr)
        raise

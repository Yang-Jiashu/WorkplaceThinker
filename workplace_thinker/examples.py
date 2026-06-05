"""
WorkplaceThinker 使用示例

这个示例展示了如何使用记忆系统帮助职场新人：
1. 第一天：了解团队情况
2. 第二天：遇到问题，系统回忆之前的分析
3. 第三天：识别风险模式
"""

import asyncio
from typing import Optional

# 导入我们的组件
from workplace_thinker import WorkplaceInsightHarness


async def example_new_employee_journey():
    """
    模拟一个职场新人的三天经历
    """
    print("=" * 60)
    print("WorkplaceThinker 示例：帮助职场新人快速融入")
    print("=" * 60)
    
    # 初始化 harness，启用记忆系统
    harness = WorkplaceInsightHarness(
        session_id="new_employee_zhang",
        enable_memory=True
    )
    
    print(f"\n✅ 记忆系统已启动，会话ID: {harness.memory.session_id if harness.memory else 'N/A'}")
    
    # ========== 第一天：新人刚入职 ==========
    print("\n" + "=" * 60)
    print("📅 第一天：刚入职，了解团队")
    print("=" * 60)
    
    day1_info = """
    组织架构：
    - 张伟 - 产品负责人 - Product团队 - 汇报王强
    - 王强 - 部门经理 - Platform团队
    - 李娜 - 资深同事 - Product团队 - 汇报王强
    - 我 - 新人 - Product团队 - 汇报张伟
    
    今天的聊天记录：
    张伟：欢迎加入！先熟悉一下这个项目，不用太着急
    李娜：（私下）你小心点，张伟经常让新人先做，最后出问题了才说流程不对
    张伟：哦对了，这个需求先做起来，后面再补审批流程
    """
    
    result1 = await harness.analyze_information(
        information=day1_info,
        question="第一天入职，我应该注意什么？"
    )
    
    print(f"\n📊 分析结果摘要：")
    print(f"   {result1['summary']}")
    
    print(f"\n⚠️  识别到的风险：")
    for risk in result1['risks'][:3]:
        print(f"   - {risk['title']} (严重度: {risk['severity']:.2f})")
        print(f"     建议: {risk['suggestion']}")
    
    # 查看记忆统计
    stats1 = harness.get_memory_stats()
    print(f"\n💾 记忆状态：")
    print(f"   已记忆人物: {stats1.get('person_profiles_count', 0)}")
    print(f"   已记录模式: {stats1.get('patterns_count', 0)}")
    
    # ========== 第二天：遇到问题 ==========
    print("\n" + "=" * 60)
    print("📅 第二天：遇到问题，系统回忆之前的分析")
    print("=" * 60)
    
    day2_info = """
    今天的情况：
    我按照张伟说的开始做需求了
    李娜看到了，私下提醒我说：你忘了？上次那个新人也是这样，最后背锅了
    张伟刚才又说：进度要加快，审批的事我来搞定
    我有点担心，想确认一下责任边界
    """
    
    result2 = await harness.analyze_information(
        information=day2_info,
        question="我现在该怎么办？"
    )
    
    print(f"\n📊 分析结果摘要：")
    print(f"   {result2['summary']}")
    
    # 检查是否找到了相似历史场景
    if 'similar_scenarios' in result2:
        print(f"\n🔍 发现相似历史场景：")
        for scenario in result2['similar_scenarios']:
            print(f"   - {scenario['summary'][:80]}...")
    
    print(f"\n💡 推荐确认的问题：")
    for q in result2['recommended_questions'][:3]:
        print(f"   - {q}")
    
    # 查看某个人物的画像
    zhang_profile = harness.get_person_profile("张伟")
    if zhang_profile:
        print(f"\n👤 张伟的画像：")
        print(f"   职位: {zhang_profile['title']}")
        print(f"   团队: {zhang_profile['team']}")
        print(f"   风险信号: {', '.join(zhang_profile['risk_signals'][:5])}")
    
    # ========== 第三天：识别模式 ==========
    print("\n" + "=" * 60)
    print("📅 第三天：系统识别出重复模式")
    print("=" * 60)
    
    day3_info = """
    最新情况：
    王强问起这个项目，说怎么没看到审批流程
    张伟说：新人在负责，我让他先做的，我来补流程
    李娜告诉我：张伟之前也跟王强说过"我来搞定"，但最后都没搞定
    我现在很担心自己背锅
    """
    
    result3 = await harness.analyze_information(
        information=day3_info,
        question="这是不是一个模式？我该如何保护自己？"
    )
    
    print(f"\n📊 分析结果摘要：")
    print(f"   {result3['summary']}")
    
    # 查看记忆中的模式
    if 'memory_context' in result3:
        patterns = result3['memory_context'].get('relevant_patterns', [])
        if patterns:
            print(f"\n🔮 识别到的模式：")
            for p in patterns:
                print(f"   - {p['name']}: {p['description']} (置信度: {p['confidence']:.2f})")
    
    # ========== 导出记忆（可选） ==========
    print("\n" + "=" * 60)
    print("💾 导出记忆供后续使用")
    print("=" * 60)
    
    memory_export = harness.export_memory()
    if memory_export:
        print(f"\n📋 记忆摘要：")
        print(f"   会话ID: {memory_export['session_id']}")
        print(f"   人物画像: {len(memory_export['person_profiles'])} 人")
        print(f"   模式: {len(memory_export['patterns'])} 个")
        print(f"   历史分析: {memory_export['historical_analyses_count']} 次")
    
    print("\n" + "=" * 60)
    print("✅ 示例完成！")
    print("=" * 60)
    print("\n💡 核心价值：")
    print("   1. 帮助新人识别职场中不易察觉的风险")
    print("   2. 通过记忆积累，识别重复出现的模式")
    print("   3. 提供中立、证据为基础的建议，而不是阴谋论")
    print("   4. 推荐具体的确认问题，帮助新人保护自己")


async def example_mini_scenarios():
    """
    一些常见的职场新人场景示例
    """
    harness = WorkplaceInsightHarness(enable_memory=True)
    
    scenarios = [
        {
            "name": "场景1：不确定谁是真正的决策者",
            "info": """
            王经理说这个事情你找李主管
            李主管说你还是听王经理的
            王经理又说这种小事你问李主管就行
            """,
            "question": "到底谁负责？"
        },
        {
            "name": "场景2：信息不对称",
            "info": """
            大家在群里讨论某个事，但好像都知道背景
            我完全听不懂，他们也不解释
            李姐私下说：别问了，这是之前就定好的
            """,
            "question": "我该怎么了解情况？"
        },
        {
            "name": "场景3：承诺变更",
            "info": """
            上周张哥说：这个周五交就行
            今天张哥说：你怎么还没做好？周三就要！
            我说：你上周说周五的...
            张哥说：我什么时候说过？你记错了
            """,
            "question": "我该怎么避免这种情况？"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n\n" + "=" * 60)
        print(f"🎯 {scenario['name']}")
        print("=" * 60)
        
        result = await harness.analyze_information(
            information=scenario['info'],
            question=scenario['question'],
            use_llm=False  # 只用规则，快速演示
        )
        
        print(f"\n📝 分析：")
        print(f"   {result['summary']}")
        
        if result['risks']:
            print(f"\n⚠️  风险提示：")
            for risk in result['risks'][:2]:
                print(f"   - {risk['title']}")
                print(f"     建议：{risk['suggestion']}")


if __name__ == "__main__":
    print("🚀 WorkplaceThinker 记忆系统示例\n")
    
    # 运行新人历程示例
    asyncio.run(example_new_employee_journey())
    
    # 可选：运行其他小场景
    # asyncio.run(example_mini_scenarios())

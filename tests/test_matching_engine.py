# tests/test_matching_engine.py
    def test_matching_accuracy():
        # 1. 准备测试数据集（含专家标注的黄金标准）
        test_cases = load_test_dataset("data/test/match_test_cases.json")

        # 2. 运行匹配引擎生成预测结果
        predictions = []
        for student, target_job in test_cases:
            result = matching_engine.calculate_overall_match(student, job_profiles[target_job])
            predictions.append((student.id, target_job, result["overall_score"]))

        # 3. 调用评估接口计算准确率
        accuracy = evaluate_match_accuracy(predictions, test_cases["expert_labels"])

        # 4. 断言验证是否达标（项目要求≥80%）
        assert accuracy >= 0.8, f"匹配准确率{accuracy:.2%}未达标准！"
        print(f"✅ 人岗匹配准确率验证通过: {accuracy:.2%}")
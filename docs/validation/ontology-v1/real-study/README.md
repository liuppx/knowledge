# 运营本体 V1 真实研究模板

本目录只保存空模板和字段说明，不保存真实合同、客户、员工、商业金额或其他敏感数据。

使用顺序：

1. 在受控环境中复制模板；
2. 完成原始数据授权和脱敏；
3. 填写 `data_inventory.csv`；
4. 冻结 `competency_questions.csv` 的 development/test split；
5. 两名标注者分别填写对象身份和断言金标；
6. 使用 `adjudication_log.csv` 记录分歧；
7. 运行各实验组并写入 `experiment_results.csv`；
8. 根据[实证研究方案](../../../运营本体V1实证研究方案.md)计算指标和作出决策。

真实数据文件和填充后的敏感模板不得提交到公开仓库。

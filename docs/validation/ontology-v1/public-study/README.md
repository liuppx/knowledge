# 运营本体 V1 公开数据代理验证

本目录不提交第三方原始合同或公共 API 的完整响应。公开数据仅用于验证研究方法、数据可得性和技术机制，不能替代真实用户需求、真实权限边界或业务维护成本证据。

运行：

```bash
python scripts/validate_public_ontology_data.py \
  --cache-dir /tmp/knowledge-public-validation \
  --output /tmp/ontology-public-validation.json
```

脚本会：

1. 按固定 Git commit 下载 ContractNLI 和 CUAD，并校验 SHA-256；
2. 验证所有人工 Evidence span/answer offset 可以回放到原文；
3. 从 USAspending 读取固定 Award 及其修改交易，验证交易金额能重算当前 Award；
4. 从 TED 读取固定修改通知及前一通知，验证买方、品类、标题和版本关系；
5. 从 GLEIF 读取固定 LEI，验证当前法定名称、历史名称和登记机关 crosswalk；
6. 输出机器可读 JSON，并在任一客观检查失败时返回非零退出码。

完整解释、局限和下一阶段门槛见[公开数据代理验证报告](../../../运营本体V1公开数据代理验证.md)。

# TG_bot 技术规范

## 输入解析规范

### 位置解析格式 (Positional Parsing)

**完整格式**：
```
[Payee] [Narration] [DiscountName] [DiscountAmount] [Amount] [Currency] [@@ ConvertedAmount ConvertedCurrency] [AssetAlias]
```

**字段说明**：

| 字段 | 必需 | 说明 | 示例 |
|------|------|------|------|
| Payee | 是 | 交易对手/商户 | `稻禾风`, `滴滴` |
| Narration | 可选 | 交易描述 | `晚饭`, `打车` |
| DiscountName | 可选 | 优惠别名 | `优惠`, `返现` |
| DiscountAmount | 可选 | 优惠金额 | `3.5` |
| Amount | 是 | 实付金额 | `32.55` |
| Currency | 可选 | 货币代码 | `CNY`, `HKD` |
| @@ | 可选 | 汇率标记 | `@@` |
| ConvertedAmount | 可选 | 转换后金额 | `15.56` |
| ConvertedCurrency | 可选 | 转换货币 | `HKD` |
| AssetAlias | 是 | 资产账户别名 | `citic`, `za`, `wx` |

### 解析优先级

1. **位置解析**：最后一个 token 必须是有效的资产别名
2. **金额解析**：支持整数和小数
3. **优惠检测**：在配置中查找 `Discount` 或 `Rebate` 关键字
4. **多币种**：检测 `@@` 分隔符

### 特殊规则

- 当存在 `@@` 转换且优惠别名为 `优惠` 时，自动映射到 `优惠hk` (HK Discount)
- 优惠金额始终为负数记入账本
- 资产账户金额自动平衡

---

## 账户别名规范

### 定义位置

1. **Beancount 元数据**（优先）：
   ```beancount
   2019-01-01 open Assets:CN:DebitCard:CITIC:1709
     alias: "1709, zx, citic"
   ```

2. **settings.yaml**（回退）：
   ```yaml
   aliases:
     "citic": "Assets:CN:DebitCard:CITIC:1709"
   ```

### 别名规则

- 大小写不敏感：`CITIC` = `citic` = `Citic`
- 支持逗号分隔多别名
- 资产别名只匹配 `Assets:` 和 `Liabilities:` 开头的账户
- 支出别名只匹配 `Expenses:` 和 `Income:` 开头的账户

### 歧义处理

当一个别名对应多个账户时：
1. 显示选择按钮列表
2. 用户点击选择
3. 继续处理流程

---

## Beancount 输出规范

### 基础交易

```beancount
2026-01-15 * "商户名" "交易描述"
    Expenses:Category                       {金额} {货币}
    Assets:PaymentAccount                  -{金额} {货币}
```

### 带优惠交易

```beancount
2026-01-15 * "商户名" "交易描述"
    Expenses:Category                       {金额} {货币}
    Expenses:XX:Discount                   -{优惠金额} {货币}
    Assets:PaymentAccount                  -{实付金额} {货币}
```

### 多币种交易

```beancount
2026-01-15 * "商户名" "交易描述"
    Expenses:Category                       {原币金额} {原币} @@ {转换金额} {目标币}
    Expenses:XX:Discount                   -{优惠金额} {目标币}
    Assets:PaymentAccount                  -{实付金额} {目标币}
```

### 格式化规则

- 账户名左对齐，宽度 40 字符
- 金额右对齐，保留 2 位小数
- 收入账户金额自动取负

---

## AI 提示词规范

### 交易详情提取

**输入**：用户描述文本 + 候选账户列表

**输出**：JSON 对象
```json
{
  "payee": "商户名",
  "narration": "交易描述",
  "account": "Expenses:Category"
}
```

**解析规则**：
- 如果描述中有明确商户，提取为 payee
- 如果只有活动描述（如 "Taxi"），payee 留空
- narration 描述交易内容/类别
- account 从候选列表中选择最匹配的

### 示例映射

| 输入 | Payee | Narration |
|------|-------|-----------|
| `Lunch McDonalds` | McDonalds | Lunch |
| `晚饭 稻禾风` | 稻禾风 | 晚饭 |
| `Taxi` | (空) | Taxi |
| `Subway 25` | Subway | Food |

---

## 错误处理规范

### API 限流 (429)

1. 尝试轮换 API Key
2. 如无备用 Key，指数退避重试
3. 最大重试 3 + Key数量 次
4. 失败后返回 `Expenses:Unknown`

### 解析失败

1. 无法识别金额：返回错误提示
2. 无法识别资产别名：回退到 `cash` 别名
3. 会话过期：提示用户重新输入

### 歧义冲突

1. 资产歧义：显示选择按钮
2. 优惠歧义：显示选择按钮
3. 用户取消：终止交易

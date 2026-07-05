# Sub-Store IP Geo Rename Script

> 文件：`tools/ip-geo-outbound-rename.js`

这个脚本用于 **Sub-Store Script Operator**，把节点名称重命名为：

`国家 | 出口国`

并支持：

- 自动从节点 `server/address/host` 解析真实 IP
- 根据真实 IP 查询归属地
- 可选检测本机真实出口归属地并追加到名称中
- 自动生成国旗 emoji
- 本地缓存，减少重复 API 请求

---

## 脚本参数

通过 Sub-Store 的 `Script Operator` 的 URL fragment 或 `arguments` 传参：

| 参数 | 作用 | 默认值 |
|---|---|---|
| `nm` | 找不到归属地时是否保留节点 | `false` |
| `out` | 是否追加出口归属地 | `false` |
| `sep` | 国家名称之间的分隔符 | ` | ` |
| `outSep` | 出口国前缀分隔符 | 同 `sep` |
| `debug` | 打印调试日志 | `false` |
| `city` | 是否在国家后追加城市 | `false` |
| `countryCode` | 使用国家代码而不是国家全名 | `false` |

---

## 推荐配置

### 仅按国家重命名

```text
https://raw.githubusercontent.com/mathlife/beancount_tgbot/main/tools/ip-geo-outbound-rename.js#nm=true
```

### 按国家重命名，并追加出口国

```text
https://raw.githubusercontent.com/mathlife/beancount_tgbot/main/tools/ip-geo-outbound-rename.js#nm=true&out=true
```

### 自定义分隔符

```text
https://raw.githubusercontent.com/mathlife/beancount_tgbot/main/tools/ip-geo-outbound-rename.js#nm=true&out=true&sep=%20|%20&outSep=%20|%20
```

---

## 在 Sub-Store 中怎么加

在目标订阅或组合的 `process` 里添加一个 `Script Operator`：

```json
{
  "type": "Script Operator",
  "args": {
    "content": "https://raw.githubusercontent.com/mathlife/beancount_tgbot/main/tools/ip-geo-outbound-rename.js#nm=true&out=true&sep=%20|%20&outSep=%20|%20",
    "mode": "link",
    "arguments": {
      "nm": "true",
      "out": "true",
      "sep": " | ",
      "outSep": " | "
    }
  },
  "customName": "IP Geo Rename",
  "disabled": false
}
```

建议把它放在：

1. `Quick Setting Operator` 之后
2. `Handle Duplicate Operator` 之前

如果你的流程里还要做去重，通常顺序是：

1. `Quick Setting Operator`
2. `Script Operator`（本脚本）
3. `Handle Duplicate Operator`
4. 其他后处理

---

## 命名规则

脚本会把节点命名成类似这样：

```text
🇺🇸 United States | 🇨🇦 Canada
🇩🇪 Germany | 🇳🇱 Netherlands
```

其中：

- 前半段 = 节点真实入口 IP 的归属地
- 后半段 = 本机真实出口 IP 的归属地
- 国旗由国家代码自动转换

---

## 缓存说明

脚本内置两层缓存：

- `GEO_CACHE`：缓存 IP 的地理信息
- `RESOLVE_CACHE`：缓存域名解析结果

这样同一次执行里重复出现的节点会少很多外部请求。

---

## 常见问题

### 1. 节点没有重命名

通常是以下原因之一：

- 节点 `server/address/host` 为空
- 域名解析失败
- Geo API 请求失败
- `nm=false` 且没有匹配到国家，节点被直接丢弃

### 2. 出口国没有显示

检查：

- `out=true` 是否开启
- 本机是否能访问 `api.ipify.org / ifconfig.me / ident.me`
- Geo API 是否正常返回

### 3. 国旗不对

脚本根据国家代码自动生成 emoji，前提是 Geo API 返回了有效的两字母国家码。

---

## 文件位置

- 脚本本体：`tools/ip-geo-outbound-rename.js`
- GitHub 路径：`main/tools/ip-geo-outbound-rename.js`

---

## 版本建议

如果你后面要继续增强，我建议加这三项：

- 缓存 TTL
- 更多 Geo API fallback
- 可配置名称模板

# Sing-box Subscriber 订阅合并清洗与安全分发服务

一个开箱即用的、专注于安全、极简与规范化的 Sing-box 订阅拉取、合并清洗与分发工具。

本项目专门解决标准 Sing-box 客户端（v1.13.14+）由于配置中包含自定义非标准字段（如 `"filter"`）导致的解析报错与启动闪退问题，并提供单路径防爆破的安全订阅分发。

---

## ✨ 核心特性

- **🚀 双架构支持**：基于 GitHub Actions 自动构建并打包 `linux/amd64` (x86_64) 和 `linux/arm64` 镜像。
- **🔒 安全零泄露**：废除传统的冗余 `/sub` 路由，采用**单级安全 Token 路径**（如 `/your_secure_token/1.json`）。在 Nginx 反代端可只放行此路径，其余未知路径探测扫描一律返回 404。
- **🧹 规范化清洗**：自动匹配并剥离删除自定义的 `"filter"` 字段，替换 `"{all}"` 占位符为匹配节点 tag，完全兼容标准 Sing-box v1.13.14+ 内核规范。
- **🔌 Hosts 静态解析替换**：支持通过一个 `hosts` 映射文件，自动将实体节点配置中的 `"server"` 域名替换为指定的 IP 地址（支持 IPv4/IPv6）。
- **🛡️ 智能 TLS SNI 保护**：当节点的域名被替换为 IP 后，若节点启用了 TLS 且未配置 SNI，脚本会自动补充原域名至 `tls.server_name`，确保 TLS 证书校验能够正常通过。
- **🛡️ 空策略组安全兜底**：若特定分组（例如台湾自动组）无匹配节点，会自动注入 `["🎯 全球直连"]` 兜底，防止客户端因策略组为空而启动失败。
- **🔄 24小时定时更新**：默认 24 小时更新一次。**容器拉起或重启瞬间会立刻触发一次更新**，无需等待。

---

## 📂 目录结构规划

为了保持系统一致性，所有数据和配置文件均统一挂载在宿主机的 `/opt/singbox-subscriber` 目录下。

```text
/opt/singbox-subscriber/
├── urls                  # [手动创建] 存放你需要拉取的原始订阅链接，一行一个
├── hosts                 # [自动生成] 域名与 IP 的映射表，用于将节点域名静态替换为指定 IP
├── templates/            # [手动创建] 存放你的 Sing-box 配置文件模板（如 1.json, 2.json）
└── output/               # [自动生成] 合并清洗完毕、供客户端下载的完美配置文件
```

---

## 🛠️ 详细部署步骤

### 第一步：初始化服务器目录

在你的服务器终端执行以下命令，创建所需目录：

```bash
# 1. 创建挂载子目录
mkdir -p /opt/singbox-subscriber/templates
mkdir -p /opt/singbox-subscriber/output

# 2. 写入你的订阅数据源链接列表（一行一个，去掉注释）
cat <<EOF > /opt/singbox-subscriber/urls
https://sub.example.com/api/v1/client/subscribe?token=your_original_sub_token
https://another-sub-provider.net/subscribe
EOF

# 3. 创建并编辑你的模板文件（将你的标准 Sing-box 基础配置文件粘贴进去）
nano /opt/singbox-subscriber/templates/1.json
```

---

### 第二步：配置域名与 IP 映射（可选）

如果你需要将获取到的节点中的特定域名替换为直连 IP，可以直接编辑挂载目录下的 `hosts` 文件。

```bash
# 编辑映射文件
nano /opt/singbox-subscriber/hosts
```

**配置格式（域名在前，IP在后，支持多个空格或制表符作为间隔，支持 IPv4/IPv6）：**
```text
# 原始域名             # 目标替换IP
node1.example.com      192.0.2.1
node2.example.com      2001:db8::1
```
*注：修改此文件后，只需重启一次容器即可立刻应用替换结果。*

---

### 第三步：配置 Docker Compose 并运行

在服务器任意部署目录下创建 `docker-compose.yml` 文件：

```yaml
services:
  singbox-subscriber:
    image: ghcr.io/adwzlad/singbox-subscriber:latest # 替换为你 GitHub 自动打包出来的真实镜像名
    container_name: singbox-subscriber
    restart: always # 实现“重启/开机即触发更新”
    ports:
      - "50000:50000"
    volumes:
      - /opt/singbox-subscriber:/opt/singbox-subscriber
    environment:
      - SUB_TOKEN=your_secure_token_here   # 你的极简安全 Token（用于客户端拉取配置，建议设长、设复杂）
      - UPDATE_INTERVAL=86400  # 定时自动更新间隔（单位秒，86400秒 = 24小时）
```

**启动服务：**
```bash
docker compose up -d
```

---

### 第四步：验证运行状态与日志

你可以实时查看容器日志来确认节点拉取、域名替换和合并清洗是否成功：

```bash
docker logs -f singbox-subscriber
```

**期待的正常输出：**
```text
--------------------------------------------------
订阅分发服务已启动，完美兼容 Sing-box v1.13.14 规范.
极简安全下载根路径: /your_secure_token_here/
--------------------------------------------------
[更新] 开始节点合并与规范化清洗...
[下载] 正在请求: https://sub.example.com/api/v1/client/subscribe?token=...
[Hosts] 已加载 2 条映射规则，开始节点地址重定向...
  └─ [SNI 保护] 已自动为节点 [US-Premium-01] 补充 tls.server_name = node1.example.com
[Hosts] 成功完成 1 处域名到 IP 的静态替换
[成功] 已生成规范配置文件: 1.json
```

---

## 🔒 Nginx 安全反向代理配置

通过以下配置，只有携带你精确安全 Token 的流量才能访问到后台服务。其他任意探测、扫描行为一律由 Nginx 直接拒绝并返回 404，极大地提升了公网环境下的隐蔽性：

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com; # 替换为你的公网域名

    # SSL 证书配置
    ssl_certificate /etc/nginx/ssl/yourdomain.pem;
    ssl_certificate_key /etc/nginx/ssl/yourdomain.key;

    # 🌟 仅放行精确匹配到你安全 Token 的请求路径
    location /your_secure_token_here/ {
        proxy_pass http://127.0.0.1:50000/your_secure_token_here/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 🌟 其它所有路径的流量一律直接返回 404，拒绝任何主动探测
    location / {
        return 404;
    }
}
```

---

## 📲 客户端订阅配置地址

配置完成后，你可以将生成的配置文件地址直接填入你的各个平台 Sing-box 客户端中：

- **`1.json` 下载地址**：`https://yourdomain.com/your_secure_token_here/1.json`
- **`2.json` 下载地址**：`https://yourdomain.com/your_secure_token_here/2.json`

---

## 📜 许可说明

本项目采用 MIT 许可证开源。请遵守你所在国家/地区的法律法规，并合理、合规、合法地使用本项目。

# Sing-box Subscriber 订阅合并分发服务

一个开箱即用的、专注于安全和规范化的 Sing-box 订阅合并与清洗工具。

该项目旨在解决标准 Sing-box 客户端（v1.13.14+）由于配置中包含自定义字段（如 `filter`）导致的启动报错或闪退问题，并提供单路径防爆破的安全分发。

---

## ✨ 核心特性

- **🚀 双架构支持**：基于 GitHub Actions 自动构建打包 `linux/amd64` 和 `linux/arm64`。
- **🔒 安全零泄露**：采用**单级安全 Token 路径**（如 `/YuXXXXBwXj/1.json`）。在 Nginx 反代端可只放行此路径，其余未知路径探测扫描一律返回 404。
- **🧹 规范化清洗**：自动匹配并剥离删除自定义的 `"filter"` 字段，替换 `"{all}"` 占位符为匹配节点 tag，完全兼容标准 Sing-box v1.13.14+ 内核规范。
- **🛡️ 空策略组兜底**：若特定分组（例如台湾自动组）无匹配节点，会自动注入 `["🎯 全球直连"]` 兜底，防止客户端因策略组为空而启动失败。
- **🔄 24小时定时更新**：默认 24 小时更新一次。**容器拉起或重启瞬间会立刻触发一次更新**，无需等待。

---

## 📂 目录结构规划

为了保持系统一致性，所有数据均统一挂载在宿主机的 `/opt/singbox-subscriber` 目录下。

```text
/opt/singbox-subscriber/
├── urls                  # [手动创建] 存放你需要拉取的原始订阅链接，一行一个
├── templates/            # [手动创建] 存放你的 Sing-box 配置文件模板（如 1.json, 2.json）
└── output/               # [自动生成] 合并清洗完毕、供客户端下载的完美配置文件
```

---

## 🛠️ 详细部署步骤

### 第一步：初始化服务器目录与配置

在你的服务器终端执行以下命令，创建目录并配置数据源：

```bash
# 1. 创建挂载子目录
mkdir -p /opt/singbox-subscriber/templates
mkdir -p /opt/singbox-subscriber/output

# 2. 写入你的订阅节点数据源链接列表（一行一个，随时可编辑此文件进行增减）
cat <<EOF > /opt/singbox-subscriber/urls
https://xxxxxx12.xyz/sui/subscribe-link-1
https://another-domain.com/sui-nodes-raw
EOF

# 3. 创建并编辑你的 1.json 模板（将你的 Sing-box 基础配置粘贴进去）
nano /opt/singbox-subscriber/templates/1.json
```

---

### 第二步：配置 Docker Compose 并运行

在服务器任意部署目录下创建 `docker-compose.yml` 文件：

```yaml
services:
  singbox-subscriber:
    image: ghcr.io/adwzlad/singbox-subscriber:latest # 替换为你 GitHub 自动打包出来的真实镜像名
    container_name: singbox-subscriber
    restart: always # 宿主机重启/容器重启时，会立刻在第一时间跑一次拉取与合并
    ports:
      - "50000:50000"
    volumes:
      - /opt/singbox-subscriber:/opt/singbox-subscriber
    environment:
      - SUB_TOKEN=YuXXXXBwXj   # 你的极简安全 Token（自定义）
      - UPDATE_INTERVAL=86400  # 定时自动更新间隔（单位秒，86400秒 = 24小时）
```

**启动服务：**
```bash
docker compose up -d
```

---

### 第三步：验证运行状态与日志

你可以实时查看容器日志来确认节点拉取和合并清洗是否成功：

```bash
docker logs -f singbox-subscriber
```

**期待的正常输出：**
```text
--------------------------------------------------
订阅分发服务已启动，完美兼容 Sing-box v1.13.14 规范.
极简安全下载根路径: /YuXXXXBwXj/
--------------------------------------------------
[更新] 开始节点合并与规范化清洗...
[下载] 正在请求: https://xxxxxx12.xyz/subscribe-link-1
[成功] 已生成规范配置文件: 1.json
```

---

## 🔒 Nginx 安全反向代理配置

通过以下配置，只有携带你精确安全 Token 的流量才能访问到后台服务，其他恶意扫描或探测一律被 Nginx 阻断并返回 404，极大地提升了安全性：

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com; # 替换为你的公网域名

    # SSL 证书配置
    ssl_certificate /etc/nginx/ssl/yourdomain.pem;
    ssl_certificate_key /etc/nginx/ssl/yourdomain.key;

    # 🌟 仅允许匹配到你安全 Token 的请求转发到容器
    location /YuXXXXBwXj/ {
        proxy_pass http://127.0.0.1:50000/YuXXXXBwXj/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 🌟 其它所有路径的流量一律返回 404，拒绝任何主动探测
    location / {
        return 404;
    }
}
```

---

## 📲 客户端订阅配置地址

配置完成后，你可以将生成的配置文件地址直接填入你的各个平台 Sing-box 客户端中：

- **`1.json` 下载地址**：`[https://yourdomain.com/YuXXXXBwXj/1.json](https://yourdomain.com/YuXXXXBwXj/1.json)`
- **`2.json` 下载地址**：`[https://yourdomain.com/YuXXXXBwXj/2.json](https://yourdomain.com/YuXXXXBwXj/2.json)`

---

## 📜 许可说明

本项目采用 MIT 许可证开源。请遵守你所在国家/地区的法律法规，并合理、合规、合法地使用本项目。

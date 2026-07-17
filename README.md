# Sing-box Subscriber 订阅合并分发服务

一个专注于安全、极简与规范化的 Sing-box 订阅合并与清洗工具。

本项目专门解决标准 Sing-box 客户端（v1.13.14+）由于配置中包含自定义字段（如 `filter`）导致的启动报错或闪退问题，并提供单路径防爆破的安全分发。

---

## ✨ 核心特性

- **🚀 双架构支持**：基于 GitHub Actions 自动构建打包 `linux/amd64` 和 `linux/arm64`。
- **🔒 安全零泄露**：采用**单级安全 Token 路径**（如 `/YuXXXXBwXj/1.json`）。在 Nginx 反代端可只放行此路径，其余扫描一律返回 404。
- **🧹 规范化清洗**：自动剥离并删除自定义的 `"filter"` 字段，完全兼容标准 Sing-box v1.13.14+ 内核。
- **🛡️ 空策略组兜底**：若特定分组（例如台湾自动组）无匹配节点，会自动注入 `["🎯 全球直连"]` 兜底，防止客户端启动失败。
- **🔄 24小时定时更新**：默认 24 小时更新一次。**容器拉起或重启瞬间会立刻触发一次更新**，无需等待。

---

## 📂 宿主机文件结构

所有数据均挂载在宿主机的 `/opt/singbox-subscriber` 目录下。

```text
/opt/singbox-subscriber/
├── urls                  # [手动创建] 存放你需要拉取的原始订阅链接，一行一个
├── templates/            # [手动创建] 存放你的 Sing-box 配置文件模板（如 1.json, 2.json）
└── output/               # [自动生成] 合并清洗完毕、供客户端下载的完美配置文件
```

---

## 🛠️ 服务器部署指南

### 1. 初始化服务器目录与配置
在你的服务器终端执行：

```bash
# 创建挂载子目录
mkdir -p /opt/singbox-subscriber/templates
mkdir -p /opt/singbox-subscriber/output

# 写入你的订阅节点数据源链接列表（一行一个）
cat <<EOF> /opt/singbox-subscriber/urls
[https://xxxxxx12.xyz/sui/subscribe-link-1](https://xxxxxx12.xyz/sui/subscribe-link-1)
[https://another-domain.com/sui-nodes-raw](https://another-domain.com/sui-nodes-raw)
EOF

# 创建并编辑你的 1.json 模板
nano /opt/singbox-subscriber/templates/1.json
```

### 2. 运行 Docker-Compose
在项目目录下创建 `docker-compose.yml` 启动服务：

```bash
docker compose up -d
```

### 3. 查看实时合并日志
```bash
docker logs -f singbox-subscriber
```

---

## 🔒 Nginx 安全反向代理配置

通过以下配置，可完美隐藏分发端口。所有未知探测流量一律返回 404：

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com; # 替换为你的公网域名

    ssl_certificate /etc/nginx/ssl/yourdomain.pem;
    ssl_certificate_key /etc/nginx/ssl/yourdomain.key;

    # 仅允许匹配到安全 Token 的请求转发到容器
    location /YuXXXXBwXj/ {
        proxy_pass [http://127.0.0.1:50000/YuXXXXBwXj/](http://127.0.0.1:50000/YuXXXXBwXj/);
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        return 404;
    }
}
```

---

## 📲 客户端订阅配置地址

- **`1.json` 地址**：`https://yourdomain.com/YuXXXXBwXj/1.json`
- **`2.json` 地址**：`https://yourdomain.com/YuXXXXBwXj/2.json`

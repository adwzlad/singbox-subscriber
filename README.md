第一步：初始化服务器目录
在你的 VPS 服务器终端执行以下命令，创建所需目录并配置数据源：

Bash
# 1. 创建挂载子目录
mkdir -p /opt/singbox-subscriber/templates

mkdir -p /opt/singbox-subscriber/output

# 2. 写入你的订阅节点数据源链接列表（一行一个，去掉注释）
nano /opt/singbox-subscriber/urls
如:
https://yourdomain.com/sub/1.json

https://yourdomain.com/sub/A.json

# 3. 将你的 Sing-box 模板文件（如 1.json）放入 templates 文件夹中
# 示例：创建并编辑你的 1.json 模板

第二步：配置 Docker Compose 并运行
在服务器任意部署目录下创建 docker-compose.yml 文件：

YAML
services:
  singbox-subscriber:
    image: ghcr.io/你的用户名/singbox-subscriber:latest # 替换为你 GitHub 自动打包出来的真实镜像名
    container_name: singbox-subscriber
    restart: always # 实现“重启/开机即触发更新”
    ports:
      - "50000:50000"
    volumes:
      - /opt/singbox-subscriber:/opt/singbox-subscriber
    environment:
      - SUB_TOKEN=YuXXXXBwXj   # 你的极简安全 Token（自定义）
      - UPDATE_INTERVAL=86400  # 定时自动更新间隔（单位秒，86400秒 = 24小时）
启动服务：

Bash
docker compose up -d
第三步：验证运行状态与日志
你可以实时查看容器日志来确认节点拉取和合并清洗是否成功：

Bash
docker logs -f singbox-subscriber
期待的正常输出：

Plaintext
--------------------------------------------------
订阅分发服务已启动，完美兼容 Sing-box v1.13.14 规范.
极简安全下载根路径: /YuXXXXBwXj/
--------------------------------------------------
[更新] 开始节点合并与规范化清洗...
[下载] 正在请求: [https://xxxxxx12.xyz/subscribe-link-1](https://xxxxxx12.xyz/subscribe-link-1)
[成功] 已生成规范配置文件: 1.json
[成功] 已生成规范配置文件: 2.json
第四步：Nginx 安全反向代理配置
通过以下配置，只有携带你精确安全 Token 的流量才能访问到后台服务，其他恶意扫描或探测一律被 Nginx 阻断并返回 404，极大地提升了安全性：

Nginx
server {
    listen 443 ssl;
    server_name yourdomain.com; # 替换为你的公网域名

    # SSL 证书配置
    ssl_certificate /etc/nginx/ssl/yourdomain.pem;
    ssl_certificate_key /etc/nginx/ssl/yourdomain.key;

    # 🌟 仅允许匹配到你安全 Token 的请求转发到容器
    location /YuXXXXBwXj/ {
        proxy_pass [http://127.0.0.1:50000/YuXXXXBwXj/](http://127.0.0.1:50000/YuXXXXBwXj/);
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 🌟 其它所有路径的流量一律返回 404
    location / {
        return 404;
    }
}
📲 客户端配置与使用
配置完成后，你可以将生成的配置文件地址直接填入你的各个平台 Sing-box 客户端中：

1.json 下载地址：https://yourdomain.com/YuXXXXBwXj/1.json

2.json 下载地址：https://yourdomain.com/YuXXXXBwXj/2.json

📜 许可说明
本项目采用 MIT 许可证开源。请遵守你所在国家/地区的法律法规，并合理、合规、合法地使用本项目。

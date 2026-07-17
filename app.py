import os
import sys
import json
import re
import time
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 配置路径（已变更为全新的一致性路径）
BASE_DIR = "/opt/singbox-subscriber"
URLS_FILE = os.path.join(BASE_DIR, "urls")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 从环境变量获取安全 Token 和更新间隔（默认 24小时）
TOKEN = os.environ.get("SUB_TOKEN", "mysecrettoken")
UPDATE_INTERVAL = int(os.environ.get("UPDATE_INTERVAL", "86400"))

# 初始化目录
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
if not os.path.exists(URLS_FILE):
    with open(URLS_FILE, "w", encoding="utf-8") as f:
        f.write("# 在此放入你的订阅链接，一行一个\n")

def fetch_nodes():
    """读取 urls 文件，下载并提取真实的代理节点"""
    nodes = []
    if not os.path.exists(URLS_FILE):
        return nodes

    with open(URLS_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    for url in urls:
        print(f"[下载] 正在请求: {url}", flush=True)
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                if "outbounds" in data:
                    for outbound in data["outbounds"]:
                        ob_type = outbound.get("type")
                        # 过滤掉非实体节点（如系统的 selector、urltest、direct、block 等）
                        if ob_type not in ["selector", "urltest", "direct", "block", "dns"]:
                            nodes.append(outbound)
        except Exception as e:
            print(f"[错误] 请求或解析失败 {url}: {e}", flush=True)
    return nodes

def merge_configs():
    """合并节点到所有 Sing-box 模板中，并严格按照 v1.13.14 规范清洗"""
    print("[更新] 开始节点合并与规范化清洗...", flush=True)
    raw_nodes = fetch_nodes()
    if not raw_nodes:
        print("[警告] 未获取到任何有效节点，跳过本次合并。", flush=True)
        return

    # 节点去重与防 tag 重名处理
    unique_nodes = []
    seen_tags = set()
    for node in raw_nodes:
        tag = node.get("tag", "unnamed")
        original_tag = tag
        counter = 1
        while tag in seen_tags:
            tag = f"{original_tag}_{counter}"
            counter += 1
        node["tag"] = tag
        seen_tags.add(tag)
        unique_nodes.append(node)

    all_node_tags = [n["tag"] for n in unique_nodes]

    if not os.path.exists(TEMPLATES_DIR):
        return
    
    templates = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
    if not templates:
        print("[提示] templates 文件夹内没有发现任何 .json 模板文件。", flush=True)
        return

    for temp_name in templates:
        temp_path = os.path.join(TEMPLATES_DIR, temp_name)
        try:
            with open(temp_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            if "outbounds" in config and isinstance(config["outbounds"], list):
                processed_outbounds = []
                for outbound in config["outbounds"]:
                    # 解析匹配 {all} 并支持内置 filter 规则
                    if "outbounds" in outbound and isinstance(outbound["outbounds"], list):
                        if "{all}" in outbound["outbounds"]:
                            filters = outbound.get("filter", [])
                            matched_tags = []
                            keywords = []

                            # 提取 include 的过滤关键字
                            if isinstance(filters, list):
                                for f_item in filters:
                                    if isinstance(f_item, dict) and f_item.get("action") == "include":
                                        kws = f_item.get("keywords", [])
                                        if isinstance(kws, list):
                                            keywords.extend(kws)
                                        elif isinstance(kws, str):
                                            keywords.append(kws)

                            if keywords:
                                regex_str = "|".join(keywords)
                                try:
                                    pattern = re.compile(regex_str, re.IGNORECASE)
                                    matched_tags = [t for t in all_node_tags if pattern.search(t)]
                                except Exception as re_err:
                                    print(f"[正则错误] 组 {outbound.get('tag')}: {re_err}", flush=True)
                                    matched_tags = all_node_tags
                            else:
                                matched_tags = all_node_tags

                            # 用匹配的实际节点标签替换占位符 "{all}"
                            new_list = []
                            for item in outbound["outbounds"]:
                                if item == "{all}":
                                    new_list.extend(matched_tags)
                                else:
                                    new_list.append(item)
                            outbound["outbounds"] = new_list

                            # 【安全兜底】如果过滤后组内无可用节点，塞入直连做兜底，防止 Sing-box 客户端启动失败
                            if not outbound["outbounds"]:
                                outbound["outbounds"] = ["🎯 全球直连"]

                    # 【核心规范化】彻底剥离自定义 "filter" 字段，防止标准 Sing-box 报错闪退
                    if "filter" in outbound:
                        del outbound["filter"]

                    processed_outbounds.append(outbound)

                # 将解析出的全部实体物理代理节点追加到全局 outbounds 列表末尾
                processed_outbounds.extend(unique_nodes)
                config["outbounds"] = processed_outbounds

            # 输出完全合规的配置文件到 output 目录
            output_path = os.path.join(OUTPUT_DIR, temp_name)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"[成功] 已生成规范配置文件: {temp_name}", flush=True)

        except Exception as e:
            print(f"[失败] 模板处理出错 {temp_name}: {e}", flush=True)

def update_loop():
    """定时循环更新：容器开启、重启时会立刻执行一次，随后每隔 24 小时执行一次"""
    while True:
        try:
            merge_configs()
        except Exception as e:
            print(f"[循环错误] {e}", flush=True)
        time.sleep(UPDATE_INTERVAL)

class SubHandler(BaseHTTPRequestHandler):
    """极简安全 HTTP 服务器：仅响应 /<TOKEN>/<文件名.json> 格式"""
    def do_GET(self):
        # 剥离前后斜杆并分割
        path = self.path.strip("/")
        parts = path.split("/")
        
        # 精确匹配长度为 2 的层级：[TOKEN, FILENAME]
        if len(parts) == 2:
            req_token = parts[0]
            filename = parts[1]
            # 严格校对 Token 及文件后缀
            if req_token == TOKEN and filename.endswith(".json"):
                filepath = os.path.join(OUTPUT_DIR, filename)
                if os.path.exists(filepath) and os.path.isfile(filepath):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    with open(filepath, "rb") as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_error(404, "File Not Found")
                    return
            else:
                self.send_error(403, "Forbidden: Invalid Token")
                return
        self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # 屏蔽普通请求成功日志，保持 Docker 日志整洁
        pass

if __name__ == "__main__":
    # 启动后台更新循环
    threading.Thread(target=update_loop, daemon=True).start()
    
    # 启动 HTTP 监听
    server_address = ("0.0.0.0", 50000)
    httpd = HTTPServer(server_address, SubHandler)
    print("--------------------------------------------------", flush=True)
    print(f"订阅分发服务已启动，完美兼容 Sing-box v1.13.14 规范.", flush=True)
    print(f"极简安全下载根路径: /{TOKEN}/", flush=True)
    print("--------------------------------------------------", flush=True)
    httpd.serve_forever()

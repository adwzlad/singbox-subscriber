import os
import sys
import json
import re
import time
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 统一的一致性挂载路径
BASE_DIR = "/opt/singbox-subscriber"
URLS_FILE = os.path.join(BASE_DIR, "urls")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
HOSTS_FILE = os.path.join(BASE_DIR, "hosts")  # 新增：Hosts 映射文件

# 从环境变量获取安全 Token 和更新间隔
TOKEN = os.environ.get("SUB_TOKEN", "mysecrettoken")
UPDATE_INTERVAL = int(os.environ.get("UPDATE_INTERVAL", "86400"))

# 初始化目录与基础文件
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(URLS_FILE):
    with open(URLS_FILE, "w", encoding="utf-8") as f:
        f.write("# 在此放入你的订阅链接，一行一个\n")

if not os.path.exists(HOSTS_FILE):
    with open(HOSTS_FILE, "w", encoding="utf-8") as f:
        f.write("# 域名与 IP 映射表，格式：域名 IP (支持 IPv4 和 IPv6，一行一个)\n")
        f.write("# 支持使用 '#' 进行注释，例如：\n")
        f.write("# atw.787612.xyz 104.21.23.45\n")
        f.write("# another.xyz 2606:4700:3030::ac43:e02c\n")

def load_hosts_mapping():
    """从 hosts 文件中读取域名与 IP 映射"""
    mapping = {}
    if not os.path.exists(HOSTS_FILE):
        return mapping
    try:
        with open(HOSTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 按空格或制表符分割
                parts = line.split()
                if len(parts) >= 2:
                    domain = parts[0].strip()
                    ip = parts[1].strip()
                    mapping[domain] = ip
    except Exception as e:
        print(f"[Hosts 错误] 读取 hosts 映射失败: {e}", flush=True)
    return mapping

def apply_hosts_mapping(nodes, mapping):
    """将节点配置中的 server 域名替换为对应的 IP，并提供智能 SNI 保护"""
    if not mapping:
        return nodes
    
    replaced_count = 0
    for node in nodes:
        if "server" in node and isinstance(node["server"], str):
            original_domain = node["server"].strip()
            if original_domain in mapping:
                target_ip = mapping[original_domain]
                node["server"] = target_ip
                replaced_count += 1
                
                # 智能 SNI 保护：防止因替换为 IP 导致 TLS 证书校验失败
                tls = node.get("tls")
                if isinstance(tls, dict) and tls.get("enabled", False):
                    if "server_name" not in tls or not tls["server_name"]:
                        tls["server_name"] = original_domain
                        node["tls"] = tls
                        print(f"  └─ [SNI 保护] 已自动为节点 [{node.get('tag')}] 补充 tls.server_name = {original_domain}", flush=True)
                        
    if replaced_count > 0:
        print(f"[Hosts] 成功完成 {replaced_count} 处域名到 IP 的静态替换", flush=True)
    return nodes

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
                        if ob_type not in ["selector", "urltest", "direct", "block", "dns"]:
                            nodes.append(outbound)
        except Exception as e:
            print(f"[错误] 请求或解析失败 {url}: {e}", flush=True)
    return nodes

def merge_configs():
    """合并节点到所有模板中，并严格规范化清洗"""
    print("[更新] 开始节点合并与规范化清洗...", flush=True)
    raw_nodes = fetch_nodes()
    if not raw_nodes:
        print("[警告] 未获取到任何有效节点，跳过本次合并。", flush=True)
        return

    # 【新功能注入】：加载 Hosts 并替换域名为 IP
    hosts_mapping = load_hosts_mapping()
    if hosts_mapping:
        print(f"[Hosts] 已加载 {len(hosts_mapping)} 条映射规则，开始节点地址重定向...", flush=True)
        raw_nodes = apply_hosts_mapping(raw_nodes, hosts_mapping)

    # 去重与防重名
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
                    if "outbounds" in outbound and isinstance(outbound["outbounds"], list):
                        if "{all}" in outbound["outbounds"]:
                            filters = outbound.get("filter", [])
                            matched_tags = []
                            keywords = []

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

                            new_list = []
                            for item in outbound["outbounds"]:
                                if item == "{all}":
                                    new_list.extend(matched_tags)
                                else:
                                    new_list.append(item)
                            outbound["outbounds"] = new_list

                            if not outbound["outbounds"]:
                                outbound["outbounds"] = ["🎯 全球直连"]

                    if "filter" in outbound:
                        del outbound["filter"]

                    processed_outbounds.append(outbound)

                processed_outbounds.extend(unique_nodes)
                config["outbounds"] = processed_outbounds

            output_path = os.path.join(OUTPUT_DIR, temp_name)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"[成功] 已生成规范配置文件: {temp_name}", flush=True)

        except Exception as e:
            print(f"[失败] 模板处理出错 {temp_name}: {e}", flush=True)

def update_loop():
    while True:
        try:
            merge_configs()
        except Exception as e:
            print(f"[循环错误] {e}", flush=True)
        time.sleep(UPDATE_INTERVAL)

class SubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.strip("/")
        parts = path.split("/")
        
        if len(parts) == 2:
            req_token = parts[0]
            filename = parts[1]
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
        pass

if __name__ == "__main__":
    threading.Thread(target=update_loop, daemon=True).start()
    server_address = ("0.0.0.0", 50000)
    httpd = HTTPServer(server_address, SubHandler)
    print("--------------------------------------------------", flush=True)
    print(f"订阅分发服务已启动，完美兼容 Sing-box v1.13.14 规范.", flush=True)
    print(f"极简安全下载根路径: /{TOKEN}/", flush=True)
    print("--------------------------------------------------", flush=True)
    httpd.serve_forever()

import os
import requests
import json
import time # 引入 time 模块用于实现延迟

# --- 从 GitHub Secrets 读取配置 ---
# Cloudflare API Token，需要有 DNS 编辑权限
CF_API_TOKEN = os.environ.get('CF_API_TOKEN')
# Cloudflare Zone ID，在域名概述页面右下角可以找到
CF_ZONE_ID = os.environ.get('CF_ZONE_ID')
# 需要更新的域名，例如 'sub.yourdomain.com'
DOMAIN_NAME = os.environ.get('CF_DOMAIN_NAME')

# --- 在此处直接设置要解析的 IP 数量 ---
# 注意: 当前脚本逻辑已被修改为只获取第 31 行的 IP，因此此处的 MAX_IPS 变量不再生效。
MAX_IPS = 3

# --- 优选 IP 的 API 地址 ---
IP_API_URL = 'https://addressesapi.090227.xyz/ip'

# --- Cloudflare API 端点 ---
CF_API_BASE_URL = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records"

# --- HTTP 请求头 ---
HEADERS = {
    'Authorization': f'Bearer {CF_API_TOKEN}',
    'Content-Type': 'application/json'
}

def get_preferred_ips():
    """从 API 的第 31 行获取优选 IP"""
    print(f"正在从 {IP_API_URL} 获取优选 IP...")
    
    retry_count = 3
    retry_delay = 10
    
    for attempt in range(retry_count):
        try:
            response = requests.get(IP_API_URL, timeout=10)
            response.raise_for_status()
            
            lines = response.text.strip().split('\n')

            # 检查 API 响应是否有足够的行数
            if len(lines) < 31:
                print(f"错误: API 响应的行数少于 31 行 (总共 {len(lines)} 行)，无法获取指定的 IP。")
                return []

            # 精确获取第 31 行 (列表索引为 30)
            target_line = lines[30]
            
            # 从目标行解析 IP
            if target_line.strip():
                ip_part = target_line.split('#')[0].strip()
                if ip_part:
                    print(f"成功从第 31 行获取并解析了 IP: {ip_part}")
                    return [ip_part] # 返回包含这一个 IP 的列表

            # 如果第 31 行为空或无法解析出 IP
            print("错误: 第 31 行为空或无法解析出有效的 IP 地址。")
            return []

        except requests.RequestException as e:
            print(f"错误: 请求优选 IP 时发生错误: {e}")
            if attempt < retry_count - 1:
                print(f"将在 {retry_delay} 秒后进行第 {attempt + 2} 次尝试...")
                time.sleep(retry_delay)
            else:
                print("已达到最大重试次数，获取 IP 失败。")
                return []

    return []

def get_existing_dns_records():
    """获取当前域名已有的 A 记录"""
    print(f"正在查询域名 {DOMAIN_NAME} 的现有 DNS A 记录...")
    params = {'type': 'A', 'name': DOMAIN_NAME}
    try:
        response = requests.get(CF_API_BASE_URL, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        records = response.json()['result']
        print(f"查询到 {len(records)} 条已存在的 A 记录。")
        return records
    except requests.RequestException as e:
        print(f"错误: 查询 DNS 记录时发生错误: {e}")
        return []
    except (KeyError, json.JSONDecodeError):
        print("错误: 解析 DNS 记录响应失败。")
        return []


def delete_dns_record(record_id):
    """删除指定的 DNS 记录"""
    delete_url = f"{CF_API_BASE_URL}/{record_id}"
    try:
        response = requests.delete(delete_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        print(f"成功删除记录: {record_id}")
        return True
    except requests.RequestException as e:
        print(f"错误: 删除记录 {record_id} 时失败: {e}")
        return False

def create_dns_record(ip):
    """为给定的 IP 创建一条新的 A 记录"""
    data = {
        'type': 'A',
        'name': DOMAIN_NAME,
        'content': ip,
        'ttl': 1,
        'proxied': False
    }
    try:
        response = requests.post(CF_API_BASE_URL, headers=HEADERS, json=data, timeout=10)
        response.raise_for_status()
        print(f"成功为 IP {ip} 创建 A 记录。")
        return True
    except requests.RequestException as e:
        print(f"错误: 为 IP {ip} 创建 A 记录时失败: {e}")
        return False

def main():
    """主执行函数"""
    print("--- 开始更新 Cloudflare 优选 IP ---")
    
    if not all([CF_API_TOKEN, CF_ZONE_ID, DOMAIN_NAME]):
        print("错误: 缺少必要的环境变量 (CF_API_TOKEN, CF_ZONE_ID, DOMAIN_NAME)。请检查 GitHub Secrets 配置。")
        return

    new_ips = get_preferred_ips()
    if not new_ips:
        print("未能获取新的 IP 地址，本次任务终止。")
        return

    existing_records = get_existing_dns_records()

    if existing_records:
        print("\n--- 开始删除旧的 DNS 记录 ---")
        for record in existing_records:
            delete_dns_record(record['id'])
    else:
        print("没有需要删除的旧记录。")

    print("\n--- 开始创建新的 DNS 记录 ---")
    success_count = 0
    for ip in new_ips:
        if create_dns_record(ip):
            success_count += 1
    
    print(f"\n--- 更新完成 ---")
    print(f"成功为 {success_count}/{len(new_ips)} 个 IP 地址创建了 DNS 记录。")

if __name__ == '__main__':
    main()
